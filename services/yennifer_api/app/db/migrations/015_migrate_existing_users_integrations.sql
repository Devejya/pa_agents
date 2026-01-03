-- Migration: 015_migrate_existing_users_integrations
-- Description: Migrate existing users with OAuth tokens to have all integrations enabled
-- Date: 2026-01-03
--
-- This migration auto-enables all integrations for existing users who already have
-- Google OAuth tokens. These users consented to all scopes under the old flow,
-- so we mark all integrations and scopes as enabled AND granted.

-- Enable all Google integrations for users who have OAuth tokens
INSERT INTO user_integrations (user_id, integration_id, is_enabled, enabled_at)
SELECT DISTINCT 
    uot.user_id, 
    i.id,
    TRUE,
    NOW()
FROM user_oauth_tokens uot
CROSS JOIN integrations i
WHERE uot.user_id IS NOT NULL
  AND uot.provider = 'google'
  AND i.provider = 'google'
  AND i.is_active = TRUE
ON CONFLICT (user_id, integration_id) DO NOTHING;

-- Enable and mark as granted all Google scopes for users who have OAuth tokens
INSERT INTO user_integration_scopes (user_id, scope_id, is_enabled, is_granted, granted_at)
SELECT DISTINCT 
    uot.user_id, 
    iscope.id,
    TRUE,  -- is_enabled
    TRUE,  -- is_granted (they already have OAuth consent)
    NOW()  -- granted_at
FROM user_oauth_tokens uot
CROSS JOIN integration_scopes iscope
JOIN integrations i ON iscope.integration_id = i.id
WHERE uot.user_id IS NOT NULL
  AND uot.provider = 'google'
  AND i.provider = 'google'
  AND i.is_active = TRUE
ON CONFLICT (user_id, scope_id) DO NOTHING;

-- Log migration stats (optional - useful for monitoring)
DO $$
DECLARE
    migrated_users INT;
    enabled_integrations INT;
    enabled_scopes INT;
BEGIN
    SELECT COUNT(DISTINCT user_id) INTO migrated_users
    FROM user_oauth_tokens
    WHERE user_id IS NOT NULL AND provider = 'google';
    
    SELECT COUNT(*) INTO enabled_integrations FROM user_integrations WHERE is_enabled = TRUE;
    SELECT COUNT(*) INTO enabled_scopes FROM user_integration_scopes WHERE is_enabled = TRUE AND is_granted = TRUE;
    
    RAISE NOTICE 'Migration complete:';
    RAISE NOTICE '  - Users with Google tokens: %', migrated_users;
    RAISE NOTICE '  - User integrations enabled: %', enabled_integrations;
    RAISE NOTICE '  - User scopes enabled/granted: %', enabled_scopes;
END;
$$;

