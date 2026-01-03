"""
Background Jobs Package.

This package contains all background jobs that run on a schedule.

Available jobs:
- core_user_sync: Syncs core user profile from Gmail (on login)
- contact_sync: Syncs Google Contacts with User Network (every 30 minutes)
- token_refresh: Refreshes OAuth tokens before expiry (every hour)
- health_check: Heartbeat job for monitoring (every 5 minutes)
- timezone_sync: Syncs user timezones from Google Calendar (daily at 3 AM)

Usage:
    # Jobs are auto-registered when imported
    from app.jobs import register_all_jobs
    
    # Call during app startup
    register_all_jobs()
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Track registered jobs
_jobs_registered = False


def register_all_jobs():
    """
    Register all background jobs with the scheduler.
    
    Call this during application startup after the scheduler is initialized.
    """
    global _jobs_registered
    
    if _jobs_registered:
        logger.warning("Jobs already registered, skipping...")
        return
    
    logger.info("📦 Registering background jobs...")
    
    # Import job modules to trigger registration via decorators
    from . import health_check
    from . import contact_sync
    from . import core_user_sync
    from . import timezone_sync
    
    _jobs_registered = True
    logger.info("✓ All background jobs registered")


def get_registered_jobs() -> list[str]:
    """Get list of registered job module names."""
    return [
        'health_check',
        'contact_sync',
        'core_user_sync',
        'timezone_sync',
    ]

