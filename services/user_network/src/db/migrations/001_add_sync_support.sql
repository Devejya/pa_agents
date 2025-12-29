-- ============================================================================
-- Migration 001: Add Contact Sync Support
-- 
-- Changes:
-- 1. Split 'name' into 'first_name', 'last_name', 'middle_names'
-- 2. Add 'date_of_birth' column
-- 3. Create 'person_external_ids' table for multi-platform sync
-- 4. Create 'sync_state' table for tracking sync tokens
-- 5. Update search vector function
-- ============================================================================

-- ============================================================================
-- Step 1: Add new name columns
-- ============================================================================

-- Add new columns
ALTER TABLE persons ADD COLUMN IF NOT EXISTS first_name VARCHAR(100);
ALTER TABLE persons ADD COLUMN IF NOT EXISTS last_name VARCHAR(100);
ALTER TABLE persons ADD COLUMN IF NOT EXISTS middle_names VARCHAR(255);
ALTER TABLE persons ADD COLUMN IF NOT EXISTS date_of_birth DATE;

-- Migrate data from 'name' to new columns
-- Logic: First word -> first_name, Last word -> last_name (if different), middle words -> middle_names
UPDATE persons
SET 
    first_name = CASE 
        WHEN name IS NOT NULL AND name != '' 
        THEN split_part(name, ' ', 1)
        ELSE NULL
    END,
    last_name = CASE 
        WHEN name IS NOT NULL AND name != '' AND position(' ' in name) > 0
        THEN (regexp_split_to_array(name, '\s+'))[array_length(regexp_split_to_array(name, '\s+'), 1)]
        ELSE NULL
    END,
    middle_names = CASE
        WHEN name IS NOT NULL AND array_length(regexp_split_to_array(name, '\s+'), 1) > 2
        THEN array_to_string((regexp_split_to_array(name, '\s+'))[2:array_length(regexp_split_to_array(name, '\s+'), 1)-1], ' ')
        ELSE NULL
    END
WHERE first_name IS NULL;

-- Make first_name required for new records (but allow NULL for migration)
-- We'll update this constraint after data migration
-- For now, we keep 'name' for backward compatibility

-- ============================================================================
-- Step 2: Create person_external_ids table
-- ============================================================================

CREATE TABLE IF NOT EXISTS person_external_ids (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    
    -- Provider information
    provider VARCHAR(50) NOT NULL,  -- 'google', 'apple', 'microsoft', 'linkedin', etc.
    external_id VARCHAR(500) NOT NULL,  -- The provider's unique ID
    
    -- Additional metadata from provider
    external_metadata JSONB DEFAULT '{}',  -- Provider-specific data (etag, resourceName, etc.)
    
    -- Sync tracking
    last_synced_at TIMESTAMPTZ,
    sync_status VARCHAR(50) DEFAULT 'synced',  -- 'synced', 'pending_push', 'pending_pull', 'conflict'
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints: One external ID per provider per person
    CONSTRAINT unique_person_provider UNIQUE(person_id, provider),
    -- Each external ID maps to one person (per provider)
    CONSTRAINT unique_provider_external_id UNIQUE(provider, external_id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_external_ids_person_id ON person_external_ids(person_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_provider ON person_external_ids(provider);
CREATE INDEX IF NOT EXISTS idx_external_ids_provider_external_id ON person_external_ids(provider, external_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_sync_status ON person_external_ids(sync_status) WHERE sync_status != 'synced';

-- ============================================================================
-- Step 3: Create sync_state table
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- User identification (core user's email or ID)
    user_id VARCHAR(255) NOT NULL,
    
    -- What we're syncing
    provider VARCHAR(50) NOT NULL,  -- 'google_contacts', 'google_calendar', 'apple_contacts', etc.
    
    -- Sync token for incremental sync
    sync_token TEXT,
    
    -- Sync timing
    last_full_sync_at TIMESTAMPTZ,
    last_incremental_sync_at TIMESTAMPTZ,
    next_sync_at TIMESTAMPTZ,
    
    -- Sync status
    sync_status VARCHAR(50) DEFAULT 'idle',  -- 'idle', 'syncing', 'failed', 'paused'
    error_message TEXT,
    consecutive_failures INT DEFAULT 0,
    
    -- Statistics
    total_synced_count INT DEFAULT 0,
    last_sync_added INT DEFAULT 0,
    last_sync_updated INT DEFAULT 0,
    last_sync_deleted INT DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- One sync state per user per provider
    CONSTRAINT unique_user_provider UNIQUE(user_id, provider)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sync_state_user_id ON sync_state(user_id);
CREATE INDEX IF NOT EXISTS idx_sync_state_provider ON sync_state(provider);
CREATE INDEX IF NOT EXISTS idx_sync_state_next_sync ON sync_state(next_sync_at) WHERE sync_status = 'idle';
CREATE INDEX IF NOT EXISTS idx_sync_state_status ON sync_state(sync_status);

-- ============================================================================
-- Step 4: Create sync_conflicts table for manual resolution
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_conflicts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- User who needs to resolve
    user_id VARCHAR(255) NOT NULL,
    
    -- What's conflicting
    person_id UUID REFERENCES persons(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    external_id VARCHAR(500),
    
    -- Conflict details
    conflict_type VARCHAR(50) NOT NULL,  -- 'duplicate_match', 'field_conflict', 'merge_required'
    local_data JSONB NOT NULL,   -- Current data in user_network
    remote_data JSONB NOT NULL,  -- Data from external provider
    suggested_resolution JSONB,  -- AI-suggested merge
    
    -- Resolution
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'resolved', 'dismissed'
    resolution_type VARCHAR(50),  -- 'keep_local', 'keep_remote', 'merge', 'create_new'
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(255),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sync_conflicts_user_id ON sync_conflicts(user_id);
CREATE INDEX IF NOT EXISTS idx_sync_conflicts_status ON sync_conflicts(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_sync_conflicts_person_id ON sync_conflicts(person_id);

-- ============================================================================
-- Step 5: Create sync_log table for tracking sync history
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- What was synced
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    sync_type VARCHAR(50) NOT NULL,  -- 'full', 'incremental', 'manual'
    direction VARCHAR(50) NOT NULL,  -- 'pull', 'push', 'bidirectional'
    
    -- Results
    status VARCHAR(50) NOT NULL,  -- 'success', 'partial', 'failed'
    records_processed INT DEFAULT 0,
    records_added INT DEFAULT 0,
    records_updated INT DEFAULT 0,
    records_failed INT DEFAULT 0,
    conflicts_created INT DEFAULT 0,
    
    -- Timing
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INT,
    
    -- Error details (if any)
    error_message TEXT,
    error_details JSONB,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sync_log_user_id ON sync_log(user_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_provider ON sync_log(provider);
CREATE INDEX IF NOT EXISTS idx_sync_log_created_at ON sync_log(created_at DESC);

-- ============================================================================
-- Step 6: Update search vector function to use new name fields
-- ============================================================================

CREATE OR REPLACE FUNCTION update_person_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        -- Name fields (highest weight)
        setweight(to_tsvector('english', COALESCE(NEW.first_name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.last_name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.middle_names, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||  -- Keep for backward compat
        setweight(to_tsvector('english', COALESCE(array_to_string(NEW.aliases, ' '), '')), 'A') ||
        -- Professional fields (medium weight)
        setweight(to_tsvector('english', COALESCE(NEW.expertise, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.company, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.latest_title, '')), 'B') ||
        -- Interests (lower weight)
        setweight(to_tsvector('english', COALESCE(
            (SELECT string_agg(interest->>'name', ' ') FROM jsonb_array_elements(NEW.interests) AS interest),
            ''
        )), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Step 7: Add triggers for updated_at on new tables
-- ============================================================================

-- Trigger for person_external_ids
CREATE OR REPLACE TRIGGER trigger_person_external_ids_updated_at
    BEFORE UPDATE ON person_external_ids
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for sync_state
CREATE OR REPLACE TRIGGER trigger_sync_state_updated_at
    BEFORE UPDATE ON sync_state
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for sync_conflicts
CREATE OR REPLACE TRIGGER trigger_sync_conflicts_updated_at
    BEFORE UPDATE ON sync_conflicts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Step 8: Add indexes for email/phone lookups (for entity resolution)
-- ============================================================================

-- Normalized phone index (for matching)
CREATE INDEX IF NOT EXISTS idx_persons_work_cell_normalized 
    ON persons (regexp_replace(work_cell, '[^0-9]', '', 'g')) 
    WHERE work_cell IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_persons_personal_cell_normalized 
    ON persons (regexp_replace(personal_cell, '[^0-9]', '', 'g')) 
    WHERE personal_cell IS NOT NULL;

-- ============================================================================
-- Migration complete!
-- ============================================================================

-- Add a migration tracking record (optional, for tracking applied migrations)
CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO _migrations (name) 
VALUES ('001_add_sync_support')
ON CONFLICT (name) DO NOTHING;

