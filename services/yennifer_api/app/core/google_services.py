"""
Google Services Client Module

Provides authenticated clients for Google Workspace APIs:
- Gmail
- Calendar
- Contacts
- Drive
- Sheets
- Docs
- Slides
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import get_settings

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# In-memory token cache for sync access
# Structure: {email: {tokens: dict, loaded_at: datetime}}
_token_cache: dict[str, dict] = {}


async def load_user_tokens(email: str) -> Optional[dict]:
    """
    Load user tokens from the database into the cache.
    
    Call this before using sync functions like get_google_credentials().
    
    Args:
        email: User's email address
        
    Returns:
        Token dictionary or None if not found
    """
    from ..routes.auth import get_google_tokens
    
    tokens = await get_google_tokens(email)
    if tokens:
        _token_cache[email] = {
            'tokens': tokens,
            'loaded_at': datetime.now(timezone.utc),
        }
        logger.debug(f"Loaded tokens into cache for {email}")
    return tokens


def _get_cached_tokens(email: str) -> Optional[dict]:
    """
    Get tokens from the in-memory cache.
    
    Note: Call load_user_tokens() first to populate the cache.
    
    Args:
        email: User's email address
        
    Returns:
        Token dictionary or None if not cached
    """
    cached = _token_cache.get(email)
    if cached:
        return cached['tokens']
    return None


def clear_token_cache(email: Optional[str] = None) -> None:
    """
    Clear the token cache.
    
    Args:
        email: Clear specific user, or all if None
    """
    global _token_cache
    if email:
        _token_cache.pop(email, None)
    else:
        _token_cache = {}


async def refresh_access_token(email: str) -> Optional[str]:
    """
    Refresh the access token for a user.
    
    Returns:
        New access token or None if refresh failed
    """
    from ..db import get_db_pool
    from ..db.token_repository import TokenRepository
    
    # Get tokens from cache or DB
    tokens = _get_cached_tokens(email)
    if not tokens:
        tokens = await load_user_tokens(email)
    
    if not tokens or not tokens.get("refresh_token"):
        logger.error(f"No refresh token for {email}")
        return None
    
    settings = get_settings()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.text}")
            return None
        
        new_tokens = response.json()
        
        # Update stored tokens (keep refresh_token if not returned)
        tokens["access_token"] = new_tokens["access_token"]
        tokens["expires_in"] = new_tokens.get("expires_in")
        if "refresh_token" in new_tokens:
            tokens["refresh_token"] = new_tokens["refresh_token"]
        
        # Save to database
        try:
            pool = await get_db_pool()
            repo = TokenRepository(pool)
            await repo.save_tokens(email, tokens, provider="google")
            
            # Update cache
            _token_cache[email] = {
                'tokens': tokens,
                'loaded_at': datetime.now(timezone.utc),
            }
            
            logger.info(f"Refreshed access token for {email}")
        except Exception as e:
            logger.error(f"Failed to save refreshed tokens: {e}")
            # Continue anyway - we have the new token
        
        return new_tokens["access_token"]


def get_google_credentials(email: str) -> Optional[Credentials]:
    """
    Get Google OAuth credentials for a user.
    
    Note: Call load_user_tokens() first if not already cached.
    
    Args:
        email: User's email address
        
    Returns:
        Google Credentials object or None if not available
    """
    tokens = _get_cached_tokens(email)
    if not tokens:
        logger.warning(f"No cached tokens for {email}. Call load_user_tokens() first.")
        return None
    
    settings = get_settings()
    
    # Create credentials object
    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URL,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    
    return creds


async def get_google_credentials_async(email: str) -> Optional[Credentials]:
    """
    Get Google OAuth credentials for a user (async version).
    
    Loads tokens from database if not cached.
    
    Args:
        email: User's email address
        
    Returns:
        Google Credentials object or None if not available
    """
    # Try cache first
    tokens = _get_cached_tokens(email)
    
    # Load from DB if not cached
    if not tokens:
        tokens = await load_user_tokens(email)
    
    if not tokens:
        logger.warning(f"No tokens found for {email}")
        return None
    
    settings = get_settings()
    
    return Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URL,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )


def build_google_service(email: str, service_name: str, version: str) -> Any:
    """
    Build a Google API service client.
    
    Note: Call load_user_tokens() first if not already cached.
    
    Args:
        email: User's email address
        service_name: API service name (gmail, calendar, people, drive, sheets, docs, slides)
        version: API version (e.g., v1, v3)
        
    Returns:
        Google API service resource
        
    Raises:
        ValueError: If no credentials available
    """
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build(service_name, version, credentials=creds)


async def build_google_service_async(email: str, service_name: str, version: str) -> Any:
    """
    Build a Google API service client (async version).
    
    Loads tokens from database if not cached.
    
    Args:
        email: User's email address
        service_name: API service name (gmail, calendar, people, drive, sheets, docs, slides)
        version: API version (e.g., v1, v3)
        
    Returns:
        Google API service resource
        
    Raises:
        ValueError: If no credentials available
    """
    creds = await get_google_credentials_async(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build(service_name, version, credentials=creds)


def get_gmail_service(email: str) -> Any:
    """Get Gmail API service for a user."""
    return build_google_service(email, "gmail", "v1")


def get_calendar_service(email: str) -> Any:
    """Get Google Calendar API service for a user."""
    return build_google_service(email, "calendar", "v3")


def get_contacts_service(email: str) -> Any:
    """Get Google People (Contacts) API service for a user."""
    return build_google_service(email, "people", "v1")


def get_drive_service(email: str) -> Any:
    """Get Google Drive API service for a user."""
    return build_google_service(email, "drive", "v3")


def get_sheets_service(email: str) -> Any:
    """Get Google Sheets API service for a user."""
    return build_google_service(email, "sheets", "v4")


def get_docs_service(email: str) -> Any:
    """Get Google Docs API service for a user."""
    return build_google_service(email, "docs", "v1")


def get_slides_service(email: str) -> Any:
    """Get Google Slides API service for a user."""
    return build_google_service(email, "slides", "v1")


# Async convenience functions
async def get_gmail_service_async(email: str) -> Any:
    """Get Gmail API service for a user (async)."""
    return await build_google_service_async(email, "gmail", "v1")


async def get_calendar_service_async(email: str) -> Any:
    """Get Google Calendar API service for a user (async)."""
    return await build_google_service_async(email, "calendar", "v3")


async def get_contacts_service_async(email: str) -> Any:
    """Get Google People (Contacts) API service for a user (async)."""
    return await build_google_service_async(email, "people", "v1")


async def get_drive_service_async(email: str) -> Any:
    """Get Google Drive API service for a user (async)."""
    return await build_google_service_async(email, "drive", "v3")


async def get_sheets_service_async(email: str) -> Any:
    """Get Google Sheets API service for a user (async)."""
    return await build_google_service_async(email, "sheets", "v4")


async def get_docs_service_async(email: str) -> Any:
    """Get Google Docs API service for a user (async)."""
    return await build_google_service_async(email, "docs", "v1")


async def get_slides_service_async(email: str) -> Any:
    """Get Google Slides API service for a user (async)."""
    return await build_google_service_async(email, "slides", "v1")
