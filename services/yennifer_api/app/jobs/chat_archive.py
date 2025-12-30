"""
Chat Archive Background Job.

Runs periodically to:
1. Archive old sessions (> 365 days) to S3 cold storage
2. Clean up archived sessions from PostgreSQL

Runs weekly by default.
"""

import logging
from datetime import datetime

from ..db import get_db_pool
from ..core.tiered_storage import get_tiered_storage

logger = logging.getLogger(__name__)


async def run_chat_archive_job() -> dict:
    """
    Archive old chat sessions for all users.
    
    Returns:
        Dict with job results.
    """
    results = {
        "started_at": datetime.utcnow().isoformat(),
        "users_processed": 0,
        "total_archived": 0,
        "total_failed": 0,
        "errors": [],
    }
    
    try:
        tiered_storage = get_tiered_storage()
        
        if not tiered_storage.archive.is_enabled:
            logger.info("Chat archive job skipped - S3 archive not configured")
            results["skipped"] = "archive_not_configured"
            return results
        
        pool = await get_db_pool()
        
        # Get all users with old sessions
        async with pool.acquire() as conn:
            users = await conn.fetch("""
                SELECT DISTINCT u.id
                FROM users u
                JOIN chat_sessions cs ON cs.user_id = u.id
                WHERE cs.is_active = true
                  AND (
                    cs.last_message_at < NOW() - INTERVAL '365 days'
                    OR (cs.last_message_at IS NULL AND cs.created_at < NOW() - INTERVAL '365 days')
                  )
            """)
        
        for user_row in users:
            user_id = user_row["id"]
            
            try:
                result = await tiered_storage.archive_old_sessions(user_id)
                
                results["users_processed"] += 1
                results["total_archived"] += result.get("archived", 0)
                results["total_failed"] += result.get("failed", 0)
                
                if result.get("errors"):
                    results["errors"].extend(result["errors"])
                    
            except Exception as e:
                logger.error(f"Failed to archive sessions for user {user_id}: {e}")
                results["errors"].append(f"User {user_id}: {str(e)}")
        
        results["completed_at"] = datetime.utcnow().isoformat()
        results["success"] = len(results["errors"]) == 0
        
        logger.info(
            f"Chat archive job completed: "
            f"{results['total_archived']} archived, "
            f"{results['total_failed']} failed"
        )
        
    except Exception as e:
        logger.error(f"Chat archive job failed: {e}")
        results["error"] = str(e)
        results["success"] = False
    
    return results


def register_chat_archive_job(scheduler):
    """
    Register the chat archive job with the scheduler.
    
    Args:
        scheduler: APScheduler instance.
    """
    from ..core.scheduler import wrap_async_job
    
    scheduler.add_job(
        wrap_async_job(run_chat_archive_job, "chat_archive"),
        trigger="cron",
        day_of_week="sun",  # Run weekly on Sunday
        hour=3,              # At 3 AM UTC
        minute=0,
        id="chat_archive",
        name="Chat Archive to S3",
        replace_existing=True,
    )
    
    logger.info("Registered chat_archive job (weekly, Sunday 3 AM UTC)")


