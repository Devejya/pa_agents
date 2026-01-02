"""
Contacts API routes with Row-Level Security.

Provides authenticated access to the user's contacts with RLS enforcement.
All queries are automatically filtered by owner_user_id via PostgreSQL RLS policies.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.auth import TokenData, get_current_user
from ..core.audit import get_audit_logger, AuditAction, ResourceType
from ..db import get_db_pool, PersonsRepository
from ..middleware import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("")
async def list_contacts(
    current_user: TokenData = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get all contacts for the authenticated user.
    
    RLS automatically filters to only this user's contacts via owner_user_id.
    """
    audit = get_audit_logger()
    
    try:
        pool = await get_db_pool()
        repo = PersonsRepository(pool)
        
        # RLS automatically filters to only this user's contacts
        contacts = await repo.list_contacts(
            user_id=current_user.user_id,
            limit=limit,
            offset=offset
        )
        
        # Audit log: read contacts list
        await audit.log_data_access(
            user_id=current_user.user_id,
            resource_type=ResourceType.PERSONS,
            action=AuditAction.READ,
            details={"count": len(contacts), "limit": limit, "offset": offset},
            ip_address=get_client_ip(),
        )
        
        return contacts
    except Exception as e:
        logger.error(f"Error getting contacts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contacts",
        )


@router.get("/core-user")
async def get_core_user(
    current_user: TokenData = Depends(get_current_user),
):
    """
    Get the core user (the authenticated user's profile).
    
    RLS ensures only the user's own core_user record is returned.
    """
    try:
        pool = await get_db_pool()
        repo = PersonsRepository(pool)
        
        core_user = await repo.get_core_user(user_id=current_user.user_id)
        
        if not core_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Core user not found",
            )
        
        return core_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting core user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve core user",
        )


@router.get("/search")
async def search_contacts(
    q: str = Query(..., min_length=1),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Search contacts by query string.
    
    RLS ensures only the user's own contacts are searched.
    """
    try:
        pool = await get_db_pool()
        repo = PersonsRepository(pool)
        
        results = await repo.search(
            user_id=current_user.user_id,
            query=q
        )
        
        return results
    except Exception as e:
        logger.error(f"Error searching contacts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search contacts",
        )


@router.get("/{contact_id}")
async def get_contact(
    contact_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Get a specific contact by ID.
    
    RLS ensures only the user's own contacts can be retrieved.
    Returns 404 if contact doesn't exist or isn't owned by the user.
    """
    audit = get_audit_logger()
    
    try:
        pool = await get_db_pool()
        repo = PersonsRepository(pool)
        
        contact = await repo.get_contact(
            user_id=current_user.user_id,
            contact_id=contact_id
        )
        
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found",
            )
        
        # Audit log: read specific contact
        await audit.log_data_access(
            user_id=current_user.user_id,
            resource_type=ResourceType.PERSONS,
            resource_id=str(contact_id),
            action=AuditAction.READ,
            ip_address=get_client_ip(),
        )
        
        return contact
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting contact {contact_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contact",
        )


@router.get("/{contact_id}/relationships")
async def get_contact_relationships(
    contact_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Get relationships for a specific contact.
    
    RLS ensures only relationships owned by the user are returned.
    """
    try:
        pool = await get_db_pool()
        repo = PersonsRepository(pool)
        
        # First verify the contact exists and is owned by the user
        contact = await repo.get_contact(
            user_id=current_user.user_id,
            contact_id=contact_id
        )
        
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found",
            )
        
        relationships = await repo.get_relationships(
            user_id=current_user.user_id,
            person_id=contact_id
        )
        
        return relationships
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting relationships for {contact_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve relationships",
        )
