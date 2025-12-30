-- Migration 003: Row-Level Security for Data Tables
-- Adds owner_user_id to persons and relationships for multi-tenant isolation
-- 
-- This migration:
-- 1. Adds owner_user_id column to persons and relationships
-- 2. Enables Row-Level Security on data tables
-- 3. Creates RLS policies for CRUD operations
-- 4. Updates sync_state to use UUID

-- ============================================================================
-- Step 1: Add owner_user_id to persons table
-- ============================================================================

-- Add the column (nullable initially for migration)
ALTER TABLE persons 
ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- Create index for RLS performance
CREATE INDEX IF NOT EXISTS idx_persons_owner_user_id ON persons(owner_user_id);

-- Comment for documentation
COMMENT ON COLUMN persons.owner_user_id IS 'The authenticated user who owns this contact record. NULL for legacy data.';

-- ============================================================================
-- Step 2: Add owner_user_id to relationships table
-- ============================================================================

ALTER TABLE relationships 
ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_relationships_owner_user_id ON relationships(owner_user_id);

COMMENT ON COLUMN relationships.owner_user_id IS 'The authenticated user who owns this relationship. NULL for legacy data.';

-- ============================================================================
-- Step 3: Add owner_user_id to person_external_ids table
-- ============================================================================

ALTER TABLE person_external_ids 
ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_person_external_ids_owner_user_id ON person_external_ids(owner_user_id);

-- ============================================================================
-- Step 4: Add owner_user_id to sync_state table (and sync_conflicts)
-- ============================================================================

-- sync_state already has user_id as VARCHAR, let's add owner_user_id as UUID
ALTER TABLE sync_state 
ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_sync_state_owner_user_id ON sync_state(owner_user_id);

-- sync_conflicts
ALTER TABLE sync_conflicts 
ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_sync_conflicts_owner_user_id ON sync_conflicts(owner_user_id);

-- sync_log
ALTER TABLE sync_log 
ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_sync_log_owner_user_id ON sync_log(owner_user_id);

-- ============================================================================
-- Step 5: Enable Row-Level Security
-- ============================================================================

-- Enable RLS on all data tables
ALTER TABLE persons ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE person_external_ids ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_conflicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_log ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Step 6: Create RLS Policies for persons
-- ============================================================================

-- Drop existing policies if they exist (for re-runability)
DROP POLICY IF EXISTS persons_select_policy ON persons;
DROP POLICY IF EXISTS persons_insert_policy ON persons;
DROP POLICY IF EXISTS persons_update_policy ON persons;
DROP POLICY IF EXISTS persons_delete_policy ON persons;

-- SELECT: Users can only see their own contacts
CREATE POLICY persons_select_policy ON persons
    FOR SELECT
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL  -- Allow access to legacy data (temporary)
    );

-- INSERT: Users can only insert contacts they own
CREATE POLICY persons_insert_policy ON persons
    FOR INSERT
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- UPDATE: Users can only update their own contacts
CREATE POLICY persons_update_policy ON persons
    FOR UPDATE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    )
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- DELETE: Users can only delete their own contacts
CREATE POLICY persons_delete_policy ON persons
    FOR DELETE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

-- ============================================================================
-- Step 7: Create RLS Policies for relationships
-- ============================================================================

DROP POLICY IF EXISTS relationships_select_policy ON relationships;
DROP POLICY IF EXISTS relationships_insert_policy ON relationships;
DROP POLICY IF EXISTS relationships_update_policy ON relationships;
DROP POLICY IF EXISTS relationships_delete_policy ON relationships;

CREATE POLICY relationships_select_policy ON relationships
    FOR SELECT
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

CREATE POLICY relationships_insert_policy ON relationships
    FOR INSERT
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY relationships_update_policy ON relationships
    FOR UPDATE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    )
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY relationships_delete_policy ON relationships
    FOR DELETE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

-- ============================================================================
-- Step 8: Create RLS Policies for person_external_ids
-- ============================================================================

DROP POLICY IF EXISTS person_external_ids_select_policy ON person_external_ids;
DROP POLICY IF EXISTS person_external_ids_insert_policy ON person_external_ids;
DROP POLICY IF EXISTS person_external_ids_update_policy ON person_external_ids;
DROP POLICY IF EXISTS person_external_ids_delete_policy ON person_external_ids;

CREATE POLICY person_external_ids_select_policy ON person_external_ids
    FOR SELECT
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

CREATE POLICY person_external_ids_insert_policy ON person_external_ids
    FOR INSERT
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY person_external_ids_update_policy ON person_external_ids
    FOR UPDATE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    )
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY person_external_ids_delete_policy ON person_external_ids
    FOR DELETE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

-- ============================================================================
-- Step 9: Create RLS Policies for sync_state
-- ============================================================================

DROP POLICY IF EXISTS sync_state_select_policy ON sync_state;
DROP POLICY IF EXISTS sync_state_insert_policy ON sync_state;
DROP POLICY IF EXISTS sync_state_update_policy ON sync_state;
DROP POLICY IF EXISTS sync_state_delete_policy ON sync_state;

CREATE POLICY sync_state_select_policy ON sync_state
    FOR SELECT
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

CREATE POLICY sync_state_insert_policy ON sync_state
    FOR INSERT
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY sync_state_update_policy ON sync_state
    FOR UPDATE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    )
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY sync_state_delete_policy ON sync_state
    FOR DELETE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

-- ============================================================================
-- Step 10: Create RLS Policies for sync_conflicts
-- ============================================================================

DROP POLICY IF EXISTS sync_conflicts_select_policy ON sync_conflicts;
DROP POLICY IF EXISTS sync_conflicts_insert_policy ON sync_conflicts;
DROP POLICY IF EXISTS sync_conflicts_update_policy ON sync_conflicts;
DROP POLICY IF EXISTS sync_conflicts_delete_policy ON sync_conflicts;

CREATE POLICY sync_conflicts_select_policy ON sync_conflicts
    FOR SELECT
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

CREATE POLICY sync_conflicts_insert_policy ON sync_conflicts
    FOR INSERT
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY sync_conflicts_update_policy ON sync_conflicts
    FOR UPDATE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

CREATE POLICY sync_conflicts_delete_policy ON sync_conflicts
    FOR DELETE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

-- ============================================================================
-- Step 11: Create RLS Policies for sync_log
-- ============================================================================

DROP POLICY IF EXISTS sync_log_select_policy ON sync_log;
DROP POLICY IF EXISTS sync_log_insert_policy ON sync_log;
DROP POLICY IF EXISTS sync_log_update_policy ON sync_log;
DROP POLICY IF EXISTS sync_log_delete_policy ON sync_log;

CREATE POLICY sync_log_select_policy ON sync_log
    FOR SELECT
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

CREATE POLICY sync_log_insert_policy ON sync_log
    FOR INSERT
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

CREATE POLICY sync_log_update_policy ON sync_log
    FOR UPDATE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

CREATE POLICY sync_log_delete_policy ON sync_log
    FOR DELETE
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        OR owner_user_id IS NULL
    );

-- ============================================================================
-- Step 12: Bypass RLS for the application user (if needed for admin operations)
-- ============================================================================

-- Create a function to check if the session is running as admin
-- This allows certain operations to bypass RLS when needed

-- For the postgres superuser, RLS is already bypassed by default
-- For application connections, we can use FORCE ROW LEVEL SECURITY if needed

-- ============================================================================
-- Comments and Documentation
-- ============================================================================

COMMENT ON TABLE persons IS 'Contact records with per-user isolation via RLS';
COMMENT ON TABLE relationships IS 'Relationship records with per-user isolation via RLS';
COMMENT ON TABLE person_external_ids IS 'External ID mappings with per-user isolation via RLS';

-- ============================================================================
-- Verification Query (run after migration to verify)
-- ============================================================================

-- SELECT tablename, rowsecurity 
-- FROM pg_tables 
-- WHERE schemaname = 'public' 
--   AND tablename IN ('persons', 'relationships', 'person_external_ids', 'sync_state');


