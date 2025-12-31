"""
Repository for user data tables (interests, important_dates, user_tasks, memories).

All data is encrypted with the user's DEK and isolated via RLS.
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

from app.core.encryption import get_encryption
from app.db.user_repository import UserRepository

logger = logging.getLogger(__name__)


class InterestsRepository:
    """Repository for user interests."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.encryption = get_encryption()

    async def add_interest(
        self,
        user_id: UUID,
        name: str,
        interest_level: int,
        category: Optional[str] = None,
        notes: Optional[str] = None,
        source: str = "user_stated",
        confidence: int = 100,
    ) -> Dict[str, Any]:
        """Add a new interest for a user."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            raise ValueError(f"No DEK found for user {user_id}")

        # Encrypt the details JSON
        details = {"name": name, "notes": notes}
        details_encrypted = self.encryption.encrypt_for_user(
            user_dek, json.dumps(details)
        )

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO interests (
                    user_id, category, interest_level, details_encrypted,
                    source, confidence, last_mentioned_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                RETURNING id, category, interest_level, source, confidence, created_at
                """,
                user_id,
                category,
                interest_level,
                details_encrypted,
                source,
                confidence,
            )

            return {
                "id": row["id"],
                "name": name,
                "category": row["category"],
                "interest_level": row["interest_level"],
                "notes": notes,
                "source": row["source"],
                "confidence": row["confidence"],
                "created_at": row["created_at"],
            }

    async def get_interests(
        self,
        user_id: UUID,
        category: Optional[str] = None,
        min_level: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get interests for a user, optionally filtered by category."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            return []

        async with self.pool.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    """
                    SELECT id, category, interest_level, details_encrypted,
                           source, confidence, created_at, last_mentioned_at
                    FROM interests
                    WHERE user_id = $1 AND category = $2 AND interest_level >= $3
                    ORDER BY interest_level DESC
                    """,
                    user_id,
                    category,
                    min_level,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, category, interest_level, details_encrypted,
                           source, confidence, created_at, last_mentioned_at
                    FROM interests
                    WHERE user_id = $1 AND interest_level >= $2
                    ORDER BY interest_level DESC
                    """,
                    user_id,
                    min_level,
                )

            interests = []
            for row in rows:
                try:
                    details = json.loads(
                        self.encryption.decrypt_for_user(
                            user_dek, row["details_encrypted"]
                        )
                    )
                    interests.append(
                        {
                            "id": row["id"],
                            "name": details.get("name"),
                            "notes": details.get("notes"),
                            "category": row["category"],
                            "interest_level": row["interest_level"],
                            "source": row["source"],
                            "confidence": row["confidence"],
                            "created_at": row["created_at"],
                            "last_mentioned_at": row["last_mentioned_at"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to decrypt interest {row['id']}: {e}")

            return interests

    async def update_interest_level(
        self, user_id: UUID, interest_id: UUID, new_level: int
    ) -> bool:
        """Update the interest level."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE interests
                SET interest_level = $3, last_mentioned_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                interest_id,
                user_id,
                new_level,
            )
            return "UPDATE 1" in result

    async def delete_interest(self, user_id: UUID, interest_id: UUID) -> bool:
        """Delete an interest."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM interests WHERE id = $1 AND user_id = $2",
                interest_id,
                user_id,
            )
            return "DELETE 1" in result


class ImportantDatesRepository:
    """Repository for important dates."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.encryption = get_encryption()

    async def add_date(
        self,
        user_id: UUID,
        title: str,
        date_value: date,
        date_type: str = "custom",
        is_recurring: bool = True,
        person_id: Optional[UUID] = None,
        notes: Optional[str] = None,
        remind_days_before: int = 7,
    ) -> Dict[str, Any]:
        """Add an important date."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            raise ValueError(f"No DEK found for user {user_id}")

        title_encrypted = self.encryption.encrypt_for_user(user_dek, title)
        notes_encrypted = (
            self.encryption.encrypt_for_user(user_dek, notes) if notes else None
        )

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO important_dates (
                    user_id, date_type, date_value, is_recurring,
                    person_id, title_encrypted, notes_encrypted, remind_days_before
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, date_type, date_value, is_recurring, person_id,
                          remind_days_before, created_at
                """,
                user_id,
                date_type,
                date_value,
                is_recurring,
                person_id,
                title_encrypted,
                notes_encrypted,
                remind_days_before,
            )

            return {
                "id": row["id"],
                "title": title,
                "date_type": row["date_type"],
                "date_value": row["date_value"],
                "is_recurring": row["is_recurring"],
                "person_id": row["person_id"],
                "notes": notes,
                "remind_days_before": row["remind_days_before"],
                "created_at": row["created_at"],
            }

    async def get_dates(
        self,
        user_id: UUID,
        date_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get important dates for a user."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            return []

        async with self.pool.acquire() as conn:
            if date_type:
                rows = await conn.fetch(
                    """
                    SELECT id, date_type, date_value, is_recurring, person_id,
                           title_encrypted, notes_encrypted, remind_days_before, created_at
                    FROM important_dates
                    WHERE user_id = $1 AND date_type = $2
                    ORDER BY date_value
                    """,
                    user_id,
                    date_type,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, date_type, date_value, is_recurring, person_id,
                           title_encrypted, notes_encrypted, remind_days_before, created_at
                    FROM important_dates
                    WHERE user_id = $1
                    ORDER BY date_value
                    """,
                    user_id,
                )

            dates = []
            for row in rows:
                try:
                    title = self.encryption.decrypt_for_user(
                        user_dek, row["title_encrypted"]
                    )
                    notes = (
                        self.encryption.decrypt_for_user(
                            user_dek, row["notes_encrypted"]
                        )
                        if row["notes_encrypted"]
                        else None
                    )
                    dates.append(
                        {
                            "id": row["id"],
                            "title": title,
                            "notes": notes,
                            "date_type": row["date_type"],
                            "date_value": row["date_value"],
                            "is_recurring": row["is_recurring"],
                            "person_id": row["person_id"],
                            "remind_days_before": row["remind_days_before"],
                            "created_at": row["created_at"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to decrypt date {row['id']}: {e}")

            return dates

    async def get_upcoming_dates(
        self, user_id: UUID, days_ahead: int = 30
    ) -> List[Dict[str, Any]]:
        """Get dates coming up in the next N days (handles recurring dates)."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            return []

        today = date.today()

        async with self.pool.acquire() as conn:
            # For recurring dates, we match by month/day
            # For non-recurring, we match the full date
            rows = await conn.fetch(
                """
                SELECT id, date_type, date_value, is_recurring, person_id,
                       title_encrypted, notes_encrypted, remind_days_before, created_at
                FROM important_dates
                WHERE user_id = $1
                AND (
                    -- Non-recurring: exact date match within range
                    (NOT is_recurring AND date_value BETWEEN $2 AND $2 + $3 * INTERVAL '1 day')
                    OR
                    -- Recurring: month/day match within range
                    (is_recurring AND (
                        MAKE_DATE(
                            EXTRACT(YEAR FROM $2::date)::int,
                            EXTRACT(MONTH FROM date_value)::int,
                            EXTRACT(DAY FROM date_value)::int
                        ) BETWEEN $2 AND $2 + $3 * INTERVAL '1 day'
                    ))
                )
                ORDER BY 
                    CASE WHEN is_recurring THEN
                        MAKE_DATE(
                            EXTRACT(YEAR FROM $2::date)::int,
                            EXTRACT(MONTH FROM date_value)::int,
                            EXTRACT(DAY FROM date_value)::int
                        )
                    ELSE date_value END
                """,
                user_id,
                today,
                days_ahead,
            )

            dates = []
            for row in rows:
                try:
                    title = self.encryption.decrypt_for_user(
                        user_dek, row["title_encrypted"]
                    )
                    notes = (
                        self.encryption.decrypt_for_user(
                            user_dek, row["notes_encrypted"]
                        )
                        if row["notes_encrypted"]
                        else None
                    )
                    dates.append(
                        {
                            "id": row["id"],
                            "title": title,
                            "notes": notes,
                            "date_type": row["date_type"],
                            "date_value": row["date_value"],
                            "is_recurring": row["is_recurring"],
                            "person_id": row["person_id"],
                            "remind_days_before": row["remind_days_before"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to decrypt date {row['id']}: {e}")

            return dates

    async def delete_date(self, user_id: UUID, date_id: UUID) -> bool:
        """Delete an important date."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM important_dates WHERE id = $1 AND user_id = $2",
                date_id,
                user_id,
            )
            return "DELETE 1" in result


class UserTasksRepository:
    """Repository for user tasks."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.encryption = get_encryption()

    async def create_task(
        self,
        user_id: UUID,
        title: str,
        task_type: str = "scheduled",
        description: Optional[str] = None,
        payload: Optional[Dict] = None,
        scheduled_at: Optional[datetime] = None,
        due_at: Optional[datetime] = None,
        schedule_cron: Optional[str] = None,
        priority: int = 50,
    ) -> Dict[str, Any]:
        """Create a new task."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            raise ValueError(f"No DEK found for user {user_id}")

        title_encrypted = self.encryption.encrypt_for_user(user_dek, title)
        description_encrypted = (
            self.encryption.encrypt_for_user(user_dek, description)
            if description
            else None
        )
        payload_encrypted = (
            self.encryption.encrypt_for_user(user_dek, json.dumps(payload))
            if payload
            else None
        )

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_tasks (
                    user_id, task_type, title_encrypted, description_encrypted,
                    payload_encrypted, scheduled_at, due_at, schedule_cron,
                    priority, next_run_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $6)
                RETURNING id, task_type, status, priority, scheduled_at, due_at,
                          schedule_cron, created_at
                """,
                user_id,
                task_type,
                title_encrypted,
                description_encrypted,
                payload_encrypted,
                scheduled_at,
                due_at,
                schedule_cron,
                priority,
            )

            return {
                "id": row["id"],
                "title": title,
                "description": description,
                "task_type": row["task_type"],
                "status": row["status"],
                "priority": row["priority"],
                "scheduled_at": row["scheduled_at"],
                "due_at": row["due_at"],
                "schedule_cron": row["schedule_cron"],
                "created_at": row["created_at"],
            }

    async def get_tasks(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get tasks for a user."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            return []

        async with self.pool.acquire() as conn:
            query = """
                SELECT id, task_type, title_encrypted, description_encrypted,
                       status, priority, scheduled_at, due_at, schedule_cron,
                       next_run_at, last_run_at, completed_at, created_at
                FROM user_tasks
                WHERE user_id = $1
            """
            params = [user_id]

            if status:
                query += " AND status = $2"
                params.append(status)
            if task_type:
                query += f" AND task_type = ${len(params) + 1}"
                params.append(task_type)

            query += " ORDER BY priority DESC, created_at DESC"

            rows = await conn.fetch(query, *params)

            tasks = []
            for row in rows:
                try:
                    title = self.encryption.decrypt_for_user(
                        user_dek, row["title_encrypted"]
                    )
                    description = (
                        self.encryption.decrypt_for_user(
                            user_dek, row["description_encrypted"]
                        )
                        if row["description_encrypted"]
                        else None
                    )
                    tasks.append(
                        {
                            "id": row["id"],
                            "title": title,
                            "description": description,
                            "task_type": row["task_type"],
                            "status": row["status"],
                            "priority": row["priority"],
                            "scheduled_at": row["scheduled_at"],
                            "due_at": row["due_at"],
                            "schedule_cron": row["schedule_cron"],
                            "next_run_at": row["next_run_at"],
                            "last_run_at": row["last_run_at"],
                            "completed_at": row["completed_at"],
                            "created_at": row["created_at"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to decrypt task {row['id']}: {e}")

            return tasks

    async def update_task_status(
        self,
        user_id: UUID,
        task_id: UUID,
        status: str,
        result: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update task status."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)

        result_encrypted = None
        if result and user_dek:
            result_encrypted = self.encryption.encrypt_for_user(user_dek, result)

        async with self.pool.acquire() as conn:
            query_result = await conn.execute(
                """
                UPDATE user_tasks
                SET status = $3,
                    result_encrypted = $4,
                    error_message = $5,
                    completed_at = CASE WHEN $3 IN ('completed', 'failed', 'cancelled') THEN NOW() ELSE completed_at END,
                    last_run_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                task_id,
                user_id,
                status,
                result_encrypted,
                error_message,
            )
            return "UPDATE 1" in query_result

    async def delete_task(self, user_id: UUID, task_id: UUID) -> bool:
        """Delete a task."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM user_tasks WHERE id = $1 AND user_id = $2",
                task_id,
                user_id,
            )
            return "DELETE 1" in result


class MemoriesRepository:
    """Repository for user memories."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.encryption = get_encryption()

    async def add_memory(
        self,
        user_id: UUID,
        fact_key: str,
        fact_value: str,
        context: str = "general",
        category: Optional[str] = None,
        source: str = "user_stated",
        confidence: int = 100,
        person_id: Optional[UUID] = None,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Add a memory about the user."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            raise ValueError(f"No DEK found for user {user_id}")

        fact_value_encrypted = self.encryption.encrypt_for_user(user_dek, fact_value)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memories (
                    user_id, context, category, fact_key, fact_value_encrypted,
                    source, confidence, person_id, expires_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (user_id, fact_key) DO UPDATE SET
                    fact_value_encrypted = EXCLUDED.fact_value_encrypted,
                    context = EXCLUDED.context,
                    category = EXCLUDED.category,
                    source = EXCLUDED.source,
                    confidence = EXCLUDED.confidence,
                    person_id = EXCLUDED.person_id,
                    expires_at = EXCLUDED.expires_at,
                    is_active = true,
                    updated_at = NOW()
                RETURNING id, context, category, fact_key, source, confidence,
                          person_id, is_active, expires_at, created_at
                """,
                user_id,
                context,
                category,
                fact_key,
                fact_value_encrypted,
                source,
                confidence,
                person_id,
                expires_at,
            )

            return {
                "id": row["id"],
                "fact_key": row["fact_key"],
                "fact_value": fact_value,
                "context": row["context"],
                "category": row["category"],
                "source": row["source"],
                "confidence": row["confidence"],
                "person_id": row["person_id"],
                "is_active": row["is_active"],
                "expires_at": row["expires_at"],
                "created_at": row["created_at"],
            }

    async def get_memory(
        self, user_id: UUID, fact_key: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific memory by key."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            return None

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, context, category, fact_key, fact_value_encrypted,
                       source, confidence, person_id, is_active, expires_at, created_at
                FROM memories
                WHERE user_id = $1 AND fact_key = $2 AND is_active = true
                AND (expires_at IS NULL OR expires_at > NOW())
                """,
                user_id,
                fact_key,
            )

            if not row:
                return None

            try:
                fact_value = self.encryption.decrypt_for_user(
                    user_dek, row["fact_value_encrypted"]
                )

                # Update last_accessed_at
                await conn.execute(
                    "UPDATE memories SET last_accessed_at = NOW() WHERE id = $1",
                    row["id"],
                )

                return {
                    "id": row["id"],
                    "fact_key": row["fact_key"],
                    "fact_value": fact_value,
                    "context": row["context"],
                    "category": row["category"],
                    "source": row["source"],
                    "confidence": row["confidence"],
                    "person_id": row["person_id"],
                    "is_active": row["is_active"],
                    "expires_at": row["expires_at"],
                    "created_at": row["created_at"],
                }
            except Exception as e:
                logger.error(f"Failed to decrypt memory {row['id']}: {e}")
                return None

    async def get_memories(
        self,
        user_id: UUID,
        context: Optional[str] = None,
        category: Optional[str] = None,
        person_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Get memories for a user with optional filters."""
        user_repo = UserRepository(self.pool)
        user_dek = await user_repo.get_user_dek(user_id)
        if not user_dek:
            return []

        async with self.pool.acquire() as conn:
            query = """
                SELECT id, context, category, fact_key, fact_value_encrypted,
                       source, confidence, person_id, is_active, expires_at, created_at
                FROM memories
                WHERE user_id = $1 AND is_active = true
                AND (expires_at IS NULL OR expires_at > NOW())
            """
            params = [user_id]

            if context:
                query += f" AND context = ${len(params) + 1}"
                params.append(context)
            if category:
                query += f" AND category = ${len(params) + 1}"
                params.append(category)
            if person_id:
                query += f" AND person_id = ${len(params) + 1}"
                params.append(person_id)

            query += " ORDER BY confidence DESC, created_at DESC"

            rows = await conn.fetch(query, *params)

            memories = []
            for row in rows:
                try:
                    fact_value = self.encryption.decrypt_for_user(
                        user_dek, row["fact_value_encrypted"]
                    )
                    memories.append(
                        {
                            "id": row["id"],
                            "fact_key": row["fact_key"],
                            "fact_value": fact_value,
                            "context": row["context"],
                            "category": row["category"],
                            "source": row["source"],
                            "confidence": row["confidence"],
                            "person_id": row["person_id"],
                            "is_active": row["is_active"],
                            "expires_at": row["expires_at"],
                            "created_at": row["created_at"],
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to decrypt memory {row['id']}: {e}")

            return memories

    async def deactivate_memory(self, user_id: UUID, fact_key: str) -> bool:
        """Deactivate a memory (soft delete)."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE memories
                SET is_active = false
                WHERE user_id = $1 AND fact_key = $2
                """,
                user_id,
                fact_key,
            )
            return "UPDATE 1" in result

    async def delete_memory(self, user_id: UUID, memory_id: UUID) -> bool:
        """Hard delete a memory."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memories WHERE id = $1 AND user_id = $2",
                memory_id,
                user_id,
            )
            return "DELETE 1" in result

