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
                id, first_name, last_name, middle_names, name,
                aliases, is_core_user, status,
                work_email, personal_email, work_cell, personal_cell, secondary_cell,
                company, latest_title, expertise,
                address, country, city, state,
                instagram_handle, religion, ethnicity, country_of_birth, city_of_birth,
                date_of_birth, interests, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9, $10, $11, $12, $13,
                $14, $15, $16,
                $17, $18, $19, $20,
                $21, $22, $23, $24, $25,
                $26, $27, $28, $29
            )
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
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


# ============================================================================
# Person External ID Repository
# ============================================================================

class PersonExternalIdRepository:
    """Repository for person external ID operations (for multi-platform sync)."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: PersonExternalIdCreate) -> PersonExternalId:
        """Create a new external ID mapping."""
        ext_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO person_external_ids (
                id, person_id, provider, external_id, external_metadata,
                last_synced_at, sync_status, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
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
            )
            return self._row_to_external_id(row)

    async def get_by_external_id(
        self, provider: str, external_id: str
    ) -> Optional[PersonExternalId]:
        """Find by provider and external ID."""
        query = """
            SELECT * FROM person_external_ids 
            WHERE provider = $1 AND external_id = $2
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, provider, external_id)
            return self._row_to_external_id(row) if row else None

    async def get_by_person_id(
        self, person_id: UUID, provider: Optional[str] = None
    ) -> list[PersonExternalId]:
        """Get all external IDs for a person."""
        if provider:
            query = """
                SELECT * FROM person_external_ids 
                WHERE person_id = $1 AND provider = $2
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, person_id, provider)
        else:
            query = "SELECT * FROM person_external_ids WHERE person_id = $1"
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, person_id)
        return [self._row_to_external_id(row) for row in rows]

    async def update_sync_status(
        self, id: UUID, status: ExternalIdSyncStatus, metadata: Optional[dict] = None
    ) -> Optional[PersonExternalId]:
        """Update sync status and optionally metadata."""
        now = datetime.utcnow()
        
        if metadata:
            query = """
                UPDATE person_external_ids 
                SET sync_status = $2, external_metadata = $3, 
                    last_synced_at = $4, updated_at = $4
                WHERE id = $1
                RETURNING *
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, id, status.value, json.dumps(metadata), now)
        else:
            query = """
                UPDATE person_external_ids 
                SET sync_status = $2, last_synced_at = $3, updated_at = $3
                WHERE id = $1
                RETURNING *
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, id, status.value, now)
        
        return self._row_to_external_id(row) if row else None

    async def upsert(
        self, person_id: UUID, provider: str, external_id: str, metadata: dict = None
    ) -> PersonExternalId:
        """Insert or update an external ID mapping."""
        now = datetime.utcnow()
        new_id = uuid4()
        
        query = """
            INSERT INTO person_external_ids (
                id, person_id, provider, external_id, external_metadata,
                last_synced_at, sync_status, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
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
            )
            return self._row_to_external_id(row)

    async def delete(self, id: UUID) -> bool:
        """Delete an external ID mapping."""
        query = "DELETE FROM person_external_ids WHERE id = $1 RETURNING id"
        async with self.pool.acquire() as conn:
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
    """Repository for sync state operations."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_or_create(self, user_id: str, provider: str) -> SyncState:
        """Get sync state for user/provider, creating if needed."""
        state = await self.get(user_id, provider)
        if state:
            return state
        return await self.create(SyncStateCreate(user_id=user_id, provider=provider))

    async def create(self, data: SyncStateCreate) -> SyncState:
        """Create a new sync state."""
        state_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO sync_state (
                id, user_id, provider, sync_status, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                state_id,
                data.user_id,
                data.provider,
                SyncStatus.IDLE.value,
                now,
                now,
            )
            return self._row_to_sync_state(row)

    async def get(self, user_id: str, provider: str) -> Optional[SyncState]:
        """Get sync state for a user and provider."""
        query = "SELECT * FROM sync_state WHERE user_id = $1 AND provider = $2"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, provider)
            return self._row_to_sync_state(row) if row else None

    async def get_all_for_user(self, user_id: str) -> list[SyncState]:
        """Get all sync states for a user."""
        query = "SELECT * FROM sync_state WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
            return [self._row_to_sync_state(row) for row in rows]

    async def get_pending_syncs(self, limit: int = 100) -> list[SyncState]:
        """Get sync states that are due for sync."""
        query = """
            SELECT * FROM sync_state 
            WHERE sync_status = 'idle' 
            AND (next_sync_at IS NULL OR next_sync_at <= NOW())
            ORDER BY next_sync_at ASC NULLS FIRST
            LIMIT $1
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [self._row_to_sync_state(row) for row in rows]

    async def update(self, user_id: str, provider: str, data: SyncStateUpdate) -> Optional[SyncState]:
        """Update sync state."""
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
            return await self.get(user_id, provider)
        
        query = f"""
            UPDATE sync_state 
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE user_id = $1 AND provider = $2
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            return self._row_to_sync_state(row) if row else None

    async def start_sync(self, user_id: str, provider: str) -> Optional[SyncState]:
        """Mark sync as started."""
        return await self.update(
            user_id, provider,
            SyncStateUpdate(sync_status=SyncStatus.SYNCING)
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
    ) -> Optional[SyncState]:
        """Mark sync as completed with statistics."""
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
        
        return await self.update(user_id, provider, update_data)

    async def fail_sync(
        self, user_id: str, provider: str, error_message: str
    ) -> Optional[SyncState]:
        """Mark sync as failed."""
        # Get current state to increment failure count
        state = await self.get(user_id, provider)
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
            )
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
    """Repository for sync conflict operations."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: SyncConflictCreate) -> SyncConflict:
        """Create a new sync conflict."""
        conflict_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO sync_conflicts (
                id, user_id, person_id, provider, external_id,
                conflict_type, local_data, remote_data, suggested_resolution,
                status, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
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
            )
            return self._row_to_conflict(row)

    async def get_pending_for_user(self, user_id: str) -> list[SyncConflict]:
        """Get all pending conflicts for a user."""
        query = """
            SELECT * FROM sync_conflicts 
            WHERE user_id = $1 AND status = 'pending'
            ORDER BY created_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
            return [self._row_to_conflict(row) for row in rows]

    async def resolve(
        self, 
        conflict_id: UUID, 
        resolution_type: ResolutionType,
        resolved_by: str
    ) -> Optional[SyncConflict]:
        """Resolve a conflict."""
        query = """
            UPDATE sync_conflicts 
            SET status = $2, resolution_type = $3, resolved_at = NOW(), 
                resolved_by = $4, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query, 
                conflict_id, 
                ConflictStatus.RESOLVED.value,
                resolution_type.value,
                resolved_by
            )
            return self._row_to_conflict(row) if row else None

    async def dismiss(self, conflict_id: UUID, dismissed_by: str) -> Optional[SyncConflict]:
        """Dismiss a conflict without resolution."""
        query = """
            UPDATE sync_conflicts 
            SET status = $2, resolved_by = $3, resolved_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        async with self.pool.acquire() as conn:
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
    """Repository for sync log operations."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, data: SyncLogCreate) -> SyncLog:
        """Create a new sync log entry."""
        log_id = uuid4()
        now = datetime.utcnow()
        
        query = """
            INSERT INTO sync_log (
                id, user_id, provider, sync_type, direction,
                status, started_at, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
        """
        
        async with self.pool.acquire() as conn:
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
    ) -> Optional[SyncLog]:
        """Complete a sync log entry."""
        now = datetime.utcnow()
        
        # Get start time to calculate duration
        get_query = "SELECT started_at FROM sync_log WHERE id = $1"
        async with self.pool.acquire() as conn:
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
        self, user_id: str, limit: int = 20
    ) -> list[SyncLog]:
        """Get recent sync logs for a user."""
        query = """
            SELECT * FROM sync_log 
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        async with self.pool.acquire() as conn:
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

