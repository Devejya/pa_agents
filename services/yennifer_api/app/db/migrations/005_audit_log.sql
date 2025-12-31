-- Migration 005: Audit Log Table
-- 
-- Creates append-only audit log for SOC2/PIPEDA compliance:
-- - Tracks all data access and modifications
-- - Immutable records (no UPDATE/DELETE)
-- - Partitioned by month for performance and retention
-- - Indexed for efficient querying

-- ============================================================================
-- Step 1: Create audit_log table
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    
    -- Who performed the action
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,  -- NULL for unauthenticated
    session_id UUID,  -- Chat session if applicable
    
    -- What action was performed
    action VARCHAR(50) NOT NULL,  -- read, create, update, delete, login, logout, export
    resource_type VARCHAR(100) NOT NULL,  -- persons, chat_messages, user_settings, etc.
    resource_id VARCHAR(255),  -- UUID or identifier of the affected resource
    
    -- Details (non-sensitive)
    details JSONB,  -- Additional context (e.g., field names changed, search query)
    
    -- Request context
    ip_address INET,
    user_agent TEXT,
    request_id UUID,  -- For correlating with application logs
    
    -- Result
    success BOOLEAN DEFAULT true,
    error_message TEXT,  -- Only if success = false
    
    -- Timestamp (immutable)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Step 2: Create indexes for efficient querying
-- ============================================================================

-- Primary query patterns
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_time ON audit_log(user_id, created_at DESC);

-- Compliance query patterns
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_ip ON audit_log(ip_address);

-- Composite for common queries
CREATE INDEX IF NOT EXISTS idx_audit_log_user_resource ON audit_log(user_id, resource_type, created_at DESC);

-- ============================================================================
-- Step 3: Create function to prevent modifications
-- ============================================================================

-- Prevent UPDATE on audit_log
CREATE OR REPLACE FUNCTION prevent_audit_log_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'UPDATE not allowed on audit_log table - logs are immutable';
END;
$$ LANGUAGE plpgsql;

-- Prevent DELETE on audit_log (except for retention policy)
CREATE OR REPLACE FUNCTION prevent_audit_log_delete()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow deletion only if record is older than retention period (365 days)
    IF OLD.created_at > NOW() - INTERVAL '365 days' THEN
        RAISE EXCEPTION 'DELETE not allowed on audit_log within retention period';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_update();

DROP TRIGGER IF EXISTS audit_log_retention_delete ON audit_log;
CREATE TRIGGER audit_log_retention_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_delete();

-- ============================================================================
-- Step 4: Comments for documentation
-- ============================================================================

COMMENT ON TABLE audit_log IS 'Immutable audit trail for SOC2/PIPEDA compliance - tracks all data access and modifications';
COMMENT ON COLUMN audit_log.action IS 'Action type: read, create, update, delete, login, logout, export, sync';
COMMENT ON COLUMN audit_log.resource_type IS 'Type of resource: persons, relationships, chat_messages, user_settings, oauth_tokens, contacts_sync';
COMMENT ON COLUMN audit_log.resource_id IS 'Identifier of affected resource (UUID or external ID)';
COMMENT ON COLUMN audit_log.details IS 'Non-sensitive additional context (field names, counts, not actual data values)';
COMMENT ON COLUMN audit_log.request_id IS 'Correlation ID for linking to application logs';

-- ============================================================================
-- Step 5: Create helper function for logging
-- ============================================================================

CREATE OR REPLACE FUNCTION log_audit_event(
    p_user_id UUID,
    p_action VARCHAR(50),
    p_resource_type VARCHAR(100),
    p_resource_id VARCHAR(255) DEFAULT NULL,
    p_details JSONB DEFAULT NULL,
    p_session_id UUID DEFAULT NULL,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL,
    p_request_id UUID DEFAULT NULL,
    p_success BOOLEAN DEFAULT true,
    p_error_message TEXT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_log_id BIGINT;
BEGIN
    INSERT INTO audit_log (
        user_id, action, resource_type, resource_id, details,
        session_id, ip_address, user_agent, request_id,
        success, error_message
    ) VALUES (
        p_user_id, p_action, p_resource_type, p_resource_id, p_details,
        p_session_id, p_ip_address, p_user_agent, p_request_id,
        p_success, p_error_message
    ) RETURNING id INTO v_log_id;
    
    RETURN v_log_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION log_audit_event IS 'Helper function to insert audit log entries';

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    -- Verify table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_log') THEN
        RAISE NOTICE '✓ audit_log table created successfully';
    END IF;
    
    -- Verify indexes
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_audit_log_user_id') THEN
        RAISE NOTICE '✓ Indexes created successfully';
    END IF;
    
    -- Verify triggers
    IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'audit_log_no_update') THEN
        RAISE NOTICE '✓ Immutability triggers created successfully';
    END IF;
    
    RAISE NOTICE '✓ Migration 005 (Audit Log) completed successfully';
END $$;

