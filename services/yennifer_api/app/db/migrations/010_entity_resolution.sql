-- Migration 010: Entity Resolution Support
-- Adds placeholder tracking, interaction scoring, and relationship strength
--
-- Run with: psql $DATABASE_URL -f 010_entity_resolution.sql

BEGIN;

-- ============================================================
-- 1. Placeholder tracking for persons
-- ============================================================

-- Track if phone/email are placeholders (not real contact info)
ALTER TABLE persons ADD COLUMN IF NOT EXISTS is_placeholder_phone BOOLEAN DEFAULT FALSE;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS is_placeholder_email BOOLEAN DEFAULT FALSE;

-- Birth year for age-based lookups
ALTER TABLE persons ADD COLUMN IF NOT EXISTS birth_year INTEGER;

-- ============================================================
-- 2. Interaction tracking for confidence scoring
-- ============================================================

-- Track when user last interacted with this person (via agent)
ALTER TABLE persons ADD COLUMN IF NOT EXISTS last_interacted_at TIMESTAMP;

-- Count of interactions (for frequency scoring)
ALTER TABLE persons ADD COLUMN IF NOT EXISTS interaction_count INTEGER DEFAULT 0;

-- ============================================================
-- 3. Relationship strength & tracking
-- ============================================================

-- Relationship strength (0-100, combines category + frequency + user rating)
ALTER TABLE relationships ADD COLUMN IF NOT EXISTS strength INTEGER DEFAULT 50;

-- Track when relationship was last referenced in conversation
ALTER TABLE relationships ADD COLUMN IF NOT EXISTS last_referenced_at TIMESTAMP;

-- Count of references (for frequency scoring)
ALTER TABLE relationships ADD COLUMN IF NOT EXISTS reference_count INTEGER DEFAULT 0;

-- User's explicit rating of relationship importance (1-5 stars, optional)
ALTER TABLE relationships ADD COLUMN IF NOT EXISTS user_rating INTEGER;

-- Add constraints (drop first if exists to avoid errors)
DO $$
BEGIN
    -- Add strength range constraint
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strength_range') THEN
        ALTER TABLE relationships ADD CONSTRAINT strength_range CHECK (strength >= 0 AND strength <= 100);
    END IF;
    
    -- Add user_rating range constraint
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_rating_range') THEN
        ALTER TABLE relationships ADD CONSTRAINT user_rating_range CHECK (user_rating IS NULL OR (user_rating >= 1 AND user_rating <= 5));
    END IF;
END $$;

-- ============================================================
-- 4. Remove hard contact constraint (allow placeholders)
-- ============================================================

-- Drop the constraint that requires real contact info
-- (We now allow placeholder contacts)
ALTER TABLE persons DROP CONSTRAINT IF EXISTS contact_method_required;

-- ============================================================
-- 5. Helper function to check if person has real contact info
-- ============================================================

CREATE OR REPLACE FUNCTION has_real_contact_info(person_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    p RECORD;
BEGIN
    SELECT * INTO p FROM persons WHERE id = person_id;
    
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    
    RETURN (
        (p.personal_cell IS NOT NULL AND (p.is_placeholder_phone IS NULL OR p.is_placeholder_phone = FALSE)) OR
        (p.work_cell IS NOT NULL AND (p.is_placeholder_phone IS NULL OR p.is_placeholder_phone = FALSE)) OR
        (p.personal_email IS NOT NULL AND (p.is_placeholder_email IS NULL OR p.is_placeholder_email = FALSE)) OR
        (p.work_email IS NOT NULL AND (p.is_placeholder_email IS NULL OR p.is_placeholder_email = FALSE))
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 6. Index for efficient person lookups
-- ============================================================

-- Index for name-based searches (case-insensitive)
CREATE INDEX IF NOT EXISTS idx_persons_name_lower ON persons (LOWER(name));
CREATE INDEX IF NOT EXISTS idx_persons_first_name_lower ON persons (LOWER(first_name));

-- Index for interaction-based sorting
CREATE INDEX IF NOT EXISTS idx_persons_last_interacted ON persons (last_interacted_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_persons_interaction_count ON persons (interaction_count DESC);

COMMIT;

-- ============================================================
-- Verification
-- ============================================================

-- Check new columns exist
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'persons' 
AND column_name IN ('is_placeholder_phone', 'is_placeholder_email', 'birth_year', 'last_interacted_at', 'interaction_count');

SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'relationships' 
AND column_name IN ('strength', 'last_referenced_at', 'reference_count', 'user_rating');

