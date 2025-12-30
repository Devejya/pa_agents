"""
Authentication utilities for Yennifer API.

Handles JWT tokens and user session management.
"""

import logging
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import get_settings

logger = logging.getLogger(__name__)

# Security scheme for JWT
security = HTTPBearer(auto_error=False)

# Context variable for current user ID (used for RLS)
_current_user_id: ContextVar[Optional[UUID]] = ContextVar("current_user_id", default=None)
_current_user_email: ContextVar[Optional[str]] = ContextVar("current_user_email", default=None)


def get_current_user_id() -> Optional[UUID]:
    """Get the current user's ID from context."""
    return _current_user_id.get()


def set_current_user_id(user_id: Optional[UUID]) -> None:
    """Set the current user's ID in context."""
    _current_user_id.set(user_id)


def get_current_user_email() -> Optional[str]:
    """Get the current user's email from context."""
    return _current_user_email.get()


def set_current_user_email(email: Optional[str]) -> None:
    """Set the current user's email in context."""
    _current_user_email.set(email)


class UserInfo(BaseModel):
    """User information from Google OAuth."""
    email: str
    name: str
    picture: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    # Google's unique user ID (sub claim)
    google_user_id: Optional[str] = None


class TokenData(BaseModel):
    """JWT token payload."""
    user_id: Optional[str] = None  # UUID as string (for new tokens)
    email: str
    name: str
    picture: Optional[str] = None
    exp: datetime
    iat: datetime


def create_access_token(user_info: UserInfo, user_id: Optional[UUID] = None) -> str:
    """
    Create a JWT access token for an authenticated user.
    
    Args:
        user_info: User information from Google OAuth
        user_id: User's internal UUID (if known)
        
    Returns:
        JWT token string
    """
    settings = get_settings()
    
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.jwt_expire_hours)
    
    payload = {
        "email": user_info.email,
        "name": user_info.name,
        "picture": user_info.picture,
        "exp": expire,
        "iat": now,
    }
    
    # Include user_id if available (new multi-tenant tokens)
    if user_id:
        payload["user_id"] = str(user_id)
    
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        TokenData if valid, None otherwise
    """
    settings = get_settings()
    
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenData(**payload)
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenData:
    """
    FastAPI dependency to get the current authenticated user.
    
    Checks for JWT token in:
    1. Authorization header (Bearer token)
    2. Cookie (auth_token)
    
    Also sets context variables for user_id and email for use in RLS
    and other per-user operations.
    
    Args:
        request: FastAPI request
        credentials: Bearer token from header
        
    Returns:
        TokenData for authenticated user
        
    Raises:
        HTTPException: If not authenticated or token invalid
    """
    token = None
    
    # Try Authorization header first
    if credentials:
        token = credentials.credentials
    
    # Fall back to cookie
    if not token:
        token = request.cookies.get("auth_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = decode_access_token(token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify email is still in whitelist
    settings = get_settings()
    if not settings.is_email_allowed(token_data.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your email is not authorized.",
        )
    
    # Set context variables for per-user operations
    set_current_user_email(token_data.email)
    if token_data.user_id:
        try:
            set_current_user_id(UUID(token_data.user_id))
        except ValueError:
            logger.warning(f"Invalid user_id in token: {token_data.user_id}")
    
    return token_data


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenData]:
    """
    FastAPI dependency to optionally get the current user.
    
    Returns None if not authenticated instead of raising an exception.
    """
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None

