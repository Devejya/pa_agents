"""
Security utilities for API key authentication.
"""

import hashlib
import secrets
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import get_settings

# API Key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: Optional[str]) -> bool:
    """
    Verify if the provided API key is valid.
    
    Uses constant-time comparison to prevent timing attacks.
    """
    settings = get_settings()
    valid_keys = settings.api_keys_list
    
    if not valid_keys:
        # No API keys configured - allow in development only
        if settings.environment == "development":
            return True
        return False
    
    if not api_key:
        return False
    
    # Use constant-time comparison
    for valid_key in valid_keys:
        if secrets.compare_digest(api_key, valid_key):
            return True
    
    return False


async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Dependency to validate API key from request header.
    
    Usage:
        @app.get("/protected")
        async def protected_route(api_key: str = Depends(get_api_key)):
            ...
    """
    if not verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


def generate_api_key(prefix: str = "un") -> str:
    """
    Generate a new API key.
    
    Format: {prefix}_{random_32_chars}
    Example: un_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
    """
    random_part = secrets.token_urlsafe(24)  # 32 characters
    return f"{prefix}_{random_part}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage.
    
    Note: Currently using plain comparison for simplicity.
    For production, consider storing hashed keys.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()

