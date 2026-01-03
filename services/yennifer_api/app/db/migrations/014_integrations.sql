-- Migration: 014_integrations
-- Description: Create tables for incremental OAuth integrations and scopes
-- Date: 2026-01-03

-- ============================================================================
-- Integration definitions (seed data - provider integrations available)
-- ============================================================================
CREATE TABLE IF NOT EXISTS integrations (
    id VARCHAR(50) PRIMARY KEY,           -- 'gmail', 'calendar', 'drive', 'uber', etc.
    provider VARCHAR(50) NOT NULL,        -- 'google', 'uber', 'instacart'
    name VARCHAR(100) NOT NULL,           -- 'Gmail', 'Google Calendar'
    description TEXT,                     -- 'Connect your Gmail account'
    capability_summary TEXT,              -- 'Read, modify and send emails'
    icon_url VARCHAR(255),                -- Logo URL or icon identifier
    is_active BOOLEAN DEFAULT TRUE,       -- Feature flag to hide/show integration
    display_order INT DEFAULT 0,          -- Order in UI
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE integrations IS 'Available integrations that users can enable (seed data)';
COMMENT ON COLUMN integrations.id IS 'Unique identifier like gmail, calendar, drive';
COMMENT ON COLUMN integrations.provider IS 'Provider like google, uber, instacart';
COMMENT ON COLUMN integrations.capability_summary IS 'Brief summary of what this integration enables';
COMMENT ON COLUMN integrations.is_active IS 'Feature flag - if false, integration is hidden from users';

-- ============================================================================
-- Scope definitions per integration (seed data)
-- ============================================================================
CREATE TABLE IF NOT EXISTS integration_scopes (
    id VARCHAR(100) PRIMARY KEY,          -- 'gmail.readonly', 'gmail.compose'
    integration_id VARCHAR(50) NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    scope_uri VARCHAR(255) NOT NULL,      -- 'https://www.googleapis.com/auth/gmail.readonly'
    name VARCHAR(100) NOT NULL,           -- 'Read emails'
    description TEXT,                     -- 'Allows reading email messages'
    is_required BOOLEAN DEFAULT FALSE,    -- If true, always requested when integration enabled
    display_order INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_integration_scopes_integration ON integration_scopes(integration_id);

COMMENT ON TABLE integration_scopes IS 'OAuth scopes available per integration (seed data)';
COMMENT ON COLUMN integration_scopes.scope_uri IS 'Full OAuth scope URI for the provider';
COMMENT ON COLUMN integration_scopes.is_required IS 'If true, this scope is always requested when the integration is enabled';

-- ============================================================================
-- User's enabled integrations
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    integration_id VARCHAR(50) NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    is_enabled BOOLEAN DEFAULT FALSE,
    enabled_at TIMESTAMPTZ,
    disabled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, integration_id)
);

CREATE INDEX IF NOT EXISTS idx_user_integrations_user ON user_integrations(user_id);
CREATE INDEX IF NOT EXISTS idx_user_integrations_enabled ON user_integrations(user_id, is_enabled) WHERE is_enabled = TRUE;

COMMENT ON TABLE user_integrations IS 'Tracks which integrations each user has enabled';

-- ============================================================================
-- User's enabled scopes per integration
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_integration_scopes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope_id VARCHAR(100) NOT NULL REFERENCES integration_scopes(id) ON DELETE CASCADE,
    is_enabled BOOLEAN DEFAULT FALSE,     -- User wants this scope active
    is_granted BOOLEAN DEFAULT FALSE,     -- True after OAuth consent obtained
    granted_at TIMESTAMPTZ,               -- When OAuth consent was obtained
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, scope_id)
);

CREATE INDEX IF NOT EXISTS idx_user_integration_scopes_user ON user_integration_scopes(user_id);
CREATE INDEX IF NOT EXISTS idx_user_integration_scopes_enabled ON user_integration_scopes(user_id, is_enabled) WHERE is_enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_user_integration_scopes_granted ON user_integration_scopes(user_id, is_granted) WHERE is_granted = TRUE;

COMMENT ON TABLE user_integration_scopes IS 'Tracks which scopes each user has enabled and been granted';
COMMENT ON COLUMN user_integration_scopes.is_enabled IS 'User preference - they want this scope active';
COMMENT ON COLUMN user_integration_scopes.is_granted IS 'OAuth state - consent has been obtained from provider';

-- ============================================================================
-- Updated_at trigger function (reuse if exists)
-- ============================================================================
CREATE OR REPLACE FUNCTION update_integrations_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS trigger_update_user_integrations_timestamp ON user_integrations;
CREATE TRIGGER trigger_update_user_integrations_timestamp
    BEFORE UPDATE ON user_integrations
    FOR EACH ROW
    EXECUTE FUNCTION update_integrations_timestamp();

DROP TRIGGER IF EXISTS trigger_update_user_integration_scopes_timestamp ON user_integration_scopes;
CREATE TRIGGER trigger_update_user_integration_scopes_timestamp
    BEFORE UPDATE ON user_integration_scopes
    FOR EACH ROW
    EXECUTE FUNCTION update_integrations_timestamp();

-- ============================================================================
-- Row Level Security (RLS) for multi-tenant isolation
-- ============================================================================
ALTER TABLE user_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_integration_scopes ENABLE ROW LEVEL SECURITY;

-- Policies for user_integrations
DROP POLICY IF EXISTS user_integrations_select_own ON user_integrations;
CREATE POLICY user_integrations_select_own ON user_integrations
    FOR SELECT USING (user_id = current_setting('app.current_user_id', true)::uuid);

DROP POLICY IF EXISTS user_integrations_insert_own ON user_integrations;
CREATE POLICY user_integrations_insert_own ON user_integrations
    FOR INSERT WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid);

DROP POLICY IF EXISTS user_integrations_update_own ON user_integrations;
CREATE POLICY user_integrations_update_own ON user_integrations
    FOR UPDATE USING (user_id = current_setting('app.current_user_id', true)::uuid);

DROP POLICY IF EXISTS user_integrations_delete_own ON user_integrations;
CREATE POLICY user_integrations_delete_own ON user_integrations
    FOR DELETE USING (user_id = current_setting('app.current_user_id', true)::uuid);

-- Policies for user_integration_scopes
DROP POLICY IF EXISTS user_integration_scopes_select_own ON user_integration_scopes;
CREATE POLICY user_integration_scopes_select_own ON user_integration_scopes
    FOR SELECT USING (user_id = current_setting('app.current_user_id', true)::uuid);

DROP POLICY IF EXISTS user_integration_scopes_insert_own ON user_integration_scopes;
CREATE POLICY user_integration_scopes_insert_own ON user_integration_scopes
    FOR INSERT WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid);

DROP POLICY IF EXISTS user_integration_scopes_update_own ON user_integration_scopes;
CREATE POLICY user_integration_scopes_update_own ON user_integration_scopes
    FOR UPDATE USING (user_id = current_setting('app.current_user_id', true)::uuid);

DROP POLICY IF EXISTS user_integration_scopes_delete_own ON user_integration_scopes;
CREATE POLICY user_integration_scopes_delete_own ON user_integration_scopes
    FOR DELETE USING (user_id = current_setting('app.current_user_id', true)::uuid);

-- ============================================================================
-- SEED DATA: Google Integrations
-- ============================================================================

-- Insert integrations
INSERT INTO integrations (id, provider, name, description, capability_summary, icon_url, is_active, display_order) VALUES
('gmail', 'google', 'Gmail', 'Connect your Gmail account', 'Read, modify and send emails', 'gmail', true, 1),
('calendar', 'google', 'Google Calendar', 'Access your calendar', 'View and manage calendar events', 'calendar', true, 2),
('contacts', 'google', 'Google Contacts', 'Access your contacts', 'View your contacts', 'contacts', true, 3),
('drive', 'google', 'Google Drive', 'Access your files', 'Browse and manage files', 'drive', true, 4),
('sheets', 'google', 'Google Sheets', 'Create and edit spreadsheets', 'Read and write spreadsheet data', 'sheets', true, 5),
('docs', 'google', 'Google Docs', 'Create and edit documents', 'Read and write documents', 'docs', true, 6),
('slides', 'google', 'Google Slides', 'Create and edit presentations', 'Read and write presentations', 'slides', true, 7)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    capability_summary = EXCLUDED.capability_summary,
    display_order = EXCLUDED.display_order;

-- Insert Gmail scopes
INSERT INTO integration_scopes (id, integration_id, scope_uri, name, description, is_required, display_order) VALUES
('gmail.readonly', 'gmail', 'https://www.googleapis.com/auth/gmail.readonly', 'Read emails', 'View your email messages and settings', true, 1),
('gmail.compose', 'gmail', 'https://www.googleapis.com/auth/gmail.compose', 'Compose emails', 'Create and send emails on your behalf', false, 2),
('gmail.modify', 'gmail', 'https://www.googleapis.com/auth/gmail.modify', 'Modify emails', 'Mark as read, archive, label, and delete emails', false, 3)
ON CONFLICT (id) DO UPDATE SET
    scope_uri = EXCLUDED.scope_uri,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_required = EXCLUDED.is_required;

-- Insert Calendar scopes
INSERT INTO integration_scopes (id, integration_id, scope_uri, name, description, is_required, display_order) VALUES
('calendar.readonly', 'calendar', 'https://www.googleapis.com/auth/calendar.readonly', 'View calendar', 'See your calendar events', true, 1),
('calendar.events', 'calendar', 'https://www.googleapis.com/auth/calendar.events', 'Manage events', 'Create, edit, and delete calendar events', false, 2),
('calendar.full', 'calendar', 'https://www.googleapis.com/auth/calendar', 'Full calendar access', 'Full access to your calendar', false, 3)
ON CONFLICT (id) DO UPDATE SET
    scope_uri = EXCLUDED.scope_uri,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_required = EXCLUDED.is_required;

-- Insert Contacts scopes
INSERT INTO integration_scopes (id, integration_id, scope_uri, name, description, is_required, display_order) VALUES
('contacts.readonly', 'contacts', 'https://www.googleapis.com/auth/contacts.readonly', 'View contacts', 'See your contacts', true, 1)
ON CONFLICT (id) DO UPDATE SET
    scope_uri = EXCLUDED.scope_uri,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_required = EXCLUDED.is_required;

-- Insert Drive scopes
INSERT INTO integration_scopes (id, integration_id, scope_uri, name, description, is_required, display_order) VALUES
('drive.readonly', 'drive', 'https://www.googleapis.com/auth/drive.readonly', 'View files', 'See your files in Google Drive', true, 1),
('drive.file', 'drive', 'https://www.googleapis.com/auth/drive.file', 'Manage files', 'Create and edit files you open with Yennifer', false, 2)
ON CONFLICT (id) DO UPDATE SET
    scope_uri = EXCLUDED.scope_uri,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_required = EXCLUDED.is_required;

-- Insert Sheets scopes
INSERT INTO integration_scopes (id, integration_id, scope_uri, name, description, is_required, display_order) VALUES
('sheets.readonly', 'sheets', 'https://www.googleapis.com/auth/spreadsheets.readonly', 'View spreadsheets', 'See your spreadsheet data', true, 1),
('sheets.full', 'sheets', 'https://www.googleapis.com/auth/spreadsheets', 'Edit spreadsheets', 'Read and write spreadsheet data', false, 2)
ON CONFLICT (id) DO UPDATE SET
    scope_uri = EXCLUDED.scope_uri,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_required = EXCLUDED.is_required;

-- Insert Docs scopes
INSERT INTO integration_scopes (id, integration_id, scope_uri, name, description, is_required, display_order) VALUES
('docs.readonly', 'docs', 'https://www.googleapis.com/auth/documents.readonly', 'View documents', 'See your document content', true, 1),
('docs.full', 'docs', 'https://www.googleapis.com/auth/documents', 'Edit documents', 'Read and write document content', false, 2)
ON CONFLICT (id) DO UPDATE SET
    scope_uri = EXCLUDED.scope_uri,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_required = EXCLUDED.is_required;

-- Insert Slides scopes
INSERT INTO integration_scopes (id, integration_id, scope_uri, name, description, is_required, display_order) VALUES
('slides.readonly', 'slides', 'https://www.googleapis.com/auth/presentations.readonly', 'View presentations', 'See your presentation content', true, 1),
('slides.full', 'slides', 'https://www.googleapis.com/auth/presentations', 'Edit presentations', 'Read and write presentation content', false, 2)
ON CONFLICT (id) DO UPDATE SET
    scope_uri = EXCLUDED.scope_uri,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_required = EXCLUDED.is_required;

