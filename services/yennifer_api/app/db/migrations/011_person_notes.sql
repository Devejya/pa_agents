-- Migration 011: Person Notes Table
-- 
-- Freeform notes about people in the network with:
-- - Per-user encryption
-- - Categories for organization
-- - Optional date for time-sensitive notes
-- - Auto-archive for expired notes
--
-- Run with: psql $DATABASE_URL -f 011_person_notes.sql

BEGIN;

-- ============================================================================
-- Create note_category enum
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'note_category') THEN
        CREATE TYPE note_category AS ENUM (
            'general',      -- Default, catch-all
            'travel',       -- Visiting, trips, travel plans
            'preference',   -- Food preferences, likes/dislikes not in interests
            'event',        -- Upcoming events, occasions
            'reminder',     -- Things to remember (owes money, promised something)
            'observation',  -- Things noticed about them
            'other'         -- Anything else
        );
    END IF;
END $$;

-- ============================================================================
-- Create person_notes table
-- ============================================================================

CREATE TABLE IF NOT EXISTS person_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    
    -- Note content (encrypted)
    content_encrypted BYTEA NOT NULL,  -- Encrypted JSON: {"text": "...", "context": "..."}
    
    -- Classification
    category note_category NOT NULL DEFAULT 'general',
    
    -- Temporal info (for time-sensitive notes)
    related_date DATE,                    -- Date the note refers to (e.g., visit date)
    is_time_sensitive BOOLEAN DEFAULT FALSE,  -- Should this note expire?
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'archived', 'expired'
    
    -- Metadata
    source VARCHAR(50) DEFAULT 'conversation',  -- 'conversation', 'user_stated', 'manual'
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_person_notes_user_id ON person_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_person_notes_person_id ON person_notes(person_id);
CREATE INDEX IF NOT EXISTS idx_person_notes_category ON person_notes(user_id, category);
CREATE INDEX IF NOT EXISTS idx_person_notes_status ON person_notes(user_id, status);
CREATE INDEX IF NOT EXISTS idx_person_notes_date ON person_notes(related_date) 
    WHERE related_date IS NOT NULL AND status = 'active';

-- For finding upcoming notes (within next N days)
CREATE INDEX IF NOT EXISTS idx_person_notes_upcoming ON person_notes(user_id, related_date, status)
    WHERE related_date IS NOT NULL AND status = 'active';

-- ============================================================================
-- Row Level Security
-- ============================================================================

ALTER TABLE person_notes ENABLE ROW LEVEL SECURITY;

CREATE POLICY person_notes_select_own ON person_notes FOR SELECT
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

CREATE POLICY person_notes_insert_own ON person_notes FOR INSERT
    WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

CREATE POLICY person_notes_update_own ON person_notes FOR UPDATE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

CREATE POLICY person_notes_delete_own ON person_notes FOR DELETE
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

-- ============================================================================
-- Triggers
-- ============================================================================

-- Updated_at trigger
CREATE TRIGGER person_notes_updated_at
    BEFORE UPDATE ON person_notes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Function to auto-expire old time-sensitive notes
-- ============================================================================

CREATE OR REPLACE FUNCTION expire_old_notes() RETURNS INTEGER AS $$
DECLARE
    expired_count INTEGER;
BEGIN
    UPDATE person_notes
    SET status = 'expired', updated_at = NOW()
    WHERE status = 'active'
      AND is_time_sensitive = TRUE
      AND related_date IS NOT NULL
      AND related_date < CURRENT_DATE;
    
    GET DIAGNOSTICS expired_count = ROW_COUNT;
    RETURN expired_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE person_notes IS 'Freeform notes about people with per-user encryption';
COMMENT ON COLUMN person_notes.content_encrypted IS 'Encrypted JSON: {"text": "note content", "context": "optional context"}';
COMMENT ON COLUMN person_notes.category IS 'Note type: general, travel, preference, event, reminder, observation, other';
COMMENT ON COLUMN person_notes.related_date IS 'Optional date the note refers to (e.g., visit date, event date)';
COMMENT ON COLUMN person_notes.is_time_sensitive IS 'If true, note will auto-expire after related_date passes';
COMMENT ON COLUMN person_notes.status IS 'active = visible, archived = hidden by user, expired = auto-hidden after date';

COMMIT;

-- ============================================================================
-- Verification
-- ============================================================================

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'person_notes'
ORDER BY ordinal_position;

