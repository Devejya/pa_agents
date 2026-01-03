"""
Integrations API routes.

Handles integration listing, enabling/disabling, and scope management.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.auth import TokenData, get_current_user
from ..core.config import get_settings
from ..db import get_db_pool
from ..db.integrations_repository import IntegrationsRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ============== Pydantic Models ==============

class ScopeResponse(BaseModel):
    """Response model for a scope."""
    id: str
    scope_uri: str
    name: str
    description: Optional[str]
    is_required: bool
    display_order: int
    is_enabled: bool = False
    is_granted: bool = False
    granted_at: Optional[str] = None


class IntegrationResponse(BaseModel):
    """Response model for an integration."""
    id: str
    provider: str
    name: str
    description: Optional[str]
    capability_summary: Optional[str]
    icon_url: Optional[str]
    display_order: int
    is_enabled: bool = False
    enabled_at: Optional[str] = None
    disabled_at: Optional[str] = None


class IntegrationDetailResponse(IntegrationResponse):
    """Response model for integration with scopes."""
    scopes: List[ScopeResponse] = []


class IntegrationListResponse(BaseModel):
    """Response for list of integrations."""
    integrations: List[IntegrationResponse]


class EnableResponse(BaseModel):
    """Response when enabling an integration or scope."""
    success: bool
    needs_auth: bool = False
    auth_url: Optional[str] = None
    integration: Optional[IntegrationDetailResponse] = None


class ScopeToggleResponse(BaseModel):
    """Response when toggling a scope."""
    success: bool
    needs_auth: bool = False
    auth_url: Optional[str] = None
    scope_id: str
    is_enabled: bool
    is_granted: bool


# ============== Helper Functions ==============

def _serialize_datetime(dt) -> Optional[str]:
    """Convert datetime to ISO string or None."""
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)


def _serialize_integration(row: dict) -> IntegrationResponse:
    """Serialize integration row to response model."""
    # Handle None values from LEFT JOINs - convert to False
    is_enabled = row.get("is_enabled")
    if is_enabled is None:
        is_enabled = False
    
    return IntegrationResponse(
        id=row["id"],
        provider=row["provider"],
        name=row["name"],
        description=row.get("description"),
        capability_summary=row.get("capability_summary"),
        icon_url=row.get("icon_url"),
        display_order=row.get("display_order") or 0,
        is_enabled=bool(is_enabled),
        enabled_at=_serialize_datetime(row.get("enabled_at")),
        disabled_at=_serialize_datetime(row.get("disabled_at")),
    )


def _serialize_scope(row: dict) -> ScopeResponse:
    """Serialize scope row to response model."""
    # Handle None values from LEFT JOINs - convert to False
    is_enabled = row.get("is_enabled")
    if is_enabled is None:
        is_enabled = False
    
    is_granted = row.get("is_granted")
    if is_granted is None:
        is_granted = False
    
    is_required = row.get("is_required")
    if is_required is None:
        is_required = False
    
    return ScopeResponse(
        id=row["id"],
        scope_uri=row["scope_uri"],
        name=row["name"],
        description=row.get("description"),
        is_required=bool(is_required),
        display_order=row.get("display_order") or 0,
        is_enabled=bool(is_enabled),
        is_granted=bool(is_granted),
        granted_at=_serialize_datetime(row.get("granted_at")),
    )


def _serialize_integration_detail(row: dict) -> IntegrationDetailResponse:
    """Serialize integration with scopes to response model."""
    # Handle None values from LEFT JOINs - convert to False
    is_enabled = row.get("is_enabled")
    if is_enabled is None:
        is_enabled = False
    
    return IntegrationDetailResponse(
        id=row["id"],
        provider=row["provider"],
        name=row["name"],
        description=row.get("description"),
        capability_summary=row.get("capability_summary"),
        icon_url=row.get("icon_url"),
        display_order=row.get("display_order") or 0,
        is_enabled=bool(is_enabled),
        enabled_at=_serialize_datetime(row.get("enabled_at")),
        disabled_at=_serialize_datetime(row.get("disabled_at")),
        scopes=[_serialize_scope(s) for s in row.get("scopes", [])],
    )


# ============== Endpoints ==============

@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    enabled_only: bool = False,
    current_user: TokenData = Depends(get_current_user),
) -> IntegrationListResponse:
    """
    List all available integrations with user's enabled status.
    
    Args:
        enabled_only: If True, only return integrations the user has enabled
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    try:
        pool = await get_db_pool()
        repo = IntegrationsRepository(pool)
        
        integrations = await repo.get_user_integrations(user_id, enabled_only=enabled_only)
        
        return IntegrationListResponse(
            integrations=[_serialize_integration(i) for i in integrations]
        )
    except Exception as e:
        # Handle case where integrations tables don't exist yet
        logger.warning(f"Failed to list integrations (tables may not exist): {e}")
        return IntegrationListResponse(integrations=[])


@router.get("/{integration_id}", response_model=IntegrationDetailResponse)
async def get_integration(
    integration_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> IntegrationDetailResponse:
    """
    Get integration details with all scopes and their enabled/granted status.
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    integration = await repo.get_user_integration(user_id, integration_id)
    
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )
    
    return _serialize_integration_detail(integration)


@router.post("/{integration_id}/enable", response_model=EnableResponse)
async def enable_integration(
    integration_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> EnableResponse:
    """
    Enable an integration for the user.
    
    If OAuth consent is needed for the required scopes, returns needs_auth=True
    with the auth_url to redirect to.
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    settings = get_settings()
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    # Check if integration exists
    integration = await repo.get_integration(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )
    
    # Check if OAuth consent is needed for required scopes
    scopes_needed = await repo.get_scopes_needing_oauth(user_id, integration_id)
    
    if scopes_needed and integration["provider"] == "google":
        # Need OAuth consent - return auth URL
        auth_url = f"{settings.api_base_url}/api/v1/auth/authorize/{integration_id}"
        
        return EnableResponse(
            success=False,
            needs_auth=True,
            auth_url=auth_url,
            integration=None,
        )
    
    # No OAuth needed (or not a Google integration) - just enable
    updated = await repo.enable_integration(user_id, integration_id)
    
    logger.info(f"Enabled integration {integration_id} for user {user_id}")
    
    return EnableResponse(
        success=True,
        needs_auth=False,
        auth_url=None,
        integration=_serialize_integration_detail(updated),
    )


@router.post("/{integration_id}/disable", response_model=EnableResponse)
async def disable_integration(
    integration_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> EnableResponse:
    """
    Disable an integration for the user.
    
    This is a local disable only - OAuth tokens are kept for quick re-enable.
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    # Check if integration exists
    integration = await repo.get_integration(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )
    
    updated = await repo.disable_integration(user_id, integration_id)
    
    logger.info(f"Disabled integration {integration_id} for user {user_id}")
    
    return EnableResponse(
        success=True,
        needs_auth=False,
        auth_url=None,
        integration=_serialize_integration_detail(updated),
    )


@router.post("/{integration_id}/scopes/{scope_id}/enable", response_model=ScopeToggleResponse)
async def enable_scope(
    integration_id: str,
    scope_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> ScopeToggleResponse:
    """
    Enable an individual scope.
    
    If OAuth consent is needed, returns needs_auth=True with the auth_url.
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    settings = get_settings()
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    # Enable the scope in our database
    result = await repo.enable_scope(user_id, scope_id)
    
    # Check if OAuth consent is needed
    if not result.get("is_granted", False):
        # Check if this is a Google integration
        integration = await repo.get_integration(integration_id)
        if integration and integration["provider"] == "google":
            # Need OAuth consent
            auth_url = f"{settings.api_base_url}/api/v1/auth/authorize/{integration_id}"
            
            return ScopeToggleResponse(
                success=True,
                needs_auth=True,
                auth_url=auth_url,
                scope_id=scope_id,
                is_enabled=True,
                is_granted=False,
            )
    
    logger.info(f"Enabled scope {scope_id} for user {user_id}")
    
    return ScopeToggleResponse(
        success=True,
        needs_auth=False,
        auth_url=None,
        scope_id=scope_id,
        is_enabled=result.get("is_enabled", True),
        is_granted=result.get("is_granted", False),
    )


@router.post("/{integration_id}/scopes/{scope_id}/disable", response_model=ScopeToggleResponse)
async def disable_scope(
    integration_id: str,
    scope_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> ScopeToggleResponse:
    """
    Disable an individual scope.
    
    This is a local disable - the OAuth grant is kept.
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    result = await repo.disable_scope(user_id, scope_id)
    
    logger.info(f"Disabled scope {scope_id} for user {user_id}")
    
    return ScopeToggleResponse(
        success=True,
        needs_auth=False,
        auth_url=None,
        scope_id=scope_id,
        is_enabled=result.get("is_enabled", False),
        is_granted=result.get("is_granted", False),
    )


@router.get("/{integration_id}/scopes", response_model=List[ScopeResponse])
async def list_scopes(
    integration_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> List[ScopeResponse]:
    """
    List all scopes for an integration with user's enabled/granted status.
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    # Get integration with scopes
    integration = await repo.get_user_integration(user_id, integration_id)
    
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )
    
    return [_serialize_scope(s) for s in integration.get("scopes", [])]


@router.post("/{integration_id}/enable-all-scopes", response_model=EnableResponse)
async def enable_all_scopes(
    integration_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> EnableResponse:
    """
    Enable all scopes for an integration.
    
    If OAuth consent is needed, returns needs_auth=True with the auth_url.
    """
    user_id = UUID(current_user.user_id) if current_user.user_id else None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID required",
        )
    
    settings = get_settings()
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    # Check if integration exists
    integration = await repo.get_integration(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{integration_id}' not found",
        )
    
    # Enable all scopes
    scopes = await repo.get_integration_scopes(integration_id)
    for scope in scopes:
        await repo.enable_scope(user_id, scope["id"])
    
    # Enable the integration
    await repo.enable_integration(user_id, integration_id, enable_required_scopes=False)
    
    # Check if OAuth consent is needed
    scopes_needed = await repo.get_scopes_needing_oauth(user_id, integration_id)
    
    if scopes_needed and integration["provider"] == "google":
        auth_url = f"{settings.api_base_url}/api/v1/auth/authorize/{integration_id}"
        
        return EnableResponse(
            success=True,
            needs_auth=True,
            auth_url=auth_url,
            integration=None,
        )
    
    # Get updated integration
    updated = await repo.get_user_integration(user_id, integration_id)
    
    logger.info(f"Enabled all scopes for {integration_id} for user {user_id}")
    
    return EnableResponse(
        success=True,
        needs_auth=False,
        auth_url=None,
        integration=_serialize_integration_detail(updated),
    )

