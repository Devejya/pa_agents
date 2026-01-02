"""
Relationship CRUD API routes with Row-Level Security.

All endpoints require X-User-ID header for RLS enforcement.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from ..deps import ApiKey, RelationshipRepo, UserId
from ...db.models import Relationship, RelationshipCreate, RelationshipUpdate

router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.post("", response_model=Relationship, status_code=status.HTTP_201_CREATED)
async def create_relationship(
    data: RelationshipCreate,
    repo: RelationshipRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Relationship:
    """Create a new relationship between two persons (owned by the authenticated user)."""
    return await repo.create(data, user_id=user_id)


@router.get("/{relationship_id}", response_model=Relationship)
async def get_relationship(
    relationship_id: UUID,
    repo: RelationshipRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Relationship:
    """Get a relationship by ID (returns 404 if not owned by user due to RLS)."""
    rel = await repo.get_by_id(relationship_id, user_id=user_id)
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )
    return rel


@router.get("/person/{person_id}", response_model=list[Relationship])
async def get_person_relationships(
    person_id: UUID,
    repo: RelationshipRepo,
    api_key: ApiKey,
    user_id: UserId,
    include_inactive: bool = False,
) -> list[Relationship]:
    """Get all relationships for a person (filtered by RLS to user's data)."""
    return await repo.get_for_person(person_id, include_inactive=include_inactive, user_id=user_id)


@router.patch("/{relationship_id}", response_model=Relationship)
async def update_relationship(
    relationship_id: UUID,
    data: RelationshipUpdate,
    repo: RelationshipRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Relationship:
    """Update a relationship (only if owned by user due to RLS)."""
    rel = await repo.update(relationship_id, data, user_id=user_id)
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )
    return rel


@router.post("/{relationship_id}/end", response_model=Relationship)
async def end_relationship(
    relationship_id: UUID,
    repo: RelationshipRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Relationship:
    """Mark a relationship as ended (preserves history, only if owned by user due to RLS)."""
    rel = await repo.end_relationship(relationship_id, user_id=user_id)
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )
    return rel


@router.delete("/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relationship(
    relationship_id: UUID,
    repo: RelationshipRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> None:
    """Delete a relationship permanently (only if owned by user due to RLS)."""
    deleted = await repo.delete(relationship_id, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )

