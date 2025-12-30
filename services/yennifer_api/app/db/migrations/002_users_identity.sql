-- Migration: 002_users_identity
-- Description: Create users and user_identities tables for multi-tenant support
-- Date: 2025-12-30

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- USERS TABLE - Core user identity with per-user encryption
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Primary email (for display/contact)
    email VARCHAR(255) UNIQUE NOT NULL,
    
    -- Per-user encryption key (DEK encrypted by KMS KEK)
    -- This is the AES-256 data encryption key, encrypted by AWS KMS
    encryption_key_blob BYTEA NOT NULL,
    encryption_key_version INT DEFAULT 1,
    
    -- User settings (encrypted with user's DEK)
    -- Decrypted: {"timezone": "America/New_York", "notification_prefs": {...}}
    settings_encrypted BYTEA,
    
    -- Timezone for display purposes (unencrypted for scheduling queries)
    timezone VARCHAR(50) DEFAULT 'UTC',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for email lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================================
-- USER_IDENTITIES TABLE - OAuth provider identities
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_identities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- OAuth provider
    provider VARCHAR(50) NOT NULL,  -- 'google', 'apple', etc.
    
    -- Hashed provider user ID for lookup (SHA-256)
    -- We hash instead of encrypt so we can do lookups during OAuth callback
    -- before we know the internal user_id
    provider_user_id_hash BYTEA NOT NULL,
    
    -- Email from OAuth (encrypted with user's DEK)
    email_encrypted BYTEA,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Unique constraint: one identity per provider per user
    CONSTRAINT unique_provider_hash UNIQUE (provider, provider_user_id_hash)
);

-- Index for OAuth callback lookups
CREATE INDEX IF NOT EXISTS idx_user_identities_lookup 
    ON user_identities(provider, provider_user_id_hash);
CREATE INDEX IF NOT EXISTS idx_user_identities_user 
    ON user_identities(user_id);

-- ============================================================================
-- UPDATE USER_OAUTH_TOKENS - Add user_id reference
-- ============================================================================

-- Add user_id column to user_oauth_tokens (nullable initially for migration)
ALTER TABLE user_oauth_tokens 
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- Index for user_id lookups
CREATE INDEX IF NOT EXISTS idx_user_oauth_tokens_user_id 
    ON user_oauth_tokens(user_id);

-- ============================================================================
-- UPDATED_AT TRIGGERS
-- ============================================================================

-- Trigger function for updated_at (reuse if exists)
CREATE OR REPLACE FUNCTION update_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to users table
DROP TRIGGER IF EXISTS trigger_users_updated_at ON users;
CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_timestamp();

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE users IS 'Core user identity with per-user encryption keys';
COMMENT ON COLUMN users.encryption_key_blob IS 'AES-256 DEK encrypted by AWS KMS KEK - use KMS Decrypt to get plaintext key';
COMMENT ON COLUMN users.settings_encrypted IS 'User preferences encrypted with their DEK';

COMMENT ON TABLE user_identities IS 'OAuth provider identities linked to users';
COMMENT ON COLUMN user_identities.provider_user_id_hash IS 'SHA-256 hash of provider:provider_user_id for lookup during OAuth';
COMMENT ON COLUMN user_identities.email_encrypted IS 'OAuth email encrypted with user DEK';


