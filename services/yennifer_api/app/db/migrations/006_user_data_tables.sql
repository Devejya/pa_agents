-- Migration 006: User Data Tables
-- 
-- Creates tables for user-specific data:
-- - interests: Things the user is interested in (hobbies, topics, etc.)
-- - important_dates: Birthdays, anniversaries, events to remember
-- - user_tasks: Scheduled and recurring tasks
-- - memories: Facts the agent should remember about the user
--
-- All tables use:
-- - Per-user data isolation via RLS
-- - Encrypted sensitive fields using user's DEK

-- ============================================================================
-- Step 1: Create interests table
-- ============================================================================

CREATE TABLE IF NOT EXISTS interests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Interest data
    category VARCHAR(100),  -- e.g., 'hobby', 'topic', 'sport', 'music', 'food'
    interest_level INTEGER NOT NULL CHECK (interest_level >= 0 AND interest_level <= 100),  -- 0-100 scale
    details_encrypted BYTEA NOT NULL,  -- JSON: {"name": "...", "notes": "..."}
    
    -- Metadata
    source VARCHAR(100),  -- Where we learned this: 'user_stated', 'inferred', 'conversation'
    confidence INTEGER DEFAULT 100 CHECK (confidence >= 0 AND confidence <= 100),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_mentioned_at TIMESTAMP WITH TIME ZONE  -- Last time user mentioned this interest
);

-- Indexes for interests
CREATE INDEX IF NOT EXISTS idx_interests_user_id ON interests(user_id);
CREATE INDEX IF NOT EXISTS idx_interests_category ON interests(user_id, category);
CREATE INDEX IF NOT EXISTS idx_interests_level ON interests(user_id, interest_level DESC);

-- Comments
COMMENT ON TABLE interests IS 'User interests with per-user encryption';
COMMENT ON COLUMN interests.interest_level IS 'Interest level 0-100 (100 = loves, 50 = likes, 0 = dislikes)';
COMMENT ON COLUMN interests.details_encrypted IS 'Encrypted JSON with name and notes';

-- ============================================================================
-- Step 2: Create important_dates table
-- ============================================================================

CREATE TABLE IF NOT EXISTS important_dates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Date info
    date_type VARCHAR(50) NOT NULL,  -- 'birthday', 'anniversary', 'event', 'deadline', 'custom'
    date_value DATE NOT NULL,  -- The actual date (year may be 1900 for recurring without year)
    is_recurring BOOLEAN DEFAULT true,  -- Does this repeat yearly?
    
    -- Related person (optional)
    person_id UUID REFERENCES persons(id) ON DELETE SET NULL,
    
    -- Details (encrypted)
    title_encrypted BYTEA NOT NULL,  -- Encrypted title/name
    notes_encrypted BYTEA,  -- Optional encrypted notes
    
    -- Reminder settings
    remind_days_before INTEGER DEFAULT 7,  -- Days before to remind
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for important_dates
CREATE INDEX IF NOT EXISTS idx_important_dates_user_id ON important_dates(user_id);
CREATE INDEX IF NOT EXISTS idx_important_dates_date ON important_dates(user_id, date_value);
CREATE INDEX IF NOT EXISTS idx_important_dates_type ON important_dates(user_id, date_type);
CREATE INDEX IF NOT EXISTS idx_important_dates_person ON important_dates(person_id) WHERE person_id IS NOT NULL;

-- For finding upcoming dates (extract month/day for recurring dates)
CREATE INDEX IF NOT EXISTS idx_important_dates_month_day ON important_dates(
    user_id,
    EXTRACT(MONTH FROM date_value),
    EXTRACT(DAY FROM date_value)
);

-- Comments
COMMENT ON TABLE important_dates IS 'Important dates to remember (birthdays, anniversaries, etc.)';
COMMENT ON COLUMN important_dates.date_value IS 'The date; for recurring dates without year, use year 1900';

-- ============================================================================
-- Step 3: Create user_tasks table
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Task type
    task_type VARCHAR(50) NOT NULL,  -- 'scheduled', 'recurring', 'async', 'reminder'
    
    -- Schedule (for recurring tasks)
    schedule_cron VARCHAR(100),  -- Cron expression for recurring tasks
    
    -- Task details (encrypted)
    title_encrypted BYTEA NOT NULL,
    description_encrypted BYTEA,
    payload_encrypted BYTEA,  -- JSON with task-specific data
    
    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'in_progress', 'completed', 'failed', 'cancelled'
    priority INTEGER DEFAULT 50 CHECK (priority >= 0 AND priority <= 100),  -- 0-100
    
    -- Timing
    scheduled_at TIMESTAMP WITH TIME ZONE,  -- When to execute (for scheduled tasks)
    due_at TIMESTAMP WITH TIME ZONE,  -- Deadline
    next_run_at TIMESTAMP WITH TIME ZONE,  -- Next execution (for recurring)
    last_run_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Result
    result_encrypted BYTEA,  -- Encrypted result/outcome
    error_message TEXT,  -- Error if failed (not encrypted, no PII)
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for user_tasks
CREATE INDEX IF NOT EXISTS idx_user_tasks_user_id ON user_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_user_tasks_status ON user_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_tasks_scheduled ON user_tasks(user_id, scheduled_at) WHERE scheduled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_tasks_due ON user_tasks(user_id, due_at) WHERE due_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_tasks_next_run ON user_tasks(next_run_at) WHERE next_run_at IS NOT NULL AND status = 'pending';
CREATE INDEX IF NOT EXISTS idx_user_tasks_priority ON user_tasks(user_id, priority DESC, created_at);

-- Comments
COMMENT ON TABLE user_tasks IS 'User tasks and scheduled jobs';
COMMENT ON COLUMN user_tasks.schedule_cron IS 'Cron expression for recurring tasks (e.g., "0 9 * * 1" for Monday 9am)';

-- ============================================================================
-- Step 4: Create memories table
-- ============================================================================

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Memory categorization
    context VARCHAR(100),  -- 'personal', 'professional', 'medical', 'preference', 'style', 'general'
    category VARCHAR(100),  -- More specific: 'communication_style', 'dietary', 'travel', etc.
    
    -- Memory content (encrypted)
    fact_key VARCHAR(255) NOT NULL,  -- Searchable key (e.g., 'preferred_coffee', 'meeting_style')
    fact_value_encrypted BYTEA NOT NULL,  -- The actual memory content
    
    -- Source and confidence
    source VARCHAR(100),  -- 'user_stated', 'inferred', 'observed', 'imported'
    confidence INTEGER DEFAULT 100 CHECK (confidence >= 0 AND confidence <= 100),
    
    -- Related entities (optional)
    person_id UUID REFERENCES persons(id) ON DELETE SET NULL,  -- If memory is about a person
    
    -- Validity
    is_active BOOLEAN DEFAULT true,  -- Can be deactivated without deletion
    expires_at TIMESTAMP WITH TIME ZONE,  -- Optional expiry
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE  -- Track usage
);

-- Indexes for memories
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_context ON memories(user_id, context);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(user_id, category);
CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_memories_person ON memories(person_id) WHERE person_id IS NOT NULL;

-- Unique constraint for upsert on fact_key per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_user_fact_key ON memories(user_id, fact_key);

-- Comments
COMMENT ON TABLE memories IS 'Facts and preferences the agent should remember about the user';
COMMENT ON COLUMN memories.fact_key IS 'Searchable key for the memory (not encrypted)';
COMMENT ON COLUMN memories.fact_value_encrypted IS 'The actual memory content (encrypted)';

-- ============================================================================
-- Step 5: Enable RLS on all tables
-- ============================================================================

-- Enable RLS
ALTER TABLE interests ENABLE ROW LEVEL SECURITY;
ALTER TABLE important_dates ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

-- Force RLS for table owners
ALTER TABLE interests FORCE ROW LEVEL SECURITY;
ALTER TABLE important_dates FORCE ROW LEVEL SECURITY;
ALTER TABLE user_tasks FORCE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- Step 6: Create RLS policies
-- ============================================================================

-- Interests policies
DROP POLICY IF EXISTS interests_select_own ON interests;
CREATE POLICY interests_select_own ON interests
    FOR SELECT
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS interests_insert_own ON interests;
CREATE POLICY interests_insert_own ON interests
    FOR INSERT
    WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS interests_update_own ON interests;
CREATE POLICY interests_update_own ON interests
    FOR UPDATE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS interests_delete_own ON interests;
CREATE POLICY interests_delete_own ON interests
    FOR DELETE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

-- Important dates policies
DROP POLICY IF EXISTS important_dates_select_own ON important_dates;
CREATE POLICY important_dates_select_own ON important_dates
    FOR SELECT
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS important_dates_insert_own ON important_dates;
CREATE POLICY important_dates_insert_own ON important_dates
    FOR INSERT
    WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS important_dates_update_own ON important_dates;
CREATE POLICY important_dates_update_own ON important_dates
    FOR UPDATE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS important_dates_delete_own ON important_dates;
CREATE POLICY important_dates_delete_own ON important_dates
    FOR DELETE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

-- User tasks policies
DROP POLICY IF EXISTS user_tasks_select_own ON user_tasks;
CREATE POLICY user_tasks_select_own ON user_tasks
    FOR SELECT
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS user_tasks_insert_own ON user_tasks;
CREATE POLICY user_tasks_insert_own ON user_tasks
    FOR INSERT
    WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS user_tasks_update_own ON user_tasks;
CREATE POLICY user_tasks_update_own ON user_tasks
    FOR UPDATE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS user_tasks_delete_own ON user_tasks;
CREATE POLICY user_tasks_delete_own ON user_tasks
    FOR DELETE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

-- Memories policies
DROP POLICY IF EXISTS memories_select_own ON memories;
CREATE POLICY memories_select_own ON memories
    FOR SELECT
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS memories_insert_own ON memories;
CREATE POLICY memories_insert_own ON memories
    FOR INSERT
    WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS memories_update_own ON memories;
CREATE POLICY memories_update_own ON memories
    FOR UPDATE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS memories_delete_own ON memories;
CREATE POLICY memories_delete_own ON memories
    FOR DELETE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

-- ============================================================================
-- Step 7: Create updated_at triggers
-- ============================================================================

-- Trigger function (reuse if exists)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS interests_updated_at ON interests;
CREATE TRIGGER interests_updated_at
    BEFORE UPDATE ON interests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS important_dates_updated_at ON important_dates;
CREATE TRIGGER important_dates_updated_at
    BEFORE UPDATE ON important_dates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS user_tasks_updated_at ON user_tasks;
CREATE TRIGGER user_tasks_updated_at
    BEFORE UPDATE ON user_tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS memories_updated_at ON memories;
CREATE TRIGGER memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    table_count INTEGER;
BEGIN
    -- Count created tables
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_name IN ('interests', 'important_dates', 'user_tasks', 'memories')
    AND table_schema = 'public';
    
    IF table_count = 4 THEN
        RAISE NOTICE '✓ All 4 user data tables created successfully';
    ELSE
        RAISE NOTICE '⚠ Only % tables created', table_count;
    END IF;
    
    -- Verify RLS
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'interests' AND rowsecurity = true) THEN
        RAISE NOTICE '✓ RLS enabled on all tables';
    END IF;
    
    RAISE NOTICE '✓ Migration 006 (User Data Tables) completed successfully';
END $$;

