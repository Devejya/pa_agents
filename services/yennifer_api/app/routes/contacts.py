"""
Contacts API routes - Proxy to User Network service.

Provides authenticated access to the User Network contacts for the frontend.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.auth import TokenData, get_current_user
from ..core.user_network_client import get_user_network_client, UserNetworkAPIError

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
    
    Returns list of persons from User Network.
    """
    client = get_user_network_client()
    
    try:
        contacts = await client.list_persons(limit=limit, offset=offset)
        return contacts
    except UserNetworkAPIError as e:
        logger.error(f"Failed to get contacts: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
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
    Get the core user (the authenticated user's profile in User Network).
    """
    client = get_user_network_client()
    
    try:
        core_user = await client.get_core_user()
        return core_user
    except UserNetworkAPIError as e:
        logger.error(f"Failed to get core user: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
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
    """
    client = get_user_network_client()
    
    try:
        results = await client.search_persons(q)
        return results
    except UserNetworkAPIError as e:
        logger.error(f"Failed to search contacts: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
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
    """
    client = get_user_network_client()
    
    try:
        contact = await client.get_person(str(contact_id))
        return contact
    except UserNetworkAPIError as e:
        logger.error(f"Failed to get contact {contact_id}: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
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
    """
    client = get_user_network_client()
    
    try:
        relationships = await client.get_relationships(str(contact_id))
        return relationships
    except UserNetworkAPIError as e:
        logger.error(f"Failed to get relationships for {contact_id}: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
    except Exception as e:
        logger.error(f"Error getting relationships for {contact_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve relationships",
        )

