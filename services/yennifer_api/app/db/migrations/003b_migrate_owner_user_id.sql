-- Migration 003b: Populate owner_user_id for existing data
-- This links existing persons, relationships, etc. to their owning users
--
-- Run this AFTER 003_rls_data_tables.sql

-- ============================================================================
-- Step 1: Link persons to users via email matching
-- ============================================================================

-- For core users: Link their person record to their user account
-- Match by email: persons.work_email or persons.personal_email = users.email

UPDATE persons p
SET owner_user_id = u.id
FROM users u
WHERE p.owner_user_id IS NULL
  AND p.is_core_user = true
  AND (
    LOWER(p.work_email) = LOWER(u.email)
    OR LOWER(p.personal_email) = LOWER(u.email)
  );

-- Log how many core users were linked
DO $$
DECLARE
    linked_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO linked_count
    FROM persons
    WHERE is_core_user = true AND owner_user_id IS NOT NULL;
    
    RAISE NOTICE 'Linked % core user person records to users', linked_count;
END $$;

-- ============================================================================
-- Step 2: Link contacts to their core user owner
-- ============================================================================

-- For contacts (non-core-users): Find the core user they're related to
-- and set owner_user_id to that core user's owner_user_id

-- First, find contacts that have a relationship with a core user
UPDATE persons p
SET owner_user_id = core_user_person.owner_user_id
FROM relationships r
JOIN persons core_user_person ON core_user_person.id = r.from_person_id
WHERE p.owner_user_id IS NULL
  AND p.is_core_user = false
  AND p.id = r.to_person_id
  AND core_user_person.is_core_user = true
  AND core_user_person.owner_user_id IS NOT NULL;

-- Also check the reverse direction (contact is from_person)
UPDATE persons p
SET owner_user_id = core_user_person.owner_user_id
FROM relationships r
JOIN persons core_user_person ON core_user_person.id = r.to_person_id
WHERE p.owner_user_id IS NULL
  AND p.is_core_user = false
  AND p.id = r.from_person_id
  AND core_user_person.is_core_user = true
  AND core_user_person.owner_user_id IS NOT NULL;

-- Log results
DO $$
DECLARE
    total_persons INTEGER;
    linked_persons INTEGER;
    unlinked_persons INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_persons FROM persons;
    SELECT COUNT(*) INTO linked_persons FROM persons WHERE owner_user_id IS NOT NULL;
    unlinked_persons := total_persons - linked_persons;
    
    RAISE NOTICE 'Persons: % total, % linked, % unlinked', total_persons, linked_persons, unlinked_persons;
END $$;

-- ============================================================================
-- Step 3: Link relationships to their owner
-- ============================================================================

-- Relationships inherit owner from the core_user in the relationship
UPDATE relationships r
SET owner_user_id = core_user_person.owner_user_id
FROM persons core_user_person
WHERE r.owner_user_id IS NULL
  AND core_user_person.id = r.from_person_id
  AND core_user_person.is_core_user = true
  AND core_user_person.owner_user_id IS NOT NULL;

-- Also check to_person
UPDATE relationships r
SET owner_user_id = core_user_person.owner_user_id
FROM persons core_user_person
WHERE r.owner_user_id IS NULL
  AND core_user_person.id = r.to_person_id
  AND core_user_person.is_core_user = true
  AND core_user_person.owner_user_id IS NOT NULL;

-- Log results
DO $$
DECLARE
    total_rels INTEGER;
    linked_rels INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_rels FROM relationships;
    SELECT COUNT(*) INTO linked_rels FROM relationships WHERE owner_user_id IS NOT NULL;
    
    RAISE NOTICE 'Relationships: % total, % linked', total_rels, linked_rels;
END $$;

-- ============================================================================
-- Step 4: Link person_external_ids to their owner
-- ============================================================================

UPDATE person_external_ids pei
SET owner_user_id = p.owner_user_id
FROM persons p
WHERE pei.owner_user_id IS NULL
  AND pei.person_id = p.id
  AND p.owner_user_id IS NOT NULL;

-- Log results
DO $$
DECLARE
    total_ids INTEGER;
    linked_ids INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_ids FROM person_external_ids;
    SELECT COUNT(*) INTO linked_ids FROM person_external_ids WHERE owner_user_id IS NOT NULL;
    
    RAISE NOTICE 'External IDs: % total, % linked', total_ids, linked_ids;
END $$;

-- ============================================================================
-- Step 5: Link sync_state to users
-- ============================================================================

-- sync_state.user_id is currently an email string
-- Link to users.id via email match
UPDATE sync_state ss
SET owner_user_id = u.id
FROM users u
WHERE ss.owner_user_id IS NULL
  AND LOWER(ss.user_id) = LOWER(u.email);

-- Log results
DO $$
DECLARE
    total_sync INTEGER;
    linked_sync INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_sync FROM sync_state;
    SELECT COUNT(*) INTO linked_sync FROM sync_state WHERE owner_user_id IS NOT NULL;
    
    RAISE NOTICE 'Sync states: % total, % linked', total_sync, linked_sync;
END $$;

-- ============================================================================
-- Step 6: Link sync_conflicts to users via email
-- ============================================================================

UPDATE sync_conflicts sc
SET owner_user_id = u.id
FROM users u
WHERE sc.owner_user_id IS NULL
  AND LOWER(sc.user_id) = LOWER(u.email);

-- ============================================================================
-- Step 7: Link sync_log to users via email
-- ============================================================================

UPDATE sync_log sl
SET owner_user_id = u.id
FROM users u
WHERE sl.owner_user_id IS NULL
  AND LOWER(sl.user_id) = LOWER(u.email);

-- ============================================================================
-- Summary Report
-- ============================================================================

DO $$
DECLARE
    rec RECORD;
BEGIN
    RAISE NOTICE '=== Migration Summary ===';
    
    FOR rec IN 
        SELECT 
            'persons' as table_name,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE owner_user_id IS NOT NULL) as linked
        FROM persons
        UNION ALL
        SELECT 
            'relationships',
            COUNT(*),
            COUNT(*) FILTER (WHERE owner_user_id IS NOT NULL)
        FROM relationships
        UNION ALL
        SELECT 
            'person_external_ids',
            COUNT(*),
            COUNT(*) FILTER (WHERE owner_user_id IS NOT NULL)
        FROM person_external_ids
        UNION ALL
        SELECT 
            'sync_state',
            COUNT(*),
            COUNT(*) FILTER (WHERE owner_user_id IS NOT NULL)
        FROM sync_state
    LOOP
        RAISE NOTICE '%: % total, % linked', rec.table_name, rec.total, rec.linked;
    END LOOP;
END $$;


