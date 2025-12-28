"""
Authentication routes for Google OAuth.

Handles login, callback, logout, and user info endpoints.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..core.auth import TokenData, UserInfo, create_access_token, get_current_user
from ..core.config import get_settings

logger = logging.getLogger(__name__)

# Token storage directory
TOKENS_DIR = Path(__file__).parent.parent.parent / "tokens"
TOKENS_DIR.mkdir(exist_ok=True)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# OAuth scopes for Google Workspace integration
OAUTH_SCOPES = [
    # Basic authentication
    "openid",
    "email",
    "profile",
    # Gmail
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    # Calendar
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    # Contacts
    "https://www.googleapis.com/auth/contacts.readonly",
    # Drive
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    # Sheets
    "https://www.googleapis.com/auth/spreadsheets",
    # Docs
    "https://www.googleapis.com/auth/documents",
    # Slides
    "https://www.googleapis.com/auth/presentations",
]


class AuthResponse(BaseModel):
    """Response for successful authentication."""
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class UserResponse(BaseModel):
    """Response for current user info."""
    email: str
    name: str
    picture: Optional[str] = None
    authenticated: bool = True


def _get_token_path(email: str) -> Path:
    """Get the token file path for a user."""
    # Sanitize email for filename
    safe_email = email.replace("@", "_at_").replace(".", "_")
    return TOKENS_DIR / f"{safe_email}_google_token.json"


def save_google_tokens(email: str, tokens: dict) -> None:
    """Save Google OAuth tokens for a user."""
    token_path = _get_token_path(email)
    token_data = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": tokens.get("expires_in"),
        "scope": tokens.get("scope"),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(token_path, "w") as f:
        json.dump(token_data, f, indent=2)
    logger.info(f"Saved Google tokens for {email}")


def get_google_tokens(email: str) -> Optional[dict]:
    """Load Google OAuth tokens for a user."""
    token_path = _get_token_path(email)
    if not token_path.exists():
        return None
    with open(token_path, "r") as f:
        return json.load(f)


def delete_google_tokens(email: str) -> None:
    """Delete Google OAuth tokens for a user."""
    token_path = _get_token_path(email)
    if token_path.exists():
        token_path.unlink()
        logger.info(f"Deleted Google tokens for {email}")


@router.get("/login")
async def login(
    request: Request,
    redirect_uri: Optional[str] = Query(None, description="Where to redirect after login"),
):
    """
    Initiate Google OAuth login flow.
    
    Redirects user to Google's consent page.
    """
    settings = get_settings()
    
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID.",
        )
    
    # Build callback URL
    # In production, use the request's host; in dev, might be different
    callback_url = str(request.url_for("oauth_callback"))
    
    # Store redirect_uri in state for after auth
    state = redirect_uri or settings.frontend_url
    
    # Build Google OAuth URL
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",  # Always show consent to get refresh token
        "state": state,
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    
    logger.info(f"Redirecting to Google OAuth: {auth_url}")
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State parameter with redirect URL"),
    error: Optional[str] = Query(None, description="Error from Google"),
):
    """
    Handle OAuth callback from Google.
    
    Exchanges authorization code for tokens and creates session.
    """
    settings = get_settings()
    
    # Check for errors
    if error:
        logger.error(f"OAuth error: {error}")
        redirect_url = f"{settings.frontend_url}/login?error={error}"
        return RedirectResponse(url=redirect_url)
    
    # Build callback URL (must match what was sent to Google)
    callback_url = str(request.url_for("oauth_callback"))
    
    try:
        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": callback_url,
                },
            )
            
            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {token_response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange authorization code",
                )
            
            tokens = token_response.json()
            access_token = tokens.get("access_token")
            
            # Get user info from Google
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            
            if userinfo_response.status_code != 200:
                logger.error(f"Failed to get user info: {userinfo_response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user information",
                )
            
            userinfo = userinfo_response.json()
            
        # Create UserInfo object
        user_info = UserInfo(
            email=userinfo.get("email"),
            name=userinfo.get("name", userinfo.get("email")),
            picture=userinfo.get("picture"),
            given_name=userinfo.get("given_name"),
            family_name=userinfo.get("family_name"),
        )
        
        logger.info(f"OAuth successful for: {user_info.email}")
        
        # Save Google tokens for API access (Calendar, Drive, etc.)
        save_google_tokens(user_info.email, tokens)
        
        # Check if email is allowed
        if not settings.is_email_allowed(user_info.email):
            logger.warning(f"Access denied for: {user_info.email}")
            redirect_url = f"{settings.frontend_url}/login?error=access_denied&email={user_info.email}"
            return RedirectResponse(url=redirect_url)
        
        # Create JWT token
        jwt_token = create_access_token(user_info)
        
        # Determine redirect URL
        redirect_url = state or settings.frontend_url
        
        # Add token to redirect URL as query param
        # Frontend will store it and use for API calls
        if "?" in redirect_url:
            redirect_url = f"{redirect_url}&token={jwt_token}"
        else:
            redirect_url = f"{redirect_url}?token={jwt_token}"
        
        # Create response with redirect
        response = RedirectResponse(url=redirect_url)
        
        # Also set as HTTP-only cookie for security
        response.set_cookie(
            key="auth_token",
            value=jwt_token,
            httponly=True,
            secure=settings.environment == "production",
            samesite="lax",
            max_age=settings.jwt_expire_hours * 3600,
        )
        
        return response
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to communicate with Google",
        )


@router.post("/logout")
async def logout(response: Response):
    """
    Log out the current user.
    
    Clears the auth cookie.
    """
    response.delete_cookie(key="auth_token")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: TokenData = Depends(get_current_user)):
    """
    Get information about the current authenticated user.
    """
    return UserResponse(
        email=current_user.email,
        name=current_user.name,
        picture=current_user.picture,
    )


@router.get("/check")
async def check_auth(request: Request):
    """
    Check if the user is authenticated.
    
    Returns authentication status without requiring auth.
    Useful for frontend to check login state.
    """
    from ..core.auth import get_optional_user
    
    user = await get_optional_user(request, None)
    
    if user:
        return {
            "authenticated": True,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
        }
    else:
        return {
            "authenticated": False,
        }

