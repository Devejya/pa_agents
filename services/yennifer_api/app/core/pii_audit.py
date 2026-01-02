"""
PII Audit Logging

Records PII masking events for compliance without storing actual PII values.

Features:
- Async batch writing for performance
- Per-request aggregation
- No PII storage - only counts and metadata
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PIIAuditEntry:
    """Single audit entry for a masking operation."""
    tool_name: str
    total_masked: int
    emails_masked: int = 0
    phones_masked: int = 0
    ssn_masked: int = 0
    cards_masked: int = 0
    accounts_masked: int = 0
    addresses_masked: int = 0
    dob_masked: int = 0
    ip_masked: int = 0
    masking_mode: str = "full"
    timestamp: datetime = field(default_factory=datetime.now)


class PIIAuditLogger:
    """
    Async audit logger for PII masking events.
    
    Collects entries during a request and flushes them in batch.
    """
    
    def __init__(self, pool=None):
        self._pool = pool
        self._pending_entries: List[Dict[str, Any]] = []
        self._flush_lock = asyncio.Lock()
        self._enabled = True
    
    def set_pool(self, pool):
        """Set the database pool (called during app startup)."""
        self._pool = pool
    
    def disable(self):
        """Disable audit logging (for testing)."""
        self._enabled = False
    
    def enable(self):
        """Enable audit logging."""
        self._enabled = True
    
    def log_masking_event(
        self,
        user_id: Optional[UUID],
        request_id: Optional[str],
        endpoint: Optional[str],
        tool_name: str,
        stats: Dict[str, int],
        masking_mode: str = "full",
    ):
        """
        Queue an audit entry for batch writing.
        
        Args:
            user_id: User who triggered the request
            request_id: Unique request identifier
            endpoint: API endpoint being called
            tool_name: Name of the tool that triggered masking
            stats: Masking statistics from PIIContext.get_stats()
            masking_mode: The masking mode used (full, financial_only, none)
        """
        logger.warning(f"log_masking_event called: enabled={self._enabled}, pool={self._pool is not None}, stats={stats}")
        
        if not self._enabled:
            logger.warning("PII audit logging is DISABLED")
            return
        
        if stats.get("total", 0) == 0:
            # Don't log if nothing was masked
            return
        
        entry = {
            "user_id": str(user_id) if user_id else None,
            "request_id": request_id,
            "endpoint": endpoint,
            "tool_name": tool_name,
            "total_masked": stats.get("total", 0),
            "emails_masked": stats.get("email", 0),
            "phones_masked": stats.get("phone", 0),
            "ssn_masked": stats.get("ssn", 0),
            "cards_masked": stats.get("card", 0),
            "accounts_masked": stats.get("account", 0),
            "addresses_masked": stats.get("address", 0),
            "dob_masked": stats.get("dob", 0),
            "ip_masked": stats.get("ip", 0),
            "masking_mode": masking_mode,
        }
        
        self._pending_entries.append(entry)
        logger.debug(f"Queued PII audit entry: {tool_name} masked {stats.get('total', 0)} items")
    
    async def flush(self):
        """
        Write all pending entries to the database.
        
        Called at the end of each request by the middleware.
        """
        logger.warning(f"flush called: enabled={self._enabled}, pool={self._pool is not None}, pending={len(self._pending_entries)}")
        
        if not self._enabled or not self._pool or not self._pending_entries:
            if not self._pool:
                logger.warning("PII audit flush skipped: no database pool")
            return
        
        async with self._flush_lock:
            entries_to_write = self._pending_entries.copy()
            self._pending_entries.clear()
        
        if not entries_to_write:
            return
        
        try:
            async with self._pool.acquire() as conn:
                # Batch insert all entries
                await conn.executemany(
                    """
                    INSERT INTO pii_audit_log (
                        user_id, request_id, endpoint, tool_name,
                        total_masked, emails_masked, phones_masked, ssn_masked,
                        cards_masked, accounts_masked, addresses_masked, dob_masked,
                        ip_masked, masking_mode
                    ) VALUES (
                        $1::uuid, $2, $3, $4,
                        $5, $6, $7, $8,
                        $9, $10, $11, $12,
                        $13, $14
                    )
                    """,
                    [
                        (
                            entry["user_id"],
                            entry["request_id"],
                            entry["endpoint"],
                            entry["tool_name"],
                            entry["total_masked"],
                            entry["emails_masked"],
                            entry["phones_masked"],
                            entry["ssn_masked"],
                            entry["cards_masked"],
                            entry["accounts_masked"],
                            entry["addresses_masked"],
                            entry["dob_masked"],
                            entry["ip_masked"],
                            entry["masking_mode"],
                        )
                        for entry in entries_to_write
                    ]
                )
                
            logger.debug(f"Flushed {len(entries_to_write)} PII audit entries")
            
        except Exception as e:
            logger.error(f"Failed to write PII audit entries: {e}")
            # Don't re-raise - audit logging should not break the request


# Global audit logger instance
_audit_logger: Optional[PIIAuditLogger] = None


def get_pii_audit_logger() -> PIIAuditLogger:
    """Get the global PII audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = PIIAuditLogger()
    return _audit_logger


def init_pii_audit_logger(pool) -> PIIAuditLogger:
    """Initialize the PII audit logger with a database pool."""
    global _audit_logger
    _audit_logger = PIIAuditLogger(pool)
    logger.info("PII audit logger initialized")
    return _audit_logger


async def log_pii_masking(
    tool_name: str,
    stats: Dict[str, int],
    user_id: Optional[UUID] = None,
    request_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    masking_mode: str = "full",
):
    """
    Convenience function to log a PII masking event.
    
    Args:
        tool_name: Name of the tool that triggered masking
        stats: Masking statistics from PIIContext.get_stats()
        user_id: Optional user ID
        request_id: Optional request ID
        endpoint: Optional API endpoint
        masking_mode: The masking mode used
    """
    audit_logger = get_pii_audit_logger()
    audit_logger.log_masking_event(
        user_id=user_id,
        request_id=request_id,
        endpoint=endpoint,
        tool_name=tool_name,
        stats=stats,
        masking_mode=masking_mode,
    )


async def flush_pii_audit():
    """Flush pending audit entries to database."""
    audit_logger = get_pii_audit_logger()
    await audit_logger.flush()

