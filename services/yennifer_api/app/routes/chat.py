"""
Chat API routes for Yennifer assistant.

Supports both in-memory and database-backed chat history.
When a user has a user_id (from multi-tenant auth), messages are persisted
to the database with per-user encryption.
"""

import asyncio
import contextvars
import logging
import time
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field

from ..core.agent import YenniferAssistant
from ..core.auth import TokenData, get_current_user
from ..core.chat_cache import get_chat_cache
from ..core.google_services import load_user_tokens
from ..core.workspace_tools import WORKSPACE_TOOLS
from ..core.memory_tools import MEMORY_TOOLS
from ..core.entity_resolution_tools import ENTITY_RESOLUTION_TOOLS
from ..core.web_search_tools import WEB_SEARCH_TOOLS
from ..core.pii import unmask_pii, get_pii_context
from ..core.pii_audit import get_pii_audit_logger, flush_pii_audit
from ..core.analytics import (
    track_message_sent,
    track_pii_masked,
    track_session_created,
    track_session_restored,
    track_tool_called,
    set_tracking_user,
    get_tool_category,
)
from ..db import get_db_pool, ChatRepository
from ..middleware.audit import get_request_id

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory session storage (keyed by email)
# Used as fallback when database persistence is not available
_sessions: dict[str, YenniferAssistant] = {}


def get_or_create_session(user_email: str, user_id: Optional[UUID] = None) -> YenniferAssistant:
    """Get existing session or create new one for the user."""
    if user_email not in _sessions:
        _sessions[user_email] = YenniferAssistant(user_email=user_email, user_id=user_id)
    # Always set user to ensure global _current_user_email is set
    # (Critical after server restarts when creating new sessions)
    _sessions[user_email].set_user(user_email, user_id)
    return _sessions[user_email]


def _build_tool_registry() -> Dict[str, Any]:
    """Build a registry mapping tool names to tool functions for re-execution."""
    registry = {}
    all_tools = WORKSPACE_TOOLS + MEMORY_TOOLS + ENTITY_RESOLUTION_TOOLS + WEB_SEARCH_TOOLS
    for tool in all_tools:
        # LangChain tools have a .name attribute
        if hasattr(tool, 'name'):
            registry[tool.name] = tool
    return registry


# Cached tool registry (built once on module load)
_TOOL_REGISTRY: Optional[Dict[str, Any]] = None


def get_tool_registry() -> Dict[str, Any]:
    """Get the tool registry, building it if needed."""
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is None:
        _TOOL_REGISTRY = _build_tool_registry()
    return _TOOL_REGISTRY


# ============== Request/Response Models ==============

class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Request to send a message."""
    message: str = Field(..., min_length=1, description="User's message")
    session_id: Optional[str] = Field(None, description="Optional session ID (UUID)")


class ChatResponse(BaseModel):
    """Response from the assistant."""
    response: str = Field(..., description="Assistant's response")
    session_id: Optional[str] = Field(None, description="Session ID if using database persistence")
    

class ChatHistoryResponse(BaseModel):
    """Chat history response."""
    messages: list[ChatMessage]
    session_id: Optional[str] = None


class ClearHistoryResponse(BaseModel):
    """Response after clearing history."""
    status: str = "success"
    message: str = "Chat history cleared"


class SessionInfo(BaseModel):
    """Chat session information."""
    id: str
    title: Optional[str]
    is_active: bool
    created_at: str
    last_message_at: Optional[str]
    message_count: int


class SessionListResponse(BaseModel):
    """List of chat sessions."""
    sessions: List[SessionInfo]


# ============== Helper Functions ==============

# Read-only tools that are safe to re-execute on session restore
# These tools only fetch data and have no side effects
READ_ONLY_TOOLS = {
    # Memory/User Network read tools
    "get_user_memories",
    "get_user_interests",
    "get_upcoming_important_dates",
    "find_person_by_relationship",
    "get_person_interests",
    "get_important_dates_for_person",
    "get_person_notes",
    "get_upcoming_person_notes",
    "find_person_candidates",
    # Workspace read tools
    "get_current_datetime",
    "get_my_profile",
    "lookup_contact_email",
    "list_calendar_events",
    "read_recent_emails",
    "search_emails",
    "get_email_details",
    "list_my_contacts",
    "search_my_contacts",
    "list_drive_files",
    "search_drive",
    "list_spreadsheets",
    "search_spreadsheets",
    "read_spreadsheet_data",
    "list_google_docs",
    "read_google_doc",
    "list_presentations",
    "read_presentation_content",
    # Web search (read-only, safe to retry)
    "web_search",
}


def repair_incomplete_tool_calls(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Repair chat history that has AIMessages with tool_calls but missing ToolMessages.
    
    This is a synchronous fallback that uses placeholders.
    For async context (where tools can be re-executed), use repair_incomplete_tool_calls_async.
    
    Args:
        history: List of message dicts with role, content, tool_calls, tool_call_id
        
    Returns:
        Repaired history with placeholder ToolMessages for orphan tool_calls
    """
    # First pass: collect all tool_call IDs from AIMessages and existing ToolMessages
    expected_tool_call_ids = {}  # tool_call_id -> (message_index, tool_call_info)
    existing_tool_call_ids = set()
    
    for i, msg in enumerate(history):
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id:
                    expected_tool_call_ids[tc_id] = (i, tc)
        elif msg["role"] == "tool" and msg.get("tool_call_id"):
            existing_tool_call_ids.add(msg["tool_call_id"])
    
    # Find orphan tool_calls (in AIMessage but no corresponding ToolMessage)
    orphan_ids = set(expected_tool_call_ids.keys()) - existing_tool_call_ids
    
    if not orphan_ids:
        return history  # No repairs needed
    
    # Log the repair
    orphan_names = [expected_tool_call_ids[tc_id][1].get("name", "unknown") for tc_id in orphan_ids]
    logger.warning(
        f"Repairing {len(orphan_ids)} orphan tool_calls in chat history: {orphan_names}. "
        f"This usually happens after a server restart during tool execution."
    )
    
    # Build repaired history by inserting placeholder ToolMessages after orphan AIMessages
    repaired = []
    for i, msg in enumerate(history):
        repaired.append(msg)
        
        # After an AIMessage with orphan tool_calls, insert placeholder ToolMessages
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id in orphan_ids:
                    tool_name = tc.get("name", "unknown")
                    placeholder = {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": f"[Tool '{tool_name}' execution was interrupted by server restart. Please retry the request.]",
                    }
                    repaired.append(placeholder)
    
    return repaired


async def repair_incomplete_tool_calls_async(
    history: List[Dict[str, Any]],
    tool_registry: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Repair chat history by re-executing read-only tools and using placeholders for writes.
    
    This is smarter than the sync version - it actually re-runs safe tools to restore
    accurate context, while using placeholders for write operations (which could cause duplicates).
    
    Args:
        history: List of message dicts with role, content, tool_calls, tool_call_id
        tool_registry: Dict mapping tool names to tool functions
        
    Returns:
        Repaired history with actual results for read-only tools, placeholders for writes
    """
    # First pass: collect all tool_call IDs
    expected_tool_call_ids = {}  # tool_call_id -> tool_call_info
    existing_tool_call_ids = set()
    
    for msg in history:
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id:
                    expected_tool_call_ids[tc_id] = tc
        elif msg["role"] == "tool" and msg.get("tool_call_id"):
            existing_tool_call_ids.add(msg["tool_call_id"])
    
    # Find orphan tool_calls
    orphan_ids = set(expected_tool_call_ids.keys()) - existing_tool_call_ids
    
    if not orphan_ids:
        return history  # No repairs needed
    
    # Categorize orphans
    read_only_orphans = []
    write_orphans = []
    for tc_id in orphan_ids:
        tc = expected_tool_call_ids[tc_id]
        tool_name = tc.get("name", "unknown")
        if tool_name in READ_ONLY_TOOLS:
            read_only_orphans.append((tc_id, tc))
        else:
            write_orphans.append((tc_id, tc))
    
    logger.warning(
        f"Repairing {len(orphan_ids)} orphan tool_calls: "
        f"{len(read_only_orphans)} read-only (will re-execute), "
        f"{len(write_orphans)} write (will use placeholders)"
    )
    
    # Re-execute read-only tools and cache results
    tool_results = {}  # tc_id -> result content
    
    for tc_id, tc in read_only_orphans:
        tool_name = tc.get("name", "unknown")
        tool_args = tc.get("args", {})
        
        if tool_name in tool_registry:
            try:
                tool_func = tool_registry[tool_name]
                # Call the tool with its original arguments
                # Use functools.partial or default args to capture variables correctly
                def invoke_tool(func=tool_func, args=tool_args):
                    return func.invoke(args)
                result = await asyncio.get_event_loop().run_in_executor(None, invoke_tool)
                tool_results[tc_id] = str(result)
                logger.info(f"Re-executed read-only tool '{tool_name}' successfully")
            except Exception as e:
                logger.warning(f"Failed to re-execute tool '{tool_name}': {e}")
                tool_results[tc_id] = f"[Tool '{tool_name}' re-execution failed: {str(e)[:100]}. Please retry.]"
        else:
            tool_results[tc_id] = f"[Tool '{tool_name}' not found in registry. Please retry.]"
    
    # Build repaired history
    repaired = []
    for msg in history:
        repaired.append(msg)
        
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id in orphan_ids:
                    tool_name = tc.get("name", "unknown")
                    
                    if tc_id in tool_results:
                        # Read-only tool - use re-executed result
                        content = tool_results[tc_id]
                    else:
                        # Write tool - use placeholder
                        content = (
                            f"[Tool '{tool_name}' was interrupted by server restart. "
                            f"This is a write operation - please verify and retry if needed to avoid duplicates.]"
                        )
                    
                    repaired.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": content,
                    })
    
    return repaired


async def persist_message(
    user_id: UUID,
    session_id: UUID,
    role: str,
    content: str,
    model: Optional[str] = None,
    tool_calls: Optional[list] = None,
    tool_call_id: Optional[str] = None,
) -> None:
    """
    Persist a message to database and cache.
    
    Args:
        user_id: User's UUID
        session_id: Chat session UUID
        role: Message role ('user', 'assistant', 'tool')
        content: Message content
        model: Optional model name (for assistant messages)
        tool_calls: Optional list of tool calls (for AIMessage with tool invocations)
        tool_call_id: Optional tool_call_id (for ToolMessage linking back to AIMessage)
    """
    try:
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        message = await chat_repo.add_message(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            model=model,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )
        
        # Also write to cache for fast retrieval (cache only stores user/assistant for UI)
        # Tool messages are not cached as they're for LLM context, not UI display
        cache = get_chat_cache()
        if cache.is_enabled and role in ("user", "assistant"):
            await cache.cache_message(user_id, session_id, message)
            
    except Exception as e:
        logger.error(f"Failed to persist message: {e}")
        # Don't fail the request, just log


async def get_or_create_db_session(user_id: UUID) -> dict:
    """Get or create a database session for the user."""
    pool = await get_db_pool()
    chat_repo = ChatRepository(pool)
    return await chat_repo.get_or_create_active_session(user_id)


async def restore_agent_context_from_db(
    agent: YenniferAssistant,
    user_id: UUID,
    session_id: UUID,
) -> bool:
    """
    Restore agent's in-memory chat history from database.
    
    This enables cross-device/browser persistence - when a user logs in
    from a new device, we load their previous conversation into the agent's
    context so the LLM has full history including tool calls and results.
    
    Args:
        agent: The YenniferAssistant instance to populate
        user_id: User's UUID for database access
        session_id: The DB session to load messages from
        
    Returns:
        True if history was restored, False otherwise
    """
    try:
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        
        # Get messages from database (already decrypted by repository)
        messages = await chat_repo.get_session_messages(
            user_id=user_id,
            session_id=session_id,
            limit=50,  # Limit context window for LLM
        )
        
        if messages:
            # Convert to agent's history format, including tool_calls and tool_call_id
            history = []
            for m in messages:
                entry: Dict[str, Any] = {"role": m["role"], "content": m["content"]}
                # Include tool_calls for AIMessage (assistant with tool invocations)
                if m.get("tool_calls"):
                    entry["tool_calls"] = m["tool_calls"]
                # Include tool_call_id for ToolMessage (tool results)
                if m.get("tool_call_id"):
                    entry["tool_call_id"] = m["tool_call_id"]
                history.append(entry)
            
            # Repair history if there are orphan tool_calls (from interrupted sessions)
            # This prevents LangChain "AIMessages with tool_calls without ToolMessage" errors
            # Use async version to re-execute read-only tools for accurate context
            history = await repair_incomplete_tool_calls_async(history, get_tool_registry())
            
            agent.set_history(history)
            logger.info(f"Restored {len(messages)} messages into agent context for user {user_id}")
            
            # Track session restored event in PostHog
            track_session_restored(
                user_id=user_id,
                session_id=str(session_id),
                message_count=len(messages),
            )
            
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Failed to restore agent context from DB: {e}")
        return False


# ============== API Endpoints ==============

@router.post("", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    current_user: TokenData = Depends(get_current_user),
) -> ChatResponse:
    """
    Send a message to Yennifer and get a response.
    
    This endpoint blocks until the full response is ready.
    The frontend should show a "thinking..." indicator while waiting.
    
    If the user has database persistence enabled (user_id in token),
    messages are saved to the database with encryption.
    
    Requires authentication via JWT token.
    """
    # Start timing for analytics
    start_time = time.time()
    
    try:
        # Load user tokens into cache for sync tool access
        tokens = await load_user_tokens(current_user.email)
        if not tokens:
            logger.warning(f"No Google tokens found for {current_user.email}")
            # Continue anyway - tools will return appropriate errors
        
        user_id = current_user.user_id  # May be None for legacy users
        session = get_or_create_session(current_user.email, user_id)
        
        # Set user ID for tool tracking context
        set_tracking_user(user_id)
        
        # Load user context (memories, interests) for personalization
        if user_id:
            try:
                await session.load_user_context()
            except Exception as e:
                logger.warning(f"Failed to load user context: {e}")
            
            # Load integration context (disabled integrations) for agent awareness
            try:
                await session.load_integration_context()
            except Exception as e:
                logger.warning(f"Failed to load integration context: {e}")
        
        # Determine if we should use database persistence
        db_session_id = None
        is_new_session = False
        
        if user_id:
            try:
                # Get or create database session
                if request.session_id:
                    db_session_id = UUID(request.session_id)
                else:
                    db_session = await get_or_create_db_session(user_id)
                    db_session_id = db_session["id"]
                    # Track if this is a brand new session (for auto-titling)
                    is_new_session = db_session.get("message_count", 0) == 0
                
                # CRITICAL: Restore agent context from DB if in-memory is empty
                # This enables cross-device persistence - when user logs in from
                # a new browser/device, we load their previous conversation
                if not session.get_history() and db_session_id:
                    await restore_agent_context_from_db(session, user_id, db_session_id)
                
                # Persist user message
                await persist_message(
                    user_id=user_id,
                    session_id=db_session_id,
                    role="user",
                    content=request.message,
                )
            except Exception as e:
                logger.error(f"Database persistence error: {e}")
                # Continue without persistence
        
        # Get response from agent
        # Run in executor with copied context to preserve ContextVars (PIIContext)
        copied_ctx = contextvars.copy_context()
        response = await asyncio.get_event_loop().run_in_executor(
            None,  # Default executor
            copied_ctx.run,
            session.chat,
            request.message,
        )
        
        # Get PII stats from the context that was used in the threadpool
        # We need to run get_pii_context() in the same copied context
        pii_ctx = copied_ctx.run(get_pii_context)
        pii_stats = pii_ctx.get_stats()
        
        # Log PII stats (always log for debugging, even if 0)
        logger.warning(
            f"PII stats after agent run: total={pii_stats.get('total', 0)}, "
            f"emails={pii_stats.get('email', 0)}, "
            f"phones={pii_stats.get('phone', 0)}, "
            f"ssn={pii_stats.get('ssn', 0)}, "
            f"cards={pii_stats.get('card', 0)}"
        )
        
        # Log PII audit if any masking occurred
        if pii_stats.get("total", 0) > 0:
            logger.warning(
                f"PII MASKED in chat request: {pii_stats['total']} items - writing audit"
            )
            
            # Queue audit entry
            audit_logger = get_pii_audit_logger()
            if audit_logger:
                audit_logger.log_masking_event(
                    user_id=user_id,
                    request_id=str(get_request_id()) if get_request_id() else None,
                    endpoint="/api/v1/chat",
                    tool_name="chat",
                    stats=pii_stats,
                    masking_mode="full",
                )
                # Flush to database
                await flush_pii_audit()
            
            # Track PII masking event in PostHog
            track_pii_masked(
                user_id=user_id,
                total_masked=pii_stats.get("total", 0),
                emails_masked=pii_stats.get("email", 0),
                phones_masked=pii_stats.get("phone", 0),
                ssn_masked=pii_stats.get("ssn", 0),
                cards_masked=pii_stats.get("card", 0),
                endpoint="/api/v1/chat",
            )
        
        # Unmask PII in response before returning to user
        # The LLM saw masked data ([CARD_1], [EMAIL_1], etc.)
        # But the user should see the actual values
        # Run unmask in the same context to access the mappings
        response = copied_ctx.run(unmask_pii, response)
        
        # Persist ALL new messages from the agent turn (tool calls, tool results, final response)
        # This enables cross-device session continuity with full tool context
        if user_id and db_session_id:
            try:
                new_messages = session.get_last_new_messages()
                for msg in new_messages:
                    if isinstance(msg, AIMessage):
                        # AIMessage - may have tool_calls (intermediate) or be final response
                        tool_calls = None
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            # Serialize tool_calls for storage
                            tool_calls = [
                                {"name": tc.get("name"), "args": tc.get("args"), "id": tc.get("id")}
                                for tc in msg.tool_calls
                            ]
                        await persist_message(
                            user_id=user_id,
                            session_id=db_session_id,
                            role="assistant",
                            content=msg.content or "",
                            model="gpt-4o",
                            tool_calls=tool_calls,
                        )
                    elif isinstance(msg, ToolMessage):
                        # ToolMessage - result from a tool call
                        await persist_message(
                            user_id=user_id,
                            session_id=db_session_id,
                            role="tool",
                            content=msg.content,
                            tool_call_id=msg.tool_call_id,
                        )
                
                # =========================================================
                # DEBUG: Log what was persisted to DB
                # Remove this block after QA is complete
                # =========================================================
                logger.warning("=" * 60)
                logger.warning(f"PERSISTED to DB: {len(new_messages)} messages for session {db_session_id}")
                for i, msg in enumerate(new_messages):
                    msg_type = type(msg).__name__
                    content_preview = (msg.content[:80] + "...") if msg.content and len(msg.content) > 80 else (msg.content or "(empty)")
                    extras = []
                    if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                        extras.append(f"tool_calls={[tc.get('name') for tc in msg.tool_calls]}")
                    if isinstance(msg, ToolMessage):
                        extras.append(f"tool_call_id={msg.tool_call_id}")
                    extra_str = f" [{', '.join(extras)}]" if extras else ""
                    logger.warning(f"  [db {i}] {msg_type}: {content_preview}{extra_str}")
                logger.warning("=" * 60)
                # =========================================================
                
                # Auto-title new sessions after first message exchange
                if is_new_session:
                    pool = await get_db_pool()
                    chat_repo = ChatRepository(pool)
                    await chat_repo.auto_title_session(user_id, db_session_id)
                    logger.debug(f"Auto-titled new session {db_session_id}")
                    
            except Exception as e:
                logger.error(f"Failed to persist agent messages: {e}")
        
        # Calculate response time and count tool calls for analytics
        response_time_ms = int((time.time() - start_time) * 1000)
        new_messages = session.get_last_new_messages()
        tool_count = sum(1 for msg in new_messages if isinstance(msg, ToolMessage))
        has_tool_calls = tool_count > 0
        
        # Track individual tool calls from AIMessage.tool_calls
        for msg in new_messages:
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.get("name", "unknown")
                    track_tool_called(
                        user_id=user_id,
                        tool_name=tool_name,
                        tool_category=get_tool_category(tool_name),
                        execution_time_ms=None,  # Not available at this level
                        success=True,  # Assume success if we got here
                        error_message=None,
                    )
        
        # Track message sent event in PostHog
        track_message_sent(
            user_id=user_id,
            session_id=str(db_session_id) if db_session_id else None,
            message_length=len(request.message),
            has_tool_calls=has_tool_calls,
            tool_count=tool_count,
            response_time_ms=response_time_ms,
        )
        
        return ChatResponse(
            response=response,
            session_id=str(db_session_id) if db_session_id else None,
        )
        
    except Exception as e:
        # Return error in the response format so frontend can display it
        error_message = f"I encountered an error processing your request: {str(e)}"
        return ChatResponse(response=error_message)


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> ChatHistoryResponse:
    """
    Get the chat history for the current user.
    
    Uses a tiered storage approach:
    1. Try Redis cache first (fast, for hot data)
    2. Fall back to PostgreSQL (authoritative)
    3. Fall back to in-memory (legacy)
    
    Also syncs the in-memory agent with history for context consistency.
    """
    user_id = current_user.user_id
    
    # Try cache/database if user has user_id
    if user_id:
        try:
            pool = await get_db_pool()
            chat_repo = ChatRepository(pool)
            
            if session_id:
                db_session_id = UUID(session_id)
            else:
                # Get most recent active session
                sessions = await chat_repo.get_user_sessions(user_id, limit=1)
                if sessions:
                    db_session_id = sessions[0]["id"]
                else:
                    # No sessions yet
                    return ChatHistoryResponse(messages=[], session_id=None)
            
            messages = None
            
            # Try cache first
            cache = get_chat_cache()
            if cache.is_enabled:
                cached_messages = await cache.get_session_messages(user_id, db_session_id)
                if cached_messages:
                    messages = cached_messages
                    logger.debug(f"Cache hit: {len(messages)} messages for session {db_session_id}")
            
            # Fall back to database on cache miss
            if messages is None:
                messages = await chat_repo.get_session_messages(
                    user_id=user_id,
                    session_id=db_session_id,
                    limit=100,
                )
                
                # Warm the cache for next time
                if messages and cache.is_enabled:
                    await cache.warm_cache(user_id, db_session_id, messages)
                    logger.debug(f"Cache warmed with {len(messages)} messages")
            
            # Sync in-memory agent with history for context consistency
            if messages:
                agent = get_or_create_session(current_user.email, user_id)
                # Include tool_calls and tool_call_id for proper LLM context
                history = []
                for m in messages:
                    entry: Dict[str, Any] = {"role": m["role"], "content": m["content"]}
                    if m.get("tool_calls"):
                        entry["tool_calls"] = m["tool_calls"]
                    if m.get("tool_call_id"):
                        entry["tool_call_id"] = m["tool_call_id"]
                    history.append(entry)
                # Repair any orphan tool_calls from interrupted sessions
                # Use async version to re-execute read-only tools
                history = await repair_incomplete_tool_calls_async(history, get_tool_registry())
                agent.set_history(history)
                logger.debug(f"Synced {len(messages)} messages to agent for {current_user.email}")
            
            return ChatHistoryResponse(
                messages=[ChatMessage(role=m["role"], content=m["content"]) for m in (messages or [])],
                session_id=str(db_session_id),
            )
            
        except Exception as e:
            logger.error(f"Failed to get history from database: {e}")
            # Fall through to in-memory
    
    # Fall back to in-memory
    session = get_or_create_session(current_user.email)
    history = session.get_history()
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
    return ChatHistoryResponse(messages=messages, session_id=None)


@router.post("/history", response_model=dict)
async def set_chat_history(
    messages: list[ChatMessage],
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """
    Set the chat history for the current user.
    
    Used to restore history from localStorage on page load.
    For database-backed sessions, this creates a new session and imports messages.
    """
    user_id = current_user.user_id
    
    # If user has user_id, import to database
    if user_id and messages:
        try:
            pool = await get_db_pool()
            chat_repo = ChatRepository(pool)
            
            # Create new session
            db_session = await chat_repo.create_session(user_id)
            db_session_id = db_session["id"]
            
            # Import messages
            for msg in messages:
                await chat_repo.add_message(
                    user_id=user_id,
                    session_id=db_session_id,
                    role=msg.role,
                    content=msg.content,
                )
            
            # Auto-title from first user message
            await chat_repo.auto_title_session(user_id, db_session_id)
            
            return {
                "status": "success",
                "message_count": len(messages),
                "session_id": str(db_session_id),
                "persisted": True,
            }
            
        except Exception as e:
            logger.error(f"Failed to persist history to database: {e}")
            # Fall through to in-memory
    
    # In-memory fallback
    session = get_or_create_session(current_user.email)
    history = [{"role": m.role, "content": m.content} for m in messages]
    session.set_history(history)
    return {"status": "success", "message_count": len(messages), "persisted": False}


@router.delete("/history", response_model=ClearHistoryResponse)
async def clear_chat_history(
    session_id: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> ClearHistoryResponse:
    """
    Clear the chat history for the current user.
    
    If session_id is provided, clears that specific session.
    Otherwise clears the most recent active session.
    
    Clears from all storage tiers: cache, database, and in-memory.
    """
    user_id = current_user.user_id
    db_session_id = None
    
    # Clear from database if applicable
    if user_id:
        try:
            pool = await get_db_pool()
            chat_repo = ChatRepository(pool)
            
            if session_id:
                db_session_id = UUID(session_id)
            else:
                sessions = await chat_repo.get_user_sessions(user_id, limit=1)
                if sessions:
                    db_session_id = sessions[0]["id"]
            
            if db_session_id:
                # Clear from database
                await chat_repo.delete_session_messages(user_id, db_session_id)
                
                # Invalidate cache
                cache = get_chat_cache()
                if cache.is_enabled:
                    await cache.invalidate_session(user_id, db_session_id)
                    logger.debug(f"Invalidated cache for session {db_session_id}")
                
        except Exception as e:
            logger.error(f"Failed to clear database history: {e}")
    
    # Also clear in-memory
    session = get_or_create_session(current_user.email)
    session.clear_history()
    return ClearHistoryResponse()


# ============== Session Management Endpoints ==============

@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    include_inactive: bool = False,
    limit: int = 20,
    current_user: TokenData = Depends(get_current_user),
) -> SessionListResponse:
    """
    List chat sessions for the current user.
    
    Requires database persistence (user_id in token).
    """
    user_id = current_user.user_id
    
    if not user_id:
        return SessionListResponse(sessions=[])
    
    try:
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        
        sessions = await chat_repo.get_user_sessions(
            user_id=user_id,
            include_inactive=include_inactive,
            limit=limit,
        )
        
        return SessionListResponse(
            sessions=[
                SessionInfo(
                    id=str(s["id"]),
                    title=s["title"],
                    is_active=s["is_active"],
                    created_at=s["created_at"],
                    last_message_at=s["last_message_at"],
                    message_count=s["message_count"],
                )
                for s in sessions
            ]
        )
        
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return SessionListResponse(sessions=[])


@router.post("/sessions", response_model=SessionInfo)
async def create_session(
    title: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
) -> SessionInfo:
    """
    Create a new chat session.
    
    Requires database persistence (user_id in token).
    """
    user_id = current_user.user_id
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database persistence not available for this user",
        )
    
    try:
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        
        session = await chat_repo.create_session(user_id, title)
        
        # Track session created event in PostHog
        track_session_created(
            user_id=user_id,
            session_id=str(session["id"]),
        )
        
        # Also clear the in-memory session for fresh start
        if current_user.email in _sessions:
            _sessions[current_user.email].clear_history()
        
        return SessionInfo(
            id=str(session["id"]),
            title=session["title"],
            is_active=session["is_active"],
            created_at=session["created_at"],
            last_message_at=None,
            message_count=session["message_count"],
        )
        
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chat session",
        )


@router.delete("/sessions/{session_id}")
async def deactivate_session(
    session_id: str,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """
    Deactivate (soft delete) a chat session.
    """
    user_id = current_user.user_id
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database persistence not available for this user",
        )
    
    try:
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        
        success = await chat_repo.deactivate_session(user_id, UUID(session_id))
        
        if success:
            return {"status": "success", "message": "Session deactivated"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate session",
        )

