"""
Repository for persons with RLS enforcement.

Provides database access to contacts/persons with Row-Level Security
automatically filtering by the authenticated user's owner_user_id.
"""

import json
import logging
from typing import Optional
from uuid import UUID

import asyncpg

from .connection import set_rls_user

logger = logging.getLogger(__name__)


class PersonsRepository:
    """
    Repository for persons with RLS enforcement.
    
    All queries automatically filter by owner_user_id via PostgreSQL RLS policies.
    The set_rls_user() call sets app.current_user_id which the RLS policy uses.
    """
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def list_contacts(
        self, 
        user_id: UUID, 
        limit: int = 100, 
        offset: int = 0
    ) -> list[dict]:
        """
        List contacts for user (RLS enforced via owner_user_id).
        
        Args:
            user_id: The authenticated user's UUID
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of contact dictionaries
        """
        async with self.pool.acquire() as conn:
            # Set RLS context - this is the key security mechanism
            await set_rls_user(conn, str(user_id))
            
            # RLS policy automatically filters to owner_user_id = user_id
            rows = await conn.fetch("""
                SELECT 
                    id,
                    first_name,
                    last_name,
                    middle_names,
                    name,
                    aliases,
                    is_core_user,
                    status,
                    work_email,
                    personal_email,
                    work_cell,
                    personal_cell,
                    secondary_cell,
                    company,
                    latest_title,
                    expertise,
                    address,
                    country,
                    city,
                    state,
                    instagram_handle,
                    interests,
                    created_at,
                    updated_at
                FROM persons 
                WHERE is_core_user = false  -- Exclude the user's own profile
                ORDER BY name
                LIMIT $1 OFFSET $2
            """, limit, offset)
            
            return [self._row_to_dict(row) for row in rows]
    
    async def get_core_user(self, user_id: UUID) -> Optional[dict]:
        """
        Get the authenticated user's core_user profile.
        
        Args:
            user_id: The authenticated user's UUID
            
        Returns:
            Core user dict or None if not found
        """
        async with self.pool.acquire() as conn:
            await set_rls_user(conn, str(user_id))
            
            row = await conn.fetchrow("""
                SELECT 
                    id,
                    first_name,
                    last_name,
                    middle_names,
                    name,
                    aliases,
                    is_core_user,
                    status,
                    work_email,
                    personal_email,
                    work_cell,
                    personal_cell,
                    secondary_cell,
                    company,
                    latest_title,
                    expertise,
                    address,
                    country,
                    city,
                    state,
                    instagram_handle,
                    interests,
                    created_at,
                    updated_at
                FROM persons 
                WHERE is_core_user = true
            """)
            
            return self._row_to_dict(row) if row else None
    
    async def get_contact(self, user_id: UUID, contact_id: UUID) -> Optional[dict]:
        """
        Get a specific contact by ID.
        
        Args:
            user_id: The authenticated user's UUID
            contact_id: The contact's UUID
            
        Returns:
            Contact dict or None if not found (or not owned by user)
        """
        async with self.pool.acquire() as conn:
            await set_rls_user(conn, str(user_id))
            
            row = await conn.fetchrow("""
                SELECT 
                    id,
                    first_name,
                    last_name,
                    middle_names,
                    name,
                    aliases,
                    is_core_user,
                    status,
                    work_email,
                    personal_email,
                    work_cell,
                    personal_cell,
                    secondary_cell,
                    company,
                    latest_title,
                    expertise,
                    address,
                    country,
                    city,
                    state,
                    instagram_handle,
                    interests,
                    created_at,
                    updated_at
                FROM persons 
                WHERE id = $1
            """, contact_id)
            
            return self._row_to_dict(row) if row else None
    
    async def search(self, user_id: UUID, query: str) -> list[dict]:
        """
        Search contacts with RLS.
        
        Uses full-text search on the persons search_vector.
        
        Args:
            user_id: The authenticated user's UUID
            query: Search query string
            
        Returns:
            List of matching contact dictionaries
        """
        async with self.pool.acquire() as conn:
            await set_rls_user(conn, str(user_id))
            
            rows = await conn.fetch("""
                SELECT 
                    id,
                    first_name,
                    last_name,
                    middle_names,
                    name,
                    aliases,
                    is_core_user,
                    status,
                    work_email,
                    personal_email,
                    work_cell,
                    personal_cell,
                    secondary_cell,
                    company,
                    latest_title,
                    expertise,
                    address,
                    country,
                    city,
                    state,
                    instagram_handle,
                    interests,
                    created_at,
                    updated_at,
                    ts_rank(search_vector, plainto_tsquery('english', $1)) as rank
                FROM persons 
                WHERE search_vector @@ plainto_tsquery('english', $1)
                  AND is_core_user = false
                ORDER BY rank DESC
                LIMIT 20
            """, query)
            
            return [self._row_to_dict(row) for row in rows]
    
    async def get_relationships(self, user_id: UUID, person_id: UUID) -> list[dict]:
        """
        Get relationships for a specific person.
        
        Args:
            user_id: The authenticated user's UUID
            person_id: The person's UUID to get relationships for
            
        Returns:
            List of relationship dictionaries
        """
        async with self.pool.acquire() as conn:
            await set_rls_user(conn, str(user_id))
            
            rows = await conn.fetch("""
                SELECT 
                    id,
                    from_person_id,
                    to_person_id,
                    category,
                    from_role,
                    to_role,
                    connection_counts,
                    similar_interests,
                    first_meeting_date,
                    length_of_relationship_years,
                    length_of_relationship_days,
                    is_active,
                    ended_at,
                    created_at,
                    updated_at
                FROM relationships 
                WHERE from_person_id = $1 OR to_person_id = $1
            """, person_id)
            
            return [self._relationship_to_dict(row) for row in rows]
    
    def _row_to_dict(self, row: asyncpg.Record) -> dict:
        """Convert a database row to a dictionary."""
        if row is None:
            return None
        
        result = dict(row)
        
        # Convert UUID to string for JSON serialization
        if result.get("id"):
            result["id"] = str(result["id"])
        
        # Convert datetime to ISO string
        if result.get("created_at"):
            result["created_at"] = result["created_at"].isoformat()
        if result.get("updated_at"):
            result["updated_at"] = result["updated_at"].isoformat()
        
        # Handle interests JSONB - ensure it's always a list
        interests = result.get("interests")
        if interests is None:
            result["interests"] = []
        elif isinstance(interests, str):
            # Handle case where asyncpg returns JSON as string
            try:
                parsed = json.loads(interests)
                result["interests"] = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                result["interests"] = []
        elif not isinstance(interests, list):
            # Handle unexpected types (e.g., dict, number)
            result["interests"] = []
        
        # Remove rank if present (from search results)
        result.pop("rank", None)
        
        return result
    
    def _relationship_to_dict(self, row: asyncpg.Record) -> dict:
        """Convert a relationship row to a dictionary."""
        if row is None:
            return None
        
        result = dict(row)
        
        # Convert UUIDs to strings
        for field in ["id", "from_person_id", "to_person_id"]:
            if result.get(field):
                result[field] = str(result[field])
        
        # Convert datetimes
        for field in ["first_meeting_date", "ended_at", "created_at", "updated_at"]:
            if result.get(field):
                result[field] = result[field].isoformat() if hasattr(result[field], 'isoformat') else str(result[field])
        
        return result

