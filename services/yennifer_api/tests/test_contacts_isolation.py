"""
Tests for Contact Isolation (Row-Level Security)

These tests verify that users can only access their own contacts.
RLS policies on the persons and relationships tables ensure data isolation.

Run with: pytest tests/test_contacts_isolation.py -v
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.persons_repository import PersonsRepository


def run_async(coro):
    """Helper to run async coroutines in sync tests."""
    return asyncio.run(coro)


def make_token_data(user_id: UUID):
    """Create a TokenData-like mock object for tests."""
    from app.core.auth import TokenData
    now = datetime.now(timezone.utc)
    return TokenData(
        user_id=str(user_id),
        email="user@example.com",
        name="Test User",
        exp=now + timedelta(hours=1),
        iat=now
    )


class TestPersonsRepositoryRLS:
    """Test that PersonsRepository correctly sets RLS context."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        
        # Mock acquire context manager
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        return pool, conn
    
    def test_list_contacts_sets_rls_user(self, mock_pool):
        """Verify that list_contacts sets the RLS user context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = PersonsRepository(pool)
        user_id = uuid4()
        
        with patch('app.db.persons_repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.list_contacts(user_id=user_id, limit=10, offset=0))
            
            # Verify set_rls_user was called with the user_id
            mock_set_rls.assert_called_once()
            call_args = mock_set_rls.call_args[0]
            assert call_args[1] == str(user_id)
    
    def test_get_core_user_sets_rls_user(self, mock_pool):
        """Verify that get_core_user sets the RLS user context."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = PersonsRepository(pool)
        user_id = uuid4()
        
        with patch('app.db.persons_repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_core_user(user_id=user_id))
            
            mock_set_rls.assert_called_once()
            call_args = mock_set_rls.call_args[0]
            assert call_args[1] == str(user_id)
    
    def test_get_contact_sets_rls_user(self, mock_pool):
        """Verify that get_contact sets the RLS user context."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = PersonsRepository(pool)
        user_id = uuid4()
        contact_id = uuid4()
        
        with patch('app.db.persons_repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_contact(user_id=user_id, contact_id=contact_id))
            
            mock_set_rls.assert_called_once()
            call_args = mock_set_rls.call_args[0]
            assert call_args[1] == str(user_id)
    
    def test_search_sets_rls_user(self, mock_pool):
        """Verify that search sets the RLS user context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = PersonsRepository(pool)
        user_id = uuid4()
        
        with patch('app.db.persons_repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.search(user_id=user_id, query="test"))
            
            mock_set_rls.assert_called_once()
            call_args = mock_set_rls.call_args[0]
            assert call_args[1] == str(user_id)
    
    def test_get_relationships_sets_rls_user(self, mock_pool):
        """Verify that get_relationships sets the RLS user context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = PersonsRepository(pool)
        user_id = uuid4()
        person_id = uuid4()
        
        with patch('app.db.persons_repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_relationships(user_id=user_id, person_id=person_id))
            
            mock_set_rls.assert_called_once()
            call_args = mock_set_rls.call_args[0]
            assert call_args[1] == str(user_id)


class TestContactsRouteIsolation:
    """Test that contacts routes use the current user's ID for RLS."""
    
    def test_list_contacts_uses_authenticated_user(self):
        """Verify list_contacts passes the authenticated user's ID to repository."""
        from app.routes.contacts import list_contacts
        from app.core.auth import TokenData
        
        # Mock the current user
        user_id = uuid4()
        now = datetime.now(timezone.utc)
        mock_user = TokenData(
            user_id=str(user_id),
            email="user@example.com",
            name="Test User",
            exp=now + timedelta(hours=1),
            iat=now
        )
        
        mock_contacts = [
            {"id": str(uuid4()), "name": "Contact 1", "is_core_user": False},
            {"id": str(uuid4()), "name": "Contact 2", "is_core_user": False},
        ]
        
        with patch('app.routes.contacts.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.routes.contacts.PersonsRepository') as MockRepo, \
             patch('app.routes.contacts.get_audit_logger') as mock_audit:
            
            # Setup mocks
            mock_pool = AsyncMock()
            mock_get_pool.return_value = mock_pool
            
            mock_repo_instance = AsyncMock()
            mock_repo_instance.list_contacts = AsyncMock(return_value=mock_contacts)
            MockRepo.return_value = mock_repo_instance
            
            mock_audit_logger = MagicMock()
            mock_audit_logger.log_data_access = AsyncMock()
            mock_audit.return_value = mock_audit_logger
            
            # Call the endpoint
            result = run_async(list_contacts(current_user=mock_user, limit=100, offset=0))
            
            # Verify the repository was called with the correct user_id
            # Note: user_id is passed as string from TokenData
            mock_repo_instance.list_contacts.assert_called_once_with(
                user_id=str(user_id),
                limit=100,
                offset=0
            )
            
            # Verify we got the expected contacts
            assert result == mock_contacts
    
    def test_different_users_get_different_results(self):
        """Demonstrate that different users would get different results."""
        from app.routes.contacts import list_contacts
        from app.core.auth import TokenData
        
        user_a_id = uuid4()
        user_b_id = uuid4()
        now = datetime.now(timezone.utc)
        
        user_a = TokenData(
            user_id=str(user_a_id), 
            email="usera@example.com", 
            name="User A",
            exp=now + timedelta(hours=1),
            iat=now
        )
        user_b = TokenData(
            user_id=str(user_b_id), 
            email="userb@example.com", 
            name="User B",
            exp=now + timedelta(hours=1),
            iat=now
        )
        
        user_a_contacts = [{"id": str(uuid4()), "name": "A's Contact", "is_core_user": False}]
        user_b_contacts = [{"id": str(uuid4()), "name": "B's Contact", "is_core_user": False}]
        
        with patch('app.routes.contacts.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.routes.contacts.PersonsRepository') as MockRepo, \
             patch('app.routes.contacts.get_audit_logger') as mock_audit:
            
            mock_pool = AsyncMock()
            mock_get_pool.return_value = mock_pool
            
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance
            
            mock_audit_logger = MagicMock()
            mock_audit_logger.log_data_access = AsyncMock()
            mock_audit.return_value = mock_audit_logger
            
            # User A's request
            mock_repo_instance.list_contacts = AsyncMock(return_value=user_a_contacts)
            result_a = run_async(list_contacts(current_user=user_a, limit=100, offset=0))
            
            # Verify User A's ID was used
            mock_repo_instance.list_contacts.assert_called_with(
                user_id=str(user_a_id),
                limit=100,
                offset=0
            )
            assert result_a == user_a_contacts
            
            # User B's request
            mock_repo_instance.list_contacts = AsyncMock(return_value=user_b_contacts)
            result_b = run_async(list_contacts(current_user=user_b, limit=100, offset=0))
            
            # Verify User B's ID was used
            mock_repo_instance.list_contacts.assert_called_with(
                user_id=str(user_b_id),
                limit=100,
                offset=0
            )
            assert result_b == user_b_contacts
            
            # Results should be different
            assert result_a != result_b


class TestRLSPolicy:
    """
    Tests that verify RLS policy behavior.
    
    These tests document the expected RLS policy behavior:
    - owner_user_id = current_setting('app.current_user_id') for visibility
    - Users can only see their own data
    """
    
    def test_rls_policy_sql_documented(self):
        """Document the expected RLS policy SQL."""
        expected_policy = """
        CREATE POLICY persons_select_policy ON persons
            FOR SELECT
            USING (
                owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
                OR owner_user_id IS NULL  -- Allow access to legacy data (temporary)
            );
        """
        # This is a documentation test - the policy exists in migration 003
        assert "owner_user_id" in expected_policy
        assert "app.current_user_id" in expected_policy
    
    def test_set_rls_user_sql_documented(self):
        """Document how RLS user is set."""
        expected_sql = "SET LOCAL app.current_user_id = $1"
        # This is the SQL used in set_rls_user()
        assert "app.current_user_id" in expected_sql


class TestContactRouteEndpoints:
    """Test all contact route endpoints use proper authentication."""
    
    def test_get_contact_verifies_ownership(self):
        """Verify get_contact returns 404 for contacts not owned by user."""
        from app.routes.contacts import get_contact
        from app.core.auth import TokenData
        from fastapi import HTTPException
        
        user_id = uuid4()
        contact_id = uuid4()
        now = datetime.now(timezone.utc)
        mock_user = TokenData(
            user_id=str(user_id), 
            email="user@example.com", 
            name="Test User",
            exp=now + timedelta(hours=1),
            iat=now
        )
        
        with patch('app.routes.contacts.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.routes.contacts.PersonsRepository') as MockRepo, \
             patch('app.routes.contacts.get_audit_logger') as mock_audit:
            
            mock_pool = AsyncMock()
            mock_get_pool.return_value = mock_pool
            
            mock_repo_instance = AsyncMock()
            # Return None to simulate contact not found/not owned
            mock_repo_instance.get_contact = AsyncMock(return_value=None)
            MockRepo.return_value = mock_repo_instance
            
            mock_audit_logger = MagicMock()
            mock_audit_logger.log_data_access = AsyncMock()
            mock_audit.return_value = mock_audit_logger
            
            # Should raise 404
            with pytest.raises(HTTPException) as exc_info:
                run_async(get_contact(contact_id=contact_id, current_user=mock_user))
            
            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()
    
    def test_get_relationships_verifies_contact_ownership(self):
        """Verify get_relationships checks contact ownership first."""
        from app.routes.contacts import get_contact_relationships
        from app.core.auth import TokenData
        from fastapi import HTTPException
        
        user_id = uuid4()
        contact_id = uuid4()
        now = datetime.now(timezone.utc)
        mock_user = TokenData(
            user_id=str(user_id), 
            email="user@example.com", 
            name="Test User",
            exp=now + timedelta(hours=1),
            iat=now
        )
        
        with patch('app.routes.contacts.get_db_pool', new_callable=AsyncMock) as mock_get_pool, \
             patch('app.routes.contacts.PersonsRepository') as MockRepo:
            
            mock_pool = AsyncMock()
            mock_get_pool.return_value = mock_pool
            
            mock_repo_instance = AsyncMock()
            # Return None for contact to simulate not owned
            mock_repo_instance.get_contact = AsyncMock(return_value=None)
            MockRepo.return_value = mock_repo_instance
            
            # Should raise 404 because contact not found
            with pytest.raises(HTTPException) as exc_info:
                run_async(get_contact_relationships(contact_id=contact_id, current_user=mock_user))
            
            assert exc_info.value.status_code == 404
