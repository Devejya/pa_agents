"""
Person CRUD API routes with Row-Level Security.

All endpoints require X-User-ID header for RLS enforcement.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ApiKey, PersonRepo, UserId
from ...db.models import Person, PersonCreate, PersonUpdate

router = APIRouter(prefix="/persons", tags=["persons"])


@router.post("", response_model=Person, status_code=status.HTTP_201_CREATED)
async def create_person(
    data: PersonCreate,
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Person:
    """Create a new person (owned by the authenticated user)."""
    return await repo.create(data, user_id=user_id)


@router.get("", response_model=list[Person])
async def list_persons(
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
    limit: int = 100,
    offset: int = 0,
) -> list[Person]:
    """List all persons with pagination (filtered by RLS to user's data)."""
    return await repo.list_all(limit=limit, offset=offset, user_id=user_id)


@router.get("/core-user", response_model=Person)
async def get_core_user(
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Person:
    """Get the core user (filtered by RLS to user's own core user)."""
    person = await repo.get_core_user(user_id=user_id)
    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Core user not found",
        )
    return person


@router.get("/search")
async def search_persons(
    q: str,
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> list[Person]:
    """Full-text search across persons (filtered by RLS to user's data)."""
    return await repo.search(q, user_id=user_id)


@router.get("/find")
async def find_by_name_or_alias(
    name: str,
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> list[Person]:
    """Find persons by name or alias (filtered by RLS to user's data)."""
    return await repo.find_by_name_or_alias(name, user_id=user_id)


@router.get("/{person_id}", response_model=Person)
async def get_person(
    person_id: UUID,
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Person:
    """Get a person by ID (returns 404 if not owned by user due to RLS)."""
    person = await repo.get_by_id(person_id, user_id=user_id)
    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )
    return person


@router.patch("/{person_id}", response_model=Person)
async def update_person(
    person_id: UUID,
    data: PersonUpdate,
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> Person:
    """Update a person (only if owned by user due to RLS)."""
    person = await repo.update(person_id, data, user_id=user_id)
    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )
    return person


@router.post("/{person_id}/interests", response_model=Person)
async def add_interest(
    person_id: UUID,
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
    interest_name: str = Query(...),
    interest_type: str = Query("other"),
    level: int = Query(50),
) -> Person:
    """
    Atomically add an interest to a person.
    
    This endpoint is safe for parallel calls - interests won't be lost
    due to race conditions. Only updates if person is owned by user (RLS).
    """
    person = await repo.add_interest(person_id, interest_name, interest_type, level, user_id=user_id)
    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )
    return person


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    person_id: UUID,
    repo: PersonRepo,
    api_key: ApiKey,
    user_id: UserId,
) -> None:
    """Delete a person (only if owned by user due to RLS)."""
    deleted = await repo.delete(person_id, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )

