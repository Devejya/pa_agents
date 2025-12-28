"""
User Network Service Client SDK.

This client provides a simple interface for the agent to communicate
with the User Network microservice.
"""

import logging
from typing import Any, Optional
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class UserNetworkClientError(Exception):
    """Base exception for User Network client errors."""
    pass


class UserNetworkClient:
    """
    HTTP client for the User Network Service.
    
    Usage:
        client = UserNetworkClient(
            base_url="http://localhost:8001",
            api_key="un_your_api_key"
        )
        
        # Get sister's contact info
        contacts = await client.get_contact_by_role("sister")
        
        # Get mother's interests
        interests = await client.get_interests_by_role("mother")
        
        # Traverse relationships
        results = await client.traverse(["sister", "husband"])
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ):
        """
        Initialize the client.
        
        Args:
            base_url: Base URL of the User Network service (e.g., http://localhost:8001)
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-API-Key": self.api_key},
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> Any:
        """Make an HTTP request."""
        client = await self._get_client()
        
        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                json=json,
            )
            response.raise_for_status()
            
            if response.status_code == 204:
                return None
            
            return response.json()
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise UserNetworkClientError(
                f"Request failed: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise UserNetworkClientError(f"Request failed: {e}") from e

    # ========================================================================
    # Query Endpoints (for Agent)
    # ========================================================================

    async def get_contact_by_role(self, role: str) -> list[dict]:
        """
        Get contact info for core user's relationship by role.
        
        Example: "What is my sister's phone number?"
        
        Args:
            role: Relationship role (e.g., "sister", "mother", "manager")
            
        Returns:
            List of contacts matching the role
        """
        return await self._request(
            "GET",
            "/api/v1/query/contact-by-role",
            params={"role": role},
        )

    async def get_interests_by_role(self, role: str) -> list[dict]:
        """
        Get interests for core user's relationship by role.
        
        Example: "What does my mother like?"
        
        Args:
            role: Relationship role (e.g., "mother", "brother")
            
        Returns:
            List of persons with their interests
        """
        return await self._request(
            "GET",
            "/api/v1/query/interests-by-role",
            params={"role": role},
        )

    async def get_contact_by_name(self, name: str) -> list[dict]:
        """
        Get contact info for a person by name.
        
        Example: "What is Alice's phone number?"
        
        Args:
            name: Person's name or alias
            
        Returns:
            List of matching contacts
        """
        return await self._request(
            "GET",
            "/api/v1/query/contact-by-name",
            params={"name": name},
        )

    async def get_interests_by_name(self, name: str) -> list[dict]:
        """
        Get interests for a person by name.
        
        Example: "What does Rajesh like?"
        
        Args:
            name: Person's name or alias
            
        Returns:
            List of persons with their interests
        """
        return await self._request(
            "GET",
            "/api/v1/query/interests-by-name",
            params={"name": name},
        )

    async def traverse(self, path: list[str]) -> list[dict]:
        """
        Traverse relationships from core user.
        
        Example: "Who is my sister's husband?"
        Call: traverse(["sister", "husband"])
        
        Args:
            path: List of roles to traverse (e.g., ["sister", "husband"])
            
        Returns:
            List of persons at the end of the path
        """
        return await self._request(
            "GET",
            "/api/v1/query/traverse",
            params={"path": ",".join(path)},
        )

    async def get_most_contacted(self, limit: int = 10) -> list[dict]:
        """
        Get the most contacted people this week.
        
        Example: "Who have I talked to most this week?"
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of most contacted persons
        """
        return await self._request(
            "GET",
            "/api/v1/query/most-contacted",
            params={"limit": limit},
        )

    # ========================================================================
    # CRUD Endpoints
    # ========================================================================

    async def get_core_user(self) -> Optional[dict]:
        """Get the core user."""
        try:
            return await self._request("GET", "/api/v1/persons/core-user")
        except UserNetworkClientError:
            return None

    async def create_person(self, data: dict) -> dict:
        """Create a new person."""
        return await self._request("POST", "/api/v1/persons", json=data)

    async def get_person(self, person_id: UUID) -> Optional[dict]:
        """Get a person by ID."""
        try:
            return await self._request("GET", f"/api/v1/persons/{person_id}")
        except UserNetworkClientError:
            return None

    async def update_person(self, person_id: UUID, data: dict) -> Optional[dict]:
        """Update a person."""
        try:
            return await self._request("PATCH", f"/api/v1/persons/{person_id}", json=data)
        except UserNetworkClientError:
            return None

    async def delete_person(self, person_id: UUID) -> bool:
        """Delete a person."""
        try:
            await self._request("DELETE", f"/api/v1/persons/{person_id}")
            return True
        except UserNetworkClientError:
            return False

    async def add_interest(
        self, 
        person_id: UUID, 
        interest_name: str, 
        interest_type: str = "other",
        level: int = 50
    ) -> dict:
        """
        Atomically add an interest to a person.
        
        This is safe for parallel calls - won't lose interests due to race conditions.
        """
        return await self._request(
            "POST",
            f"/api/v1/persons/{person_id}/interests",
            params={
                "interest_name": interest_name,
                "interest_type": interest_type,
                "level": level,
            },
        )

    async def search_persons(self, query: str) -> list[dict]:
        """Full-text search across persons."""
        return await self._request(
            "GET",
            "/api/v1/persons/search",
            params={"q": query},
        )

    async def find_person_by_name(self, name: str) -> list[dict]:
        """Find persons by name or alias."""
        return await self._request(
            "GET",
            "/api/v1/persons/find",
            params={"name": name},
        )

    async def create_relationship(self, data: dict) -> dict:
        """Create a new relationship."""
        return await self._request("POST", "/api/v1/relationships", json=data)

    async def get_relationship(self, rel_id: UUID) -> Optional[dict]:
        """Get a relationship by ID."""
        try:
            return await self._request("GET", f"/api/v1/relationships/{rel_id}")
        except UserNetworkClientError:
            return None

    async def get_person_relationships(
        self, person_id: UUID, include_inactive: bool = False
    ) -> list[dict]:
        """Get all relationships for a person."""
        return await self._request(
            "GET",
            f"/api/v1/relationships/person/{person_id}",
            params={"include_inactive": include_inactive},
        )

    async def end_relationship(self, rel_id: UUID) -> Optional[dict]:
        """Mark a relationship as ended."""
        try:
            return await self._request("POST", f"/api/v1/relationships/{rel_id}/end")
        except UserNetworkClientError:
            return None

    async def health_check(self) -> bool:
        """Check if the service is healthy."""
        try:
            result = await self._request("GET", "/health")
            return result.get("status") == "healthy"
        except UserNetworkClientError:
            return False


# Convenience function for creating a client from environment
def create_client_from_env() -> UserNetworkClient:
    """
    Create a UserNetworkClient from environment variables.
    
    Environment variables:
        USER_NETWORK_URL: Base URL of the service
        USER_NETWORK_API_KEY: API key for authentication
    """
    import os
    
    base_url = os.getenv("USER_NETWORK_URL", "http://localhost:8001")
    api_key = os.getenv("USER_NETWORK_API_KEY", "")
    
    if not api_key:
        logger.warning("USER_NETWORK_API_KEY not set")
    
    return UserNetworkClient(base_url=base_url, api_key=api_key)

