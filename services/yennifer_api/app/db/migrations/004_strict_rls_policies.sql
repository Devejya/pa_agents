-- Migration: 004_strict_rls_policies.sql
-- Description: Update RLS policies to require exact owner_user_id match (no NULL fallback)
-- Author: Auto-generated
-- Date: 2026-01-02
--
-- IMPORTANT: This migration makes RLS policies stricter by removing the
-- "OR owner_user_id IS NULL" fallback. Before running this:
-- 1. Ensure all existing rows have a valid owner_user_id
-- 2. Run the verification query at the bottom to check for NULL values

BEGIN;

-- ============================================================================
-- PERSONS TABLE
-- ============================================================================

-- persons_select_policy is already strict (no NULL fallback) - skip

-- Update persons_update_policy
DROP POLICY IF EXISTS persons_update_policy ON persons;
CREATE POLICY persons_update_policy ON persons
    FOR UPDATE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

-- Update persons_delete_policy
DROP POLICY IF EXISTS persons_delete_policy ON persons;
CREATE POLICY persons_delete_policy ON persons
    FOR DELETE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

-- Update persons_insert_policy to enforce owner_user_id on insert
DROP POLICY IF EXISTS persons_insert_policy ON persons;
CREATE POLICY persons_insert_policy ON persons
    FOR INSERT
    WITH CHECK (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);


-- ============================================================================
-- RELATIONSHIPS TABLE
-- ============================================================================

DROP POLICY IF EXISTS relationships_select_policy ON relationships;
CREATE POLICY relationships_select_policy ON relationships
    FOR SELECT
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS relationships_insert_policy ON relationships;
CREATE POLICY relationships_insert_policy ON relationships
    FOR INSERT
    WITH CHECK (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS relationships_update_policy ON relationships;
CREATE POLICY relationships_update_policy ON relationships
    FOR UPDATE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS relationships_delete_policy ON relationships;
CREATE POLICY relationships_delete_policy ON relationships
    FOR DELETE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);


-- ============================================================================
-- PERSON_EXTERNAL_IDS TABLE
-- ============================================================================

DROP POLICY IF EXISTS person_external_ids_select_policy ON person_external_ids;
CREATE POLICY person_external_ids_select_policy ON person_external_ids
    FOR SELECT
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS person_external_ids_insert_policy ON person_external_ids;
CREATE POLICY person_external_ids_insert_policy ON person_external_ids
    FOR INSERT
    WITH CHECK (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS person_external_ids_update_policy ON person_external_ids;
CREATE POLICY person_external_ids_update_policy ON person_external_ids
    FOR UPDATE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS person_external_ids_delete_policy ON person_external_ids;
CREATE POLICY person_external_ids_delete_policy ON person_external_ids
    FOR DELETE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);


-- ============================================================================
-- SYNC_STATE TABLE
-- ============================================================================

DROP POLICY IF EXISTS sync_state_select_policy ON sync_state;
CREATE POLICY sync_state_select_policy ON sync_state
    FOR SELECT
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_state_insert_policy ON sync_state;
CREATE POLICY sync_state_insert_policy ON sync_state
    FOR INSERT
    WITH CHECK (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_state_update_policy ON sync_state;
CREATE POLICY sync_state_update_policy ON sync_state
    FOR UPDATE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_state_delete_policy ON sync_state;
CREATE POLICY sync_state_delete_policy ON sync_state
    FOR DELETE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);


-- ============================================================================
-- SYNC_CONFLICTS TABLE
-- ============================================================================

DROP POLICY IF EXISTS sync_conflicts_select_policy ON sync_conflicts;
CREATE POLICY sync_conflicts_select_policy ON sync_conflicts
    FOR SELECT
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_conflicts_insert_policy ON sync_conflicts;
CREATE POLICY sync_conflicts_insert_policy ON sync_conflicts
    FOR INSERT
    WITH CHECK (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_conflicts_update_policy ON sync_conflicts;
CREATE POLICY sync_conflicts_update_policy ON sync_conflicts
    FOR UPDATE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_conflicts_delete_policy ON sync_conflicts;
CREATE POLICY sync_conflicts_delete_policy ON sync_conflicts
    FOR DELETE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);


-- ============================================================================
-- SYNC_LOG TABLE
-- ============================================================================

DROP POLICY IF EXISTS sync_log_select_policy ON sync_log;
CREATE POLICY sync_log_select_policy ON sync_log
    FOR SELECT
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_log_insert_policy ON sync_log;
CREATE POLICY sync_log_insert_policy ON sync_log
    FOR INSERT
    WITH CHECK (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_log_update_policy ON sync_log;
CREATE POLICY sync_log_update_policy ON sync_log
    FOR UPDATE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);

DROP POLICY IF EXISTS sync_log_delete_policy ON sync_log;
CREATE POLICY sync_log_delete_policy ON sync_log
    FOR DELETE
    USING (owner_user_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid);


COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES (run these BEFORE the migration)
-- ============================================================================
-- Check for rows with NULL owner_user_id that would become inaccessible:
--
-- SELECT 'persons' as table_name, COUNT(*) as null_count FROM persons WHERE owner_user_id IS NULL
-- UNION ALL
-- SELECT 'relationships', COUNT(*) FROM relationships WHERE owner_user_id IS NULL
-- UNION ALL
-- SELECT 'person_external_ids', COUNT(*) FROM person_external_ids WHERE owner_user_id IS NULL
-- UNION ALL
-- SELECT 'sync_state', COUNT(*) FROM sync_state WHERE owner_user_id IS NULL
-- UNION ALL
-- SELECT 'sync_conflicts', COUNT(*) FROM sync_conflicts WHERE owner_user_id IS NULL
-- UNION ALL
-- SELECT 'sync_log', COUNT(*) FROM sync_log WHERE owner_user_id IS NULL;
--
-- If any counts are > 0, you need to either:
-- 1. Assign an owner_user_id to those rows, or
-- 2. Delete those orphaned rows
-- ============================================================================

