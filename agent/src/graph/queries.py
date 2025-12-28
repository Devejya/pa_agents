"""
Graph traversal queries for User Relationship Graph.

Implements common query patterns using PostgreSQL recursive CTEs.
Designed for future migration to Neptune/Neo4j (Cypher/Gremlin).
"""

import json
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import asyncpg

from .models import Interest, Person, PersonStatus


@dataclass
class TraversalResult:
    """Result of a graph traversal query."""
    person: Person
    path: list[str]  # List of roles traversed
    depth: int


class GraphQueries:
    """
    Graph traversal queries using PostgreSQL recursive CTEs.
    
    Example queries this class handles:
    - "What is my sister's phone number?"
    - "What are my manager's interests?"
    - "Who is my brother's wife?"
    - "What does my mother like?" (for gift suggestions)
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_core_user_contact_by_role(
        self, role: str
    ) -> list[dict]:
        """
        Get contact info for core user's relationship by role.
        
        Example: "What is my sister's phone number?"
        Query: get_core_user_contact_by_role("sister")
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
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, role)
            return [
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "relationship": row["relationship"],
                    "personal_cell": row["personal_cell"],
                    "work_cell": row["work_cell"],
                    "secondary_cell": row["secondary_cell"],
                    "personal_email": row["personal_email"],
                    "work_email": row["work_email"],
                }
                for row in rows
            ]

    async def get_core_user_contact_interests(
        self, role: str
    ) -> list[dict]:
        """
        Get interests for core user's relationship by role.
        
        Example: "What does my mother like?"
        Query: get_core_user_contact_interests("mother")
        """
        query = """
            SELECT 
                p.id,
                p.name,
                p.interests,
                r.to_role as relationship
            FROM persons core
            JOIN relationships r ON core.id = r.from_person_id
            JOIN persons p ON r.to_person_id = p.id
            WHERE core.is_core_user = TRUE
              AND LOWER(r.to_role) = LOWER($1)
              AND r.is_active = TRUE
              AND p.status = 'active'
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, role)
            results = []
            for row in rows:
                interests_data = row["interests"]
                if isinstance(interests_data, str):
                    interests_data = json.loads(interests_data)
                
                interests = [Interest(**i) for i in interests_data] if interests_data else []
                results.append({
                    "id": str(row["id"]),
                    "name": row["name"],
                    "relationship": row["relationship"],
                    "interests": [
                        {
                            "name": i.name,
                            "type": i.type.value,
                            "level": i.level,
                        }
                        for i in interests
                    ],
                })
            return results

    async def traverse_from_core_user(
        self, path: list[str], max_depth: int = 5
    ) -> list[TraversalResult]:
        """
        Traverse relationships from core user following a path of roles.
        
        Example: "Who is my sister's husband?"
        Query: traverse_from_core_user(["sister", "husband"])
        
        Example: "What are my brother's wife's interests?"
        Query: traverse_from_core_user(["brother", "wife"])
        """
        if not path:
            return []

        # Build recursive CTE for path traversal
        # This is a simplified version - for complex paths, we unroll the recursion
        
        if len(path) == 1:
            # Single hop - use simple query
            query = """
                SELECT 
                    p.*,
                    r.to_role as final_role
                FROM persons core
                JOIN relationships r ON core.id = r.from_person_id
                JOIN persons p ON r.to_person_id = p.id
                WHERE core.is_core_user = TRUE
                  AND LOWER(r.to_role) = LOWER($1)
                  AND r.is_active = TRUE
                  AND p.status = 'active'
            """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, path[0])
                return [
                    TraversalResult(
                        person=self._row_to_person(row),
                        path=path,
                        depth=1,
                    )
                    for row in rows
                ]

        elif len(path) == 2:
            # Two hops - my sister's husband
            query = """
                SELECT 
                    p2.*
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
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, path[0], path[1])
                return [
                    TraversalResult(
                        person=self._row_to_person(row),
                        path=path,
                        depth=2,
                    )
                    for row in rows
                ]

        elif len(path) == 3:
            # Three hops - my sister's husband's mother
            query = """
                SELECT 
                    p3.*
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
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, path[0], path[1], path[2])
                return [
                    TraversalResult(
                        person=self._row_to_person(row),
                        path=path,
                        depth=3,
                    )
                    for row in rows
                ]

        else:
            # For deeper paths, use recursive CTE
            return await self._recursive_traverse(path, max_depth)

    async def _recursive_traverse(
        self, path: list[str], max_depth: int
    ) -> list[TraversalResult]:
        """
        Generic recursive traversal for arbitrary depth paths.
        
        Uses PostgreSQL recursive CTE.
        """
        query = """
            WITH RECURSIVE path_traversal AS (
                -- Base case: start from core user's first relationship
                SELECT 
                    p.id,
                    p.name,
                    1 as depth,
                    ARRAY[r.to_role] as path_taken,
                    p.id as current_node
                FROM persons core
                JOIN relationships r ON core.id = r.from_person_id
                JOIN persons p ON r.to_person_id = p.id
                WHERE core.is_core_user = TRUE
                  AND LOWER(r.to_role) = LOWER($1)
                  AND r.is_active = TRUE
                  AND p.status = 'active'
                
                UNION ALL
                
                -- Recursive case: follow the path
                SELECT 
                    p.id,
                    p.name,
                    pt.depth + 1,
                    pt.path_taken || r.to_role,
                    p.id
                FROM path_traversal pt
                JOIN relationships r ON pt.current_node = r.from_person_id
                JOIN persons p ON r.to_person_id = p.id
                WHERE pt.depth < $2
                  AND r.is_active = TRUE
                  AND p.status = 'active'
            )
            SELECT DISTINCT pt.*, p.*
            FROM path_traversal pt
            JOIN persons p ON pt.current_node = p.id
            WHERE pt.depth = $3
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                query, 
                path[0] if path else "", 
                len(path),
                len(path)
            )
            
            # Filter results that match the exact path
            results = []
            for row in rows:
                path_taken = row["path_taken"]
                if self._path_matches(path_taken, path):
                    results.append(
                        TraversalResult(
                            person=self._row_to_person(row),
                            path=path,
                            depth=row["depth"],
                        )
                    )
            return results

    def _path_matches(self, actual: list[str], expected: list[str]) -> bool:
        """Check if the traversed path matches expected roles."""
        if len(actual) != len(expected):
            return False
        return all(
            a.lower() == e.lower() 
            for a, e in zip(actual, expected)
        )

    async def find_person_by_name(
        self, name: str
    ) -> list[dict]:
        """
        Find a person by name and return their info with relationships to core user.
        
        Example: "What is Alice's phone number?"
        """
        query = """
            SELECT 
                p.*,
                r.to_role as relationship_to_core,
                r.category
            FROM persons p
            LEFT JOIN relationships r ON p.id = r.to_person_id
            LEFT JOIN persons core ON r.from_person_id = core.id AND core.is_core_user = TRUE
            WHERE (LOWER(p.name) LIKE LOWER($1) OR $2 = ANY(SELECT LOWER(unnest(p.aliases))))
              AND p.status = 'active'
        """
        name_lower = name.lower().strip()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, f"%{name}%", name_lower)
            results = []
            for row in rows:
                person = self._row_to_person(row)
                results.append({
                    "person": person,
                    "relationship_to_core": row["relationship_to_core"],
                    "category": row["category"],
                })
            return results

    async def get_person_with_interests_by_name(
        self, name: str
    ) -> list[dict]:
        """
        Get person's interests by name.
        
        Example: "What does Rajesh like?"
        """
        results = await self.find_person_by_name(name)
        return [
            {
                "id": str(r["person"].id),
                "name": r["person"].name,
                "relationship": r["relationship_to_core"],
                "interests": [
                    {
                        "name": i.name,
                        "type": i.type.value,
                        "level": i.level,
                    }
                    for i in r["person"].interests
                ],
                "expertise": r["person"].expertise,
                "country": r["person"].country,
                "city": r["person"].city,
            }
            for r in results
        ]

    async def get_contact_info_by_name(
        self, name: str
    ) -> list[dict]:
        """
        Get contact information for a person by name.
        
        Example: "What is Alice's phone number?"
        """
        results = await self.find_person_by_name(name)
        return [
            {
                "id": str(r["person"].id),
                "name": r["person"].name,
                "relationship": r["relationship_to_core"],
                "personal_cell": r["person"].personal_cell,
                "work_cell": r["person"].work_cell,
                "secondary_cell": r["person"].secondary_cell,
                "personal_email": r["person"].personal_email,
                "work_email": r["person"].work_email,
            }
            for r in results
        ]

    async def get_most_contacted_this_week(
        self, limit: int = 10
    ) -> list[dict]:
        """
        Get the most contacted people this week.
        
        Example: "Who have I talked to most this week?"
        """
        query = """
            SELECT 
                p.id,
                p.name,
                r.to_role as relationship,
                (r.connection_counts->>'text_count_past_one_week')::int as texts,
                (r.connection_counts->>'call_count_past_one_week')::int as calls,
                (r.connection_counts->>'meet_count_past_one_week')::int as meets
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
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "relationship": row["relationship"],
                    "texts_this_week": row["texts"] or 0,
                    "calls_this_week": row["calls"] or 0,
                    "meets_this_week": row["meets"] or 0,
                }
                for row in rows
            ]

    def _row_to_person(self, row: asyncpg.Record) -> Person:
        """Convert database row to Person model."""
        interests_data = row.get("interests", [])
        if isinstance(interests_data, str):
            interests_data = json.loads(interests_data)
        
        from .models import Interest
        interests = [Interest(**i) for i in interests_data] if interests_data else []
        
        return Person(
            id=row["id"],
            name=row["name"],
            aliases=row.get("aliases") or [],
            is_core_user=row.get("is_core_user", False),
            status=PersonStatus(row.get("status", "active")),
            work_email=row.get("work_email"),
            personal_email=row.get("personal_email"),
            work_cell=row.get("work_cell"),
            personal_cell=row.get("personal_cell"),
            secondary_cell=row.get("secondary_cell"),
            company=row.get("company"),
            latest_title=row.get("latest_title"),
            expertise=row.get("expertise"),
            address=row.get("address"),
            country=row.get("country", "Unknown"),
            city=row.get("city"),
            state=row.get("state"),
            instagram_handle=row.get("instagram_handle"),
            religion=row.get("religion"),
            ethnicity=row.get("ethnicity"),
            country_of_birth=row.get("country_of_birth"),
            city_of_birth=row.get("city_of_birth"),
            interests=interests,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

