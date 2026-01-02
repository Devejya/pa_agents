"""
Sync management API routes with Row-Level Security.

These routes manage contact synchronization state, conflicts, and logs.
All endpoints require X-User-ID header for RLS enforcement.
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import (
    ApiKey,
    ExternalIdRepo,
    PersonRepo,
    SyncConflictRepo,
    SyncLogRepo,
    SyncStateRepo,
    UserId,
)
from ...db.models import (
    PersonExternalId,
    PersonExternalIdCreate,
    ResolutionType,
    SyncConflict,
    SyncLog,
    SyncProvider,
    SyncState,
    SyncStateUpdate,
)

router = APIRouter(prefix="/sync", tags=["sync"])


# ============================================================================
# Sync State Routes
# ============================================================================

@router.get("/state/{target_user_id}", response_model=list[SyncState])
async def get_sync_states(
    target_user_id: str,
    repo: SyncStateRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
) -> list[SyncState]:
    """Get all sync states for a user (filtered by RLS)."""
    return await repo.get_all_for_user(target_user_id, rls_user_id=rls_user_id)


@router.get("/state/{target_user_id}/{provider}", response_model=SyncState)
async def get_sync_state(
    target_user_id: str,
    provider: str,
    repo: SyncStateRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
) -> SyncState:
    """Get sync state for a specific user and provider (filtered by RLS)."""
    state = await repo.get(target_user_id, provider, rls_user_id=rls_user_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync state not found",
        )
    return state


@router.post("/state/{target_user_id}/{provider}", response_model=SyncState)
async def create_or_get_sync_state(
    target_user_id: str,
    provider: str,
    repo: SyncStateRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
) -> SyncState:
    """Get or create sync state for a user and provider (uses RLS)."""
    return await repo.get_or_create(target_user_id, provider, rls_user_id=rls_user_id)


@router.patch("/state/{target_user_id}/{provider}", response_model=SyncState)
async def update_sync_state(
    target_user_id: str,
    provider: str,
    data: SyncStateUpdate,
    repo: SyncStateRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
) -> SyncState:
    """Update sync state (only if owned by RLS user)."""
    state = await repo.update(target_user_id, provider, data, rls_user_id=rls_user_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync state not found",
        )
    return state


# ============================================================================
# External ID Routes
# ============================================================================

@router.get("/external-ids/{person_id}", response_model=list[PersonExternalId])
async def get_person_external_ids(
    person_id: UUID,
    repo: ExternalIdRepo,
    api_key: ApiKey,
    user_id: UserId,
    provider: Optional[str] = None,
) -> list[PersonExternalId]:
    """Get all external IDs for a person (filtered by RLS)."""
    return await repo.get_by_person_id(person_id, provider, user_id=user_id)


@router.get("/external-ids/lookup/{provider}/{external_id:path}", response_model=PersonExternalId)
async def lookup_by_external_id(
    provider: str,
    external_id: str,
    repo: ExternalIdRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> PersonExternalId:
    """Find person by external ID from a provider (filtered by RLS)."""
    ext_id = await repo.get_by_external_id(provider, external_id, user_id=user_id)
    if not ext_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="External ID not found",
        )
    return ext_id


@router.post("/external-ids", response_model=PersonExternalId, status_code=status.HTTP_201_CREATED)
async def create_external_id(
    data: PersonExternalIdCreate,
    repo: ExternalIdRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> PersonExternalId:
    """Create a new external ID mapping (owned by RLS user)."""
    return await repo.create(data, user_id=user_id)


@router.put("/external-ids/{person_id}/{provider}", response_model=PersonExternalId)
async def upsert_external_id(
    person_id: UUID,
    provider: str,
    external_id: str,
    repo: ExternalIdRepo,
    api_key: ApiKey,
    user_id: UserId,
    metadata: Optional[dict] = None,
) -> PersonExternalId:
    """Create or update an external ID mapping (owned by RLS user)."""
    return await repo.upsert(person_id, provider, external_id, metadata, user_id=user_id)


@router.delete("/external-ids/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_external_id(
    id: UUID,
    repo: ExternalIdRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> None:
    """Delete an external ID mapping (only if owned by RLS user)."""
    deleted = await repo.delete(id, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="External ID not found",
        )


# ============================================================================
# Sync Conflict Routes
# ============================================================================

@router.get("/conflicts/{target_user_id}", response_model=list[SyncConflict])
async def get_pending_conflicts(
    target_user_id: str,
    repo: SyncConflictRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
) -> list[SyncConflict]:
    """Get all pending sync conflicts for a user (filtered by RLS)."""
    return await repo.get_pending_for_user(target_user_id, rls_user_id=rls_user_id)


@router.post("/conflicts/{conflict_id}/resolve", response_model=SyncConflict)
async def resolve_conflict(
    conflict_id: UUID,
    resolution_type: ResolutionType,
    resolved_by: str,
    repo: SyncConflictRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
) -> SyncConflict:
    """Resolve a sync conflict (only if owned by RLS user)."""
    conflict = await repo.resolve(conflict_id, resolution_type, resolved_by, rls_user_id=rls_user_id)
    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found",
        )
    return conflict


@router.post("/conflicts/{conflict_id}/dismiss", response_model=SyncConflict)
async def dismiss_conflict(
    conflict_id: UUID,
    dismissed_by: str,
    repo: SyncConflictRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
) -> SyncConflict:
    """Dismiss a sync conflict without resolution (only if owned by RLS user)."""
    conflict = await repo.dismiss(conflict_id, dismissed_by, rls_user_id=rls_user_id)
    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found",
        )
    return conflict


# ============================================================================
# Sync Log Routes
# ============================================================================

@router.get("/logs/{target_user_id}", response_model=list[SyncLog])
async def get_sync_logs(
    target_user_id: str,
    repo: SyncLogRepo,
    api_key: ApiKey,
    rls_user_id: UserId,
    limit: int = Query(20, ge=1, le=100),
) -> list[SyncLog]:
    """Get recent sync logs for a user (filtered by RLS)."""
    return await repo.get_recent_for_user(target_user_id, limit, rls_user_id=rls_user_id)

