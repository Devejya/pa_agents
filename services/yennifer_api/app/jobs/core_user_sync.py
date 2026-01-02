"""
Core User Sync Background Job.

Syncs the authenticated user's profile from Gmail data:
- Extracts name, email from Gmail profile
- Discovers additional info from sent emails (signature, company, title)
- Creates or updates the core user record in User Network service

Triggered after OAuth callback to initialize user data.

Note: All operations go through UserNetworkClient with user_id for RLS enforcement.
"""

import base64
import logging
import re
from datetime import datetime
from typing import Optional

from ..core.user_network_client import get_user_network_client, UserNetworkAPIError
from ..routes.auth import get_google_tokens
from ..db import get_db_pool
from ..db.user_repository import UserRepository

logger = logging.getLogger(__name__)


async def _get_user_id_for_email(user_email: str) -> Optional[str]:
    """
    Look up the user_id UUID for a given email address.
    
    Args:
        user_email: User's email address
        
    Returns:
        User ID string (UUID) if found, None otherwise
    """
    try:
        pool = await get_db_pool()
        user_repo = UserRepository(pool)
        user = await user_repo.get_user_by_email(user_email)
        
        if user and user.get('id'):
            return str(user['id'])
        return None
    except Exception as e:
        logger.error(f"Failed to look up user_id for {user_email}: {e}")
        return None


async def sync_core_user_from_gmail(user_email: str) -> dict:
    """
    Sync core user data from Gmail.
    
    This function:
    1. Gets user profile from Gmail API
    2. Fetches recent sent emails to extract signature info
    3. Creates or updates the core user in User Network
    
    Args:
        user_email: User's email address
        
    Returns:
        Sync result with user info
    """
    logger.info(f"🔄 Starting core user sync for {user_email}")
    
    result = {
        'success': False,
        'user_email': user_email,
        'created': False,
        'updated': False,
        'error': None,
        'user_data': {},
    }
    
    try:
        # Step 1: Get OAuth tokens
        tokens = await get_google_tokens(user_email)
        if not tokens:
            result['error'] = 'No valid OAuth token'
            logger.error(f"No tokens for {user_email}")
            return result
        
        # Step 2: Get Gmail profile
        profile_data = await _get_gmail_profile(user_email)
        if not profile_data:
            result['error'] = 'Failed to get Gmail profile'
            logger.error(f"Failed to get Gmail profile for {user_email}")
            return result
        
        logger.info(f"📧 Got Gmail profile for {user_email}: {profile_data.get('name', 'Unknown')}")
        
        # Step 3: Extract additional info from sent emails
        signature_data = await _extract_info_from_sent_emails(user_email)
        if signature_data:
            logger.info(f"📝 Extracted signature data for {user_email}: {signature_data}")
        
        # Step 4: Merge profile and signature data
        user_data = _merge_user_data(profile_data, signature_data)
        result['user_data'] = user_data
        
        # Step 5: Create or update core user in User Network
        sync_result = await _upsert_core_user(user_email, user_data)
        result['created'] = sync_result.get('created', False)
        result['updated'] = sync_result.get('updated', False)
        result['success'] = True
        
        logger.info(
            f"✅ Core user sync complete for {user_email}: "
            f"{'created' if result['created'] else 'updated'}"
        )
        
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"❌ Core user sync failed for {user_email}: {e}")
    
    return result


async def _get_gmail_profile(user_email: str) -> Optional[dict]:
    """
    Get user profile from Gmail API.
    
    Returns:
        Profile dict with email, name, etc.
    """
    from ..core.google_services import build_google_service_async
    
    try:
        gmail = await build_google_service_async(user_email, 'gmail', 'v1')
        
        # Get user's profile
        profile = gmail.users().getProfile(userId='me').execute()
        
        # Also get send-as settings for name info
        send_as_list = gmail.users().settings().sendAs().list(userId='me').execute()
        send_as_settings = send_as_list.get('sendAs', [])
        
        # Find primary send-as (usually has the user's display name)
        primary_alias = None
        for alias in send_as_settings:
            if alias.get('isPrimary') or alias.get('isDefault'):
                primary_alias = alias
                break
        
        if not primary_alias and send_as_settings:
            primary_alias = send_as_settings[0]
        
        # Extract name from send-as settings
        display_name = None
        if primary_alias:
            display_name = primary_alias.get('displayName') or primary_alias.get('sendAsEmail')
        
        # Parse name into first/last
        first_name, last_name = _parse_display_name(display_name)
        
        return {
            'email': profile.get('emailAddress', user_email),
            'first_name': first_name,
            'last_name': last_name,
            'display_name': display_name,
        }
        
    except Exception as e:
        logger.error(f"Failed to get Gmail profile: {e}")
        return None


async def _extract_info_from_sent_emails(user_email: str, max_emails: int = 10) -> Optional[dict]:
    """
    Extract additional user info from sent emails.
    
    Looks for:
    - Email signature (company, title, phone)
    - Common greeting patterns
    
    Args:
        user_email: User's email
        max_emails: Maximum number of sent emails to analyze
        
    Returns:
        Extracted data dict or None
    """
    from ..core.google_services import build_google_service_async
    
    try:
        gmail = await build_google_service_async(user_email, 'gmail', 'v1')
        
        # Get recent sent emails
        sent_messages = gmail.users().messages().list(
            userId='me',
            labelIds=['SENT'],
            maxResults=max_emails,
        ).execute()
        
        messages = sent_messages.get('messages', [])
        if not messages:
            logger.debug(f"No sent messages found for {user_email}")
            return None
        
        # Analyze each message for signature
        extracted_data = {
            'company': None,
            'title': None,
            'phone': None,
            'address': None,
        }
        
        for msg_ref in messages[:max_emails]:
            try:
                msg = gmail.users().messages().get(
                    userId='me',
                    id=msg_ref['id'],
                    format='full',
                ).execute()
                
                body_text = _extract_body_text(msg)
                if body_text:
                    signature_info = _parse_email_signature(body_text)
                    
                    # Merge extracted info (first match wins)
                    for key, value in signature_info.items():
                        if value and not extracted_data.get(key):
                            extracted_data[key] = value
                
                # Stop if we have enough data
                if all(extracted_data.values()):
                    break
                    
            except Exception as e:
                logger.debug(f"Failed to parse message {msg_ref['id']}: {e}")
                continue
        
        # Return None if nothing was extracted
        if not any(extracted_data.values()):
            return None
            
        return extracted_data
        
    except Exception as e:
        logger.error(f"Failed to extract info from sent emails: {e}")
        return None


def _extract_body_text(message: dict) -> Optional[str]:
    """
    Extract plain text body from Gmail message.
    """
    payload = message.get('payload', {})
    
    # Try to get plain text body
    if payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    
    # Look in parts
    parts = payload.get('parts', [])
    for part in parts:
        if part.get('mimeType') == 'text/plain':
            data = part.get('body', {}).get('data')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        # Check nested parts
        nested_parts = part.get('parts', [])
        for nested in nested_parts:
            if nested.get('mimeType') == 'text/plain':
                data = nested.get('body', {}).get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    
    return None


def _parse_email_signature(body_text: str) -> dict:
    """
    Parse email signature for company, title, and contact info.
    
    Common signature patterns:
    - Name
    - Title | Company
    - Phone: xxx-xxx-xxxx
    - Address line
    """
    result = {
        'company': None,
        'title': None,
        'phone': None,
        'address': None,
    }
    
    # Get the last part of the email (likely signature)
    # Look for common signature markers
    signature_markers = ['--', 'Best,', 'Regards,', 'Thanks,', 'Cheers,', 'Sincerely,']
    signature_start = -1
    
    lines = body_text.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        for marker in signature_markers:
            if stripped.startswith(marker) or stripped == marker:
                signature_start = i
                break
        if signature_start >= 0:
            break
    
    # If no marker found, take last 15 lines
    if signature_start < 0:
        signature_start = max(0, len(lines) - 15)
    
    signature_lines = lines[signature_start:]
    signature_text = '\n'.join(signature_lines)
    
    # Extract phone number
    phone_patterns = [
        r'(?:Phone|Tel|Cell|Mobile|P|T|C|M)[:\s]*(\+?[\d\s\-\.\(\)]{10,})',
        r'(\+?1?[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})',
    ]
    for pattern in phone_patterns:
        match = re.search(pattern, signature_text, re.IGNORECASE)
        if match:
            phone = re.sub(r'[^\d+]', '', match.group(1))
            if len(phone) >= 10:
                result['phone'] = phone
                break
    
    # Extract title and company
    # Look for patterns like "Title | Company" or "Title at Company" or "Title, Company"
    title_company_patterns = [
        r'^([A-Z][A-Za-z\s&]+)\s*[|@]\s*([A-Z][A-Za-z\s&\.,]+)$',
        r'^([A-Z][A-Za-z\s&]+)\s+at\s+([A-Z][A-Za-z\s&\.,]+)$',
        r'^([A-Z][A-Za-z\s&]+),\s*([A-Z][A-Za-z\s&\.,]+)$',
    ]
    
    for line in signature_lines:
        stripped = line.strip()
        if not stripped or len(stripped) < 5:
            continue
            
        for pattern in title_company_patterns:
            match = re.match(pattern, stripped)
            if match:
                potential_title = match.group(1).strip()
                potential_company = match.group(2).strip()
                
                # Validate title (should contain common title words)
                title_keywords = ['engineer', 'manager', 'director', 'vp', 'ceo', 
                                'cto', 'founder', 'developer', 'designer', 'analyst',
                                'consultant', 'lead', 'head', 'chief', 'officer',
                                'president', 'associate', 'partner', 'coordinator']
                is_title = any(kw in potential_title.lower() for kw in title_keywords)
                
                if is_title:
                    result['title'] = potential_title
                    result['company'] = potential_company
                    break
        
        if result['title']:
            break
    
    # If no title found, look for just company name
    if not result['company']:
        company_indicators = ['inc.', 'inc', 'llc', 'ltd', 'corp', 'corporation', 
                             'company', 'co.', 'technologies', 'solutions', 'group']
        for line in signature_lines:
            stripped = line.strip()
            if any(indicator in stripped.lower() for indicator in company_indicators):
                # Clean up the line
                result['company'] = stripped
                break
    
    return result


def _parse_display_name(display_name: Optional[str]) -> tuple[str, Optional[str]]:
    """
    Parse display name into first and last name.
    
    Returns:
        Tuple of (first_name, last_name)
    """
    if not display_name:
        return ('User', None)
    
    # Remove any email addresses that might be in the name
    name = re.sub(r'<[^>]+>', '', display_name).strip()
    name = re.sub(r'[\"\']', '', name).strip()
    
    if not name:
        return ('User', None)
    
    parts = name.split()
    if len(parts) == 1:
        return (parts[0], None)
    elif len(parts) == 2:
        return (parts[0], parts[1])
    else:
        # First name is first part, last name is everything else
        return (parts[0], ' '.join(parts[1:]))


def _merge_user_data(profile_data: dict, signature_data: Optional[dict]) -> dict:
    """
    Merge profile and signature data into a unified user data dict.
    """
    user_data = {
        'first_name': profile_data.get('first_name', 'User'),
        'last_name': profile_data.get('last_name'),
        'work_email': profile_data.get('email'),
        'is_core_user': True,
    }
    
    if signature_data:
        if signature_data.get('company'):
            user_data['company'] = signature_data['company']
        if signature_data.get('title'):
            user_data['latest_title'] = signature_data['title']
        if signature_data.get('phone'):
            user_data['personal_cell'] = signature_data['phone']
    
    return user_data


async def _upsert_core_user(user_email: str, user_data: dict) -> dict:
    """
    Create or update the core user in User Network service.
    
    Returns:
        Dict with 'created' or 'updated' flag
    """
    result = {
        'created': False,
        'updated': False,
    }
    
    # Look up user_id for RLS enforcement
    user_id = await _get_user_id_for_email(user_email)
    if not user_id:
        logger.error(f"User not found in database for {user_email}")
        raise ValueError(f"User not found for email: {user_email}")
    
    # Get client with user context for RLS
    client = get_user_network_client(user_id=user_id)
    
    try:
        # Check if core user already exists
        existing_user = await client.get_core_user()
        
        if existing_user:
            # Update existing user
            person_id = str(existing_user['id'])
            
            # Build update data (only non-null fields, preserve existing data)
            update_data = {}
            for key, value in user_data.items():
                if value is not None and key != 'is_core_user':
                    # Only update if we have new info or existing is empty
                    existing_value = existing_user.get(key)
                    if not existing_value or value != existing_value:
                        update_data[key] = value
            
            if update_data:
                await client.update_person(person_id, update_data)
                result['updated'] = True
                logger.info(f"Updated core user {person_id} with: {list(update_data.keys())}")
            else:
                logger.info(f"Core user {person_id} already up to date")
                result['updated'] = True  # Still mark as updated for tracking
                
        else:
            # Create new core user
            # Ensure we have required fields
            create_data = {
                'first_name': user_data.get('first_name', 'User'),
                'last_name': user_data.get('last_name'),
                'work_email': user_data.get('work_email') or user_email,
                'is_core_user': True,
            }
            
            # Add optional fields
            for key in ['company', 'latest_title', 'personal_cell']:
                if user_data.get(key):
                    create_data[key] = user_data[key]
            
            new_user = await client.create_person(create_data)
            result['created'] = True
            logger.info(f"Created core user: {new_user.get('id')}")
            
    except UserNetworkAPIError as e:
        logger.error(f"User Network API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to upsert core user: {e}")
        raise
    
    return result


async def trigger_core_user_sync(user_email: str) -> dict:
    """
    Trigger core user sync for a specific user.
    
    Called from OAuth callback after user login.
    
    Args:
        user_email: User's email address
        
    Returns:
        Sync result
    """
    logger.info(f"🏃 Core user sync triggered for {user_email}")
    return await sync_core_user_from_gmail(user_email)

