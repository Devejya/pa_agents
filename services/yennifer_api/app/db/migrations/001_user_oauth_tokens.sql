-- Migration: 001_user_oauth_tokens
-- Description: Create table for storing encrypted OAuth tokens
-- Date: 2025-12-28

-- User OAuth tokens table
-- Stores encrypted Google OAuth tokens for each user
CREATE TABLE IF NOT EXISTS user_oauth_tokens (
    id SERIAL PRIMARY KEY,
    
    -- User identifier (email)
    email VARCHAR(255) NOT NULL UNIQUE,
    
    -- Provider (for future multi-provider support)
    provider VARCHAR(50) NOT NULL DEFAULT 'google',
    
    -- Encrypted token data (contains access_token, refresh_token, etc.)
    -- Encrypted using Fernet symmetric encryption
    encrypted_tokens TEXT NOT NULL,
    
    -- Token metadata (not encrypted)
    token_type VARCHAR(50) DEFAULT 'Bearer',
    expires_at TIMESTAMPTZ,
    
    -- Scopes granted
    scopes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Last successful token use
    last_used_at TIMESTAMPTZ,
    
    -- Token status
    is_valid BOOLEAN DEFAULT TRUE,
    revoked_at TIMESTAMPTZ,
    revoke_reason VARCHAR(255),
    
    -- Unique constraint on email + provider
    CONSTRAINT unique_user_provider UNIQUE (email, provider)
);

-- Index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_user_oauth_tokens_email ON user_oauth_tokens(email);
CREATE INDEX IF NOT EXISTS idx_user_oauth_tokens_provider ON user_oauth_tokens(provider);
CREATE INDEX IF NOT EXISTS idx_user_oauth_tokens_valid ON user_oauth_tokens(is_valid) WHERE is_valid = TRUE;

-- Updated_at trigger function
CREATE OR REPLACE FUNCTION update_oauth_tokens_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger
DROP TRIGGER IF EXISTS trigger_update_oauth_tokens_timestamp ON user_oauth_tokens;
CREATE TRIGGER trigger_update_oauth_tokens_timestamp
    BEFORE UPDATE ON user_oauth_tokens
    FOR EACH ROW
    EXECUTE FUNCTION update_oauth_tokens_timestamp();

-- Comment on table
COMMENT ON TABLE user_oauth_tokens IS 'Stores encrypted OAuth tokens for user authentication with external providers';
COMMENT ON COLUMN user_oauth_tokens.encrypted_tokens IS 'Fernet-encrypted JSON containing access_token, refresh_token, and other token data';
COMMENT ON COLUMN user_oauth_tokens.scopes IS 'Space-separated list of OAuth scopes granted';

