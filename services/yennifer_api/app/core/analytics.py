"""
PostHog Analytics Service for Yennifer API.

Provides unified analytics tracking for:
- User events (login, logout, app opened)
- Chat events (message sent, session created/restored)
- AI events (errors, fallback responses)
- Tool execution (with timing and categories)
- PII masking events
- Contact sync events

Uses the same PostHog project as the frontend waitlist page.

NOTE: Uses module-level PostHog API.
PostHog SDK v6.x changed from `project_api_key` to `api_key`.
We set both for backwards compatibility.
"""

import functools
import logging
import time
from typing import Any, Callable, Optional
from uuid import UUID

import posthog

from .config import get_settings

logger = logging.getLogger(__name__)

# Track initialization state
_initialized: bool = False


def init_analytics() -> bool:
    """
    Initialize PostHog analytics using module-level configuration.
    
    PostHog SDK v6.x uses `posthog.api_key` (not `project_api_key`).
    We set both for backwards compatibility with older versions.
    
    Call this during application startup.
    
    Returns:
        True if successfully initialized, False otherwise.
    """
    global _initialized
    
    settings = get_settings()
    
    if not settings.posthog_api_key:
        logger.warning("PostHog API key not configured - analytics disabled")
        return False
    
    try:
        # PostHog v6.x uses `api_key`, older versions used `project_api_key`
        # Set both for compatibility
        posthog.api_key = settings.posthog_api_key
        posthog.project_api_key = settings.posthog_api_key  # Backwards compat
        posthog.host = settings.posthog_host
        
        # Disable in test environment
        posthog.disabled = settings.environment == "test"
        
        # Enable debug logging in development
        posthog.debug = settings.environment == "development"
        
        _initialized = True
        logger.info(f"PostHog analytics initialized (host: {settings.posthog_host})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize PostHog: {e}")
        return False


def shutdown_analytics() -> None:
    """
    Shutdown PostHog analytics.
    
    Flushes any pending events before shutdown.
    Call this during application shutdown.
    """
    global _initialized
    
    if not _initialized:
        return
    
    try:
        posthog.flush()
        posthog.shutdown()
        logger.info("PostHog analytics shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down PostHog: {e}")
    finally:
        _initialized = False


def _get_distinct_id(user_id: Optional[UUID]) -> str:
    """Get the distinct ID for a user (UUID as string, or 'anonymous')."""
    if user_id:
        return str(user_id)
    return "anonymous"


# =============================================================================
# Core Tracking Functions
# =============================================================================

def track_event(
    user_id: Optional[UUID],
    event_name: str,
    properties: Optional[dict[str, Any]] = None,
) -> None:
    """
    Track a generic event.
    
    Args:
        user_id: User's UUID (used as distinct_id)
        event_name: Name of the event
        properties: Additional event properties
    """
    if not _initialized:
        return
    
    try:
        posthog.capture(
            distinct_id=_get_distinct_id(user_id),
            event=event_name,
            properties=properties or {},
        )
    except Exception as e:
        logger.error(f"Failed to track event '{event_name}': {e}")


def identify_user(
    user_id: UUID,
    traits: Optional[dict[str, Any]] = None,
) -> None:
    """
    Identify a user with traits.
    
    NOTE: posthog.identify() may not be available in older SDK versions.
    We fall back to capture with $set if identify is not available.
    
    Args:
        user_id: User's UUID
        traits: User properties (name, email hash, etc.)
    """
    if not _initialized:
        return
    
    try:
        # Try identify first (newer SDK versions)
        if hasattr(posthog, 'identify'):
            posthog.identify(
                distinct_id=str(user_id),
                properties=traits or {},
            )
        else:
            # Fallback: use capture with $set for older versions
            posthog.capture(
                distinct_id=str(user_id),
                event="$identify",
                properties={"$set": traits or {}},
            )
    except Exception as e:
        logger.error(f"Failed to identify user: {e}")


# =============================================================================
# User Events
# =============================================================================

def track_user_login(
    user_id: Optional[UUID],
    is_new_user: bool = False,
    login_method: str = "google_oauth",
) -> None:
    """Track user login event."""
    track_event(
        user_id=user_id,
        event_name="user_login",
        properties={
            "is_new_user": is_new_user,
            "login_method": login_method,
        },
    )


def track_user_logout(user_id: Optional[UUID]) -> None:
    """Track user logout event."""
    track_event(
        user_id=user_id,
        event_name="user_logout",
        properties={},
    )


def track_app_opened(user_id: Optional[UUID]) -> None:
    """Track when user opens/returns to the app."""
    track_event(
        user_id=user_id,
        event_name="app_opened",
        properties={},
    )


def track_oauth_error(
    user_id: Optional[UUID],
    error_type: str,
    error_message: Optional[str] = None,
) -> None:
    """Track OAuth-related errors."""
    track_event(
        user_id=user_id,
        event_name="oauth_error",
        properties={
            "error_type": error_type,
            "error_message": error_message,
        },
    )


# =============================================================================
# Chat Events
# =============================================================================

def track_message_sent(
    user_id: Optional[UUID],
    session_id: Optional[str],
    message_length: int,
    has_tool_calls: bool = False,
    tool_count: int = 0,
    response_time_ms: Optional[int] = None,
) -> None:
    """Track when a user sends a message."""
    track_event(
        user_id=user_id,
        event_name="message_sent",
        properties={
            "session_id": session_id,
            "message_length": message_length,
            "has_tool_calls": has_tool_calls,
            "tool_count": tool_count,
            "response_time_ms": response_time_ms,
        },
    )


def track_session_created(
    user_id: Optional[UUID],
    session_id: str,
) -> None:
    """Track when a new chat session is created."""
    track_event(
        user_id=user_id,
        event_name="session_created",
        properties={
            "session_id": session_id,
        },
    )


def track_session_restored(
    user_id: Optional[UUID],
    session_id: str,
    message_count: int,
) -> None:
    """Track when a session is restored from database (cross-device)."""
    track_event(
        user_id=user_id,
        event_name="session_restored",
        properties={
            "session_id": session_id,
            "message_count": message_count,
        },
    )


# =============================================================================
# AI Events
# =============================================================================

def track_ai_error(
    user_id: Optional[UUID],
    error_type: str,
    error_message: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """Track AI response generation errors."""
    track_event(
        user_id=user_id,
        event_name="ai_error",
        properties={
            "error_type": error_type,
            "error_message": error_message,
            "session_id": session_id,
        },
    )


def track_fallback_shown(
    user_id: Optional[UUID],
    session_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Track when fallback message is shown to user."""
    track_event(
        user_id=user_id,
        event_name="fallback_shown",
        properties={
            "session_id": session_id,
            "reason": reason,
        },
    )


# =============================================================================
# PII Events
# =============================================================================

def track_pii_masked(
    user_id: Optional[UUID],
    total_masked: int,
    emails_masked: int = 0,
    phones_masked: int = 0,
    ssn_masked: int = 0,
    cards_masked: int = 0,
    endpoint: Optional[str] = None,
) -> None:
    """Track PII masking events."""
    track_event(
        user_id=user_id,
        event_name="pii_masked",
        properties={
            "total_masked": total_masked,
            "emails_masked": emails_masked,
            "phones_masked": phones_masked,
            "ssn_masked": ssn_masked,
            "cards_masked": cards_masked,
            "endpoint": endpoint,
        },
    )


# =============================================================================
# Tool Events
# =============================================================================

# Tool category mapping
TOOL_CATEGORIES = {
    # Gmail
    "read_emails": "gmail",
    "get_email_by_id": "gmail",
    "send_email": "gmail",
    "search_emails": "gmail",
    # Calendar
    "list_calendar_events": "calendar",
    "create_calendar_event": "calendar",
    "update_calendar_event": "calendar",
    "delete_calendar_event": "calendar",
    "get_calendar_event": "calendar",
    "get_current_datetime": "calendar",
    # Contacts
    "list_contacts": "contacts",
    "search_contacts": "contacts",
    "lookup_contact_email": "contacts",
    # Drive
    "list_drive_files": "drive",
    "search_drive_files": "drive",
    "get_file_content": "drive",
    "create_drive_folder": "drive",
    "rename_drive_file": "drive",
    "move_drive_file": "drive",
    "delete_drive_file": "drive",
    "copy_drive_file": "drive",
    # Sheets
    "create_spreadsheet": "sheets",
    "add_sheet_to_spreadsheet": "sheets",
    "read_spreadsheet": "sheets",
    "read_spreadsheet_data": "sheets",
    "write_to_spreadsheet": "sheets",
    "write_spreadsheet_data": "sheets",
    "list_spreadsheets": "sheets",
    "search_spreadsheets": "sheets",
    # Docs
    "read_document": "docs",
    "create_document": "docs",
    "list_documents": "docs",
    "append_to_document": "docs",
    "replace_text_in_document": "docs",
    "insert_text_at_position": "docs",
    # Slides
    "read_presentation": "slides",
    "list_presentations": "slides",
    "create_presentation": "slides",
    "add_slide": "slides",
    "add_text_to_slide": "slides",
    "delete_slide": "slides",
    # Memory
    "get_user_memories": "memory",
    "save_user_memory": "memory",
    "get_user_interests": "memory",
    "save_user_interest": "memory",
    "get_upcoming_important_dates": "memory",
    "save_important_date_for_person": "memory",
    "get_important_dates_for_person": "memory",
    "get_person_interests": "memory",
    "save_person_interest": "memory",
    "save_person_note": "memory",
    "get_person_notes": "memory",
    "get_upcoming_person_notes": "memory",
    # Entity Resolution
    "find_person_candidates": "entity",
    "find_person_by_relationship": "entity",
    "create_person_in_network": "entity",
    "confirm_person_selection": "entity",
    "check_person_has_contact": "entity",
    "update_person_contact": "entity",
    "add_relationship_between_persons": "entity",
    # Web Search
    "web_search": "web_search",
    # Contact Sync
    "trigger_contact_sync": "contact_sync",
}


def get_tool_category(tool_name: str) -> str:
    """Get the category for a tool name."""
    return TOOL_CATEGORIES.get(tool_name, "unknown")


def track_tool_called(
    user_id: Optional[UUID],
    tool_name: str,
    tool_category: Optional[str] = None,
    execution_time_ms: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """Track tool execution."""
    if tool_category is None:
        tool_category = get_tool_category(tool_name)
    
    track_event(
        user_id=user_id,
        event_name="tool_called",
        properties={
            "tool_name": tool_name,
            "tool_category": tool_category,
            "execution_time_ms": execution_time_ms,
            "success": success,
            "error_message": error_message,
        },
    )


# =============================================================================
# Contact Sync Events
# =============================================================================

def track_contact_sync(
    user_id: Optional[UUID],
    contacts_added: int = 0,
    contacts_updated: int = 0,
    contacts_total: int = 0,
    sync_type: str = "manual",
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """Track contact sync completion."""
    track_event(
        user_id=user_id,
        event_name="contact_sync_completed",
        properties={
            "contacts_added": contacts_added,
            "contacts_updated": contacts_updated,
            "contacts_total": contacts_total,
            "sync_type": sync_type,
            "success": success,
            "error_message": error_message,
        },
    )


# =============================================================================
# Tool Tracking Decorator
# =============================================================================

# Context variable to hold current user_id for tool tracking
_current_tracking_user_id: Optional[UUID] = None


def set_tracking_user(user_id: Optional[UUID]) -> None:
    """Set the current user ID for tool tracking context."""
    global _current_tracking_user_id
    _current_tracking_user_id = user_id


def get_tracking_user() -> Optional[UUID]:
    """Get the current user ID for tool tracking."""
    return _current_tracking_user_id


def tracked_tool(tool_name: str, category: Optional[str] = None):
    """
    Decorator to track tool execution with timing.
    
    Usage:
        @tracked_tool("read_emails", "gmail")
        def read_emails(...):
            ...
    
    Or without category (will be auto-detected):
        @tracked_tool("read_emails")
        def read_emails(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error_msg = None
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                execution_time_ms = int((time.time() - start_time) * 1000)
                track_tool_called(
                    user_id=get_tracking_user(),
                    tool_name=tool_name,
                    tool_category=category,
                    execution_time_ms=execution_time_ms,
                    success=success,
                    error_message=error_msg,
                )
        
        return wrapper
    return decorator

