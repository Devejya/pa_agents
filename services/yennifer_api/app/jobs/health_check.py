"""
Health Check Background Job.

A simple heartbeat job that runs every 5 minutes to verify the scheduler is working.
Also useful for monitoring and alerting.
"""

import logging
from datetime import datetime

from ..core.scheduler import register_job

logger = logging.getLogger(__name__)

# Track job execution statistics
_stats = {
    'last_run': None,
    'run_count': 0,
    'errors': 0,
}


@register_job(
    trigger='interval',
    minutes=5,
    id='health_check',
    name='Scheduler Health Check',
    timeout_seconds=60,  # Health check should complete in 1 minute
)
async def health_check_job():
    """
    Simple heartbeat job to verify scheduler is running.
    
    Runs every 5 minutes and logs the scheduler status.
    """
    global _stats
    
    now = datetime.utcnow()
    _stats['last_run'] = now
    _stats['run_count'] += 1
    
    logger.info(
        f"💓 Scheduler heartbeat #{_stats['run_count']} at {now.isoformat()}"
    )
    
    # You could add more checks here:
    # - Database connectivity
    # - External service health
    # - Memory/CPU usage
    # - Queue depths
    
    return {
        'status': 'healthy',
        'timestamp': now.isoformat(),
        'run_count': _stats['run_count'],
    }


def get_health_stats() -> dict:
    """Get health check statistics."""
    return {
        'last_run': _stats['last_run'].isoformat() if _stats['last_run'] else None,
        'run_count': _stats['run_count'],
        'errors': _stats['errors'],
    }

