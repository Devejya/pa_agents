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

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import get_settings

logger = logging.getLogger(__name__)

# Token storage directory
TOKENS_DIR = Path(__file__).parent.parent.parent / "tokens"

# Google OAuth endpoints
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_token_path(email: str) -> Path:
    """Get the token file path for a user."""
    safe_email = email.replace("@", "_at_").replace(".", "_")
    return TOKENS_DIR / f"{safe_email}_google_token.json"


def _load_tokens(email: str) -> Optional[dict]:
    """Load Google OAuth tokens for a user."""
    token_path = _get_token_path(email)
    if not token_path.exists():
        logger.warning(f"No tokens found for {email}")
        return None
    with open(token_path, "r") as f:
        return json.load(f)


def _save_tokens(email: str, tokens: dict) -> None:
    """Save Google OAuth tokens for a user."""
    token_path = _get_token_path(email)
    TOKENS_DIR.mkdir(exist_ok=True)
    with open(token_path, "w") as f:
        json.dump(tokens, f, indent=2)


async def refresh_access_token(email: str) -> Optional[str]:
    """
    Refresh the access token for a user.
    
    Returns:
        New access token or None if refresh failed
    """
    tokens = _load_tokens(email)
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
        tokens["saved_at"] = datetime.now(timezone.utc).isoformat()
        if "refresh_token" in new_tokens:
            tokens["refresh_token"] = new_tokens["refresh_token"]
        
        _save_tokens(email, tokens)
        logger.info(f"Refreshed access token for {email}")
        
        return new_tokens["access_token"]


def get_google_credentials(email: str) -> Optional[Credentials]:
    """
    Get Google OAuth credentials for a user.
    
    Args:
        email: User's email address
        
    Returns:
        Google Credentials object or None if not available
    """
    tokens = _load_tokens(email)
    if not tokens:
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


def get_gmail_service(email: str) -> Any:
    """Get Gmail API service for a user."""
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build("gmail", "v1", credentials=creds)


def get_calendar_service(email: str) -> Any:
    """Get Google Calendar API service for a user."""
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build("calendar", "v3", credentials=creds)


def get_contacts_service(email: str) -> Any:
    """Get Google People (Contacts) API service for a user."""
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build("people", "v1", credentials=creds)


def get_drive_service(email: str) -> Any:
    """Get Google Drive API service for a user."""
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build("drive", "v3", credentials=creds)


def get_sheets_service(email: str) -> Any:
    """Get Google Sheets API service for a user."""
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build("sheets", "v4", credentials=creds)


def get_docs_service(email: str) -> Any:
    """Get Google Docs API service for a user."""
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build("docs", "v1", credentials=creds)


def get_slides_service(email: str) -> Any:
    """Get Google Slides API service for a user."""
    creds = get_google_credentials(email)
    if not creds:
        raise ValueError(f"No Google credentials for {email}. Please re-authenticate.")
    return build("slides", "v1", credentials=creds)

