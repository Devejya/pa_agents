"""
FastAPI dependencies.
"""

from typing import Annotated

import asyncpg
from fastapi import Depends

from ..core.security import get_api_key
from ..db.connection import get_db_pool
from ..db.repository import (
    PersonRepository,
    PersonExternalIdRepository,
    RelationshipRepository,
    SyncStateRepository,
    SyncConflictRepository,
    SyncLogRepository,
)


async def get_person_repo() -> PersonRepository:
    """Get PersonRepository instance."""
    pool = await get_db_pool()
    return PersonRepository(pool)


async def get_relationship_repo() -> RelationshipRepository:
    """Get RelationshipRepository instance."""
    pool = await get_db_pool()
    return RelationshipRepository(pool)


async def get_external_id_repo() -> PersonExternalIdRepository:
    """Get PersonExternalIdRepository instance."""
    pool = await get_db_pool()
    return PersonExternalIdRepository(pool)


async def get_sync_state_repo() -> SyncStateRepository:
    """Get SyncStateRepository instance."""
    pool = await get_db_pool()
    return SyncStateRepository(pool)


async def get_sync_conflict_repo() -> SyncConflictRepository:
    """Get SyncConflictRepository instance."""
    pool = await get_db_pool()
    return SyncConflictRepository(pool)


async def get_sync_log_repo() -> SyncLogRepository:
    """Get SyncLogRepository instance."""
    pool = await get_db_pool()
    return SyncLogRepository(pool)


# Type aliases for dependency injection
ApiKey = Annotated[str, Depends(get_api_key)]
PersonRepo = Annotated[PersonRepository, Depends(get_person_repo)]
RelationshipRepo = Annotated[RelationshipRepository, Depends(get_relationship_repo)]
ExternalIdRepo = Annotated[PersonExternalIdRepository, Depends(get_external_id_repo)]
SyncStateRepo = Annotated[SyncStateRepository, Depends(get_sync_state_repo)]
SyncConflictRepo = Annotated[SyncConflictRepository, Depends(get_sync_conflict_repo)]
SyncLogRepo = Annotated[SyncLogRepository, Depends(get_sync_log_repo)]
DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]

