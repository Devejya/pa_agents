"""
Relationship CRUD API routes.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from ..deps import ApiKey, RelationshipRepo
from ...db.models import Relationship, RelationshipCreate, RelationshipUpdate

router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.post("", response_model=Relationship, status_code=status.HTTP_201_CREATED)
async def create_relationship(
    data: RelationshipCreate,
    repo: RelationshipRepo,
    api_key: ApiKey,
) -> Relationship:
    """Create a new relationship between two persons."""
    return await repo.create(data)


@router.get("/{relationship_id}", response_model=Relationship)
async def get_relationship(
    relationship_id: UUID,
    repo: RelationshipRepo,
    api_key: ApiKey,
) -> Relationship:
    """Get a relationship by ID."""
    rel = await repo.get_by_id(relationship_id)
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
    include_inactive: bool = False,
) -> list[Relationship]:
    """Get all relationships for a person."""
    return await repo.get_for_person(person_id, include_inactive=include_inactive)


@router.patch("/{relationship_id}", response_model=Relationship)
async def update_relationship(
    relationship_id: UUID,
    data: RelationshipUpdate,
    repo: RelationshipRepo,
    api_key: ApiKey,
) -> Relationship:
    """Update a relationship."""
    rel = await repo.update(relationship_id, data)
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
) -> Relationship:
    """Mark a relationship as ended (preserves history)."""
    rel = await repo.end_relationship(relationship_id)
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
) -> None:
    """Delete a relationship permanently."""
    deleted = await repo.delete(relationship_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )

