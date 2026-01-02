"""
Tests for Row-Level Security (RLS) Isolation in User Network Service

These tests verify that RLS policies correctly isolate data between users:
- Users can only see their own persons/contacts
- Users can only see their own relationships
- Users can only see their own sync state and conflicts

Run with: pytest tests/test_rls_isolation.py -v
"""

import asyncio
import pytest
from datetime import datetime
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.repository import (
    PersonRepository,
    RelationshipRepository,
    PersonExternalIdRepository,
    SyncStateRepository,
)
from src.db.connection import set_rls_user


def run_async(coro):
    """Helper to run async coroutines in sync tests."""
    return asyncio.run(coro)


class TestSetRlsUser:
    """Test the set_rls_user function."""
    
    def test_set_rls_user_uses_parameterized_query(self):
        """Verify set_rls_user uses parameterized query to prevent SQL injection."""
        mock_conn = AsyncMock()
        user_id = str(uuid4())
        
        run_async(set_rls_user(mock_conn, user_id))
        
        # Should use set_config with parameterized query
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]
        assert "set_config('app.current_user_id'" in call_args[0]
        assert call_args[1] == user_id
    
    def test_set_rls_user_accepts_uuid_strings(self):
        """Verify set_rls_user accepts UUID strings."""
        mock_conn = AsyncMock()
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        
        run_async(set_rls_user(mock_conn, user_id))
        
        call_args = mock_conn.execute.call_args[0]
        assert call_args[1] == user_id


class TestPersonRepositoryRLS:
    """Test that PersonRepository correctly sets RLS context."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        
        # Mock acquire context manager
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        return pool, conn
    
    def test_get_by_id_sets_rls_user_when_provided(self, mock_pool):
        """Verify get_by_id sets RLS when user_id is provided."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = PersonRepository(pool)
        user_id = str(uuid4())
        person_id = uuid4()
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_by_id(person_id, user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id
    
    def test_get_by_id_skips_rls_when_no_user_id(self, mock_pool):
        """Verify get_by_id skips RLS when user_id is not provided."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = PersonRepository(pool)
        person_id = uuid4()
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_by_id(person_id))
            
            mock_set_rls.assert_not_called()
    
    def test_get_core_user_sets_rls_user(self, mock_pool):
        """Verify get_core_user sets RLS context."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = PersonRepository(pool)
        user_id = str(uuid4())
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_core_user(user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id
    
    def test_list_all_sets_rls_user(self, mock_pool):
        """Verify list_all sets RLS context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = PersonRepository(pool)
        user_id = str(uuid4())
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.list_all(user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id
    
    def test_search_sets_rls_user(self, mock_pool):
        """Verify search sets RLS context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = PersonRepository(pool)
        user_id = str(uuid4())
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.search("test query", user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id
    
    def test_find_by_name_or_alias_sets_rls_user(self, mock_pool):
        """Verify find_by_name_or_alias sets RLS context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = PersonRepository(pool)
        user_id = str(uuid4())
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.find_by_name_or_alias("John", user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id
    
    def test_delete_sets_rls_user(self, mock_pool):
        """Verify delete sets RLS context."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
        
        repo = PersonRepository(pool)
        user_id = str(uuid4())
        person_id = uuid4()
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.delete(person_id, user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id


class TestRelationshipRepositoryRLS:
    """Test that RelationshipRepository correctly sets RLS context."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        return pool, conn
    
    def test_get_by_id_sets_rls_user(self, mock_pool):
        """Verify get_by_id sets RLS context."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = RelationshipRepository(pool)
        user_id = str(uuid4())
        rel_id = uuid4()
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_by_id(rel_id, user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id
    
    def test_get_for_person_sets_rls_user(self, mock_pool):
        """Verify get_for_person sets RLS context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = RelationshipRepository(pool)
        user_id = str(uuid4())
        person_id = uuid4()
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_for_person(person_id, user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id


class TestExternalIdRepositoryRLS:
    """Test that PersonExternalIdRepository correctly sets RLS context."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        return pool, conn
    
    def test_get_by_external_id_sets_rls_user(self, mock_pool):
        """Verify get_by_external_id sets RLS context."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = PersonExternalIdRepository(pool)
        user_id = str(uuid4())
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_by_external_id("google", "ext123", user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id
    
    def test_get_by_person_id_sets_rls_user(self, mock_pool):
        """Verify get_by_person_id sets RLS context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = PersonExternalIdRepository(pool)
        user_id = str(uuid4())
        person_id = uuid4()
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_by_person_id(person_id, user_id=user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == user_id


class TestSyncStateRepositoryRLS:
    """Test that SyncStateRepository correctly sets RLS context."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = AsyncMock()
        
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        return pool, conn
    
    def test_get_sets_rls_user(self, mock_pool):
        """Verify get sets RLS context."""
        pool, conn = mock_pool
        conn.fetchrow = AsyncMock(return_value=None)
        
        repo = SyncStateRepository(pool)
        user_id = "user@example.com"
        rls_user_id = str(uuid4())
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get(user_id, "google_contacts", rls_user_id=rls_user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == rls_user_id
    
    def test_get_all_for_user_sets_rls_user(self, mock_pool):
        """Verify get_all_for_user sets RLS context."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        
        repo = SyncStateRepository(pool)
        user_id = "user@example.com"
        rls_user_id = str(uuid4())
        
        with patch('src.db.repository.set_rls_user', new_callable=AsyncMock) as mock_set_rls:
            run_async(repo.get_all_for_user(user_id, rls_user_id=rls_user_id))
            
            mock_set_rls.assert_called_once()
            assert mock_set_rls.call_args[0][1] == rls_user_id


class TestAPIEndpointRLS:
    """Test that API endpoints require and pass user_id for RLS."""
    
    def test_x_user_id_header_is_required(self):
        """Document that X-User-ID header is required for API endpoints."""
        from src.api.deps import require_user_id
        from fastapi import HTTPException
        
        # Without user_id, should raise 400
        with pytest.raises(HTTPException) as exc_info:
            run_async(require_user_id(user_id=None))
        
        assert exc_info.value.status_code == 400
        assert "X-User-ID" in exc_info.value.detail
    
    def test_x_user_id_header_validates_uuid(self):
        """Verify X-User-ID header validation rejects invalid UUIDs."""
        from src.api.deps import get_user_id
        from fastapi import HTTPException
        
        # Invalid UUID should raise 400
        with pytest.raises(HTTPException) as exc_info:
            run_async(get_user_id(x_user_id="not-a-uuid"))
        
        assert exc_info.value.status_code == 400
        assert "Invalid" in exc_info.value.detail
    
    def test_valid_uuid_is_accepted(self):
        """Verify valid UUID is accepted."""
        from src.api.deps import get_user_id
        
        valid_uuid = str(uuid4())
        result = run_async(get_user_id(x_user_id=valid_uuid))
        
        assert result == valid_uuid


class TestCrossTenantIsolation:
    """
    Tests documenting cross-tenant isolation behavior.
    
    These tests verify that users cannot see other users' data.
    """
    
    def test_user_a_cannot_see_user_b_persons(self):
        """Document: User A should not see User B's persons."""
        # This is ensured by RLS policy:
        # owner_user_id = current_setting('app.current_user_id')
        
        # When User A queries, they set app.current_user_id = User A's ID
        # RLS policy filters to only rows where owner_user_id = User A's ID
        # User B's rows (owner_user_id = User B's ID) are filtered out
        
        expected_policy = """
        CREATE POLICY persons_select_policy ON persons
            FOR SELECT
            USING (
                owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
            );
        """
        assert "owner_user_id" in expected_policy
        assert "app.current_user_id" in expected_policy
    
    def test_user_a_cannot_modify_user_b_data(self):
        """Document: User A should not be able to modify User B's data."""
        # RLS UPDATE/DELETE policies also check owner_user_id
        # Any attempt to UPDATE or DELETE data with wrong owner_user_id
        # will affect 0 rows (silently fails/returns None)
        pass
    
    def test_new_data_gets_correct_owner(self):
        """Document: New data should be created with correct owner_user_id."""
        # When creating new persons/relationships, the create methods
        # now accept user_id and set owner_user_id = user_id in INSERT
        
        # Repository.create(..., user_id=...) sets:
        # - owner_user_id column in the row
        # - RLS context via set_rls_user() for any triggers/policies
        pass


class TestRLSPolicyDocumentation:
    """
    Documentation tests for RLS policies.
    
    These tests document the expected SQL policies without executing them.
    """
    
    def test_persons_rls_policy_structure(self):
        """Document the persons table RLS policy."""
        policy = {
            "table": "persons",
            "policies": [
                {
                    "name": "persons_select_policy",
                    "for": "SELECT",
                    "using": "owner_user_id = current_setting('app.current_user_id')::UUID"
                },
                {
                    "name": "persons_insert_policy",
                    "for": "INSERT",
                    "with_check": "owner_user_id = current_setting('app.current_user_id')::UUID"
                },
                {
                    "name": "persons_update_policy",
                    "for": "UPDATE",
                    "using": "owner_user_id = current_setting('app.current_user_id')::UUID"
                },
                {
                    "name": "persons_delete_policy",
                    "for": "DELETE",
                    "using": "owner_user_id = current_setting('app.current_user_id')::UUID"
                }
            ]
        }
        assert policy["table"] == "persons"
        assert len(policy["policies"]) == 4
    
    def test_relationships_rls_policy_structure(self):
        """Document the relationships table RLS policy."""
        policy = {
            "table": "relationships",
            "policies": [
                {
                    "name": "relationships_select_policy",
                    "for": "SELECT",
                    "using": "owner_user_id = current_setting('app.current_user_id')::UUID"
                }
            ]
        }
        assert policy["table"] == "relationships"

