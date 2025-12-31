-- Migration 009: Restore contact_method_required constraint
-- Require at least one contact method (email or phone) for persons
--
-- Run with: psql $DATABASE_URL -f 009_restore_contact_required.sql

BEGIN;

-- Restore the constraint that requires at least one contact method
ALTER TABLE persons ADD CONSTRAINT contact_method_required 
CHECK (
    personal_cell IS NOT NULL OR 
    work_cell IS NOT NULL OR 
    work_email IS NOT NULL OR 
    personal_email IS NOT NULL
);

COMMIT;

-- Verify constraint is added
SELECT conname FROM pg_constraint WHERE conrelid = 'persons'::regclass AND conname = 'contact_method_required';

