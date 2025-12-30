"""
Authentication routes for Google OAuth.

Handles login, callback, logout, and user info endpoints.
"""

import asyncio
import logging
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..core.auth import TokenData, UserInfo, create_access_token, get_current_user
from ..core.config import get_settings
from ..db import get_db_pool
from ..db.token_repository import TokenRepository
from ..db.user_repository import UserRepository

logger = logging.getLogger(__name__)

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


async def save_google_tokens(email: str, tokens: dict) -> None:
    """
    Save Google OAuth tokens for a user to the database.
    
    Args:
        email: User's email address.
        tokens: OAuth token data from Google.
    """
    try:
        pool = await get_db_pool()
        repo = TokenRepository(pool)
        await repo.save_tokens(email, tokens, provider="google")
        logger.info(f"Saved Google tokens for {email}")
    except Exception as e:
        logger.error(f"Failed to save tokens for {email}: {e}")
        raise


async def get_google_tokens(email: str) -> Optional[dict]:
    """
    Load Google OAuth tokens for a user from the database.
    
    Args:
        email: User's email address.
        
    Returns:
        Token dictionary if found, None otherwise.
    """
    try:
        pool = await get_db_pool()
        repo = TokenRepository(pool)
        return await repo.get_tokens(email, provider="google")
    except Exception as e:
        logger.error(f"Failed to get tokens for {email}: {e}")
        return None


async def delete_google_tokens(email: str) -> None:
    """
    Delete (revoke) Google OAuth tokens for a user.
    
    Args:
        email: User's email address.
    """
    try:
        pool = await get_db_pool()
        repo = TokenRepository(pool)
        await repo.delete_tokens(email, provider="google", reason="user_logout")
        logger.info(f"Deleted Google tokens for {email}")
    except Exception as e:
        logger.error(f"Failed to delete tokens for {email}: {e}")


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


async def _trigger_initial_core_user_sync(user_email: str, user_info: dict):
    """
    Background task to sync core user data after login.
    
    This runs asynchronously after the OAuth callback completes,
    so the user isn't blocked waiting for sync to finish.
    
    Args:
        user_email: User's email address
        user_info: Basic user info from Google OAuth (name, picture, etc.)
    """
    from ..jobs.core_user_sync import trigger_core_user_sync
    
    try:
        logger.info(f"👤 Triggering core user sync for {user_email}")
        result = await trigger_core_user_sync(user_email)
        
        if result.get('success'):
            action = 'created' if result.get('created') else 'updated'
            logger.info(f"✅ Core user {action} for {user_email}")
        else:
            logger.warning(f"⚠️ Core user sync incomplete for {user_email}: {result.get('error')}")
    except Exception as e:
        logger.error(f"❌ Core user sync failed for {user_email}: {e}")


async def _trigger_initial_contact_sync(user_email: str):
    """
    Background task to sync contacts after user login.
    
    This runs asynchronously after the OAuth callback completes,
    so the user isn't blocked waiting for sync to finish.
    """
    from ..jobs.contact_sync import trigger_manual_sync
    
    try:
        logger.info(f"🔄 Triggering initial contact sync for {user_email}")
        result = await trigger_manual_sync(user_email)
        
        if result.get('success'):
            added = result.get('added', 0)
            updated = result.get('updated', 0)
            logger.info(f"✅ Initial sync complete for {user_email}: {added} added, {updated} updated")
        else:
            logger.warning(f"⚠️ Initial sync incomplete for {user_email}: {result.get('errors', [])}")
    except Exception as e:
        logger.error(f"❌ Initial contact sync failed for {user_email}: {e}")


@router.get("/callback")
async def oauth_callback(
    request: Request,
    background_tasks: BackgroundTasks,
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
        google_user_id = userinfo.get("id") or userinfo.get("sub")  # Google's unique ID
        user_info = UserInfo(
            email=userinfo.get("email"),
            name=userinfo.get("name", userinfo.get("email")),
            picture=userinfo.get("picture"),
            given_name=userinfo.get("given_name"),
            family_name=userinfo.get("family_name"),
            google_user_id=google_user_id,
        )
        
        logger.info(f"OAuth successful for: {user_info.email}")
        
        # Save Google tokens for API access (Calendar, Drive, etc.)
        await save_google_tokens(user_info.email, tokens)
        
        # Check if email is allowed
        if not settings.is_email_allowed(user_info.email):
            logger.warning(f"Access denied for: {user_info.email}")
            redirect_url = f"{settings.frontend_url}/login?error=access_denied&email={user_info.email}"
            return RedirectResponse(url=redirect_url)
        
        # Find or create user in our database
        user_id = None
        try:
            pool = await get_db_pool()
            user_repo = UserRepository(pool)
            
            # Try to find existing user by OAuth identity
            existing_user = await user_repo.find_user_by_oauth("google", google_user_id)
            
            if existing_user:
                user_id = existing_user["id"]
                logger.info(f"Found existing user {user_id} for {user_info.email}")
            else:
                # Try to find by email (user might exist from before multi-tenant)
                user_by_email = await user_repo.get_user_by_email(user_info.email)
                
                if user_by_email:
                    # User exists, just add this OAuth identity
                    user_id = user_by_email["id"]
                    await user_repo.add_identity(
                        user_id, "google", google_user_id, user_info.email
                    )
                    logger.info(f"Linked Google identity to existing user {user_id}")
                else:
                    # Create new user
                    new_user = await user_repo.create_user(
                        email=user_info.email,
                        provider="google",
                        provider_user_id=google_user_id,
                        provider_email=user_info.email,
                    )
                    user_id = new_user["id"]
                    logger.info(f"Created new user {user_id} for {user_info.email}")
            
            # Link any existing OAuth tokens to this user
            await user_repo.link_oauth_tokens_to_user(user_info.email, user_id)
            
        except Exception as e:
            # Log but don't fail login - user can still use the app without user_id
            logger.error(f"Failed to create/find user for {user_info.email}: {e}")
            # Continue without user_id for backwards compatibility
        
        # Create JWT token (now includes user_id if available)
        jwt_token = create_access_token(user_info, user_id=user_id)
        
        # Trigger core user sync in background first (to create/update user record)
        background_tasks.add_task(
            _trigger_initial_core_user_sync, 
            user_info.email,
            {
                'name': user_info.name,
                'given_name': user_info.given_name,
                'family_name': user_info.family_name,
                'picture': user_info.picture,
            }
        )
        logger.info(f"👤 Scheduled core user sync for {user_info.email}")
        
        # Trigger contact sync in background (don't block login)
        background_tasks.add_task(_trigger_initial_contact_sync, user_info.email)
        logger.info(f"📇 Scheduled initial contact sync for {user_info.email}")
        
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

