"""
Contact Sync Background Job.

Syncs Google Contacts with the User Network service:
- Pulls new/updated contacts from Google
- Pushes local changes to Google
- Handles conflicts and entity resolution
- Sends notifications on completion/failure

Runs every 30 minutes by default.

Note: All operations go through UserNetworkClient with user_id for RLS enforcement.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..core.scheduler import register_job
from ..core.user_network_client import get_user_network_client, UserNetworkAPIError
from ..core.analytics import track_contact_sync
from ..routes.auth import get_google_tokens
from ..db import get_db_pool
from ..db.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Track sync statistics per user (in-memory cache for quick access)
_sync_stats: dict[str, dict] = {}

# Provider name for Google Contacts
GOOGLE_CONTACTS_PROVIDER = "google_contacts"


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


@register_job(
    trigger='interval',
    minutes=30,
    id='contact_sync_scheduler',
    name='Contact Sync Scheduler',
    # Use default 20-minute timeout - sync can take a while for many users
)
async def contact_sync_scheduler():
    """
    Main scheduler job that triggers contact sync for all users.
    
    This job:
    1. Gets list of users with Google Contacts sync enabled
    2. Checks which users are due for sync
    3. Runs sync for each user
    """
    logger.info("📇 Contact sync scheduler running...")
    
    try:
        # Get users with sync enabled
        users_to_sync = await get_users_due_for_sync()
        
        if not users_to_sync:
            logger.info("No users due for contact sync")
            return {'synced': 0, 'skipped': 0, 'failed': 0}
        
        logger.info(f"Found {len(users_to_sync)} user(s) due for sync")
        
        synced = 0
        failed = 0
        skipped = 0
        
        for user_email in users_to_sync:
            try:
                result = await sync_user_contacts(user_email)
                if result.get('success'):
                    synced += 1
                elif result.get('skipped'):
                    skipped += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to sync contacts for {user_email}: {e}")
                failed += 1
        
        logger.info(f"📇 Contact sync complete: {synced} synced, {skipped} skipped, {failed} failed")
        
        return {
            'synced': synced,
            'skipped': skipped,
            'failed': failed,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Contact sync scheduler error: {e}")
        raise


async def get_users_due_for_sync() -> list[str]:
    """
    Get list of user emails that need contact sync.
    
    Checks:
    - Users with valid Google OAuth tokens
    - Users whose sync state is 'idle' and next_sync_at has passed
    - Users who haven't had too many consecutive failures
    
    Returns:
        List of user email addresses
    """
    try:
        # Get all users from our database
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Get users who have OAuth tokens (i.e., have authenticated)
            users = await conn.fetch("""
                SELECT DISTINCT u.id, u.email 
                FROM users u
                JOIN user_oauth_tokens t ON u.id = t.user_id
                WHERE t.provider = 'google'
            """)
        
        if not users:
            logger.debug("No users with Google OAuth found")
            return []
        
        users_due = []
        now = datetime.utcnow()
        
        for user in users:
            user_email = user['email']
            user_id = str(user['id'])
            
            # Check if user has valid Google tokens
            tokens = await get_google_tokens(user_email)
            if not tokens:
                logger.debug(f"No valid Google tokens for {user_email}")
                continue
            
            # Get client with user context for RLS
            client = get_user_network_client(user_id=user_id)
            
            # Check sync state
            try:
                sync_state = await client.get_sync_state(user_email, GOOGLE_CONTACTS_PROVIDER)
                
                if sync_state:
                    # Skip if sync is already running
                    if sync_state.get('sync_status') == 'syncing':
                        logger.debug(f"Sync already in progress for {user_email}")
                        continue
                    
                    # Skip if in failed state with too many failures
                    if sync_state.get('sync_status') == 'failed':
                        logger.debug(f"Sync in failed state for {user_email}")
                        continue
                    
                    # Check if next_sync_at has passed
                    next_sync = sync_state.get('next_sync_at')
                    if next_sync:
                        next_sync_dt = datetime.fromisoformat(next_sync.replace('Z', '+00:00'))
                        if next_sync_dt.replace(tzinfo=None) > now:
                            logger.debug(f"Not yet time to sync for {user_email}")
                            continue
                
                users_due.append(user_email)
                
            except UserNetworkAPIError as e:
                logger.warning(f"Failed to get sync state for {user_email}: {e}")
                # If we can't get sync state, still try to sync
                users_due.append(user_email)
        
        return users_due
        
    except Exception as e:
        logger.error(f"Unexpected error getting users for sync: {e}")
        return []


async def sync_user_contacts(user_email: str) -> dict:
    """
    Sync contacts for a specific user.
    
    Process:
    1. Look up user_id from email for RLS context
    2. Mark sync as started in User Network
    3. Get user's Google OAuth token
    4. Fetch contacts from Google (using syncToken for incremental)
    5. Match against existing User Network contacts
    6. Create/update/flag conflicts
    7. Update sync state with results
    
    Args:
        user_email: User's email address
        
    Returns:
        Sync result with statistics
    """
    logger.info(f"🔄 Starting contact sync for {user_email}")
    
    start_time = datetime.utcnow()
    
    result = {
        'success': False,
        'skipped': False,
        'user_email': user_email,
        'added': 0,
        'updated': 0,
        'conflicts': 0,
        'errors': [],
        'duration_ms': 0,
    }
    
    # Step 0: Look up user_id for RLS enforcement
    user_id = await _get_user_id_for_email(user_email)
    if not user_id:
        result['errors'].append('User not found in database')
        result['skipped'] = True
        logger.warning(f"User not found for email {user_email}, skipping sync")
        return result
    
    # Get client with user context for RLS
    client = get_user_network_client(user_id=user_id)
    
    try:
        # Step 1: Get or create sync state and mark as syncing
        sync_state = await client.get_or_create_sync_state(user_email, GOOGLE_CONTACTS_PROVIDER)
        await client.start_sync(user_email, GOOGLE_CONTACTS_PROVIDER)
        
        # Step 2: Get OAuth token
        tokens = await get_google_tokens(user_email)
        if not tokens:
            result['errors'].append('No valid OAuth token')
            result['skipped'] = True
            await client.fail_sync(user_email, GOOGLE_CONTACTS_PROVIDER, 'No OAuth token')
            await notify_token_expired(user_email)
            return result
        
        # Step 3: Fetch contacts from Google
        sync_token = sync_state.get('sync_token')
        is_full_sync = sync_token is None
        
        google_contacts, new_sync_token = await fetch_google_contacts(
            user_email, 
            tokens,
            sync_token=sync_token,
        )
        
        logger.info(f"Fetched {len(google_contacts)} contacts from Google for {user_email}")
        
        # Step 4: Process each contact
        added = 0
        updated = 0
        conflicts = 0
        
        for g_contact in google_contacts:
            try:
                sync_result = await sync_single_contact(
                    client,
                    user_email,
                    g_contact,
                )
                if sync_result == 'added':
                    added += 1
                elif sync_result == 'updated':
                    updated += 1
                elif sync_result == 'conflict':
                    conflicts += 1
            except Exception as e:
                logger.error(f"Failed to sync contact: {e}")
                result['errors'].append(str(e))
        
        result['added'] = added
        result['updated'] = updated
        result['conflicts'] = conflicts
        result['success'] = True
        
        # Step 5: Update sync state with success
        await client.complete_sync(
            user_email,
            GOOGLE_CONTACTS_PROVIDER,
            sync_token=new_sync_token,
            added=added,
            updated=updated,
            is_full_sync=is_full_sync,
        )
        
        logger.info(
            f"✓ Contact sync completed for {user_email}: "
            f"{added} added, {updated} updated, {conflicts} conflicts"
        )
        
    except UserNetworkAPIError as e:
        error_msg = f"User Network API error: {e.message}"
        logger.error(f"Contact sync error for {user_email}: {error_msg}")
        result['errors'].append(error_msg)
        
        try:
            await client.fail_sync(user_email, GOOGLE_CONTACTS_PROVIDER, error_msg)
        except Exception:
            pass
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Contact sync error for {user_email}: {error_msg}")
        result['errors'].append(error_msg)
        
        try:
            await client.fail_sync(user_email, GOOGLE_CONTACTS_PROVIDER, error_msg)
        except Exception:
            pass
    
    finally:
        end_time = datetime.utcnow()
        result['duration_ms'] = int((end_time - start_time).total_seconds() * 1000)
        
        # Update in-memory stats cache
        _sync_stats[user_email] = {
            'last_sync': end_time,
            'last_result': result,
        }
        
        # Track contact sync event in PostHog
        # Note: user_id not available here, but user_email is tracked via sync_type
        track_contact_sync(
            user_id=None,  # User ID not available in this context
            contacts_added=result.get('added', 0),
            contacts_updated=result.get('updated', 0),
            contacts_total=result.get('added', 0) + result.get('updated', 0),
            sync_type="scheduled",
            success=result.get('success', False),
            error_message=result['errors'][0] if result.get('errors') else None,
        )
        
        # Send notification if there were changes or errors
        try:
            await notify_sync_complete(user_email, result)
        except Exception as e:
            logger.error(f"Failed to send sync notification: {e}")
    
    return result


async def sync_single_contact(
    client,
    user_email: str,
    google_contact: dict,
) -> str:
    """
    Sync a single Google contact to User Network.
    
    Entity resolution order:
    1. Match by Google resource ID (if previously synced)
    2. Match by email
    3. Match by phone
    4. Create new contact if no match
    
    Args:
        client: UserNetworkClient instance
        user_email: User's email
        google_contact: Contact data from Google
        
    Returns:
        'added', 'updated', or 'conflict'
    """
    resource_name = google_contact.get('resourceName', '')
    
    # Extract contact info from Google format
    names = google_contact.get('names', [{}])
    emails = google_contact.get('emailAddresses', [])
    phones = google_contact.get('phoneNumbers', [])
    orgs = google_contact.get('organizations', [{}])
    addresses = google_contact.get('addresses', [{}])
    birthdays = google_contact.get('birthdays', [{}])
    
    first_name = names[0].get('givenName', '') if names else ''
    last_name = names[0].get('familyName', '') if names else ''
    middle_name = names[0].get('middleName', '') if names else ''
    
    # Skip contacts without a name
    if not first_name and not last_name:
        display_name = names[0].get('displayName', '') if names else ''
        if display_name:
            # Use display name as first name
            first_name = display_name
        else:
            logger.debug(f"Skipping contact without name: {resource_name}")
            return 'skipped'
    
    primary_email = emails[0].get('value', '') if emails else ''
    primary_phone = phones[0].get('value', '') if phones else ''
    company = orgs[0].get('name', '') if orgs else ''
    title = orgs[0].get('title', '') if orgs else ''
    
    # Build person data for User Network
    person_data = {
        'first_name': first_name,
        'last_name': last_name or None,
        'middle_names': middle_name or None,
        'work_email': primary_email or None,
        'personal_cell': primary_phone or None,
        'company': company or None,
        'latest_title': title or None,
    }
    
    # Try to find existing person
    existing_person = None
    match_type = None
    
    # 1. Try by Google resource ID
    try:
        ext_id = await client.lookup_by_external_id('google', resource_name)
        if ext_id:
            existing_person = await client.get_person(ext_id['person_id'])
            match_type = 'google_id'
    except Exception as e:
        logger.debug(f"External ID lookup failed: {e}")
    
    # 2. Try by email
    if not existing_person and primary_email:
        try:
            existing_person = await client.find_person_by_email(primary_email)
            if existing_person:
                match_type = 'email'
        except Exception as e:
            logger.debug(f"Email lookup failed: {e}")
    
    # 3. Try by phone (TODO: implement phone lookup in User Network)
    
    if existing_person:
        # Update existing person
        person_id = str(existing_person['id'])
        
        # Only update fields that have values
        update_data = {k: v for k, v in person_data.items() if v is not None}
        
        if update_data:
            await client.update_person(person_id, update_data)
        
        # Ensure external ID mapping exists
        if match_type != 'google_id':
            await client.upsert_external_id(
                person_id,
                'google',
                resource_name,
                metadata={'etag': google_contact.get('etag')},
            )
        
        logger.debug(f"Updated person {person_id} (matched by {match_type})")
        return 'updated'
    
    else:
        # Create new person
        # Ensure at least one contact method
        if not primary_email and not primary_phone:
            logger.debug(f"Skipping contact without email or phone: {resource_name}")
            return 'skipped'
        
        try:
            new_person = await client.create_person(person_data)
            person_id = str(new_person['id'])
            
            # Create external ID mapping
            await client.upsert_external_id(
                person_id,
                'google',
                resource_name,
                metadata={'etag': google_contact.get('etag')},
            )
            
            logger.debug(f"Created new person {person_id}")
            return 'added'
            
        except UserNetworkAPIError as e:
            if 'contact method required' in str(e.message).lower():
                logger.debug(f"Skipping contact without contact method: {resource_name}")
                return 'skipped'
            raise


async def trigger_manual_sync(user_email: str, user_id=None) -> dict:
    """
    Trigger an immediate sync for a specific user.
    
    Called from API endpoint when user requests manual sync.
    
    Args:
        user_email: User's email address
        user_id: Optional user UUID for analytics
        
    Returns:
        Sync result
    """
    logger.info(f"🏃 Manual sync triggered for {user_email}")
    result = await sync_user_contacts(user_email)
    
    # Track manual sync event (override the scheduled sync tracking)
    track_contact_sync(
        user_id=user_id,
        contacts_added=result.get('added', 0),
        contacts_updated=result.get('updated', 0),
        contacts_total=result.get('added', 0) + result.get('updated', 0),
        sync_type="manual",
        success=result.get('success', False),
        error_message=result['errors'][0] if result.get('errors') else None,
    )
    
    return result


def get_sync_stats(user_email: Optional[str] = None) -> dict:
    """
    Get sync statistics from in-memory cache.
    
    Args:
        user_email: Optional email to get stats for specific user
        
    Returns:
        Sync statistics
    """
    if user_email:
        return _sync_stats.get(user_email, {})
    return _sync_stats


# ============================================================================
# Google Contacts API Helpers
# ============================================================================

async def fetch_google_contacts(
    user_email: str,
    tokens: dict,
    sync_token: Optional[str] = None,
    page_size: int = 100,
) -> tuple[list[dict], Optional[str]]:
    """
    Fetch contacts from Google People API.
    
    Args:
        user_email: User's email
        tokens: OAuth tokens
        sync_token: Previous sync token for incremental sync
        page_size: Number of contacts per page
        
    Returns:
        Tuple of (contacts list, new sync token)
    """
    from ..core.google_services import build_google_service_async
    
    try:
        # Build People API service
        service = await build_google_service_async(user_email, 'people', 'v1')
        
        contacts = []
        next_page_token = None
        new_sync_token = None
        
        # Fields to request
        person_fields = (
            'names,emailAddresses,phoneNumbers,organizations,'
            'addresses,birthdays,metadata'
        )
        
        while True:
            # Build request
            if sync_token:
                # Incremental sync
                request = service.people().connections().list(
                    resourceName='people/me',
                    pageSize=page_size,
                    personFields=person_fields,
                    syncToken=sync_token,
                    pageToken=next_page_token,
                )
            else:
                # Full sync
                request = service.people().connections().list(
                    resourceName='people/me',
                    pageSize=page_size,
                    personFields=person_fields,
                    pageToken=next_page_token,
                )
            
            # Execute request
            response = request.execute()
            
            # Add contacts from this page
            page_contacts = response.get('connections', [])
            contacts.extend(page_contacts)
            
            # Get next page token
            next_page_token = response.get('nextPageToken')
            
            # Get sync token (only on last page)
            if not next_page_token:
                new_sync_token = response.get('nextSyncToken')
            
            # Continue if there are more pages
            if not next_page_token:
                break
        
        logger.info(f"Fetched {len(contacts)} contacts from Google for {user_email}")
        return contacts, new_sync_token
        
    except Exception as e:
        # Check if sync token is invalid
        if 'Sync token is' in str(e) or '410' in str(e):
            logger.warning(f"Sync token expired for {user_email}, doing full sync")
            # Retry without sync token
            return await fetch_google_contacts(user_email, tokens, sync_token=None)
        raise


async def notify_token_expired(user_email: str):
    """
    Send notification that user's OAuth token has expired.
    """
    from ..services.email import send_token_expiry_alert
    
    logger.info(f"Sending token expiry notification to {user_email}")
    
    try:
        result = await send_token_expiry_alert(user_email, provider="Google")
        if result.get("success"):
            logger.info(f"Token expiry notification sent to {user_email}")
        else:
            logger.warning(f"Failed to send token expiry notification: {result.get('error')}")
    except Exception as e:
        logger.error(f"Error sending token expiry notification: {e}")


async def notify_sync_complete(user_email: str, sync_result: dict):
    """
    Send notification about sync completion.
    
    Only sends if there were significant changes or errors.
    """
    from ..services.email import send_sync_notification, send_sync_failure_alert
    
    # Only notify if there were changes or errors
    added = sync_result.get("added", 0)
    updated = sync_result.get("updated", 0)
    errors = sync_result.get("errors", [])
    success = sync_result.get("success", False)
    
    # Skip notification if nothing happened
    if added == 0 and updated == 0 and not errors:
        logger.debug(f"Skipping sync notification for {user_email} - no changes")
        return
    
    try:
        if success:
            result = await send_sync_notification(user_email, sync_result, sync_type="contacts")
        else:
            # For failures, use the failure alert
            error_msg = errors[0] if errors else "Unknown error"
            result = await send_sync_failure_alert(
                user_email, 
                sync_type="contacts",
                error_message=error_msg,
                consecutive_failures=1,
            )
        
        if result.get("success"):
            logger.info(f"Sync notification sent to {user_email}")
        else:
            logger.warning(f"Failed to send sync notification: {result.get('error')}")
    except Exception as e:
        logger.error(f"Error sending sync notification: {e}")
