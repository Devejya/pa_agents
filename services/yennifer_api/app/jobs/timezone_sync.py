"""
Timezone Sync Background Job.

Syncs user timezones from Google Calendar settings to the local database.
This ensures users get accurate local time for calendar operations.

Runs daily at 3 AM UTC.
"""

import logging

from ..core.scheduler import register_job
from ..core.google_services import get_user_calendar_timezone, load_user_tokens
from ..db import get_db_pool
from ..db.user_repository import UserRepository
from ..db.integrations_repository import IntegrationsRepository

logger = logging.getLogger(__name__)

# Required scope for timezone sync - only users with this scope granted will be synced
REQUIRED_SCOPE = "calendar.readonly"


@register_job(
    trigger='cron',
    hour=3,
    minute=0,
    id='timezone_sync',
    name='Sync User Timezones from Google Calendar',
)
async def sync_user_timezones():
    """
    Sync all users' timezones from Google Calendar.
    
    Iterates through all users with the calendar.readonly scope granted and updates their
    timezone in the local database based on their Google Calendar settings.
    
    This job runs daily to keep timezone information up-to-date, especially
    for users who travel or change their calendar timezone settings.
    """
    logger.info("Starting timezone sync job...")
    
    pool = await get_db_pool()
    user_repo = UserRepository(pool)
    integrations_repo = IntegrationsRepository(pool)
    
    # Get users who have the calendar.readonly scope granted
    eligible_users = await integrations_repo.get_users_with_scope_granted(REQUIRED_SCOPE, provider='google')
    
    if not eligible_users:
        logger.info(f"No users with {REQUIRED_SCOPE} scope granted, skipping sync")
        return
    
    # Get user details including current timezone for eligible users
    user_ids = [u['id'] for u in eligible_users]
    async with pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT id, email, timezone as current_tz
            FROM users
            WHERE id = ANY($1::uuid[])
        """, user_ids)
    
    if not users:
        logger.info("No users found after scope check, skipping sync")
        return
    
    logger.info(f"Found {len(users)} users to sync timezones for")
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    for user in users:
        user_email = user['email']
        user_id = user['id']
        current_tz = user['current_tz'] or 'UTC'
        
        try:
            # Load tokens first (required for Google API calls)
            tokens = await load_user_tokens(user_email)
            if not tokens:
                logger.debug(f"No valid tokens for {user_email}, skipping")
                skipped_count += 1
                continue
            
            # Fetch timezone from Google Calendar
            new_tz = get_user_calendar_timezone(user_email)
            
            # Only update if timezone changed
            if new_tz != current_tz:
                await user_repo.update_user_timezone(user_id, new_tz)
                logger.info(f"Updated timezone for {user_email}: {current_tz} -> {new_tz}")
                success_count += 1
            else:
                logger.debug(f"Timezone unchanged for {user_email}: {current_tz}")
                skipped_count += 1
            
        except Exception as e:
            error_count += 1
            logger.warning(f"Failed to sync timezone for {user_email}: {e}")
            # Continue processing other users
    
    logger.info(
        f"Timezone sync complete: {success_count} updated, "
        f"{skipped_count} unchanged, {error_count} errors"
    )

