"""
User Network API Client.

HTTP client for interacting with the User Network service.
Used by background jobs for sync state management, person lookups, etc.

Usage:
    from app.core.user_network_client import UserNetworkClient
    
    client = UserNetworkClient()
    
    # Get or create sync state
    state = await client.get_or_create_sync_state("user@email.com", "google_contacts")
    
    # Update sync state after sync
    await client.update_sync_state("user@email.com", "google_contacts", {
        "sync_token": "new_token",
        "last_sync_added": 5,
        "last_sync_updated": 3,
    })
"""

import logging
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


class UserNetworkAPIError(Exception):
    """Exception for User Network API errors."""
    def __init__(self, status_code: int, message: str, details: Optional[dict] = None):
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(f"User Network API error ({status_code}): {message}")


class UserNetworkClient:
    """
    HTTP client for User Network service.
    
    Handles:
    - Sync state management
    - External ID lookups
    - Person CRUD operations
    - Sync conflict management
    - Sync logging
    
    Important: All operations now require a user_id for Row-Level Security (RLS).
    The user_id is sent as the X-User-ID header with each request.
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        user_id: Optional[str] = None,
    ):
        """
        Initialize the client.
        
        Args:
            base_url: User Network API base URL (default: from settings)
            api_key: API key for authentication (default: from settings)
            timeout: Request timeout in seconds
            user_id: User ID for RLS enforcement (required for most operations)
        """
        settings = get_settings()
        self.base_url = (base_url or settings.user_network_api_url).rstrip('/')
        self.api_key = api_key or settings.user_network_api_key
        self.timeout = timeout
        self.user_id = user_id
        
        # Validate configuration
        if not self.api_key:
            logger.warning("User Network API key not configured")
    
    def with_user(self, user_id: str) -> "UserNetworkClient":
        """
        Create a new client instance with the specified user_id for RLS.
        
        Args:
            user_id: User ID (UUID string) for RLS enforcement
            
        Returns:
            New UserNetworkClient instance with user_id set
        """
        return UserNetworkClient(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            user_id=user_id,
        )
    
    def _get_headers(self) -> dict:
        """Get headers for API requests, including X-User-ID for RLS."""
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.user_id:
            headers["X-User-ID"] = str(self.user_id)
        return headers
    
    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        """
        Make an HTTP request to the User Network API.
        
        Args:
            method: HTTP method (GET, POST, PATCH, PUT, DELETE)
            path: API path (e.g., "/api/v1/sync/state/user@email.com")
            json: JSON body for POST/PATCH/PUT
            params: Query parameters
            
        Returns:
            Response JSON data
            
        Raises:
            UserNetworkAPIError: On API errors
        """
        url = f"{self.base_url}{path}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    json=json,
                    params=params,
                )
                
                # Handle success
                if response.status_code in (200, 201):
                    return response.json()
                
                # Handle 204 No Content
                if response.status_code == 204:
                    return None
                
                # Handle errors
                try:
                    error_data = response.json()
                    message = error_data.get("detail", str(error_data))
                except Exception:
                    message = response.text or f"HTTP {response.status_code}"
                
                raise UserNetworkAPIError(
                    status_code=response.status_code,
                    message=message,
                    details=error_data if isinstance(error_data, dict) else None,
                )
                
        except httpx.TimeoutException:
            raise UserNetworkAPIError(
                status_code=408,
                message=f"Request timed out after {self.timeout}s",
            )
        except httpx.RequestError as e:
            raise UserNetworkAPIError(
                status_code=503,
                message=f"Connection error: {str(e)}",
            )
    
    # =========================================================================
    # Sync State Methods
    # =========================================================================
    
    async def get_sync_state(
        self,
        user_id: str,
        provider: str,
    ) -> Optional[dict]:
        """
        Get sync state for a user and provider.
        
        Args:
            user_id: User email or ID
            provider: Provider name (e.g., "google_contacts")
            
        Returns:
            Sync state dict or None if not found
        """
        try:
            return await self._request(
                "GET",
                f"/api/v1/sync/state/{user_id}/{provider}",
            )
        except UserNetworkAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def get_or_create_sync_state(
        self,
        user_id: str,
        provider: str,
    ) -> dict:
        """
        Get or create sync state for a user and provider.
        
        Args:
            user_id: User email or ID
            provider: Provider name (e.g., "google_contacts")
            
        Returns:
            Sync state dict
        """
        return await self._request(
            "POST",
            f"/api/v1/sync/state/{user_id}/{provider}",
        )
    
    async def get_all_sync_states(self, user_id: str) -> list[dict]:
        """
        Get all sync states for a user.
        
        Args:
            user_id: User email or ID
            
        Returns:
            List of sync state dicts
        """
        return await self._request(
            "GET",
            f"/api/v1/sync/state/{user_id}",
        )
    
    async def update_sync_state(
        self,
        user_id: str,
        provider: str,
        updates: dict,
    ) -> dict:
        """
        Update sync state.
        
        Args:
            user_id: User email or ID
            provider: Provider name
            updates: Dict of fields to update (sync_token, sync_status, etc.)
            
        Returns:
            Updated sync state dict
        """
        return await self._request(
            "PATCH",
            f"/api/v1/sync/state/{user_id}/{provider}",
            json=updates,
        )
    
    async def start_sync(self, user_id: str, provider: str) -> dict:
        """Mark sync as started."""
        return await self.update_sync_state(user_id, provider, {
            "sync_status": "syncing",
        })
    
    async def complete_sync(
        self,
        user_id: str,
        provider: str,
        sync_token: Optional[str] = None,
        added: int = 0,
        updated: int = 0,
        is_full_sync: bool = False,
        next_sync_minutes: int = 30,
    ) -> dict:
        """
        Mark sync as completed.
        
        Args:
            user_id: User email or ID
            provider: Provider name
            sync_token: New sync token from provider
            added: Number of records added
            updated: Number of records updated
            is_full_sync: Whether this was a full sync
            next_sync_minutes: Minutes until next sync
        """
        from datetime import timedelta
        
        now = datetime.utcnow()
        updates = {
            "sync_status": "idle",
            "last_sync_added": added,
            "last_sync_updated": updated,
            "consecutive_failures": 0,
            "error_message": None,
            "next_sync_at": (now + timedelta(minutes=next_sync_minutes)).isoformat(),
        }
        
        if sync_token:
            updates["sync_token"] = sync_token
        
        if is_full_sync:
            updates["last_full_sync_at"] = now.isoformat()
        else:
            updates["last_incremental_sync_at"] = now.isoformat()
        
        return await self.update_sync_state(user_id, provider, updates)
    
    async def fail_sync(
        self,
        user_id: str,
        provider: str,
        error_message: str,
    ) -> dict:
        """
        Mark sync as failed.
        
        Implements exponential backoff for retries.
        """
        from datetime import timedelta
        
        # Get current state to check failure count
        state = await self.get_sync_state(user_id, provider)
        current_failures = state.get("consecutive_failures", 0) if state else 0
        new_failures = current_failures + 1
        
        # Exponential backoff: 5, 10, 20, 40, 80 min... max 24 hours
        backoff_minutes = min(5 * (2 ** new_failures), 24 * 60)
        
        # Mark as failed after 5 consecutive failures
        status = "failed" if new_failures >= 5 else "idle"
        
        now = datetime.utcnow()
        return await self.update_sync_state(user_id, provider, {
            "sync_status": status,
            "error_message": error_message,
            "consecutive_failures": new_failures,
            "next_sync_at": (now + timedelta(minutes=backoff_minutes)).isoformat(),
        })
    
    # =========================================================================
    # External ID Methods
    # =========================================================================
    
    async def lookup_by_external_id(
        self,
        provider: str,
        external_id: str,
    ) -> Optional[dict]:
        """
        Find person by external ID.
        
        Args:
            provider: Provider name (e.g., "google")
            external_id: External ID from provider
            
        Returns:
            External ID mapping dict or None if not found
        """
        try:
            return await self._request(
                "GET",
                f"/api/v1/sync/external-ids/lookup/{provider}/{external_id}",
            )
        except UserNetworkAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def get_person_external_ids(
        self,
        person_id: str,
        provider: Optional[str] = None,
    ) -> list[dict]:
        """
        Get all external IDs for a person.
        
        Args:
            person_id: Person UUID
            provider: Optional provider filter
            
        Returns:
            List of external ID dicts
        """
        params = {"provider": provider} if provider else None
        return await self._request(
            "GET",
            f"/api/v1/sync/external-ids/{person_id}",
            params=params,
        )
    
    async def upsert_external_id(
        self,
        person_id: str,
        provider: str,
        external_id: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Create or update external ID mapping.
        
        Args:
            person_id: Person UUID
            provider: Provider name
            external_id: External ID
            metadata: Optional provider-specific metadata
            
        Returns:
            External ID mapping dict
        """
        params = {"external_id": external_id}
        if metadata:
            params["metadata"] = metadata
        
        return await self._request(
            "PUT",
            f"/api/v1/sync/external-ids/{person_id}/{provider}",
            params=params,
        )
    
    # =========================================================================
    # Person Methods
    # =========================================================================
    # 
    # WARNING: These methods bypass Row-Level Security (RLS).
    # For user-facing endpoints, use PersonsRepository from app.db instead,
    # which enforces RLS via owner_user_id.
    #
    # These methods should ONLY be used by:
    # - Background sync jobs (contact_sync.py)
    # - Admin operations
    # - System-level operations that need cross-tenant access
    # =========================================================================
    
    async def get_person(self, person_id: str) -> Optional[dict]:
        """
        Get a person by ID.
        
        WARNING: Bypasses RLS. For user-facing access, use PersonsRepository.
        """
        try:
            return await self._request(
                "GET",
                f"/api/v1/persons/{person_id}",
            )
        except UserNetworkAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def find_person_by_email(self, email: str) -> Optional[dict]:
        """Find a person by email (searches work_email and personal_email)."""
        try:
            results = await self._request(
                "GET",
                "/api/v1/persons/find",
                params={"name": email},  # The find endpoint searches name and aliases
            )
            # Filter by email match
            email_lower = email.lower()
            for person in results:
                if (
                    person.get("work_email", "").lower() == email_lower or
                    person.get("personal_email", "").lower() == email_lower
                ):
                    return person
            return None
        except UserNetworkAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def search_persons(self, query: str) -> list[dict]:
        """
        Search persons by query.
        
        WARNING: Bypasses RLS. For user-facing access, use PersonsRepository.search().
        """
        return await self._request(
            "GET",
            "/api/v1/persons/search",
            params={"q": query},
        )
    
    async def create_person(self, data: dict) -> dict:
        """Create a new person."""
        return await self._request(
            "POST",
            "/api/v1/persons",
            json=data,
        )
    
    async def update_person(self, person_id: str, data: dict) -> dict:
        """Update a person."""
        return await self._request(
            "PATCH",
            f"/api/v1/persons/{person_id}",
            json=data,
        )
    
    # =========================================================================
    # Sync Conflict Methods
    # =========================================================================
    
    async def get_pending_conflicts(self, user_id: str) -> list[dict]:
        """Get pending sync conflicts for a user."""
        return await self._request(
            "GET",
            f"/api/v1/sync/conflicts/{user_id}",
        )
    
    async def create_conflict(
        self,
        user_id: str,
        provider: str,
        conflict_type: str,
        local_data: dict,
        remote_data: dict,
        person_id: Optional[str] = None,
        external_id: Optional[str] = None,
        suggested_resolution: Optional[dict] = None,
    ) -> dict:
        """Create a sync conflict for manual resolution."""
        # Note: This would need a POST endpoint in user_network
        # For now, we'll skip conflict creation and log instead
        logger.warning(
            f"Sync conflict for {user_id}: {conflict_type} "
            f"(person_id={person_id}, external_id={external_id})"
        )
        return {
            "user_id": user_id,
            "conflict_type": conflict_type,
            "status": "logged",
        }
    
    # =========================================================================
    # Sync Log Methods
    # =========================================================================
    
    async def get_sync_logs(self, user_id: str, limit: int = 20) -> list[dict]:
        """Get recent sync logs for a user."""
        return await self._request(
            "GET",
            f"/api/v1/sync/logs/{user_id}",
            params={"limit": limit},
        )
    
    # =========================================================================
    # Core User Methods
    # =========================================================================
    
    async def get_core_user(self) -> Optional[dict]:
        """
        Get the core user (main user of the system).
        
        WARNING: Bypasses RLS. For user-facing access, use PersonsRepository.get_core_user().
        """
        try:
            return await self._request(
                "GET",
                "/api/v1/persons/core-user",
            )
        except UserNetworkAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    async def get_all_core_users(self) -> list[dict]:
        """
        Get all core users (for multi-tenant scenarios).
        
        Currently returns single core user as a list.
        """
        core_user = await self.get_core_user()
        return [core_user] if core_user else []
    
    async def list_persons(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        List all persons with pagination.
        
        WARNING: Bypasses RLS - returns ALL persons across ALL users.
        For user-facing access, use PersonsRepository.list_contacts().
        Only use this for background sync or admin operations.
        """
        return await self._request(
            "GET",
            "/api/v1/persons",
            params={"limit": limit, "offset": offset},
        )
    
    async def get_relationships(self, person_id: str) -> list[dict]:
        """
        Get relationships for a person.
        
        WARNING: Bypasses RLS. For user-facing access, use PersonsRepository.get_relationships().
        """
        try:
            return await self._request(
                "GET",
                f"/api/v1/relationships/person/{person_id}",
            )
        except UserNetworkAPIError as e:
            if e.status_code == 404:
                return []
            raise
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> bool:
        """Check if User Network service is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False


# Global client instance (lazy initialization)
_client: Optional[UserNetworkClient] = None


def get_user_network_client(user_id: Optional[str] = None) -> UserNetworkClient:
    """
    Get the User Network client instance.
    
    Args:
        user_id: Optional user ID for RLS enforcement. If provided, returns
                 a client configured to send X-User-ID header with requests.
                 Required for most operations to comply with RLS policies.
    
    Returns:
        UserNetworkClient instance. If user_id is provided, returns a new
        instance with user context. Otherwise returns the global instance
        (for backwards compatibility with system-level operations).
    """
    global _client
    
    # If user_id provided, return a client with user context
    if user_id:
        if _client is None:
            _client = UserNetworkClient()
        return _client.with_user(user_id)
    
    # Otherwise return the global client without user context
    # (for backwards compatibility with admin/system operations)
    if _client is None:
        _client = UserNetworkClient()
    return _client

