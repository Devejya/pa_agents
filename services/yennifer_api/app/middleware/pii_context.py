"""
PII Context Middleware

Sets up a fresh PIIContext for each HTTP request, ensuring:
1. Request isolation - each request has its own masking context
2. Clean teardown - context is cleared after request completes
3. Audit logging - stats are logged for compliance

Note: We store the PIIContext in both ContextVar AND request.state because
BaseHTTPMiddleware can have issues with ContextVar propagation to child handlers.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..core.pii import PIIContext, set_pii_context, clear_pii_context, get_pii_context
from ..core.pii_audit import get_pii_audit_logger, flush_pii_audit
from .audit import get_request_id, get_current_user_id

logger = logging.getLogger(__name__)


class PIIContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that creates a fresh PIIContext for each request.
    
    This ensures:
    - Each request has isolated PII tracking
    - Masked items can be resolved within the same request
    - Context is properly cleaned up after request
    - Audit entries are flushed to database
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Create fresh context for this request
        ctx = PIIContext()
        set_pii_context(ctx)
        
        # Also store in request.state for cross-context access
        # (BaseHTTPMiddleware can lose ContextVars in some scenarios)
        request.state.pii_context = ctx
        
        try:
            response = await call_next(request)
            
            # Get stats from the actual context that was used
            # (might be different if ContextVar didn't propagate)
            actual_ctx = get_pii_context()
            stats = actual_ctx.get_stats()
            
            if stats["total"] > 0:
                logger.info(
                    f"PII masked in request {request.url.path}: "
                    f"{stats['total']} items "
                    f"(emails: {stats.get('email', 0)}, "
                    f"phones: {stats.get('phone', 0)}, "
                    f"ssn: {stats.get('ssn', 0)}, "
                    f"cards: {stats.get('card', 0)})"
                )
                
                # Queue audit log entry
                audit_logger = get_pii_audit_logger()
                request_id = get_request_id()
                user_id = get_current_user_id()
                
                if audit_logger:
                    audit_logger.log_masking_event(
                        user_id=user_id,
                        request_id=str(request_id) if request_id else None,
                        endpoint=request.url.path,
                        tool_name="request",
                        stats=stats,
                        masking_mode="full",
                    )
                else:
                    logger.warning("PII audit logger not initialized - skipping audit")
            
            # Flush audit entries to database
            await flush_pii_audit()
            
            return response
            
        finally:
            # Always clear context, even on errors
            clear_pii_context()

