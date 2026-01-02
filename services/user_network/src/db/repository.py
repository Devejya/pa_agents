"""
Repository layer for database operations.

All repository methods that access RLS-protected tables require a user_id parameter.
The user_id is used to set the PostgreSQL session variable `app.current_user_id`,
which the RLS policies use to filter rows by owner_user_id.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import asyncpg

from .connection import set_rls_user
from .models import (
    ConnectionCounts,
    ConflictStatus,
    ExternalIdSyncStatus,
    Interest,
    InterestCreate,
    Person,
    PersonCreate,
    PersonExternalId,
    PersonExternalIdCreate,
    PersonStatus,
    PersonUpdate,
    Relationship,
    RelationshipCategory,
    RelationshipCreate,
    RelationshipUpdate,
    ResolutionType,
    SyncConflict,
    SyncConflictCreate,
    SyncLog,
    SyncLogCreate,
    SyncLogUpdate,
    SyncProvider,
    SyncState,
    SyncStateCreate,
    SyncStateUpdate,
    SyncStatus,
)

logger = logging.getLogger(__name__)


class PersonRepository:
    """Repository for person operations with RLS enforcement."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: PersonCreate, user_id: Optional[str] = None) -> Person:
        """
        Create a new person.
        
        Args:
            data: Person creation data
            user_id: User ID for RLS context (required for RLS-protected inserts)
        """
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
                id, first_name, last_name, middle_names, name,
                aliases, is_core_user, status,
                work_email, personal_email, work_cell, personal_cell, secondary_cell,
                company, latest_title, expertise,
                address, country, city, state,
                instagram_handle, religion, ethnicity, country_of_birth, city_of_birth,
                date_of_birth, interests, created_at, updated_at, owner_user_id
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9, $10, $11, $12, $13,
                $14, $15, $16,
                $17, $18, $19, $20,
                $21, $22, $23, $24, $25,
                $26, $27, $28, $29, $30
            )
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(
                query,
                person_id,
                data.first_name,
                data.last_name,
                data.middle_names,
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
                data.date_of_birth,
                json.dumps([i.model_dump(mode="json") for i in interests]),
                now,
                now,
                UUID(user_id) if user_id else None,
            )
            return self._row_to_person(row)

    async def get_by_id(self, person_id: UUID, user_id: Optional[str] = None) -> Optional[Person]:
        """
        Get a person by ID.
        
        Args:
            person_id: The person's UUID
            user_id: User ID for RLS context (filters to only this user's data)
        """
        query = "SELECT * FROM persons WHERE id = $1"
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, person_id)
            return self._row_to_person(row) if row else None

    async def get_core_user(self, user_id: Optional[str] = None) -> Optional[Person]:
        """
        Get the core user.
        
        Args:
            user_id: User ID for RLS context (filters to only this user's core user)
        """
        query = "SELECT * FROM persons WHERE is_core_user = TRUE LIMIT 1"
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query)
            return self._row_to_person(row) if row else None

    async def find_by_name_or_alias(self, query_text: str, user_id: Optional[str] = None) -> list[Person]:
        """
        Find persons by name or alias.
        
        Args:
            query_text: Name or alias to search for
            user_id: User ID for RLS context
        """
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
            if user_id:
                await set_rls_user(conn, user_id)
            rows = await conn.fetch(query, query_lower, f"%{query_lower}%")
            return [self._row_to_person(row) for row in rows]

    async def search(self, search_text: str, user_id: Optional[str] = None) -> list[Person]:
        """
        Full-text search across persons.
        
        Args:
            search_text: Text to search for
            user_id: User ID for RLS context
        """
        query = """
            SELECT *, ts_rank(search_vector, query) AS rank
            FROM persons, plainto_tsquery('english', $1) query
            WHERE search_vector @@ query
            ORDER BY rank DESC
            LIMIT 20
        """
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            rows = await conn.fetch(query, search_text)
            return [self._row_to_person(row) for row in rows]

    async def update(self, person_id: UUID, data: PersonUpdate, user_id: Optional[str] = None) -> Optional[Person]:
        """
        Update a person.
        
        Args:
            person_id: The person's UUID
            data: Update data
            user_id: User ID for RLS context
        """
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
            return await self.get_by_id(person_id, user_id)
        
        query = f"""
            UPDATE persons 
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, *values)
            return self._row_to_person(row) if row else None

    async def add_interest(
        self, person_id: UUID, interest_name: str, interest_type: str, level: int,
        user_id: Optional[str] = None
    ) -> Optional[Person]:
        """
        Atomically add an interest to a person.
        
        Uses PostgreSQL's JSONB concatenation to avoid race conditions
        when multiple interests are added in parallel.
        
        Args:
            person_id: The person's UUID
            interest_name: Name of the interest
            interest_type: Type of interest
            level: Interest level (0-100)
            user_id: User ID for RLS context
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
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(
                query, 
                person_id, 
                interest_name,
                interest_type,
                level,
                interest_json
            )
            return self._row_to_person(row) if row else None

    async def delete(self, person_id: UUID, user_id: Optional[str] = None) -> bool:
        """
        Delete a person.
        
        Args:
            person_id: The person's UUID
            user_id: User ID for RLS context
        """
        query = "DELETE FROM persons WHERE id = $1 RETURNING id"
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, person_id)
            return row is not None

    async def list_all(self, limit: int = 100, offset: int = 0, user_id: Optional[str] = None) -> list[Person]:
        """
        List all persons with pagination.
        
        Args:
            limit: Maximum number of results
            offset: Pagination offset
            user_id: User ID for RLS context
        """
        query = """
            SELECT * FROM persons 
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            rows = await conn.fetch(query, limit, offset)
            return [self._row_to_person(row) for row in rows]

    def _row_to_person(self, row: asyncpg.Record) -> Person:
        """Convert database row to Person model."""
        interests_data = row["interests"]
        if isinstance(interests_data, str):
            interests_data = json.loads(interests_data)
        
        interests = [Interest(**i) for i in interests_data] if interests_data else []
        
        # Handle backward compatibility: if first_name is None, derive from name
        first_name = row.get("first_name")
        if not first_name and row.get("name"):
            name_parts = row["name"].split()
            first_name = name_parts[0] if name_parts else ""
        
        return Person(
            id=row["id"],
            first_name=first_name or "",
            last_name=row.get("last_name"),
            middle_names=row.get("middle_names"),
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
            date_of_birth=row.get("date_of_birth"),
            interests=interests,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class RelationshipRepository:
    """Repository for relationship operations with RLS enforcement."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: RelationshipCreate, user_id: Optional[str] = None) -> Relationship:
        """
        Create a new relationship.
        
        Args:
            data: Relationship creation data
            user_id: User ID for RLS context
        """
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
                is_active, created_at, updated_at, owner_user_id
            ) VALUES (
                $1, $2, $3,
                $4, $5, $6,
                $7, $8,
                $9, $10, $11,
                $12, $13, $14, $15
            )
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
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
                UUID(user_id) if user_id else None,
            )
            return self._row_to_relationship(row)

    async def get_by_id(self, rel_id: UUID, user_id: Optional[str] = None) -> Optional[Relationship]:
        """
        Get a relationship by ID.
        
        Args:
            rel_id: The relationship's UUID
            user_id: User ID for RLS context
        """
        query = "SELECT * FROM relationships WHERE id = $1"
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, rel_id)
            return self._row_to_relationship(row) if row else None

    async def get_for_person(
        self, person_id: UUID, include_inactive: bool = False, user_id: Optional[str] = None
    ) -> list[Relationship]:
        """
        Get all relationships for a person.
        
        Args:
            person_id: The person's UUID
            include_inactive: Whether to include inactive relationships
            user_id: User ID for RLS context
        """
        query = """
            SELECT * FROM relationships 
            WHERE (from_person_id = $1 OR to_person_id = $1)
        """
        if not include_inactive:
            query += " AND is_active = TRUE"
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            rows = await conn.fetch(query, person_id)
            return [self._row_to_relationship(row) for row in rows]

    async def update(
        self, rel_id: UUID, data: RelationshipUpdate, user_id: Optional[str] = None
    ) -> Optional[Relationship]:
        """
        Update a relationship.
        
        Args:
            rel_id: The relationship's UUID
            data: Update data
            user_id: User ID for RLS context
        """
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
            return await self.get_by_id(rel_id, user_id)
        
        query = f"""
            UPDATE relationships 
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, *values)
            return self._row_to_relationship(row) if row else None

    async def end_relationship(self, rel_id: UUID, user_id: Optional[str] = None) -> Optional[Relationship]:
        """
        Mark a relationship as ended.
        
        Args:
            rel_id: The relationship's UUID
            user_id: User ID for RLS context
        """
        query = """
            UPDATE relationships 
            SET is_active = FALSE, ended_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, rel_id)
            return self._row_to_relationship(row) if row else None

    async def delete(self, rel_id: UUID, user_id: Optional[str] = None) -> bool:
        """
        Delete a relationship.
        
        Args:
            rel_id: The relationship's UUID
            user_id: User ID for RLS context
        """
        query = "DELETE FROM relationships WHERE id = $1 RETURNING id"
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
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


# ============================================================================
# Person External ID Repository
# ============================================================================

class PersonExternalIdRepository:
    """Repository for person external ID operations (for multi-platform sync) with RLS enforcement."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: PersonExternalIdCreate, user_id: Optional[str] = None) -> PersonExternalId:
        """
        Create a new external ID mapping.
        
        Args:
            data: External ID creation data
            user_id: User ID for RLS context
        """
        ext_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO person_external_ids (
                id, person_id, provider, external_id, external_metadata,
                last_synced_at, sync_status, created_at, updated_at, owner_user_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(
                query,
                ext_id,
                data.person_id,
                data.provider.value,
                data.external_id,
                json.dumps(data.external_metadata),
                now,
                ExternalIdSyncStatus.SYNCED.value,
                now,
                now,
                UUID(user_id) if user_id else None,
            )
            return self._row_to_external_id(row)

    async def get_by_external_id(
        self, provider: str, external_id: str, user_id: Optional[str] = None
    ) -> Optional[PersonExternalId]:
        """
        Find by provider and external ID.
        
        Args:
            provider: The sync provider name
            external_id: The external system's ID
            user_id: User ID for RLS context
        """
        query = """
            SELECT * FROM person_external_ids 
            WHERE provider = $1 AND external_id = $2
        """
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, provider, external_id)
            return self._row_to_external_id(row) if row else None

    async def get_by_person_id(
        self, person_id: UUID, provider: Optional[str] = None, user_id: Optional[str] = None
    ) -> list[PersonExternalId]:
        """
        Get all external IDs for a person.
        
        Args:
            person_id: The person's UUID
            provider: Optional provider to filter by
            user_id: User ID for RLS context
        """
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            if provider:
                query = """
                    SELECT * FROM person_external_ids 
                    WHERE person_id = $1 AND provider = $2
                """
                rows = await conn.fetch(query, person_id, provider)
            else:
                query = "SELECT * FROM person_external_ids WHERE person_id = $1"
                rows = await conn.fetch(query, person_id)
            return [self._row_to_external_id(row) for row in rows]

    async def update_sync_status(
        self, id: UUID, status: ExternalIdSyncStatus, metadata: Optional[dict] = None,
        user_id: Optional[str] = None
    ) -> Optional[PersonExternalId]:
        """
        Update sync status and optionally metadata.
        
        Args:
            id: The external ID record's UUID
            status: New sync status
            metadata: Optional metadata to update
            user_id: User ID for RLS context
        """
        now = datetime.utcnow()
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            if metadata:
                query = """
                    UPDATE person_external_ids 
                    SET sync_status = $2, external_metadata = $3, 
                        last_synced_at = $4, updated_at = $4
                    WHERE id = $1
                    RETURNING *
                """
                row = await conn.fetchrow(query, id, status.value, json.dumps(metadata), now)
            else:
                query = """
                    UPDATE person_external_ids 
                    SET sync_status = $2, last_synced_at = $3, updated_at = $3
                    WHERE id = $1
                    RETURNING *
                """
                row = await conn.fetchrow(query, id, status.value, now)
            
            return self._row_to_external_id(row) if row else None

    async def upsert(
        self, person_id: UUID, provider: str, external_id: str, metadata: dict = None,
        user_id: Optional[str] = None
    ) -> PersonExternalId:
        """
        Insert or update an external ID mapping.
        
        Args:
            person_id: The person's UUID
            provider: The sync provider name
            external_id: The external system's ID
            metadata: Optional metadata
            user_id: User ID for RLS context
        """
        now = datetime.utcnow()
        new_id = uuid4()
        
        query = """
            INSERT INTO person_external_ids (
                id, person_id, provider, external_id, external_metadata,
                last_synced_at, sync_status, created_at, updated_at, owner_user_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (provider, external_id) 
            DO UPDATE SET 
                person_id = EXCLUDED.person_id,
                external_metadata = EXCLUDED.external_metadata,
                last_synced_at = EXCLUDED.last_synced_at,
                sync_status = $7,
                updated_at = EXCLUDED.updated_at
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(
                query,
                new_id,
                person_id,
                provider,
                external_id,
                json.dumps(metadata or {}),
                now,
                ExternalIdSyncStatus.SYNCED.value,
                now,
                now,
                UUID(user_id) if user_id else None,
            )
            return self._row_to_external_id(row)

    async def delete(self, id: UUID, user_id: Optional[str] = None) -> bool:
        """
        Delete an external ID mapping.
        
        Args:
            id: The external ID record's UUID
            user_id: User ID for RLS context
        """
        query = "DELETE FROM person_external_ids WHERE id = $1 RETURNING id"
        async with self.pool.acquire() as conn:
            if user_id:
                await set_rls_user(conn, user_id)
            row = await conn.fetchrow(query, id)
            return row is not None

    def _row_to_external_id(self, row: asyncpg.Record) -> PersonExternalId:
        """Convert database row to PersonExternalId model."""
        metadata = row["external_metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        return PersonExternalId(
            id=row["id"],
            person_id=row["person_id"],
            provider=SyncProvider(row["provider"]),
            external_id=row["external_id"],
            external_metadata=metadata or {},
            last_synced_at=row["last_synced_at"],
            sync_status=ExternalIdSyncStatus(row["sync_status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ============================================================================
# Sync State Repository
# ============================================================================

class SyncStateRepository:
    """Repository for sync state operations with RLS enforcement."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_or_create(self, user_id: str, provider: str, rls_user_id: Optional[str] = None) -> SyncState:
        """
        Get sync state for user/provider, creating if needed.
        
        Args:
            user_id: The user ID this sync state belongs to
            provider: The sync provider name
            rls_user_id: User ID for RLS context (defaults to user_id if not provided)
        """
        rls_id = rls_user_id or user_id
        state = await self.get(user_id, provider, rls_user_id=rls_id)
        if state:
            return state
        return await self.create(SyncStateCreate(user_id=user_id, provider=provider), rls_user_id=rls_id)

    async def create(self, data: SyncStateCreate, rls_user_id: Optional[str] = None) -> SyncState:
        """
        Create a new sync state.
        
        Args:
            data: Sync state creation data
            rls_user_id: User ID for RLS context
        """
        state_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO sync_state (
                id, user_id, provider, sync_status, created_at, updated_at, owner_user_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            row = await conn.fetchrow(
                query,
                state_id,
                data.user_id,
                data.provider,
                SyncStatus.IDLE.value,
                now,
                now,
                UUID(rls_user_id) if rls_user_id else None,
            )
            return self._row_to_sync_state(row)

    async def get(self, user_id: str, provider: str, rls_user_id: Optional[str] = None) -> Optional[SyncState]:
        """
        Get sync state for a user and provider.
        
        Args:
            user_id: The user ID this sync state belongs to
            provider: The sync provider name
            rls_user_id: User ID for RLS context
        """
        query = "SELECT * FROM sync_state WHERE user_id = $1 AND provider = $2"
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            row = await conn.fetchrow(query, user_id, provider)
            return self._row_to_sync_state(row) if row else None

    async def get_all_for_user(self, user_id: str, rls_user_id: Optional[str] = None) -> list[SyncState]:
        """
        Get all sync states for a user.
        
        Args:
            user_id: The user ID to get sync states for
            rls_user_id: User ID for RLS context
        """
        query = "SELECT * FROM sync_state WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            rows = await conn.fetch(query, user_id)
            return [self._row_to_sync_state(row) for row in rows]

    async def get_pending_syncs(self, limit: int = 100, rls_user_id: Optional[str] = None) -> list[SyncState]:
        """
        Get sync states that are due for sync.
        
        Note: When rls_user_id is provided, this only returns pending syncs for that user.
        For background jobs that need cross-tenant access, omit rls_user_id.
        
        Args:
            limit: Maximum number of results
            rls_user_id: User ID for RLS context (optional for background jobs)
        """
        query = """
            SELECT * FROM sync_state 
            WHERE sync_status = 'idle' 
            AND (next_sync_at IS NULL OR next_sync_at <= NOW())
            ORDER BY next_sync_at ASC NULLS FIRST
            LIMIT $1
        """
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            rows = await conn.fetch(query, limit)
            return [self._row_to_sync_state(row) for row in rows]

    async def update(self, user_id: str, provider: str, data: SyncStateUpdate, rls_user_id: Optional[str] = None) -> Optional[SyncState]:
        """
        Update sync state.
        
        Args:
            user_id: The user ID this sync state belongs to
            provider: The sync provider name
            data: Update data
            rls_user_id: User ID for RLS context
        """
        updates = []
        values = [user_id, provider]
        param_count = 2
        
        update_data = data.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            param_count += 1
            if field == "sync_status" and value is not None:
                updates.append(f"{field} = ${param_count}")
                values.append(value.value if hasattr(value, "value") else value)
            else:
                updates.append(f"{field} = ${param_count}")
                values.append(value)
        
        if not updates:
            return await self.get(user_id, provider, rls_user_id=rls_user_id)
        
        query = f"""
            UPDATE sync_state 
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE user_id = $1 AND provider = $2
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            row = await conn.fetchrow(query, *values)
            return self._row_to_sync_state(row) if row else None

    async def start_sync(self, user_id: str, provider: str, rls_user_id: Optional[str] = None) -> Optional[SyncState]:
        """
        Mark sync as started.
        
        Args:
            user_id: The user ID this sync state belongs to
            provider: The sync provider name
            rls_user_id: User ID for RLS context
        """
        return await self.update(
            user_id, provider,
            SyncStateUpdate(sync_status=SyncStatus.SYNCING),
            rls_user_id=rls_user_id
        )

    async def complete_sync(
        self, 
        user_id: str, 
        provider: str,
        sync_token: Optional[str] = None,
        added: int = 0,
        updated: int = 0,
        is_full_sync: bool = False,
        next_sync_minutes: int = 30,
        rls_user_id: Optional[str] = None,
    ) -> Optional[SyncState]:
        """
        Mark sync as completed with statistics.
        
        Args:
            user_id: The user ID this sync state belongs to
            provider: The sync provider name
            sync_token: Optional sync token for incremental sync
            added: Number of records added
            updated: Number of records updated
            is_full_sync: Whether this was a full sync
            next_sync_minutes: Minutes until next sync
            rls_user_id: User ID for RLS context
        """
        now = datetime.utcnow()
        from datetime import timedelta
        
        update_data = SyncStateUpdate(
            sync_status=SyncStatus.IDLE,
            sync_token=sync_token,
            last_sync_added=added,
            last_sync_updated=updated,
            consecutive_failures=0,
            error_message=None,
            next_sync_at=now + timedelta(minutes=next_sync_minutes),
        )
        
        if is_full_sync:
            update_data.last_full_sync_at = now
        else:
            update_data.last_incremental_sync_at = now
        
        return await self.update(user_id, provider, update_data, rls_user_id=rls_user_id)

    async def fail_sync(
        self, user_id: str, provider: str, error_message: str, rls_user_id: Optional[str] = None
    ) -> Optional[SyncState]:
        """
        Mark sync as failed.
        
        Args:
            user_id: The user ID this sync state belongs to
            provider: The sync provider name
            error_message: Error description
            rls_user_id: User ID for RLS context
        """
        # Get current state to increment failure count
        state = await self.get(user_id, provider, rls_user_id=rls_user_id)
        failures = (state.consecutive_failures if state else 0) + 1
        
        # Exponential backoff: 5min, 10min, 20min, 40min, etc. (max 24 hours)
        from datetime import timedelta
        backoff_minutes = min(5 * (2 ** failures), 24 * 60)
        
        return await self.update(
            user_id, provider,
            SyncStateUpdate(
                sync_status=SyncStatus.FAILED if failures >= 5 else SyncStatus.IDLE,
                error_message=error_message,
                consecutive_failures=failures,
                next_sync_at=datetime.utcnow() + timedelta(minutes=backoff_minutes),
            ),
            rls_user_id=rls_user_id
        )

    def _row_to_sync_state(self, row: asyncpg.Record) -> SyncState:
        """Convert database row to SyncState model."""
        return SyncState(
            id=row["id"],
            user_id=row["user_id"],
            provider=row["provider"],
            sync_token=row["sync_token"],
            last_full_sync_at=row["last_full_sync_at"],
            last_incremental_sync_at=row["last_incremental_sync_at"],
            next_sync_at=row["next_sync_at"],
            sync_status=SyncStatus(row["sync_status"]),
            error_message=row["error_message"],
            consecutive_failures=row["consecutive_failures"],
            total_synced_count=row["total_synced_count"],
            last_sync_added=row["last_sync_added"],
            last_sync_updated=row["last_sync_updated"],
            last_sync_deleted=row["last_sync_deleted"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ============================================================================
# Sync Conflict Repository
# ============================================================================

class SyncConflictRepository:
    """Repository for sync conflict operations with RLS enforcement."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: SyncConflictCreate, rls_user_id: Optional[str] = None) -> SyncConflict:
        """
        Create a new sync conflict.
        
        Args:
            data: Sync conflict creation data
            rls_user_id: User ID for RLS context
        """
        conflict_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO sync_conflicts (
                id, user_id, person_id, provider, external_id,
                conflict_type, local_data, remote_data, suggested_resolution,
                status, created_at, updated_at, owner_user_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            row = await conn.fetchrow(
                query,
                conflict_id,
                data.user_id,
                data.person_id,
                data.provider.value,
                data.external_id,
                data.conflict_type.value,
                json.dumps(data.local_data),
                json.dumps(data.remote_data),
                json.dumps(data.suggested_resolution) if data.suggested_resolution else None,
                ConflictStatus.PENDING.value,
                now,
                now,
                UUID(rls_user_id) if rls_user_id else None,
            )
            return self._row_to_conflict(row)

    async def get_pending_for_user(self, user_id: str, rls_user_id: Optional[str] = None) -> list[SyncConflict]:
        """
        Get all pending conflicts for a user.
        
        Args:
            user_id: The user ID to get conflicts for
            rls_user_id: User ID for RLS context
        """
        query = """
            SELECT * FROM sync_conflicts 
            WHERE user_id = $1 AND status = 'pending'
            ORDER BY created_at DESC
        """
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            rows = await conn.fetch(query, user_id)
            return [self._row_to_conflict(row) for row in rows]

    async def resolve(
        self, 
        conflict_id: UUID, 
        resolution_type: ResolutionType,
        resolved_by: str,
        rls_user_id: Optional[str] = None
    ) -> Optional[SyncConflict]:
        """
        Resolve a conflict.
        
        Args:
            conflict_id: The conflict's UUID
            resolution_type: How the conflict was resolved
            resolved_by: Who resolved the conflict
            rls_user_id: User ID for RLS context
        """
        query = """
            UPDATE sync_conflicts 
            SET status = $2, resolution_type = $3, resolved_at = NOW(), 
                resolved_by = $4, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            row = await conn.fetchrow(
                query, 
                conflict_id, 
                ConflictStatus.RESOLVED.value,
                resolution_type.value,
                resolved_by
            )
            return self._row_to_conflict(row) if row else None

    async def dismiss(self, conflict_id: UUID, dismissed_by: str, rls_user_id: Optional[str] = None) -> Optional[SyncConflict]:
        """
        Dismiss a conflict without resolution.
        
        Args:
            conflict_id: The conflict's UUID
            dismissed_by: Who dismissed the conflict
            rls_user_id: User ID for RLS context
        """
        query = """
            UPDATE sync_conflicts 
            SET status = $2, resolved_by = $3, resolved_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            row = await conn.fetchrow(
                query, conflict_id, ConflictStatus.DISMISSED.value, dismissed_by
            )
            return self._row_to_conflict(row) if row else None

    def _row_to_conflict(self, row: asyncpg.Record) -> SyncConflict:
        """Convert database row to SyncConflict model."""
        local_data = row["local_data"]
        remote_data = row["remote_data"]
        suggested = row["suggested_resolution"]
        
        if isinstance(local_data, str):
            local_data = json.loads(local_data)
        if isinstance(remote_data, str):
            remote_data = json.loads(remote_data)
        if isinstance(suggested, str):
            suggested = json.loads(suggested)
        
        return SyncConflict(
            id=row["id"],
            user_id=row["user_id"],
            person_id=row["person_id"],
            provider=SyncProvider(row["provider"]),
            external_id=row["external_id"],
            conflict_type=row["conflict_type"],
            local_data=local_data or {},
            remote_data=remote_data or {},
            suggested_resolution=suggested,
            status=ConflictStatus(row["status"]),
            resolution_type=ResolutionType(row["resolution_type"]) if row["resolution_type"] else None,
            resolved_at=row["resolved_at"],
            resolved_by=row["resolved_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ============================================================================
# Sync Log Repository
# ============================================================================

class SyncLogRepository:
    """Repository for sync log operations with RLS enforcement."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: SyncLogCreate, rls_user_id: Optional[str] = None) -> SyncLog:
        """
        Create a new sync log entry.
        
        Args:
            data: Sync log creation data
            rls_user_id: User ID for RLS context
        """
        log_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO sync_log (
                id, user_id, provider, sync_type, direction,
                status, started_at, created_at, owner_user_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            row = await conn.fetchrow(
                query,
                log_id,
                data.user_id,
                data.provider,
                data.sync_type,
                data.direction,
                "running",
                data.started_at,
                now,
                UUID(rls_user_id) if rls_user_id else None,
            )
            return self._row_to_log(row)

    async def complete(
        self, 
        log_id: UUID, 
        status: str,
        processed: int = 0,
        added: int = 0,
        updated: int = 0,
        failed: int = 0,
        conflicts: int = 0,
        error_message: Optional[str] = None,
        error_details: Optional[dict] = None,
        rls_user_id: Optional[str] = None,
    ) -> Optional[SyncLog]:
        """
        Complete a sync log entry.
        
        Args:
            log_id: The sync log's UUID
            status: Final status
            processed: Records processed
            added: Records added
            updated: Records updated
            failed: Records failed
            conflicts: Conflicts created
            error_message: Optional error message
            error_details: Optional error details
            rls_user_id: User ID for RLS context
        """
        now = datetime.utcnow()
        
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            
            # Get start time to calculate duration
            get_query = "SELECT started_at FROM sync_log WHERE id = $1"
            start_row = await conn.fetchrow(get_query, log_id)
            if not start_row:
                return None
            
            duration_ms = int((now - start_row["started_at"]).total_seconds() * 1000)
            
            query = """
                UPDATE sync_log 
                SET status = $2, records_processed = $3, records_added = $4,
                    records_updated = $5, records_failed = $6, conflicts_created = $7,
                    completed_at = $8, duration_ms = $9, 
                    error_message = $10, error_details = $11
                WHERE id = $1
                RETURNING *
            """
            
            row = await conn.fetchrow(
                query,
                log_id,
                status,
                processed,
                added,
                updated,
                failed,
                conflicts,
                now,
                duration_ms,
                error_message,
                json.dumps(error_details) if error_details else None,
            )
            return self._row_to_log(row) if row else None

    async def get_recent_for_user(
        self, user_id: str, limit: int = 20, rls_user_id: Optional[str] = None
    ) -> list[SyncLog]:
        """
        Get recent sync logs for a user.
        
        Args:
            user_id: The user ID to get logs for
            limit: Maximum number of results
            rls_user_id: User ID for RLS context
        """
        query = """
            SELECT * FROM sync_log 
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        async with self.pool.acquire() as conn:
            if rls_user_id:
                await set_rls_user(conn, rls_user_id)
            rows = await conn.fetch(query, user_id, limit)
            return [self._row_to_log(row) for row in rows]

    def _row_to_log(self, row: asyncpg.Record) -> SyncLog:
        """Convert database row to SyncLog model."""
        error_details = row["error_details"]
        if isinstance(error_details, str):
            error_details = json.loads(error_details)
        
        return SyncLog(
            id=row["id"],
            user_id=row["user_id"],
            provider=row["provider"],
            sync_type=row["sync_type"],
            direction=row["direction"],
            status=row["status"],
            records_processed=row["records_processed"],
            records_added=row["records_added"],
            records_updated=row["records_updated"],
            records_failed=row["records_failed"],
            conflicts_created=row["conflicts_created"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
            error_message=row["error_message"],
            error_details=error_details,
            created_at=row["created_at"],
        )

