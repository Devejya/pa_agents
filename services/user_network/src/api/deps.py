"""
FastAPI dependencies.
"""

from typing import Annotated, Optional
from uuid import UUID

import asyncpg
from fastapi import Depends, Header, HTTPException, status

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


async def get_user_id(x_user_id: Optional[str] = Header(None)) -> Optional[str]:
    """
    Extract and validate user ID from X-User-ID header.
    
    The user ID is required for RLS (Row-Level Security) enforcement.
    All data access is filtered by owner_user_id based on this value.
    
    Returns:
        The validated user ID string, or None if not provided.
        
    Raises:
        HTTPException: If the header value is not a valid UUID.
    """
    if x_user_id is None:
        return None
    
    try:
        UUID(x_user_id)  # Validate UUID format
        return x_user_id
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-User-ID header: must be a valid UUID"
        )


def require_user_id(user_id: Optional[str] = Depends(get_user_id)) -> str:
    """
    Require a valid user ID from X-User-ID header.
    
    Use this dependency for endpoints that require RLS enforcement.
    
    Returns:
        The validated user ID string.
        
    Raises:
        HTTPException: If the header is missing or invalid.
    """
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-ID header is required"
        )
    return user_id


# Type aliases for dependency injection
ApiKey = Annotated[str, Depends(get_api_key)]
UserId = Annotated[str, Depends(require_user_id)]
OptionalUserId = Annotated[Optional[str], Depends(get_user_id)]
PersonRepo = Annotated[PersonRepository, Depends(get_person_repo)]
RelationshipRepo = Annotated[RelationshipRepository, Depends(get_relationship_repo)]
ExternalIdRepo = Annotated[PersonExternalIdRepository, Depends(get_external_id_repo)]
SyncStateRepo = Annotated[SyncStateRepository, Depends(get_sync_state_repo)]
SyncConflictRepo = Annotated[SyncConflictRepository, Depends(get_sync_conflict_repo)]
SyncLogRepo = Annotated[SyncLogRepository, Depends(get_sync_log_repo)]
DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]

