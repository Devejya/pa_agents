"""
Chat API routes for Yennifer assistant.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.agent import YenniferAssistant
from ..core.auth import TokenData, get_current_user


router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory session storage (keyed by email)
# In production, use Redis or database
_sessions: dict[str, YenniferAssistant] = {}


def get_or_create_session(user_email: str) -> YenniferAssistant:
    """Get existing session or create new one for the user."""
    if user_email not in _sessions:
        _sessions[user_email] = YenniferAssistant(user_email=user_email)
    else:
        # Ensure user email is set (in case session was created without it)
        _sessions[user_email].set_user(user_email)
    return _sessions[user_email]


# ============== Request/Response Models ==============

class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Request to send a message."""
    message: str = Field(..., min_length=1, description="User's message")


class ChatResponse(BaseModel):
    """Response from the assistant."""
    response: str = Field(..., description="Assistant's response")
    

class ChatHistoryResponse(BaseModel):
    """Chat history response."""
    messages: list[ChatMessage]


class ClearHistoryResponse(BaseModel):
    """Response after clearing history."""
    status: str = "success"
    message: str = "Chat history cleared"


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
    
    Requires authentication via JWT token.
    """
    try:
        session = get_or_create_session(current_user.email)
        response = session.chat(request.message)
        return ChatResponse(response=response)
    except Exception as e:
        # Return error in the response format so frontend can display it
        error_message = f"I encountered an error processing your request: {str(e)}"
        return ChatResponse(response=error_message)


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    current_user: TokenData = Depends(get_current_user),
) -> ChatHistoryResponse:
    """
    Get the chat history for the current user.
    
    Returns empty list if no history exists.
    """
    session = get_or_create_session(current_user.email)
    history = session.get_history()
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in history]
    return ChatHistoryResponse(messages=messages)


@router.post("/history", response_model=dict)
async def set_chat_history(
    messages: list[ChatMessage],
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """
    Set the chat history for the current user.
    
    Used to restore history from localStorage on page load.
    """
    session = get_or_create_session(current_user.email)
    history = [{"role": m.role, "content": m.content} for m in messages]
    session.set_history(history)
    return {"status": "success", "message_count": len(messages)}


@router.delete("/history", response_model=ClearHistoryResponse)
async def clear_chat_history(
    current_user: TokenData = Depends(get_current_user),
) -> ClearHistoryResponse:
    """
    Clear the chat history for the current user.
    """
    session = get_or_create_session(current_user.email)
    session.clear_history()
    return ClearHistoryResponse()
