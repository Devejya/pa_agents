"""
Repository layer for database operations.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import asyncpg

from .models import (
    ConnectionCounts,
    Interest,
    InterestCreate,
    Person,
    PersonCreate,
    PersonStatus,
    PersonUpdate,
    Relationship,
    RelationshipCategory,
    RelationshipCreate,
    RelationshipUpdate,
)

logger = logging.getLogger(__name__)


class PersonRepository:
    """Repository for person operations."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: PersonCreate) -> Person:
        """Create a new person."""
        person_id = uuid4()
        now = datetime.utcnow()
        
        # Convert interests to Interest models with IDs
        interests = [
            Interest(
                id=uuid4(),
                name=i.name,
                type=i.type,
                level=i.level,
                monthly_frequency=i.monthly_frequency,
                sample_instance=i.sample_instance,
                sample_instance_date=i.sample_instance_date,
            )
            for i in data.interests
        ]
        
        query = """
            INSERT INTO persons (
                id, name, aliases, is_core_user, status,
                work_email, personal_email, work_cell, personal_cell, secondary_cell,
                company, latest_title, expertise,
                address, country, city, state,
                instagram_handle, religion, ethnicity, country_of_birth, city_of_birth,
                interests, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13,
                $14, $15, $16, $17,
                $18, $19, $20, $21, $22,
                $23, $24, $25
            )
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                person_id,
                data.name,
                data.aliases,
                data.is_core_user,
                data.status.value,
                data.work_email,
                data.personal_email,
                data.work_cell,
                data.personal_cell,
                data.secondary_cell,
                data.company,
                data.latest_title,
                data.expertise,
                data.address,
                data.country,
                data.city,
                data.state,
                data.instagram_handle,
                data.religion,
                data.ethnicity,
                data.country_of_birth,
                data.city_of_birth,
                json.dumps([i.model_dump(mode="json") for i in interests]),
                now,
                now,
            )
            return self._row_to_person(row)

    async def get_by_id(self, person_id: UUID) -> Optional[Person]:
        """Get a person by ID."""
        query = "SELECT * FROM persons WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, person_id)
            return self._row_to_person(row) if row else None

    async def get_core_user(self) -> Optional[Person]:
        """Get the core user."""
        query = "SELECT * FROM persons WHERE is_core_user = TRUE LIMIT 1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            return self._row_to_person(row) if row else None

    async def find_by_name_or_alias(self, query_text: str) -> list[Person]:
        """Find persons by name or alias."""
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
            LIMIT 20
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, query_lower, f"%{query_lower}%")
            return [self._row_to_person(row) for row in rows]

    async def search(self, search_text: str) -> list[Person]:
        """Full-text search across persons."""
        query = """
            SELECT *, ts_rank(search_vector, query) AS rank
            FROM persons, plainto_tsquery('english', $1) query
            WHERE search_vector @@ query
            ORDER BY rank DESC
            LIMIT 20
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, search_text)
            return [self._row_to_person(row) for row in rows]

    async def update(self, person_id: UUID, data: PersonUpdate) -> Optional[Person]:
        """Update a person."""
        # Build dynamic update query
        updates = []
        values = [person_id]
        param_count = 1
        
        update_data = data.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            param_count += 1
            if field == "interests" and value is not None:
                # Convert interests
                interests = [
                    Interest(
                        id=uuid4(),
                        name=i["name"],
                        type=i["type"],
                        level=i["level"],
                        monthly_frequency=i.get("monthly_frequency"),
                        sample_instance=i.get("sample_instance"),
                        sample_instance_date=i.get("sample_instance_date"),
                    )
                    for i in value
                ]
                updates.append(f"{field} = ${param_count}")
                values.append(json.dumps([i.model_dump(mode="json") for i in interests]))
            elif field == "status" and value is not None:
                updates.append(f"{field} = ${param_count}")
                values.append(value.value if hasattr(value, "value") else value)
            else:
                updates.append(f"{field} = ${param_count}")
                values.append(value)
        
        if not updates:
            return await self.get_by_id(person_id)
        
        query = f"""
            UPDATE persons 
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            return self._row_to_person(row) if row else None

    async def add_interest(
        self, person_id: UUID, interest_name: str, interest_type: str, level: int
    ) -> Optional[Person]:
        """
        Atomically add an interest to a person.
        
        Uses PostgreSQL's JSONB concatenation to avoid race conditions
        when multiple interests are added in parallel.
        """
        interest_id = str(uuid4())
        interest_json = json.dumps({
            "id": interest_id,
            "name": interest_name,
            "type": interest_type,
            "level": level,
            "monthly_frequency": None,
            "sample_instance": None,
            "sample_instance_date": None,
        })
        
        # Atomic append using JSONB concatenation
        # Also checks if interest with same name exists and updates it instead
        query = """
            UPDATE persons 
            SET 
                interests = CASE
                    -- If interest with same name exists, update it
                    WHEN EXISTS (
                        SELECT 1 FROM jsonb_array_elements(interests) elem 
                        WHERE LOWER(elem->>'name') = LOWER($2)
                    ) THEN (
                        SELECT jsonb_agg(
                            CASE 
                                WHEN LOWER(elem->>'name') = LOWER($2) 
                                THEN jsonb_set(
                                    jsonb_set(elem, '{level}', to_jsonb($4::int)),
                                    '{type}', to_jsonb($3::text)
                                )
                                ELSE elem
                            END
                        )
                        FROM jsonb_array_elements(interests) elem
                    )
                    -- Otherwise append new interest
                    ELSE interests || $5::jsonb
                END,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query, 
                person_id, 
                interest_name,
                interest_type,
                level,
                interest_json
            )
            return self._row_to_person(row) if row else None

    async def delete(self, person_id: UUID) -> bool:
        """Delete a person."""
        query = "DELETE FROM persons WHERE id = $1 RETURNING id"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, person_id)
            return row is not None

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Person]:
        """List all persons with pagination."""
        query = """
            SELECT * FROM persons 
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)
            return [self._row_to_person(row) for row in rows]

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


class RelationshipRepository:
    """Repository for relationship operations."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: RelationshipCreate) -> Relationship:
        """Create a new relationship."""
        rel_id = uuid4()
        now = datetime.utcnow()
        connection_counts = ConnectionCounts()
        
        query = """
            INSERT INTO relationships (
                id, from_person_id, to_person_id,
                category, from_role, to_role,
                connection_counts, similar_interests,
                first_meeting_date, length_of_relationship_years,
                length_of_relationship_days,
                is_active, created_at, updated_at
            ) VALUES (
                $1, $2, $3,
                $4, $5, $6,
                $7, $8,
                $9, $10, $11,
                $12, $13, $14
            )
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                rel_id,
                data.from_person_id,
                data.to_person_id,
                data.category.value,
                data.from_role,
                data.to_role,
                json.dumps(connection_counts.model_dump(mode="json")),
                data.similar_interests,
                data.first_meeting_date,
                data.length_of_relationship_years,
                data.length_of_relationship_days,
                True,
                now,
                now,
            )
            return self._row_to_relationship(row)

    async def get_by_id(self, rel_id: UUID) -> Optional[Relationship]:
        """Get a relationship by ID."""
        query = "SELECT * FROM relationships WHERE id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, rel_id)
            return self._row_to_relationship(row) if row else None

    async def get_for_person(
        self, person_id: UUID, include_inactive: bool = False
    ) -> list[Relationship]:
        """Get all relationships for a person."""
        query = """
            SELECT * FROM relationships 
            WHERE (from_person_id = $1 OR to_person_id = $1)
        """
        if not include_inactive:
            query += " AND is_active = TRUE"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, person_id)
            return [self._row_to_relationship(row) for row in rows]

    async def update(
        self, rel_id: UUID, data: RelationshipUpdate
    ) -> Optional[Relationship]:
        """Update a relationship."""
        updates = []
        values = [rel_id]
        param_count = 1
        
        update_data = data.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            param_count += 1
            if field == "category" and value is not None:
                updates.append(f"{field} = ${param_count}")
                values.append(value.value if hasattr(value, "value") else value)
            else:
                updates.append(f"{field} = ${param_count}")
                values.append(value)
        
        if not updates:
            return await self.get_by_id(rel_id)
        
        query = f"""
            UPDATE relationships 
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            return self._row_to_relationship(row) if row else None

    async def end_relationship(self, rel_id: UUID) -> Optional[Relationship]:
        """Mark a relationship as ended."""
        query = """
            UPDATE relationships 
            SET is_active = FALSE, ended_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, rel_id)
            return self._row_to_relationship(row) if row else None

    async def delete(self, rel_id: UUID) -> bool:
        """Delete a relationship."""
        query = "DELETE FROM relationships WHERE id = $1 RETURNING id"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, rel_id)
            return row is not None

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

