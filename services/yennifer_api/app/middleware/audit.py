"""
Audit Middleware for request tracking.

Captures request context (IP, user agent, request ID) and makes it
available throughout the request lifecycle for audit logging.
"""

import logging
from contextvars import ContextVar
from typing import Optional
from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Context variables for request tracking
_request_id: ContextVar[Optional[UUID]] = ContextVar("request_id", default=None)
_client_ip: ContextVar[Optional[str]] = ContextVar("client_ip", default=None)
_user_agent: ContextVar[Optional[str]] = ContextVar("user_agent", default=None)
_current_user_id: ContextVar[Optional[UUID]] = ContextVar("current_user_id", default=None)


def get_request_id() -> Optional[UUID]:
    """Get the current request ID."""
    return _request_id.get()


def get_client_ip() -> Optional[str]:
    """Get the current client IP."""
    return _client_ip.get()


def get_user_agent() -> Optional[str]:
    """Get the current user agent."""
    return _user_agent.get()


def get_current_user_id() -> Optional[UUID]:
    """Get the current user ID from context."""
    return _current_user_id.get()


def set_current_user_id(user_id: UUID):
    """Set the current user ID in context (called after auth)."""
    _current_user_id.set(user_id)


def get_real_client_ip(request: Request) -> str:
    """
    Get the real client IP, handling proxies.
    
    Checks X-Forwarded-For header first (set by nginx/load balancer),
    then falls back to direct client IP.
    """
    # Check X-Forwarded-For header (may contain multiple IPs)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP is the original client
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fallback to direct client
    if request.client:
        return request.client.host
    
    return "unknown"


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware to capture request context for audit logging.
    
    Sets context variables that can be accessed throughout the request:
    - request_id: Unique identifier for the request
    - client_ip: Real client IP (handling proxies)
    - user_agent: Client user agent string
    """
    
    async def dispatch(self, request: Request, call_next):
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID")
        if request_id:
            try:
                request_id = UUID(request_id)
            except ValueError:
                request_id = uuid4()
        else:
            request_id = uuid4()
        
        # Extract client info
        client_ip = get_real_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:500]  # Truncate long UAs
        
        # Set context variables
        _request_id.set(request_id)
        _client_ip.set(client_ip)
        _user_agent.set(user_agent)
        _current_user_id.set(None)  # Reset for each request
        
        # Add request ID to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request_id)
        
        return response


# Utility functions for use in route handlers

def get_audit_context() -> dict:
    """
    Get the current audit context for logging.
    
    Returns a dict that can be passed to audit logger methods.
    """
    return {
        "request_id": get_request_id(),
        "ip_address": get_client_ip(),
        "user_agent": get_user_agent(),
        "user_id": get_current_user_id(),
    }

