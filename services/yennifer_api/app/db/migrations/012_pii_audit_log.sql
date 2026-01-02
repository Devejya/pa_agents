-- PII Masking Audit Log
-- Tracks PII masking events for compliance without storing actual PII values
-- 
-- Purpose:
-- 1. Compliance auditing - prove PII is being protected
-- 2. Monitoring - detect unusual masking patterns
-- 3. Debugging - trace issues without exposing PII

CREATE TABLE IF NOT EXISTS pii_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Request context
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    request_id VARCHAR(100),
    endpoint VARCHAR(255),
    tool_name VARCHAR(100),
    
    -- Masking statistics (no actual PII values stored)
    total_masked INTEGER NOT NULL DEFAULT 0,
    emails_masked INTEGER NOT NULL DEFAULT 0,
    phones_masked INTEGER NOT NULL DEFAULT 0,
    ssn_masked INTEGER NOT NULL DEFAULT 0,
    cards_masked INTEGER NOT NULL DEFAULT 0,
    accounts_masked INTEGER NOT NULL DEFAULT 0,
    addresses_masked INTEGER NOT NULL DEFAULT 0,
    dob_masked INTEGER NOT NULL DEFAULT 0,
    ip_masked INTEGER NOT NULL DEFAULT 0,
    
    -- Masking mode used
    masking_mode VARCHAR(20) DEFAULT 'full',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_pii_audit_user ON pii_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_pii_audit_time ON pii_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_pii_audit_request ON pii_audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_pii_audit_tool ON pii_audit_log(tool_name);

-- Partitioning hint: For production with high volume, consider partitioning by created_at
-- This table can grow large, so plan for archival/rotation

COMMENT ON TABLE pii_audit_log IS 'Audit log for PII masking events - stores counts only, never actual PII';
COMMENT ON COLUMN pii_audit_log.total_masked IS 'Total number of PII items masked in this request/tool call';
COMMENT ON COLUMN pii_audit_log.masking_mode IS 'full, financial_only, or none';

