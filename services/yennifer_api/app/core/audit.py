"""
Audit Logging Service for SOC2/PIPEDA Compliance.

Provides async audit logging for all data access and modifications.
Logs are immutable and stored in PostgreSQL for compliance queries.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Audit action types."""
    # Data operations
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    
    # Auth operations
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    TOKEN_REFRESH = "token_refresh"
    
    # Sync operations
    SYNC_START = "sync_start"
    SYNC_COMPLETE = "sync_complete"
    SYNC_FAILED = "sync_failed"
    
    # Export/Import
    EXPORT = "export"
    IMPORT = "import"
    
    # Admin operations
    SETTINGS_CHANGE = "settings_change"


class ResourceType(str, Enum):
    """Resource types that can be audited."""
    PERSONS = "persons"
    RELATIONSHIPS = "relationships"
    CHAT_MESSAGES = "chat_messages"
    CHAT_SESSIONS = "chat_sessions"
    USER_SETTINGS = "user_settings"
    OAUTH_TOKENS = "oauth_tokens"
    CONTACTS_SYNC = "contacts_sync"
    CALENDAR_EVENTS = "calendar_events"
    EMAILS = "emails"
    DOCUMENTS = "documents"
    SPREADSHEETS = "spreadsheets"
    USER_PROFILE = "user_profile"


class AuditEntry(BaseModel):
    """Audit log entry model."""
    user_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[UUID] = None
    success: bool = True
    error_message: Optional[str] = None


class AuditLogger:
    """
    Async audit logger for compliance tracking.
    
    Uses a background task queue to avoid blocking request handling.
    Falls back to sync logging if queue is full.
    """
    
    def __init__(self, pool=None, max_queue_size: int = 1000):
        """
        Initialize the audit logger.
        
        Args:
            pool: Database connection pool (asyncpg.Pool)
            max_queue_size: Maximum pending audit entries before blocking
        """
        self._pool = pool
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
    
    def set_pool(self, pool):
        """Set the database pool (called after pool is created)."""
        self._pool = pool
    
    async def start(self):
        """Start the background worker."""
        if self._running:
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Audit logger background worker started")
    
    async def stop(self):
        """Stop the background worker gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        # Wait for queue to drain (with timeout)
        try:
            await asyncio.wait_for(self._drain_queue(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"Audit queue drain timeout, {self._queue.qsize()} entries may be lost")
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Audit logger background worker stopped")
    
    async def _drain_queue(self):
        """Drain remaining entries from queue."""
        while not self._queue.empty():
            await asyncio.sleep(0.1)
    
    async def _worker(self):
        """Background worker that processes audit entries."""
        batch: List[AuditEntry] = []
        batch_size = 50
        flush_interval = 5.0  # seconds
        last_flush = asyncio.get_event_loop().time()
        
        while self._running or not self._queue.empty():
            try:
                # Get entry with timeout
                try:
                    entry = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                    batch.append(entry)
                except asyncio.TimeoutError:
                    pass
                
                # Flush conditions
                current_time = asyncio.get_event_loop().time()
                should_flush = (
                    len(batch) >= batch_size or
                    (batch and current_time - last_flush >= flush_interval)
                )
                
                if should_flush and batch:
                    await self._flush_batch(batch)
                    batch = []
                    last_flush = current_time
                    
            except Exception as e:
                logger.error(f"Audit worker error: {e}")
                await asyncio.sleep(1.0)
        
        # Final flush
        if batch:
            await self._flush_batch(batch)
    
    async def _flush_batch(self, batch: List[AuditEntry]):
        """Write a batch of audit entries to the database."""
        if not self._pool:
            logger.warning("Audit logger has no database pool, entries lost")
            return
        
        try:
            async with self._pool.acquire() as conn:
                # Use COPY for batch insert (more efficient)
                values = [
                    (
                        entry.user_id,
                        entry.session_id,
                        entry.action,
                        entry.resource_type,
                        entry.resource_id,
                        json.dumps(entry.details) if entry.details else None,
                        entry.ip_address,
                        entry.user_agent,
                        entry.request_id,
                        entry.success,
                        entry.error_message,
                    )
                    for entry in batch
                ]
                
                await conn.executemany(
                    """
                    INSERT INTO audit_log (
                        user_id, session_id, action, resource_type, resource_id,
                        details, ip_address, user_agent, request_id,
                        success, error_message
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7::inet, $8, $9, $10, $11)
                    """,
                    values
                )
                
                logger.debug(f"Flushed {len(batch)} audit entries to database")
                
        except Exception as e:
            logger.error(f"Failed to flush audit batch: {e}")
            # Don't retry - audit logs shouldn't block application
    
    async def log(
        self,
        action: Union[AuditAction, str],
        resource_type: Union[ResourceType, str],
        resource_id: Optional[str] = None,
        user_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[UUID] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ):
        """
        Log an audit entry asynchronously.
        
        Args:
            action: The action performed (read, create, update, delete, etc.)
            resource_type: Type of resource affected
            resource_id: Identifier of the specific resource
            user_id: User who performed the action
            session_id: Chat session if applicable
            details: Additional non-sensitive context
            ip_address: Client IP address
            user_agent: Client user agent string
            request_id: Correlation ID for request tracing
            success: Whether the action succeeded
            error_message: Error message if action failed
        """
        entry = AuditEntry(
            user_id=user_id,
            session_id=session_id,
            action=action.value if isinstance(action, AuditAction) else action,
            resource_type=resource_type.value if isinstance(resource_type, ResourceType) else resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id or uuid4(),
            success=success,
            error_message=error_message,
        )
        
        try:
            # Try non-blocking put
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            # Queue full - log synchronously as fallback
            logger.warning("Audit queue full, logging synchronously")
            await self._write_entry_sync(entry)
    
    async def _write_entry_sync(self, entry: AuditEntry):
        """Write a single entry synchronously (fallback)."""
        if not self._pool:
            return
            
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log (
                        user_id, session_id, action, resource_type, resource_id,
                        details, ip_address, user_agent, request_id,
                        success, error_message
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7::inet, $8, $9, $10, $11)
                    """,
                    entry.user_id,
                    entry.session_id,
                    entry.action,
                    entry.resource_type,
                    entry.resource_id,
                    json.dumps(entry.details) if entry.details else None,
                    entry.ip_address,
                    entry.user_agent,
                    entry.request_id,
                    entry.success,
                    entry.error_message,
                )
        except Exception as e:
            logger.error(f"Failed to write audit entry sync: {e}")
    
    # Convenience methods for common operations
    
    async def log_login(
        self,
        user_id: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ):
        """Log a login attempt."""
        action = AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED
        await self.log(
            action=action,
            resource_type=ResourceType.USER_PROFILE,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
        )
    
    async def log_logout(
        self,
        user_id: UUID,
        ip_address: Optional[str] = None,
    ):
        """Log a logout."""
        await self.log(
            action=AuditAction.LOGOUT,
            resource_type=ResourceType.USER_PROFILE,
            user_id=user_id,
            ip_address=ip_address,
        )
    
    async def log_data_access(
        self,
        user_id: UUID,
        resource_type: Union[ResourceType, str],
        resource_id: Optional[str] = None,
        action: AuditAction = AuditAction.READ,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ):
        """Log data access (read/create/update/delete)."""
        await self.log(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            details=details,
            ip_address=ip_address,
        )
    
    async def log_sync(
        self,
        user_id: UUID,
        sync_type: str,
        action: AuditAction,
        details: Optional[dict] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ):
        """Log sync operation (contacts, calendar, etc.)."""
        await self.log(
            action=action,
            resource_type=ResourceType.CONTACTS_SYNC,
            user_id=user_id,
            details={"sync_type": sync_type, **(details or {})},
            success=success,
            error_message=error_message,
        )


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


async def init_audit_logger(pool) -> AuditLogger:
    """Initialize and start the audit logger with a database pool."""
    audit_logger = get_audit_logger()
    audit_logger.set_pool(pool)
    await audit_logger.start()
    return audit_logger


async def shutdown_audit_logger():
    """Gracefully shutdown the audit logger."""
    global _audit_logger
    if _audit_logger:
        await _audit_logger.stop()

