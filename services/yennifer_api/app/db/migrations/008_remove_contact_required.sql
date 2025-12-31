-- Migration 008: Remove contact_method_required constraint
-- Allow persons to be created without email/phone
--
-- Run with: psql $DATABASE_URL -f 008_remove_contact_required.sql

BEGIN;

-- Drop the constraint that requires at least one contact method
ALTER TABLE persons DROP CONSTRAINT IF EXISTS contact_method_required;

COMMIT;

-- Verify constraint is removed
SELECT conname FROM pg_constraint WHERE conrelid = 'persons'::regclass;

