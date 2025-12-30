-- Migration 004: Chat Sessions and Messages Tables
-- 
-- Creates tables for persisting chat history with:
-- - Per-user data isolation via RLS
-- - Encrypted message content using user's DEK
-- - Session management for multiple conversations
-- - Partitioning by date for warm tier (future)

-- ============================================================================
-- Step 1: Create chat_sessions table
-- ============================================================================

CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Session metadata
    title VARCHAR(255),  -- Optional title (auto-generated or user-set)
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE,
    
    -- Message counts (denormalized for performance)
    message_count INTEGER DEFAULT 0
);

-- Indexes for chat_sessions
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_active ON chat_sessions(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_message ON chat_sessions(last_message_at DESC);

-- Comments
COMMENT ON TABLE chat_sessions IS 'Chat conversation sessions with per-user isolation';
COMMENT ON COLUMN chat_sessions.title IS 'Optional session title, can be auto-generated from first message';

-- ============================================================================
-- Step 2: Create chat_messages table
-- ============================================================================

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- Denormalized for RLS
    
    -- Message content (encrypted with user's DEK)
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content_encrypted BYTEA NOT NULL,  -- Fernet-encrypted with user's DEK
    
    -- Tool calls (for assistant messages that used tools)
    tool_calls_encrypted BYTEA,  -- Optional: encrypted JSON of tool calls
    
    -- Metadata
    tokens_used INTEGER,  -- Optional: token count for this message
    model VARCHAR(50),    -- Model used (for assistant messages)
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for chat_messages
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at DESC);

-- Comments
COMMENT ON TABLE chat_messages IS 'Individual chat messages with encrypted content';
COMMENT ON COLUMN chat_messages.content_encrypted IS 'Message content encrypted with user DEK via Fernet';
COMMENT ON COLUMN chat_messages.role IS 'Message role: user, assistant, or system';

-- ============================================================================
-- Step 3: Create trigger for updated_at on chat_sessions
-- ============================================================================

-- Use existing update_updated_at_timestamp function if it exists, or create it
CREATE OR REPLACE FUNCTION update_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER trigger_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_timestamp();

-- ============================================================================
-- Step 4: Create trigger to update session stats on new message
-- ============================================================================

CREATE OR REPLACE FUNCTION update_session_on_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE chat_sessions
    SET 
        message_count = message_count + 1,
        last_message_at = NEW.created_at,
        updated_at = NOW()
    WHERE id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_session_on_message ON chat_messages;
CREATE TRIGGER trigger_update_session_on_message
    AFTER INSERT ON chat_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_session_on_message();

-- ============================================================================
-- Step 5: Enable Row-Level Security
-- ============================================================================

ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

-- Force RLS for table owner
ALTER TABLE chat_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE chat_messages FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- Step 6: RLS Policies for chat_sessions
-- ============================================================================

DROP POLICY IF EXISTS chat_sessions_select_policy ON chat_sessions;
DROP POLICY IF EXISTS chat_sessions_insert_policy ON chat_sessions;
DROP POLICY IF EXISTS chat_sessions_update_policy ON chat_sessions;
DROP POLICY IF EXISTS chat_sessions_delete_policy ON chat_sessions;

-- SELECT: Users can only see their own sessions
CREATE POLICY chat_sessions_select_policy ON chat_sessions
    FOR SELECT
    USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- INSERT: Users can only create sessions for themselves
CREATE POLICY chat_sessions_insert_policy ON chat_sessions
    FOR INSERT
    WITH CHECK (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- UPDATE: Users can only update their own sessions
CREATE POLICY chat_sessions_update_policy ON chat_sessions
    FOR UPDATE
    USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    )
    WITH CHECK (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- DELETE: Users can only delete their own sessions
CREATE POLICY chat_sessions_delete_policy ON chat_sessions
    FOR DELETE
    USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- ============================================================================
-- Step 7: RLS Policies for chat_messages
-- ============================================================================

DROP POLICY IF EXISTS chat_messages_select_policy ON chat_messages;
DROP POLICY IF EXISTS chat_messages_insert_policy ON chat_messages;
DROP POLICY IF EXISTS chat_messages_update_policy ON chat_messages;
DROP POLICY IF EXISTS chat_messages_delete_policy ON chat_messages;

-- SELECT: Users can only see their own messages
CREATE POLICY chat_messages_select_policy ON chat_messages
    FOR SELECT
    USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- INSERT: Users can only create messages for themselves
CREATE POLICY chat_messages_insert_policy ON chat_messages
    FOR INSERT
    WITH CHECK (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- UPDATE: Users can only update their own messages (rare, but for edits)
CREATE POLICY chat_messages_update_policy ON chat_messages
    FOR UPDATE
    USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    )
    WITH CHECK (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- DELETE: Users can only delete their own messages
CREATE POLICY chat_messages_delete_policy ON chat_messages
    FOR DELETE
    USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
    );

-- ============================================================================
-- Step 8: Grant permissions to application role
-- ============================================================================

-- Grant to existing rls_test_user if it exists
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rls_test_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sessions TO rls_test_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_messages TO rls_test_user;
    END IF;
END
$$;

-- ============================================================================
-- Verification Queries (run after migration)
-- ============================================================================

-- SELECT tablename, rowsecurity, forcerowsecurity
-- FROM pg_tables t
-- JOIN pg_class c ON t.tablename = c.relname
-- WHERE schemaname = 'public' 
--   AND tablename IN ('chat_sessions', 'chat_messages');

-- SELECT policyname, tablename, cmd, qual 
-- FROM pg_policies 
-- WHERE tablename IN ('chat_sessions', 'chat_messages');


