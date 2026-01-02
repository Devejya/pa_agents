-- Migration: 004a_fix_null_owner_user_ids.sql
-- Description: Fix NULL owner_user_id values before applying strict RLS policies
-- Author: Auto-generated
-- Date: 2026-01-02
--
-- This migration MUST be run BEFORE 004_strict_rls_policies.sql
-- It assigns owner_user_id to orphaned records or deletes truly orphaned ones.

BEGIN;

-- ============================================================================
-- INVESTIGATION QUERIES (run these first to understand the data)
-- ============================================================================

-- Check person_external_ids with NULL owner_user_id
-- These should inherit owner_user_id from their linked person
DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    -- Count external_ids that can be fixed by inheriting from person
    SELECT COUNT(*) INTO orphan_count
    FROM person_external_ids pei
    JOIN persons p ON pei.person_id = p.id
    WHERE pei.owner_user_id IS NULL
      AND p.owner_user_id IS NOT NULL;
    
    RAISE NOTICE 'person_external_ids that can inherit owner from person: %', orphan_count;
    
    -- Count truly orphaned external_ids (person also has no owner)
    SELECT COUNT(*) INTO orphan_count
    FROM person_external_ids pei
    LEFT JOIN persons p ON pei.person_id = p.id
    WHERE pei.owner_user_id IS NULL
      AND (p.owner_user_id IS NULL OR p.id IS NULL);
    
    RAISE NOTICE 'person_external_ids with no resolvable owner (will be deleted): %', orphan_count;
END $$;


-- ============================================================================
-- FIX person_external_ids: Inherit owner_user_id from linked person
-- ============================================================================

UPDATE person_external_ids pei
SET owner_user_id = p.owner_user_id
FROM persons p
WHERE pei.person_id = p.id
  AND pei.owner_user_id IS NULL
  AND p.owner_user_id IS NOT NULL;

-- Report how many were fixed
DO $$
DECLARE
    remaining INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining
    FROM person_external_ids
    WHERE owner_user_id IS NULL;
    
    IF remaining > 0 THEN
        RAISE NOTICE 'person_external_ids still with NULL owner_user_id: % (will be deleted)', remaining;
    ELSE
        RAISE NOTICE 'All person_external_ids now have owner_user_id assigned';
    END IF;
END $$;

-- Delete truly orphaned external_ids (where person doesn't exist or has no owner)
DELETE FROM person_external_ids
WHERE owner_user_id IS NULL;


-- ============================================================================
-- FIX sync_state: Look up owner from user_identifier (email) or delete
-- ============================================================================

-- First, try to look up the user by email (user_id column stores email in sync_state)
UPDATE sync_state ss
SET owner_user_id = u.id
FROM users u
WHERE ss.owner_user_id IS NULL
  AND ss.user_id = u.email;

-- Report and delete any remaining orphaned sync_state
DO $$
DECLARE
    remaining INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining
    FROM sync_state
    WHERE owner_user_id IS NULL;
    
    IF remaining > 0 THEN
        RAISE NOTICE 'Deleting % orphaned sync_state records (no matching user found)', remaining;
    END IF;
END $$;

DELETE FROM sync_state
WHERE owner_user_id IS NULL;


-- ============================================================================
-- VERIFICATION: Confirm no NULL owner_user_id remains
-- ============================================================================

DO $$
DECLARE
    persons_null INTEGER;
    relationships_null INTEGER;
    external_ids_null INTEGER;
    sync_state_null INTEGER;
    sync_conflicts_null INTEGER;
    sync_log_null INTEGER;
BEGIN
    SELECT COUNT(*) INTO persons_null FROM persons WHERE owner_user_id IS NULL;
    SELECT COUNT(*) INTO relationships_null FROM relationships WHERE owner_user_id IS NULL;
    SELECT COUNT(*) INTO external_ids_null FROM person_external_ids WHERE owner_user_id IS NULL;
    SELECT COUNT(*) INTO sync_state_null FROM sync_state WHERE owner_user_id IS NULL;
    SELECT COUNT(*) INTO sync_conflicts_null FROM sync_conflicts WHERE owner_user_id IS NULL;
    SELECT COUNT(*) INTO sync_log_null FROM sync_log WHERE owner_user_id IS NULL;
    
    RAISE NOTICE '=== FINAL VERIFICATION ===';
    RAISE NOTICE 'persons with NULL owner_user_id: %', persons_null;
    RAISE NOTICE 'relationships with NULL owner_user_id: %', relationships_null;
    RAISE NOTICE 'person_external_ids with NULL owner_user_id: %', external_ids_null;
    RAISE NOTICE 'sync_state with NULL owner_user_id: %', sync_state_null;
    RAISE NOTICE 'sync_conflicts with NULL owner_user_id: %', sync_conflicts_null;
    RAISE NOTICE 'sync_log with NULL owner_user_id: %', sync_log_null;
    
    IF persons_null + relationships_null + external_ids_null + 
       sync_state_null + sync_conflicts_null + sync_log_null > 0 THEN
        RAISE EXCEPTION 'FAILED: Some records still have NULL owner_user_id. Review manually.';
    ELSE
        RAISE NOTICE 'SUCCESS: All records have owner_user_id assigned. Safe to apply strict RLS.';
    END IF;
END $$;


-- ============================================================================
-- ADD NOT NULL CONSTRAINTS to prevent future NULL owner_user_id
-- ============================================================================
-- These constraints ensure code MUST provide owner_user_id going forward.
-- If any INSERT fails after this, it's a bug in the calling code.

ALTER TABLE persons 
    ALTER COLUMN owner_user_id SET NOT NULL;

ALTER TABLE relationships 
    ALTER COLUMN owner_user_id SET NOT NULL;

ALTER TABLE person_external_ids 
    ALTER COLUMN owner_user_id SET NOT NULL;

ALTER TABLE sync_state 
    ALTER COLUMN owner_user_id SET NOT NULL;

ALTER TABLE sync_conflicts 
    ALTER COLUMN owner_user_id SET NOT NULL;

ALTER TABLE sync_log 
    ALTER COLUMN owner_user_id SET NOT NULL;

DO $$ BEGIN
    RAISE NOTICE 'NOT NULL constraints added - future inserts MUST provide owner_user_id';
END $$;

COMMIT;

-- ============================================================================
-- NEXT STEP: Run 004_strict_rls_policies.sql to enforce exact match
-- ============================================================================

