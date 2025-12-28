"""
Query API routes for agent use.

These endpoints are optimized for common agent queries like:
- "What is my sister's phone number?"
- "What does my mother like?"
- "Who is my brother's wife?"
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ApiKey, DbPool
from ...db.models import (
    ContactInfo,
    Interest,
    MostContactedPerson,
    Person,
    PersonInterests,
    PersonStatus,
    TraversalResult,
)

router = APIRouter(prefix="/query", tags=["queries"])


@router.get("/contact-by-role", response_model=list[ContactInfo])
async def get_contact_by_role(
    role: str,
    pool: DbPool,
    api_key: ApiKey,
) -> list[ContactInfo]:
    """
    Get contact info for core user's relationship by role.
    
    Example: "What is my sister's phone number?"
    Query: /query/contact-by-role?role=sister
    """
    query = """
        SELECT 
            p.id,
            p.name,
            p.personal_cell,
            p.work_cell,
            p.secondary_cell,
            p.personal_email,
            p.work_email,
            r.to_role as relationship
        FROM persons core
        JOIN relationships r ON core.id = r.from_person_id
        JOIN persons p ON r.to_person_id = p.id
        WHERE core.is_core_user = TRUE
          AND LOWER(r.to_role) = LOWER($1)
          AND r.is_active = TRUE
          AND p.status = 'active'
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, role)
        return [
            ContactInfo(
                id=row["id"],
                name=row["name"],
                relationship=row["relationship"],
                personal_cell=row["personal_cell"],
                work_cell=row["work_cell"],
                secondary_cell=row["secondary_cell"],
                personal_email=row["personal_email"],
                work_email=row["work_email"],
            )
            for row in rows
        ]


@router.get("/interests-by-role", response_model=list[PersonInterests])
async def get_interests_by_role(
    role: str,
    pool: DbPool,
    api_key: ApiKey,
) -> list[PersonInterests]:
    """
    Get interests for core user's relationship by role.
    
    Example: "What does my mother like?"
    Query: /query/interests-by-role?role=mother
    """
    query = """
        SELECT 
            p.id,
            p.name,
            p.interests,
            p.expertise,
            p.country,
            p.city,
            r.to_role as relationship
        FROM persons core
        JOIN relationships r ON core.id = r.from_person_id
        JOIN persons p ON r.to_person_id = p.id
        WHERE core.is_core_user = TRUE
          AND LOWER(r.to_role) = LOWER($1)
          AND r.is_active = TRUE
          AND p.status = 'active'
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, role)
        results = []
        for row in rows:
            interests_data = row["interests"]
            if isinstance(interests_data, str):
                interests_data = json.loads(interests_data)
            
            interests = [Interest(**i) for i in interests_data] if interests_data else []
            results.append(
                PersonInterests(
                    id=row["id"],
                    name=row["name"],
                    relationship=row["relationship"],
                    interests=interests,
                    expertise=row["expertise"],
                    country=row["country"],
                    city=row["city"],
                )
            )
        return results


@router.get("/contact-by-name", response_model=list[ContactInfo])
async def get_contact_by_name(
    name: str,
    pool: DbPool,
    api_key: ApiKey,
) -> list[ContactInfo]:
    """
    Get contact info for a person by name.
    
    Example: "What is Rachel's phone number?"
    Query: /query/contact-by-name?name=Rachel
    """
    name_lower = name.lower().strip()
    query = """
        SELECT 
            p.id,
            p.name,
            p.personal_cell,
            p.work_cell,
            p.secondary_cell,
            p.personal_email,
            p.work_email,
            r.to_role as relationship
        FROM persons p
        LEFT JOIN relationships r ON p.id = r.to_person_id
        LEFT JOIN persons core ON r.from_person_id = core.id AND core.is_core_user = TRUE
        WHERE (LOWER(p.name) LIKE $1 OR $2 = ANY(SELECT LOWER(unnest(p.aliases))))
          AND p.status = 'active'
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, f"%{name_lower}%", name_lower)
        return [
            ContactInfo(
                id=row["id"],
                name=row["name"],
                relationship=row["relationship"],
                personal_cell=row["personal_cell"],
                work_cell=row["work_cell"],
                secondary_cell=row["secondary_cell"],
                personal_email=row["personal_email"],
                work_email=row["work_email"],
            )
            for row in rows
        ]


@router.get("/interests-by-name", response_model=list[PersonInterests])
async def get_interests_by_name(
    name: str,
    pool: DbPool,
    api_key: ApiKey,
) -> list[PersonInterests]:
    """
    Get interests for a person by name.
    
    Example: "What does Rajesh like?"
    Query: /query/interests-by-name?name=Rajesh
    """
    name_lower = name.lower().strip()
    query = """
        SELECT 
            p.id,
            p.name,
            p.interests,
            p.expertise,
            p.country,
            p.city,
            r.to_role as relationship
        FROM persons p
        LEFT JOIN relationships r ON p.id = r.to_person_id
        LEFT JOIN persons core ON r.from_person_id = core.id AND core.is_core_user = TRUE
        WHERE (LOWER(p.name) LIKE $1 OR $2 = ANY(SELECT LOWER(unnest(p.aliases))))
          AND p.status = 'active'
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, f"%{name_lower}%", name_lower)
        results = []
        for row in rows:
            interests_data = row["interests"]
            if isinstance(interests_data, str):
                interests_data = json.loads(interests_data)
            
            interests = [Interest(**i) for i in interests_data] if interests_data else []
            results.append(
                PersonInterests(
                    id=row["id"],
                    name=row["name"],
                    relationship=row["relationship"],
                    interests=interests,
                    expertise=row["expertise"],
                    country=row["country"],
                    city=row["city"],
                )
            )
        return results


@router.get("/traverse")
async def traverse_relationships(
    path: str = Query(..., description="Comma-separated path, e.g., 'sister,husband'"),
    pool: DbPool = None,
    api_key: ApiKey = None,
) -> list[dict]:
    """
    Traverse relationships from core user.
    
    Example: "Who is my sister's husband?"
    Query: /query/traverse?path=sister,husband
    
    Example: "What are my brother's wife's interests?"
    Query: /query/traverse?path=brother,wife
    """
    roles = [r.strip().lower() for r in path.split(",") if r.strip()]
    
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path cannot be empty",
        )
    
    if len(roles) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path cannot exceed 5 hops",
        )
    
    # Build query based on path length
    if len(roles) == 1:
        query = """
            SELECT p.*, r.to_role as final_role
            FROM persons core
            JOIN relationships r ON core.id = r.from_person_id
            JOIN persons p ON r.to_person_id = p.id
            WHERE core.is_core_user = TRUE
              AND LOWER(r.to_role) = LOWER($1)
              AND r.is_active = TRUE
              AND p.status = 'active'
        """
        params = [roles[0]]
    
    elif len(roles) == 2:
        query = """
            SELECT p2.*, r2.to_role as final_role
            FROM persons core
            JOIN relationships r1 ON core.id = r1.from_person_id
            JOIN persons p1 ON r1.to_person_id = p1.id
            JOIN relationships r2 ON p1.id = r2.from_person_id
            JOIN persons p2 ON r2.to_person_id = p2.id
            WHERE core.is_core_user = TRUE
              AND LOWER(r1.to_role) = LOWER($1)
              AND LOWER(r2.to_role) = LOWER($2)
              AND r1.is_active = TRUE
              AND r2.is_active = TRUE
              AND p1.status = 'active'
              AND p2.status = 'active'
        """
        params = roles[:2]
    
    elif len(roles) == 3:
        query = """
            SELECT p3.*, r3.to_role as final_role
            FROM persons core
            JOIN relationships r1 ON core.id = r1.from_person_id
            JOIN persons p1 ON r1.to_person_id = p1.id
            JOIN relationships r2 ON p1.id = r2.from_person_id
            JOIN persons p2 ON r2.to_person_id = p2.id
            JOIN relationships r3 ON p2.id = r3.from_person_id
            JOIN persons p3 ON r3.to_person_id = p3.id
            WHERE core.is_core_user = TRUE
              AND LOWER(r1.to_role) = LOWER($1)
              AND LOWER(r2.to_role) = LOWER($2)
              AND LOWER(r3.to_role) = LOWER($3)
              AND r1.is_active = TRUE
              AND r2.is_active = TRUE
              AND r3.is_active = TRUE
              AND p1.status = 'active'
              AND p2.status = 'active'
              AND p3.status = 'active'
        """
        params = roles[:3]
    
    else:
        # For 4-5 hops, use recursive CTE
        query = """
            WITH RECURSIVE path_traversal AS (
                SELECT 
                    p.id,
                    1 as depth,
                    ARRAY[r.to_role] as path_taken
                FROM persons core
                JOIN relationships r ON core.id = r.from_person_id
                JOIN persons p ON r.to_person_id = p.id
                WHERE core.is_core_user = TRUE
                  AND LOWER(r.to_role) = LOWER($1)
                  AND r.is_active = TRUE
                  AND p.status = 'active'
                
                UNION ALL
                
                SELECT 
                    p.id,
                    pt.depth + 1,
                    pt.path_taken || r.to_role
                FROM path_traversal pt
                JOIN relationships r ON pt.id = r.from_person_id
                JOIN persons p ON r.to_person_id = p.id
                WHERE pt.depth < $2
                  AND r.is_active = TRUE
                  AND p.status = 'active'
            )
            SELECT p.*, pt.path_taken
            FROM path_traversal pt
            JOIN persons p ON pt.id = p.id
            WHERE pt.depth = $2
        """
        params = [roles[0], len(roles)]
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        results = []
        for row in rows:
            interests_data = row.get("interests", [])
            if isinstance(interests_data, str):
                interests_data = json.loads(interests_data)
            
            results.append({
                "id": str(row["id"]),
                "name": row["name"],
                "path": roles,
                "depth": len(roles),
                "personal_cell": row.get("personal_cell"),
                "work_cell": row.get("work_cell"),
                "personal_email": row.get("personal_email"),
                "work_email": row.get("work_email"),
                "interests": interests_data,
                "country": row.get("country"),
                "city": row.get("city"),
            })
        return results


@router.get("/most-contacted", response_model=list[MostContactedPerson])
async def get_most_contacted(
    pool: DbPool,
    api_key: ApiKey,
    limit: int = 10,
) -> list[MostContactedPerson]:
    """
    Get the most contacted people this week.
    
    Example: "Who have I talked to most this week?"
    Query: /query/most-contacted?limit=10
    """
    query = """
        SELECT 
            p.id,
            p.name,
            r.to_role as relationship,
            COALESCE((r.connection_counts->>'text_count_past_one_week')::int, 0) as texts,
            COALESCE((r.connection_counts->>'call_count_past_one_week')::int, 0) as calls,
            COALESCE((r.connection_counts->>'meet_count_past_one_week')::int, 0) as meets
        FROM persons core
        JOIN relationships r ON core.id = r.from_person_id
        JOIN persons p ON r.to_person_id = p.id
        WHERE core.is_core_user = TRUE
          AND r.is_active = TRUE
          AND p.status = 'active'
        ORDER BY (
            COALESCE((r.connection_counts->>'text_count_past_one_week')::int, 0) +
            COALESCE((r.connection_counts->>'call_count_past_one_week')::int, 0) * 5 +
            COALESCE((r.connection_counts->>'meet_count_past_one_week')::int, 0) * 10
        ) DESC
        LIMIT $1
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, limit)
        return [
            MostContactedPerson(
                id=row["id"],
                name=row["name"],
                relationship=row["relationship"],
                texts_this_week=row["texts"],
                calls_this_week=row["calls"],
                meets_this_week=row["meets"],
            )
            for row in rows
        ]

