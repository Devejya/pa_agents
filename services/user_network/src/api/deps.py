"""
FastAPI dependencies.
"""

from typing import Annotated

import asyncpg
from fastapi import Depends

from ..core.security import get_api_key
from ..db.connection import get_db_pool
from ..db.repository import PersonRepository, RelationshipRepository


async def get_person_repo() -> PersonRepository:
    """Get PersonRepository instance."""
    pool = await get_db_pool()
    return PersonRepository(pool)


async def get_relationship_repo() -> RelationshipRepository:
    """Get RelationshipRepository instance."""
    pool = await get_db_pool()
    return RelationshipRepository(pool)


# Type aliases for dependency injection
ApiKey = Annotated[str, Depends(get_api_key)]
PersonRepo = Annotated[PersonRepository, Depends(get_person_repo)]
RelationshipRepo = Annotated[RelationshipRepository, Depends(get_relationship_repo)]
DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]

