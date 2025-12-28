"""
Person CRUD API routes.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ApiKey, PersonRepo
from ...db.models import Person, PersonCreate, PersonUpdate

router = APIRouter(prefix="/persons", tags=["persons"])


@router.post("", response_model=Person, status_code=status.HTTP_201_CREATED)
async def create_person(
    data: PersonCreate,
    repo: PersonRepo,
    api_key: ApiKey,
) -> Person:
    """Create a new person."""
    return await repo.create(data)


@router.get("", response_model=list[Person])
async def list_persons(
    repo: PersonRepo,
    api_key: ApiKey,
    limit: int = 100,
    offset: int = 0,
) -> list[Person]:
    """List all persons with pagination."""
    return await repo.list_all(limit=limit, offset=offset)


@router.get("/core-user", response_model=Person)
async def get_core_user(
    repo: PersonRepo,
    api_key: ApiKey,
) -> Person:
    """Get the core user."""
    person = await repo.get_core_user()
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
) -> list[Person]:
    """Full-text search across persons."""
    return await repo.search(q)


@router.get("/find")
async def find_by_name_or_alias(
    name: str,
    repo: PersonRepo,
    api_key: ApiKey,
) -> list[Person]:
    """Find persons by name or alias."""
    return await repo.find_by_name_or_alias(name)


@router.get("/{person_id}", response_model=Person)
async def get_person(
    person_id: UUID,
    repo: PersonRepo,
    api_key: ApiKey,
) -> Person:
    """Get a person by ID."""
    person = await repo.get_by_id(person_id)
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
) -> Person:
    """Update a person."""
    person = await repo.update(person_id, data)
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
    interest_name: str = Query(...),
    interest_type: str = Query("other"),
    level: int = Query(50),
) -> Person:
    """
    Atomically add an interest to a person.
    
    This endpoint is safe for parallel calls - interests won't be lost
    due to race conditions.
    """
    person = await repo.add_interest(person_id, interest_name, interest_type, level)
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
) -> None:
    """Delete a person."""
    deleted = await repo.delete(person_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found",
        )

