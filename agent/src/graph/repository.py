"""
Repository layer for User Relationship Graph.

Handles all database operations for persons and relationships.
Designed for easy migration to Neptune/Neo4j.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import asyncpg

from .models import (
    AuditLog,
    ConnectionCounts,
    Interest,
    Person,
    PersonStatus,
    Relationship,
    RelationshipCategory,
)

logger = logging.getLogger(__name__)


class GraphRepository:
    """
    Repository for graph database operations.
    
    Uses PostgreSQL with graph-like query patterns.
    Designed for future migration to Neptune/Neo4j.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ========================================================================
    # Person Operations
    # ========================================================================

    async def create_person(self, person: Person, actor_id: str = "system") -> Person:
        """Create a new person node."""
        query = """
            INSERT INTO persons (
                id, name, aliases, is_core_user, status,
                work_email, personal_email, work_cell, personal_cell, secondary_cell,
                company, latest_title, expertise,
                address, country, city, state,
                instagram_handle, religion, ethnicity, country_of_birth, city_of_birth,
                interests
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13,
                $14, $15, $16, $17,
                $18, $19, $20, $21, $22,
                $23
            )
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                person.id,
                person.name,
                person.aliases,
                person.is_core_user,
                person.status.value,
                person.work_email,
                person.personal_email,
                person.work_cell,
                person.personal_cell,
                person.secondary_cell,
                person.company,
                person.latest_title,
                person.expertise,
                person.address,
                person.country,
                person.city,
                person.state,
                person.instagram_handle,
                person.religion,
                person.ethnicity,
                person.country_of_birth,
                person.city_of_birth,
                json.dumps([i.model_dump(mode="json") for i in person.interests]),
            )
            await self._log_audit(
                conn, actor_id, "write", "person", str(person.id), ["all"]
            )
            return self._row_to_person(row)

    async def get_person_by_id(
        self, person_id: UUID, actor_id: str = "system"
    ) -> Optional[Person]:
        """Get a person by their ID."""
        query = "SELECT * FROM persons WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, person_id)
            if row:
                await self._log_audit(
                    conn, actor_id, "read", "person", str(person_id), ["all"]
                )
                return self._row_to_person(row)
            return None

    async def get_core_user(self, actor_id: str = "system") -> Optional[Person]:
        """Get the core user."""
        query = "SELECT * FROM persons WHERE is_core_user = TRUE LIMIT 1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            if row:
                await self._log_audit(
                    conn, actor_id, "read", "person", str(row["id"]), ["all"]
                )
                return self._row_to_person(row)
            return None

    async def find_person_by_name_or_alias(
        self, query_text: str, actor_id: str = "system"
    ) -> list[Person]:
        """Find persons by name or alias (case-insensitive)."""
        query_lower = query_text.lower().strip()
        query = """
            SELECT * FROM persons 
            WHERE LOWER(name) = $1 
               OR $1 = ANY(aliases)
               OR LOWER(name) LIKE $2
            ORDER BY 
                CASE WHEN LOWER(name) = $1 THEN 0
                     WHEN $1 = ANY(aliases) THEN 1
                     ELSE 2
                END
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, query_lower, f"%{query_lower}%")
            persons = [self._row_to_person(row) for row in rows]
            for p in persons:
                await self._log_audit(
                    conn, actor_id, "read", "person", str(p.id), ["name", "aliases"]
                )
            return persons

    async def search_persons(
        self, search_text: str, actor_id: str = "system"
    ) -> list[Person]:
        """Full-text search across persons (name, aliases, expertise, interests)."""
        query = """
            SELECT *, ts_rank(search_vector, query) AS rank
            FROM persons, plainto_tsquery('english', $1) query
            WHERE search_vector @@ query
            ORDER BY rank DESC
            LIMIT 20
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, search_text)
            persons = [self._row_to_person(row) for row in rows]
            for p in persons:
                await self._log_audit(
                    conn, actor_id, "read", "person", str(p.id), ["search"]
                )
            return persons

    async def update_person(
        self, person: Person, actor_id: str = "system"
    ) -> Optional[Person]:
        """Update an existing person."""
        query = """
            UPDATE persons SET
                name = $2, aliases = $3, is_core_user = $4, status = $5,
                work_email = $6, personal_email = $7, work_cell = $8, 
                personal_cell = $9, secondary_cell = $10,
                company = $11, latest_title = $12, expertise = $13,
                address = $14, country = $15, city = $16, state = $17,
                instagram_handle = $18, religion = $19, ethnicity = $20, 
                country_of_birth = $21, city_of_birth = $22,
                interests = $23
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                person.id,
                person.name,
                person.aliases,
                person.is_core_user,
                person.status.value,
                person.work_email,
                person.personal_email,
                person.work_cell,
                person.personal_cell,
                person.secondary_cell,
                person.company,
                person.latest_title,
                person.expertise,
                person.address,
                person.country,
                person.city,
                person.state,
                person.instagram_handle,
                person.religion,
                person.ethnicity,
                person.country_of_birth,
                person.city_of_birth,
                json.dumps([i.model_dump(mode="json") for i in person.interests]),
            )
            if row:
                await self._log_audit(
                    conn, actor_id, "write", "person", str(person.id), ["all"]
                )
                return self._row_to_person(row)
            return None

    async def delete_person(self, person_id: UUID, actor_id: str = "system") -> bool:
        """Delete a person (cascades to relationships)."""
        query = "DELETE FROM persons WHERE id = $1 RETURNING id"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, person_id)
            if row:
                await self._log_audit(
                    conn, actor_id, "delete", "person", str(person_id), ["all"]
                )
                return True
            return False

    # ========================================================================
    # Relationship Operations
    # ========================================================================

    async def create_relationship(
        self, relationship: Relationship, actor_id: str = "system"
    ) -> Relationship:
        """Create a new relationship edge."""
        query = """
            INSERT INTO relationships (
                id, from_person_id, to_person_id,
                category, from_role, to_role,
                connection_counts, similar_interests,
                first_meeting_date, length_of_relationship_years, 
                length_of_relationship_days,
                is_active, ended_at
            ) VALUES (
                $1, $2, $3,
                $4, $5, $6,
                $7, $8,
                $9, $10, $11,
                $12, $13
            )
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                relationship.id,
                relationship.from_person_id,
                relationship.to_person_id,
                relationship.category.value,
                relationship.from_role,
                relationship.to_role,
                json.dumps(relationship.connection_counts.model_dump(mode="json")),
                relationship.similar_interests,
                relationship.first_meeting_date,
                relationship.length_of_relationship_years,
                relationship.length_of_relationship_days,
                relationship.is_active,
                relationship.ended_at,
            )
            await self._log_audit(
                conn, actor_id, "write", "relationship", str(relationship.id), ["all"]
            )
            return self._row_to_relationship(row)

    async def get_relationships_for_person(
        self, person_id: UUID, include_inactive: bool = False, actor_id: str = "system"
    ) -> list[Relationship]:
        """Get all relationships for a person (both directions)."""
        query = """
            SELECT * FROM relationships 
            WHERE (from_person_id = $1 OR to_person_id = $1)
        """
        if not include_inactive:
            query += " AND is_active = TRUE"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, person_id)
            relationships = [self._row_to_relationship(row) for row in rows]
            for r in relationships:
                await self._log_audit(
                    conn, actor_id, "read", "relationship", str(r.id), ["all"]
                )
            return relationships

    async def find_relationship_by_role(
        self,
        from_person_id: UUID,
        role: str,
        actor_id: str = "system",
    ) -> list[tuple[Person, Relationship]]:
        """
        Find persons related to from_person by role.
        E.g., find core user's "sister" or "manager".
        """
        role_lower = role.lower().strip()
        query = """
            SELECT p.*, r.id as rel_id, r.from_person_id, r.to_person_id,
                   r.category, r.from_role, r.to_role, r.connection_counts,
                   r.similar_interests, r.first_meeting_date,
                   r.length_of_relationship_years, r.length_of_relationship_days,
                   r.is_active, r.ended_at, r.created_at as rel_created_at,
                   r.updated_at as rel_updated_at
            FROM relationships r
            JOIN persons p ON r.to_person_id = p.id
            WHERE r.from_person_id = $1 
              AND LOWER(r.to_role) = $2
              AND r.is_active = TRUE
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, from_person_id, role_lower)
            results = []
            for row in rows:
                person = self._row_to_person(row)
                relationship = Relationship(
                    id=row["rel_id"],
                    from_person_id=row["from_person_id"],
                    to_person_id=row["to_person_id"],
                    category=RelationshipCategory(row["category"]),
                    from_role=row["from_role"],
                    to_role=row["to_role"],
                    connection_counts=ConnectionCounts(**json.loads(row["connection_counts"])),
                    similar_interests=row["similar_interests"],
                    first_meeting_date=row["first_meeting_date"],
                    length_of_relationship_years=row["length_of_relationship_years"],
                    length_of_relationship_days=row["length_of_relationship_days"],
                    is_active=row["is_active"],
                    ended_at=row["ended_at"],
                    created_at=row["rel_created_at"],
                    updated_at=row["rel_updated_at"],
                )
                results.append((person, relationship))
                await self._log_audit(
                    conn, actor_id, "read", "person", str(person.id), ["all"]
                )
            return results

    async def end_relationship(
        self, relationship_id: UUID, actor_id: str = "system"
    ) -> Optional[Relationship]:
        """Mark a relationship as ended (for history preservation)."""
        query = """
            UPDATE relationships 
            SET is_active = FALSE, ended_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, relationship_id)
            if row:
                await self._log_audit(
                    conn, actor_id, "write", "relationship", str(relationship_id), 
                    ["is_active", "ended_at"]
                )
                return self._row_to_relationship(row)
            return None

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _row_to_person(self, row: asyncpg.Record) -> Person:
        """Convert database row to Person model."""
        interests_data = row["interests"]
        if isinstance(interests_data, str):
            interests_data = json.loads(interests_data)
        
        interests = [Interest(**i) for i in interests_data] if interests_data else []
        
        return Person(
            id=row["id"],
            name=row["name"],
            aliases=row["aliases"] or [],
            is_core_user=row["is_core_user"],
            status=PersonStatus(row["status"]),
            work_email=row["work_email"],
            personal_email=row["personal_email"],
            work_cell=row["work_cell"],
            personal_cell=row["personal_cell"],
            secondary_cell=row["secondary_cell"],
            company=row["company"],
            latest_title=row["latest_title"],
            expertise=row["expertise"],
            address=row["address"],
            country=row["country"],
            city=row["city"],
            state=row["state"],
            instagram_handle=row["instagram_handle"],
            religion=row["religion"],
            ethnicity=row["ethnicity"],
            country_of_birth=row["country_of_birth"],
            city_of_birth=row["city_of_birth"],
            interests=interests,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_relationship(self, row: asyncpg.Record) -> Relationship:
        """Convert database row to Relationship model."""
        connection_counts_data = row["connection_counts"]
        if isinstance(connection_counts_data, str):
            connection_counts_data = json.loads(connection_counts_data)
        
        return Relationship(
            id=row["id"],
            from_person_id=row["from_person_id"],
            to_person_id=row["to_person_id"],
            category=RelationshipCategory(row["category"]),
            from_role=row["from_role"],
            to_role=row["to_role"],
            connection_counts=ConnectionCounts(**connection_counts_data),
            similar_interests=row["similar_interests"] or [],
            first_meeting_date=row["first_meeting_date"],
            length_of_relationship_years=row["length_of_relationship_years"],
            length_of_relationship_days=row["length_of_relationship_days"],
            is_active=row["is_active"],
            ended_at=row["ended_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def _log_audit(
        self,
        conn: asyncpg.Connection,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        fields: list[str],
    ) -> None:
        """Log an audit entry."""
        try:
            await conn.execute(
                """
                INSERT INTO audit_logs (actor_id, action, resource_type, resource_id, fields_accessed)
                VALUES ($1, $2, $3, $4, $5)
                """,
                actor_id,
                action,
                resource_type,
                resource_id,
                fields,
            )
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

