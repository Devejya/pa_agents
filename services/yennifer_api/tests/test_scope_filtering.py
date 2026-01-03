"""
Tests for Scope-Based User Filtering

These tests verify that:
1. IntegrationsRepository correctly filters users by granted scopes
2. Scheduled jobs use scope filtering to only process eligible users

Run with: pytest tests/test_scope_filtering.py -v
"""

import asyncio
import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.integrations_repository import IntegrationsRepository


def run_async(coro):
    """Helper to run async coroutines in sync tests."""
    return asyncio.run(coro)


class TestGetUsersWithScopeGranted:
    """Test the get_users_with_scope_granted repository method."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        
        # Mock acquire context manager
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        return pool, conn
    
    def test_returns_users_with_scope_granted(self, mock_pool):
        """Verify that users with is_granted=TRUE are returned."""
        pool, conn = mock_pool
        
        user1_id = uuid4()
        user2_id = uuid4()
        
        # Mock database response
        conn.fetch = AsyncMock(return_value=[
            {'id': user1_id, 'email': 'user1@example.com'},
            {'id': user2_id, 'email': 'user2@example.com'},
        ])
        
        repo = IntegrationsRepository(pool)
        result = run_async(repo.get_users_with_scope_granted('contacts.readonly'))
        
        # Verify correct SQL was executed
        conn.fetch.assert_called_once()
        call_args = conn.fetch.call_args
        sql = call_args[0][0]
        
        # SQL should join user_oauth_tokens and user_integration_scopes
        assert 'user_oauth_tokens' in sql
        assert 'user_integration_scopes' in sql
        assert 'is_granted = TRUE' in sql
        
        # Verify parameters
        params = call_args[0][1:]
        assert params[0] == 'google'  # provider
        assert params[1] == 'contacts.readonly'  # scope_id
        
        # Verify result
        assert len(result) == 2
        assert result[0]['email'] == 'user1@example.com'
        assert result[1]['email'] == 'user2@example.com'
    
    def test_returns_empty_list_when_no_users_have_scope(self, mock_pool):
        """Verify empty list returned when no users have the scope granted."""
        pool, conn = mock_pool
        
        conn.fetch = AsyncMock(return_value=[])
        
        repo = IntegrationsRepository(pool)
        result = run_async(repo.get_users_with_scope_granted('contacts.readonly'))
        
        assert result == []
    
    def test_filters_by_provider(self, mock_pool):
        """Verify that provider parameter is used in the query."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = IntegrationsRepository(pool)
        
        # Test with default provider
        run_async(repo.get_users_with_scope_granted('contacts.readonly'))
        default_call = conn.fetch.call_args
        assert default_call[0][1] == 'google'
        
        # Test with custom provider
        run_async(repo.get_users_with_scope_granted('some.scope', provider='microsoft'))
        custom_call = conn.fetch.call_args
        assert custom_call[0][1] == 'microsoft'
    
    def test_filters_by_scope_id(self, mock_pool):
        """Verify different scope IDs produce different queries."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = IntegrationsRepository(pool)
        
        # Test contacts scope
        run_async(repo.get_users_with_scope_granted('contacts.readonly'))
        call1 = conn.fetch.call_args
        assert call1[0][2] == 'contacts.readonly'
        
        # Test calendar scope
        run_async(repo.get_users_with_scope_granted('calendar.readonly'))
        call2 = conn.fetch.call_args
        assert call2[0][2] == 'calendar.readonly'


class TestUserHasScopeGranted:
    """Test the user_has_scope_granted repository method."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        return pool, conn
    
    def test_returns_true_when_scope_granted(self, mock_pool):
        """Verify returns True when user has the scope granted."""
        pool, conn = mock_pool
        user_id = uuid4()
        
        # Mock finding a row (scope is granted)
        conn.fetchrow = AsyncMock(return_value={'dummy': 1})
        
        repo = IntegrationsRepository(pool)
        result = run_async(repo.user_has_scope_granted(user_id, 'contacts.readonly'))
        
        assert result is True
    
    def test_returns_false_when_scope_not_granted(self, mock_pool):
        """Verify returns False when user doesn't have the scope granted."""
        pool, conn = mock_pool
        user_id = uuid4()
        
        # Mock not finding a row (scope not granted)
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = IntegrationsRepository(pool)
        result = run_async(repo.user_has_scope_granted(user_id, 'contacts.readonly'))
        
        assert result is False
    
    def test_checks_is_granted_flag(self, mock_pool):
        """Verify SQL checks is_granted = TRUE."""
        pool, conn = mock_pool
        user_id = uuid4()
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = IntegrationsRepository(pool)
        run_async(repo.user_has_scope_granted(user_id, 'contacts.readonly'))
        
        # Verify SQL includes is_granted check
        call_args = conn.fetchrow.call_args
        sql = call_args[0][0]
        assert 'is_granted = TRUE' in sql


class TestContactSyncScopeFiltering:
    """Test that contact_sync job uses scope filtering."""
    
    def test_get_users_due_for_sync_uses_scope_filter(self):
        """Verify get_users_due_for_sync filters by contacts.readonly scope."""
        import sys
        
        # Mock posthog before importing contact_sync
        sys.modules['posthog'] = MagicMock()
        
        from app.jobs.contact_sync import get_users_due_for_sync, REQUIRED_SCOPE
        
        # Verify the required scope constant
        assert REQUIRED_SCOPE == 'contacts.readonly'
        
        # Mock the repository and database
        mock_pool = MagicMock()
        mock_repo = AsyncMock()
        
        # Users with scope granted
        user1_id = uuid4()
        user2_id = uuid4()
        mock_repo.get_users_with_scope_granted = AsyncMock(return_value=[
            {'id': user1_id, 'email': 'user1@example.com'},
            {'id': user2_id, 'email': 'user2@example.com'},
        ])
        
        with patch('app.jobs.contact_sync.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.jobs.contact_sync.IntegrationsRepository') as MockRepo, \
             patch('app.jobs.contact_sync.get_google_tokens', new_callable=AsyncMock) as mock_tokens, \
             patch('app.jobs.contact_sync.get_user_network_client') as mock_client:
            
            mock_get_pool.return_value = mock_pool
            MockRepo.return_value = mock_repo
            
            # Mock tokens and sync state
            mock_tokens.return_value = {'access_token': 'test'}
            mock_client_instance = AsyncMock()
            mock_client_instance.get_sync_state = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance
            
            # Run the function
            result = run_async(get_users_due_for_sync())
            
            # Verify the repository was called with correct scope
            mock_repo.get_users_with_scope_granted.assert_called_once_with(
                REQUIRED_SCOPE,
                provider='google'
            )
    
    def test_returns_empty_when_no_users_have_scope(self):
        """Verify returns empty list when no users have contacts scope."""
        import sys
        
        # Mock posthog before importing contact_sync
        sys.modules['posthog'] = MagicMock()
        
        from app.jobs.contact_sync import get_users_due_for_sync
        
        mock_pool = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_users_with_scope_granted = AsyncMock(return_value=[])
        
        with patch('app.jobs.contact_sync.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.jobs.contact_sync.IntegrationsRepository') as MockRepo:
            
            mock_get_pool.return_value = mock_pool
            MockRepo.return_value = mock_repo
            
            result = run_async(get_users_due_for_sync())
            
            assert result == []


class TestTimezoneSyncScopeFiltering:
    """Test that timezone_sync job uses scope filtering."""
    
    def test_timezone_sync_required_scope(self):
        """Verify timezone_sync uses calendar.readonly scope."""
        from app.jobs.timezone_sync import REQUIRED_SCOPE
        
        assert REQUIRED_SCOPE == 'calendar.readonly'
    
    def test_sync_user_timezones_filters_by_scope(self):
        """Verify sync_user_timezones filters users by calendar.readonly scope."""
        from app.jobs.timezone_sync import sync_user_timezones
        
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_repo = AsyncMock()
        mock_user_repo = AsyncMock()
        
        # No users with scope
        mock_repo.get_users_with_scope_granted = AsyncMock(return_value=[])
        
        with patch('app.jobs.timezone_sync.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.jobs.timezone_sync.IntegrationsRepository') as MockIntRepo, \
             patch('app.jobs.timezone_sync.UserRepository') as MockUserRepo:
            
            mock_get_pool.return_value = mock_pool
            MockIntRepo.return_value = mock_repo
            MockUserRepo.return_value = mock_user_repo
            
            # Run the job
            run_async(sync_user_timezones())
            
            # Verify scope filtering was called with calendar.readonly
            mock_repo.get_users_with_scope_granted.assert_called_once_with(
                'calendar.readonly',
                provider='google'
            )


class TestScopeConstants:
    """Test that scope constants are correctly defined."""
    
    def test_contact_sync_scope(self):
        """Verify contact_sync uses contacts.readonly scope."""
        import sys
        
        # Mock posthog before importing contact_sync
        sys.modules['posthog'] = MagicMock()
        
        from app.jobs.contact_sync import REQUIRED_SCOPE
        assert REQUIRED_SCOPE == 'contacts.readonly'
    
    def test_timezone_sync_scope(self):
        """Verify timezone_sync uses calendar.readonly scope."""
        from app.jobs.timezone_sync import REQUIRED_SCOPE
        assert REQUIRED_SCOPE == 'calendar.readonly'


# =============================================================================
# Integration Tests
# =============================================================================

class TestContactSyncSchedulerIntegration:
    """
    Integration tests for contact_sync_scheduler job.
    
    Tests the full scheduler flow with various scope configurations.
    """
    
    def test_scheduler_skips_users_without_contacts_scope(self):
        """
        Integration test: Users without contacts.readonly scope are skipped.
        
        Scenario:
        - User A has contacts.readonly scope granted
        - User B does NOT have contacts.readonly scope
        - Only User A should be synced
        """
        import sys
        sys.modules['posthog'] = MagicMock()
        
        from app.jobs.contact_sync import contact_sync_scheduler
        
        user_a_id = uuid4()
        
        # Mock repo returns only User A (has scope)
        mock_pool = MagicMock()
        mock_repo = AsyncMock()
        mock_repo.get_users_with_scope_granted = AsyncMock(return_value=[
            {'id': user_a_id, 'email': 'usera@example.com'},
            # User B is NOT returned because they don't have the scope
        ])
        
        mock_sync_result = {
            'success': True,
            'skipped': False,
            'added': 5,
            'updated': 2,
            'conflicts': 0,
            'errors': [],
            'duration_ms': 100,
        }
        
        with patch('app.jobs.contact_sync.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.jobs.contact_sync.IntegrationsRepository') as MockRepo, \
             patch('app.jobs.contact_sync.sync_user_contacts', new_callable=AsyncMock) as mock_sync, \
             patch('app.jobs.contact_sync.get_google_tokens', new_callable=AsyncMock) as mock_tokens, \
             patch('app.jobs.contact_sync.get_user_network_client') as mock_client:
            
            mock_get_pool.return_value = mock_pool
            MockRepo.return_value = mock_repo
            mock_sync.return_value = mock_sync_result
            mock_tokens.return_value = {'access_token': 'test'}
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get_sync_state = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance
            
            # Run the scheduler
            result = run_async(contact_sync_scheduler())
            
            # Verify only User A was synced
            assert result['synced'] == 1
            assert result['failed'] == 0
            
            # Verify sync was called only for User A
            mock_sync.assert_called_once_with('usera@example.com')
    
    def test_scheduler_completes_successfully_with_no_eligible_users(self):
        """
        Integration test: Scheduler completes gracefully when no users have scope.
        """
        import sys
        sys.modules['posthog'] = MagicMock()
        
        from app.jobs.contact_sync import contact_sync_scheduler
        
        mock_pool = MagicMock()
        mock_repo = AsyncMock()
        # No users have the contacts scope
        mock_repo.get_users_with_scope_granted = AsyncMock(return_value=[])
        
        with patch('app.jobs.contact_sync.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.jobs.contact_sync.IntegrationsRepository') as MockRepo:
            
            mock_get_pool.return_value = mock_pool
            MockRepo.return_value = mock_repo
            
            # Run the scheduler
            result = run_async(contact_sync_scheduler())
            
            # Should complete successfully with zero synced
            assert result['synced'] == 0
            assert result['skipped'] == 0
            assert result['failed'] == 0


class TestTimezoneSyncIntegration:
    """Integration tests for timezone_sync job."""
    
    def test_timezone_sync_filters_users_by_scope(self):
        """
        Integration test: Only users with calendar.readonly scope are synced.
        """
        from app.jobs.timezone_sync import sync_user_timezones
        
        user_a_id = uuid4()
        
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # User A has calendar scope and different timezone
        mock_conn.fetch = AsyncMock(return_value=[
            {'id': user_a_id, 'email': 'usera@example.com', 'current_tz': 'UTC'},
        ])
        
        mock_integrations_repo = AsyncMock()
        mock_integrations_repo.get_users_with_scope_granted = AsyncMock(return_value=[
            {'id': user_a_id, 'email': 'usera@example.com'},
        ])
        
        mock_user_repo = AsyncMock()
        mock_user_repo.update_user_timezone = AsyncMock()
        
        with patch('app.jobs.timezone_sync.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.jobs.timezone_sync.IntegrationsRepository') as MockIntRepo, \
             patch('app.jobs.timezone_sync.UserRepository') as MockUserRepo, \
             patch('app.jobs.timezone_sync.load_user_tokens', new_callable=AsyncMock) as mock_load_tokens, \
             patch('app.jobs.timezone_sync.get_user_calendar_timezone') as mock_get_tz:
            
            mock_get_pool.return_value = mock_pool
            MockIntRepo.return_value = mock_integrations_repo
            MockUserRepo.return_value = mock_user_repo
            mock_load_tokens.return_value = {'access_token': 'test'}
            mock_get_tz.return_value = 'America/Los_Angeles'
            
            # Run the job
            run_async(sync_user_timezones())
            
            # Verify scope filtering was called
            mock_integrations_repo.get_users_with_scope_granted.assert_called_once_with(
                'calendar.readonly',
                provider='google'
            )
            
            # Verify timezone was updated for User A
            mock_user_repo.update_user_timezone.assert_called_once_with(
                user_a_id, 'America/Los_Angeles'
            )
    
    def test_timezone_sync_skips_when_no_users_have_scope(self):
        """
        Integration test: Job completes gracefully when no users have calendar scope.
        """
        from app.jobs.timezone_sync import sync_user_timezones
        
        mock_pool = MagicMock()
        mock_integrations_repo = AsyncMock()
        mock_integrations_repo.get_users_with_scope_granted = AsyncMock(return_value=[])
        
        mock_user_repo = AsyncMock()
        
        with patch('app.jobs.timezone_sync.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.jobs.timezone_sync.IntegrationsRepository') as MockIntRepo, \
             patch('app.jobs.timezone_sync.UserRepository') as MockUserRepo:
            
            mock_get_pool.return_value = mock_pool
            MockIntRepo.return_value = mock_integrations_repo
            MockUserRepo.return_value = mock_user_repo
            
            # Run the job - should complete without error
            run_async(sync_user_timezones())
            
            # Verify no timezone updates were attempted
            mock_user_repo.update_user_timezone.assert_not_called()

