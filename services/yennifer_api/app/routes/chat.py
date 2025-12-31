"""
Chat API routes for Yennifer assistant.

Supports both in-memory and database-backed chat history.
When a user has a user_id (from multi-tenant auth), messages are persisted
to the database with per-user encryption.
"""

import logging
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.agent import YenniferAssistant
from ..core.auth import TokenData, get_current_user
from ..core.google_services import load_user_tokens
from ..db import get_db_pool, ChatRepository

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory session storage (keyed by email)
# Used as fallback when database persistence is not available
_sessions: dict[str, YenniferAssistant] = {}


def get_or_create_session(user_email: str, user_id: Optional[UUID] = None) -> YenniferAssistant:
    """Get existing session or create new one for the user."""
    if user_email not in _sessions:
        _sessions[user_email] = YenniferAssistant(user_email=user_email, user_id=user_id)
    else:
        # Ensure user email and ID are set (in case session was created without them)
        _sessions[user_email].set_user(user_email, user_id)
    return _sessions[user_email]


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

async def persist_message(
    user_id: UUID,
    session_id: UUID,
    role: str,
    content: str,
    model: Optional[str] = None,
) -> None:
    """Persist a message to the database."""
    try:
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        await chat_repo.add_message(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            model=model,
        )
    except Exception as e:
        logger.error(f"Failed to persist message: {e}")
        # Don't fail the request, just log


async def get_or_create_db_session(user_id: UUID) -> dict:
    """Get or create a database session for the user."""
    pool = await get_db_pool()
    chat_repo = ChatRepository(pool)
    return await chat_repo.get_or_create_active_session(user_id)


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
    try:
        # Load user tokens into cache for sync tool access
        tokens = await load_user_tokens(current_user.email)
        if not tokens:
            logger.warning(f"No Google tokens found for {current_user.email}")
            # Continue anyway - tools will return appropriate errors
        
        user_id = current_user.user_id  # May be None for legacy users
        session = get_or_create_session(current_user.email, user_id)
        
        # Load user context (memories, interests) for personalization
        if user_id:
            try:
                await session.load_user_context()
            except Exception as e:
                logger.warning(f"Failed to load user context: {e}")
        
        # Determine if we should use database persistence
        db_session_id = None
        
        if user_id:
            try:
                # Get or create database session
                if request.session_id:
                    db_session_id = UUID(request.session_id)
                else:
                    db_session = await get_or_create_db_session(user_id)
                    db_session_id = db_session["id"]
                
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
        response = session.chat(request.message)
        
        # Persist assistant response
        if user_id and db_session_id:
            try:
                await persist_message(
                    user_id=user_id,
                    session_id=db_session_id,
                    role="assistant",
                    content=response,
                    model="gpt-4o",  # Or get from config
                )
            except Exception as e:
                logger.error(f"Failed to persist assistant message: {e}")
        
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
    
    If session_id is provided, returns history from that specific session.
    Otherwise returns the most recent session's history.
    
    Falls back to in-memory history if no database session exists.
    """
    user_id = current_user.user_id
    
    # Try database first if user has user_id
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
            
            # Get messages from database
            messages = await chat_repo.get_session_messages(
                user_id=user_id,
                session_id=db_session_id,
                limit=100,
            )
            
            return ChatHistoryResponse(
                messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
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
    """
    user_id = current_user.user_id
    
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
                else:
                    db_session_id = None
            
            if db_session_id:
                await chat_repo.delete_session_messages(user_id, db_session_id)
                
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

