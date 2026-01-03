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
from ..core.audit import get_audit_logger, AuditAction, ResourceType
from ..core.analytics import (
    track_user_login,
    track_user_logout,
    track_app_opened,
    track_oauth_error,
    identify_user,
)
from ..middleware import get_client_ip, get_user_agent, set_current_user_id
from ..db import get_db_pool
from ..db.token_repository import TokenRepository
from ..db.user_repository import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Minimal scopes for initial sign-in (authentication only)
# Additional scopes are requested incrementally when user enables integrations
MINIMAL_SCOPES = [
    "openid",
    "email",
    "profile",
]

# Legacy: Full OAuth scopes (kept for reference and migration)
# New users get minimal scopes; integrations are added incrementally
LEGACY_OAUTH_SCOPES = [
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


async def save_google_tokens(email: str, tokens: dict, user_id: Optional[str] = None) -> None:
    """
    Save Google OAuth tokens for a user to the database.
    
    Args:
        email: User's email address.
        tokens: OAuth token data from Google.
        user_id: Optional user UUID (for linking to multi-tenant user).
    """
    from uuid import UUID
    
    try:
        pool = await get_db_pool()
        repo = TokenRepository(pool)
        
        # Convert user_id string to UUID if provided
        uid = UUID(user_id) if user_id else None
        
        await repo.save_tokens(email, tokens, provider="google", user_id=uid)
        logger.info(f"Saved Google tokens for {email}" + (f" (user_id={user_id})" if user_id else ""))
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
    # TODO: Once integrations migration is complete and all existing users are migrated,
    # change this back to MINIMAL_SCOPES for incremental OAuth.
    # For now, use LEGACY_OAUTH_SCOPES to avoid breaking existing users.
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(LEGACY_OAUTH_SCOPES),  # Temporarily use full scopes
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


@router.get("/authorize/{integration_id}")
async def authorize_integration(
    request: Request,
    integration_id: str,
    redirect_uri: Optional[str] = Query(None, description="Where to redirect after authorization"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Initiate incremental OAuth for a specific integration.
    
    Uses Google's incremental authorization with include_granted_scopes=true
    to add new scopes while keeping existing ones.
    
    Args:
        integration_id: The integration to authorize (e.g., 'gmail', 'calendar')
        redirect_uri: Where to redirect after authorization
    """
    from uuid import UUID
    from ..db.integrations_repository import IntegrationsRepository
    
    settings = get_settings()
    
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth not configured",
        )
    
    # Get user_id
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required for incremental authorization",
        )
    
    # Get scopes needed for this integration
    pool = await get_db_pool()
    integrations_repo = IntegrationsRepository(pool)
    
    # Check if integration exists
    integration = await integrations_repo.get_integration(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )
    
    # Only support Google integrations for now
    if integration["provider"] != "google":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration '{integration_id}' does not use Google OAuth",
        )
    
    # Get scopes that need OAuth consent
    scopes_needed = await integrations_repo.get_scopes_needing_oauth(user_id, integration_id)
    
    if not scopes_needed:
        # All scopes already granted, just enable the integration
        await integrations_repo.enable_integration(user_id, integration_id)
        
        # Redirect back to integrations page
        redirect_url = redirect_uri or f"{settings.frontend_url}/integrations"
        return RedirectResponse(url=redirect_url)
    
    # Build scope URIs list
    scope_uris = [s["scope_uri"] for s in scopes_needed]
    
    # Build callback URL
    callback_url = str(request.url_for("oauth_integration_callback"))
    
    # Encode state with integration_id and redirect_uri
    import json
    import base64
    state_data = {
        "integration_id": integration_id,
        "redirect_uri": redirect_uri or f"{settings.frontend_url}/integrations",
        "user_id": str(user_id),
    }
    state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()
    
    # Build Google OAuth URL for incremental authorization
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(scope_uris),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",  # Key: keeps existing scopes
        "state": state,
        "login_hint": current_user.email,  # Pre-fill email
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    
    logger.info(f"Redirecting to Google OAuth for {integration_id} scopes: {scope_uris}")
    return RedirectResponse(url=auth_url)


@router.get("/authorize/callback", name="oauth_integration_callback")
async def oauth_integration_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter with integration info"),
    error: Optional[str] = Query(None, description="Error from Google"),
):
    """
    Handle OAuth callback for incremental authorization.
    
    Updates the user's token with new scopes and marks them as granted.
    """
    import json
    import base64
    from uuid import UUID
    from ..db.integrations_repository import IntegrationsRepository
    
    settings = get_settings()
    
    # Decode state
    try:
        state_data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        integration_id = state_data["integration_id"]
        redirect_uri = state_data["redirect_uri"]
        user_id = UUID(state_data["user_id"])
    except Exception as e:
        logger.error(f"Failed to decode state: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )
    
    # Check for errors
    if error:
        logger.error(f"OAuth integration error for {integration_id}: {error}")
        redirect_url = f"{redirect_uri}?error={error}&integration={integration_id}"
        return RedirectResponse(url=redirect_url)
    
    # Build callback URL (must match what was sent to Google)
    callback_url = str(request.url_for("oauth_integration_callback"))
    
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
                logger.error(f"Token exchange failed for {integration_id}: {token_response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange authorization code",
                )
            
            tokens = token_response.json()
        
        # Get the user's email from the database
        pool = await get_db_pool()
        user_repo = UserRepository(pool)
        user = await user_repo.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        user_email = user["email"]
        
        # Save the updated tokens
        await save_google_tokens(user_email, tokens, user_id=str(user_id))
        
        # Mark scopes as granted
        integrations_repo = IntegrationsRepository(pool)
        
        # Get scope IDs for this integration
        integration_scopes = await integrations_repo.get_integration_scopes(integration_id)
        scope_ids = [s["id"] for s in integration_scopes]
        
        # Mark them as granted
        await integrations_repo.mark_scopes_granted(user_id, scope_ids)
        
        # Enable the integration
        await integrations_repo.enable_integration(user_id, integration_id)
        
        logger.info(f"Successfully authorized {integration_id} for user {user_id}")
        
        # Redirect back to integrations page with success
        redirect_url = f"{redirect_uri}?success=true&integration={integration_id}"
        return RedirectResponse(url=redirect_url)
        
    except httpx.RequestError as e:
        logger.error(f"HTTP request error during integration auth: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to communicate with Google",
        )


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
                # Track OAuth error
                track_oauth_error(
                    user_id=None,
                    error_type="token_exchange_failed",
                    error_message=f"Status {token_response.status_code}",
                )
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
        
        # Check if email is allowed (before any DB operations)
        if not settings.is_email_allowed(user_info.email):
            logger.warning(f"Access denied for: {user_info.email}")
            
            # Audit log: login denied
            audit = get_audit_logger()
            await audit.log(
                action=AuditAction.LOGIN_FAILED,
                resource_type=ResourceType.USER_PROFILE,
                ip_address=get_client_ip(),
                user_agent=get_user_agent(),
                details={"email": user_info.email, "reason": "not_in_whitelist"},
                success=False,
                error_message="Email not in allowed list",
            )
            
            # Track OAuth access denied
            track_oauth_error(
                user_id=None,
                error_type="access_denied",
                error_message=f"Email not in whitelist: {user_info.email}",
            )
            
            redirect_url = f"{settings.frontend_url}/login?error=access_denied&email={user_info.email}"
            return RedirectResponse(url=redirect_url)
        
        # Find or create user in our database (before saving tokens, so we can link them)
        user_id = None
        is_new_user = False
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
                    is_new_user = True
                    logger.info(f"Created new user {user_id} for {user_info.email}")
            
        except Exception as e:
            # Log but don't fail login - user can still use the app without user_id
            logger.error(f"Failed to create/find user for {user_info.email}: {e}")
            # Continue without user_id for backwards compatibility
        
        # Save Google tokens for API access (Calendar, Drive, etc.)
        # Now includes user_id if we have it
        await save_google_tokens(
            user_info.email, 
            tokens, 
            user_id=str(user_id) if user_id else None
        )
        
        # Create JWT token (now includes user_id if available)
        jwt_token = create_access_token(user_info, user_id=user_id)
        
        # Audit log: successful login
        audit = get_audit_logger()
        await audit.log_login(
            user_id=user_id,
            ip_address=get_client_ip(),
            user_agent=get_user_agent(),
            success=True,
        )
        
        # Track login event in PostHog
        track_user_login(
            user_id=user_id,
            is_new_user=is_new_user,
            login_method="google_oauth",
        )
        
        # Identify user in PostHog (for user properties)
        if user_id:
            identify_user(user_id, {"login_method": "google_oauth"})
        
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
async def logout(
    response: Response,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Log out the current user.
    
    Clears the auth cookie and logs the logout.
    """
    # Audit log: logout
    audit = get_audit_logger()
    await audit.log_logout(
        user_id=current_user.user_id,
        ip_address=get_client_ip(),
    )
    
    # Track logout event in PostHog
    track_user_logout(user_id=current_user.user_id)
    
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
        # Track app opened event in PostHog
        track_app_opened(user_id=user.user_id)
        
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

