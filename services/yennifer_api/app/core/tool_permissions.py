"""
Tool Permissions Layer

Maps tools to required scopes and filters available tools based on user's
enabled integrations and scopes.
"""

import logging
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from ..db import get_db_pool
from ..db.integrations_repository import IntegrationsRepository

logger = logging.getLogger(__name__)


# ============================================================================
# Tool-to-Scope Mapping
# Maps tool function names to the scope IDs required to use them
# ============================================================================

TOOL_SCOPE_REQUIREMENTS: Dict[str, List[str]] = {
    # === Utility tools (no scope required) ===
    "get_current_datetime": [],
    "get_my_profile": [],
    "lookup_contact_email": [],
    
    # === Gmail tools ===
    "read_recent_emails": ["gmail.readonly"],
    "read_important_emails": ["gmail.readonly"],
    "search_emails": ["gmail.readonly"],
    "get_email_details": ["gmail.readonly"],
    "send_email": ["gmail.compose"],
    
    # === Calendar tools ===
    "list_calendar_events": ["calendar.readonly"],
    "create_calendar_event": ["calendar.events"],
    "update_calendar_event": ["calendar.events"],
    "delete_calendar_event": ["calendar.events"],
    
    # === Contacts tools ===
    "list_my_contacts": ["contacts.readonly"],
    "search_my_contacts": ["contacts.readonly"],
    "sync_contacts_to_database": ["contacts.readonly"],
    
    # === Drive tools ===
    "list_drive_files": ["drive.readonly"],
    "search_drive": ["drive.readonly"],
    "create_drive_folder": ["drive.file"],
    "rename_drive_file": ["drive.file"],
    "move_drive_file": ["drive.file"],
    "delete_drive_file": ["drive.file"],
    "copy_drive_file": ["drive.file"],
    
    # === Sheets tools ===
    "list_spreadsheets": ["sheets.readonly"],
    "search_spreadsheets": ["sheets.readonly"],
    "read_spreadsheet_data": ["sheets.readonly"],
    "create_new_spreadsheet": ["sheets.full"],
    "add_sheet_to_spreadsheet": ["sheets.full"],
    "write_spreadsheet_data": ["sheets.full"],
    
    # === Docs tools ===
    "list_google_docs": ["docs.readonly"],
    "read_google_doc": ["docs.readonly"],
    "create_google_doc": ["docs.full"],
    "append_to_google_doc": ["docs.full"],
    "find_replace_in_doc": ["docs.full"],
    
    # === Slides tools ===
    "list_presentations": ["slides.readonly"],
    "read_presentation_content": ["slides.readonly"],
    "create_slides_presentation": ["slides.full"],
    "add_slide_to_presentation": ["slides.full"],
    "add_text_to_presentation_slide": ["slides.full"],
    "delete_presentation_slide": ["slides.full"],
}

# Tools that don't require any Google scopes (memory, entity resolution, web search)
# These are always available
ALWAYS_AVAILABLE_TOOLS: Set[str] = {
    # Utility
    "get_current_datetime",
    "get_my_profile",
    "lookup_contact_email",
    # Memory tools (use User Network, not Google APIs)
    "save_user_memory",
    "get_user_memories",
    "save_user_interest",
    "get_user_interests",
    "save_important_date_for_person",
    "get_upcoming_important_dates",
    "get_important_dates_for_person",
    "save_person_interest",
    "get_person_interests",
    "save_person_note",
    "get_person_notes",
    "get_upcoming_person_notes",
    # Entity resolution tools
    "find_person_by_relationship",
    "find_person_candidates",
    "create_person_in_network",
    "add_relationship_between_persons",
    "update_person_contact",
    "check_person_has_contact",
    "confirm_person_selection",
    # Web search
    "web_search",
}


async def get_user_enabled_scopes(user_id: UUID) -> Set[str]:
    """
    Get the set of scope IDs that the user has enabled AND been granted.
    
    Args:
        user_id: User's UUID
        
    Returns:
        Set of scope IDs like {'gmail.readonly', 'calendar.events'}
    """
    pool = await get_db_pool()
    repo = IntegrationsRepository(pool)
    
    # Get scopes that are both enabled by user AND have OAuth consent
    scopes = await repo.get_user_enabled_scopes(user_id, granted_only=True)
    return set(scopes)


async def get_available_tool_names(user_id: UUID) -> Set[str]:
    """
    Get the set of tool names available to a user based on their enabled scopes.
    
    Args:
        user_id: User's UUID
        
    Returns:
        Set of tool names the user can use
    """
    enabled_scopes = await get_user_enabled_scopes(user_id)
    
    available = set(ALWAYS_AVAILABLE_TOOLS)
    
    for tool_name, required_scopes in TOOL_SCOPE_REQUIREMENTS.items():
        # Tool is available if user has all required scopes
        # Tools with no requirements (empty list) are also available
        if not required_scopes or all(scope in enabled_scopes for scope in required_scopes):
            available.add(tool_name)
    
    return available


async def filter_tools_for_user(user_id: UUID, tools: List[Any]) -> List[Any]:
    """
    Filter a list of tools to only those the user has permission to use.
    
    Args:
        user_id: User's UUID
        tools: List of LangChain tool objects
        
    Returns:
        Filtered list of tools
    """
    available_names = await get_available_tool_names(user_id)
    
    filtered = []
    for tool in tools:
        tool_name = getattr(tool, 'name', None)
        if tool_name and tool_name in available_names:
            filtered.append(tool)
        elif tool_name:
            logger.debug(f"Filtering out tool '{tool_name}' - user lacks required scopes")
    
    return filtered


async def get_disabled_integrations_for_agent(user_id: UUID) -> List[Dict[str, str]]:
    """
    Get information about disabled integrations for the agent context.
    
    Returns a simplified list suitable for building the system prompt.
    
    Args:
        user_id: User's UUID
        
    Returns:
        List of dicts with 'name' and 'capability_summary' keys
    """
    try:
        pool = await get_db_pool()
        repo = IntegrationsRepository(pool)
        
        disabled = await repo.get_disabled_integrations(user_id)
        
        return [
            {
                "name": i["name"],
                "capability_summary": i.get("capability_summary", i.get("description", "")),
            }
            for i in disabled
        ]
    except Exception as e:
        # Tables may not exist yet - return empty list (all integrations available)
        logger.warning(f"Failed to get disabled integrations (tables may not exist): {e}")
        return []


def get_scope_for_tool(tool_name: str) -> List[str]:
    """
    Get the scopes required for a specific tool.
    
    Args:
        tool_name: Name of the tool
        
    Returns:
        List of required scope IDs (empty if no special scopes needed)
    """
    return TOOL_SCOPE_REQUIREMENTS.get(tool_name, [])


def get_integration_for_tool(tool_name: str) -> Optional[str]:
    """
    Get the integration ID that a tool belongs to.
    
    Args:
        tool_name: Name of the tool
        
    Returns:
        Integration ID (e.g., 'gmail', 'calendar') or None
    """
    required_scopes = TOOL_SCOPE_REQUIREMENTS.get(tool_name, [])
    
    if not required_scopes:
        return None
    
    # Extract integration from first scope (e.g., 'gmail.readonly' -> 'gmail')
    first_scope = required_scopes[0]
    return first_scope.split('.')[0] if '.' in first_scope else first_scope


# ============================================================================
# Integration capability summaries (used when building agent context)
# ============================================================================

INTEGRATION_CAPABILITIES: Dict[str, str] = {
    "gmail": "reading and sending emails",
    "calendar": "viewing and managing calendar events",
    "contacts": "accessing contact information",
    "drive": "browsing and managing files",
    "sheets": "reading and writing spreadsheets",
    "docs": "reading and writing documents",
    "slides": "reading and writing presentations",
}


def get_capability_summary(integration_id: str) -> str:
    """Get a human-readable summary of what an integration enables."""
    return INTEGRATION_CAPABILITIES.get(integration_id, f"using {integration_id}")

