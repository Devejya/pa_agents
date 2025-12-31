-- Migration 007: Add person_id to interests table
-- This allows storing interests for persons (contacts) in addition to users
--
-- Use case: "My wife loves hiking" → store hiking interest for wife (person)
-- vs "I love hiking" → store hiking interest for user
--
-- Run with: psql $DATABASE_URL -f 007_person_interests.sql

BEGIN;

-- ============================================================================
-- 1. Add person_id column to interests table
-- ============================================================================

-- Add nullable person_id column
ALTER TABLE interests
ADD COLUMN IF NOT EXISTS person_id UUID REFERENCES persons(id) ON DELETE CASCADE;

-- Add comment explaining the column
COMMENT ON COLUMN interests.person_id IS 
'If set, this interest belongs to a person (contact). If NULL, it belongs to the user.';

-- ============================================================================
-- 2. Add check constraint: either user_id OR person_id must be set (not both)
-- ============================================================================

-- Note: We allow both to be set for now, but typically:
-- - user_id IS NOT NULL AND person_id IS NULL → user's own interest
-- - user_id IS NOT NULL AND person_id IS NOT NULL → interest of a contact (owned by user for RLS)

-- ============================================================================
-- 3. Add index for querying person interests
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_interests_person_id ON interests(person_id) WHERE person_id IS NOT NULL;

-- ============================================================================
-- 4. Update RLS policy to include person_id lookups
-- ============================================================================

-- The existing RLS policy on user_id should still work since:
-- - User's interests: user_id = current_user_id
-- - Person's interests: user_id = current_user_id (owner), person_id = specific person

-- ============================================================================
-- 5. Add person_id to important_dates if not already there
-- ============================================================================

-- Check if person_id column exists in important_dates
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'important_dates' AND column_name = 'person_id'
    ) THEN
        ALTER TABLE important_dates
        ADD COLUMN person_id UUID REFERENCES persons(id) ON DELETE SET NULL;
        
        COMMENT ON COLUMN important_dates.person_id IS 
        'The person this date is associated with (e.g., wife for "wife''s birthday")';
        
        CREATE INDEX idx_important_dates_person_id ON important_dates(person_id) 
        WHERE person_id IS NOT NULL;
    END IF;
END $$;

COMMIT;

-- ============================================================================
-- Verification
-- ============================================================================

-- Check interests table structure
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'interests'
ORDER BY ordinal_position;

-- Check important_dates table structure  
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'important_dates'
ORDER BY ordinal_position;

