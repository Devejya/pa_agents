"""
Background Job Scheduler using APScheduler.

This module provides:
- AsyncIOScheduler for running background jobs
- Job registration and management
- Lifecycle integration with FastAPI
- Job timeout support (default 20 minutes)

Usage:
    from app.core.scheduler import scheduler, register_job

    # Register a job with default 20-minute timeout
    @register_job(trigger='interval', minutes=30, id='my_job')
    async def my_background_job():
        # Do something
        pass

    # Register with custom timeout (5 minutes)
    @register_job(trigger='interval', minutes=30, id='my_job', timeout_seconds=300)
    async def quick_job():
        pass

    # Or register manually
    scheduler.add_job(my_func, 'interval', minutes=30, id='my_job')
"""

import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional, Any
from functools import wraps

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)

logger = logging.getLogger(__name__)

# ============================================================================
# Scheduler Configuration
# ============================================================================

# Default job timeout (20 minutes)
DEFAULT_JOB_TIMEOUT_SECONDS = 20 * 60  # 1200 seconds

# Shutdown timeout (wait for running jobs to finish)
SHUTDOWN_TIMEOUT_SECONDS = 30

# Job stores configuration
jobstores = {
    'default': MemoryJobStore()
}

# Executors configuration
executors = {
    'default': AsyncIOExecutor(),
}

# Job defaults
job_defaults = {
    'coalesce': True,  # Combine multiple pending executions into one
    'max_instances': 1,  # Only one instance of each job running at a time
    'misfire_grace_time': 60 * 5,  # 5 minutes grace time for missed jobs
}

# Create the scheduler
scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
    timezone='UTC',
)


# ============================================================================
# Event Listeners
# ============================================================================

def job_executed_listener(event: JobExecutionEvent):
    """Log when a job completes successfully."""
    job_id = event.job_id
    run_time = event.scheduled_run_time
    logger.info(f"✓ Job '{job_id}' executed successfully at {run_time}")


def job_error_listener(event: JobExecutionEvent):
    """Log when a job fails."""
    job_id = event.job_id
    exception = event.exception
    traceback = event.traceback
    logger.error(f"✗ Job '{job_id}' failed with error: {exception}")
    if traceback:
        logger.error(f"  Traceback: {traceback}")


def job_missed_listener(event: JobExecutionEvent):
    """Log when a job is missed."""
    job_id = event.job_id
    scheduled_time = event.scheduled_run_time
    logger.warning(f"⚠ Job '{job_id}' missed its scheduled time: {scheduled_time}")


# Register event listeners
scheduler.add_listener(job_executed_listener, EVENT_JOB_EXECUTED)
scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
scheduler.add_listener(job_missed_listener, EVENT_JOB_MISSED)


# ============================================================================
# Job Timeout Exception
# ============================================================================

class JobTimeoutError(Exception):
    """Raised when a job exceeds its timeout."""
    def __init__(self, job_id: str, timeout_seconds: int):
        self.job_id = job_id
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Job '{job_id}' timed out after {timeout_seconds} seconds")


# ============================================================================
# Job Registration Decorator
# ============================================================================

def register_job(
    trigger: str = 'interval',
    id: Optional[str] = None,
    name: Optional[str] = None,
    replace_existing: bool = True,
    timeout_seconds: Optional[int] = None,
    **trigger_args
) -> Callable:
    """
    Decorator to register a function as a scheduled job.
    
    Args:
        trigger: Type of trigger ('interval', 'cron', 'date')
        id: Unique job ID (defaults to function name)
        name: Human-readable job name
        replace_existing: Replace job if it already exists
        timeout_seconds: Max execution time (default: 20 minutes)
        **trigger_args: Arguments for the trigger (e.g., minutes=30, hour=9)
    
    Examples:
        # Run every 30 minutes with default 20-minute timeout
        @register_job(trigger='interval', minutes=30)
        async def sync_contacts():
            pass
        
        # Run with custom 5-minute timeout
        @register_job(trigger='interval', minutes=30, timeout_seconds=300)
        async def quick_job():
            pass
        
        # Run at 9 AM every day
        @register_job(trigger='cron', hour=9, minute=0)
        async def daily_report():
            pass
        
        # Run once at a specific time
        @register_job(trigger='date', run_date='2024-01-01 00:00:00')
        async def new_year_greeting():
            pass
    """
    # Use default timeout if not specified
    job_timeout = timeout_seconds if timeout_seconds is not None else DEFAULT_JOB_TIMEOUT_SECONDS
    
    def decorator(func: Callable) -> Callable:
        job_id = id or func.__name__
        job_name = name or func.__name__
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Execute job with timeout enforcement."""
            start_time = datetime.utcnow()
            logger.info(f"⏱ Job '{job_id}' starting (timeout: {job_timeout}s)")
            
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=job_timeout
                )
                
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"✓ Job '{job_id}' completed in {elapsed:.2f}s")
                return result
                
            except asyncio.TimeoutError:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.error(
                    f"⏰ Job '{job_id}' TIMED OUT after {elapsed:.2f}s "
                    f"(limit: {job_timeout}s)"
                )
                # Re-raise as our custom exception for better tracking
                raise JobTimeoutError(job_id, job_timeout)
            
            except Exception as e:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.error(f"✗ Job '{job_id}' failed after {elapsed:.2f}s: {e}")
                raise
        
        # Store job info for later registration
        wrapper._job_info = {
            'func': wrapper,
            'trigger': trigger,
            'id': job_id,
            'name': job_name,
            'replace_existing': replace_existing,
            'timeout_seconds': job_timeout,
            'trigger_args': trigger_args,
        }
        
        # Register the job immediately if scheduler is running
        if scheduler.running:
            scheduler.add_job(
                wrapper,
                trigger,
                id=job_id,
                name=job_name,
                replace_existing=replace_existing,
                **trigger_args
            )
            logger.info(f"📅 Registered job: {job_id} ({trigger}, timeout: {job_timeout}s)")
        else:
            # Store for later registration
            _pending_jobs.append(wrapper)
        
        return wrapper
    return decorator


# Store pending jobs to register when scheduler starts
_pending_jobs: list[Callable] = []


# ============================================================================
# Scheduler Lifecycle
# ============================================================================

def start_scheduler():
    """Start the scheduler and register pending jobs."""
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return
    
    # Register pending jobs
    for job_func in _pending_jobs:
        if hasattr(job_func, '_job_info'):
            info = job_func._job_info
            scheduler.add_job(
                info['func'],
                info['trigger'],
                id=info['id'],
                name=info['name'],
                replace_existing=info['replace_existing'],
                **info['trigger_args']
            )
            timeout = info.get('timeout_seconds', DEFAULT_JOB_TIMEOUT_SECONDS)
            logger.info(f"📅 Registered job: {info['id']} ({info['trigger']}, timeout: {timeout}s)")
    
    _pending_jobs.clear()
    
    # Start the scheduler
    scheduler.start()
    logger.info(f"🚀 Background scheduler started (default timeout: {DEFAULT_JOB_TIMEOUT_SECONDS}s)")
    
    # Log registered jobs
    jobs = scheduler.get_jobs()
    if jobs:
        logger.info(f"📋 Registered {len(jobs)} job(s):")
        for job in jobs:
            next_run = job.next_run_time
            logger.info(f"   - {job.id}: next run at {next_run}")
    else:
        logger.info("📋 No jobs registered yet")


def stop_scheduler(timeout: Optional[int] = None):
    """
    Stop the scheduler gracefully.
    
    Args:
        timeout: Max seconds to wait for running jobs (default: SHUTDOWN_TIMEOUT_SECONDS)
                 If None, uses the default. Set to 0 for immediate shutdown.
    """
    if not scheduler.running:
        logger.warning("Scheduler is not running")
        return
    
    wait_timeout = timeout if timeout is not None else SHUTDOWN_TIMEOUT_SECONDS
    
    if wait_timeout > 0:
        logger.info(f"🛑 Stopping scheduler (waiting up to {wait_timeout}s for running jobs)...")
        
        # APScheduler's shutdown(wait=True) doesn't have a timeout,
        # so we need to handle it ourselves
        import threading
        
        shutdown_complete = threading.Event()
        
        def do_shutdown():
            scheduler.shutdown(wait=True)
            shutdown_complete.set()
        
        shutdown_thread = threading.Thread(target=do_shutdown)
        shutdown_thread.start()
        
        # Wait with timeout
        if shutdown_complete.wait(timeout=wait_timeout):
            logger.info("🛑 Background scheduler stopped gracefully")
        else:
            # Timeout reached, force shutdown
            logger.warning(
                f"⚠ Shutdown timeout ({wait_timeout}s) reached, "
                "forcing scheduler stop (some jobs may be interrupted)"
            )
            scheduler.shutdown(wait=False)
            logger.info("🛑 Background scheduler force-stopped")
    else:
        # Immediate shutdown
        logger.info("🛑 Stopping scheduler immediately...")
        scheduler.shutdown(wait=False)
        logger.info("🛑 Background scheduler stopped (immediate)")


def get_job_status() -> list[dict]:
    """Get status of all registered jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        # Try to get timeout from job function's stored info
        timeout = DEFAULT_JOB_TIMEOUT_SECONDS
        if hasattr(job.func, '_job_info'):
            timeout = job.func._job_info.get('timeout_seconds', DEFAULT_JOB_TIMEOUT_SECONDS)
        
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger),
            'pending': job.pending,
            'timeout_seconds': timeout,
        })
    return jobs


def pause_job(job_id: str) -> bool:
    """Pause a specific job."""
    try:
        scheduler.pause_job(job_id)
        logger.info(f"⏸ Job '{job_id}' paused")
        return True
    except Exception as e:
        logger.error(f"Failed to pause job '{job_id}': {e}")
        return False


def resume_job(job_id: str) -> bool:
    """Resume a paused job."""
    try:
        scheduler.resume_job(job_id)
        logger.info(f"▶ Job '{job_id}' resumed")
        return True
    except Exception as e:
        logger.error(f"Failed to resume job '{job_id}': {e}")
        return False


def run_job_now(job_id: str) -> bool:
    """Trigger a job to run immediately."""
    try:
        job = scheduler.get_job(job_id)
        if job:
            scheduler.modify_job(job_id, next_run_time=datetime.now())
            logger.info(f"🏃 Job '{job_id}' triggered for immediate execution")
            return True
        else:
            logger.warning(f"Job '{job_id}' not found")
            return False
    except Exception as e:
        logger.error(f"Failed to trigger job '{job_id}': {e}")
        return False


def remove_job(job_id: str) -> bool:
    """Remove a job from the scheduler."""
    try:
        scheduler.remove_job(job_id)
        logger.info(f"🗑 Job '{job_id}' removed")
        return True
    except Exception as e:
        logger.error(f"Failed to remove job '{job_id}': {e}")
        return False


# ============================================================================
# Utility Functions
# ============================================================================

def add_job(
    func: Callable,
    trigger: str,
    id: str,
    name: Optional[str] = None,
    replace_existing: bool = True,
    **trigger_args
) -> Any:
    """
    Add a job to the scheduler programmatically.
    
    Args:
        func: The function to run
        trigger: Type of trigger ('interval', 'cron', 'date')
        id: Unique job ID
        name: Human-readable job name
        replace_existing: Replace job if it already exists
        **trigger_args: Arguments for the trigger
    
    Returns:
        The job instance
    """
    job = scheduler.add_job(
        func,
        trigger,
        id=id,
        name=name or id,
        replace_existing=replace_existing,
        **trigger_args
    )
    logger.info(f"📅 Added job: {id} ({trigger})")
    return job


def schedule_once(func: Callable, delay_seconds: int, job_id: Optional[str] = None) -> Any:
    """
    Schedule a function to run once after a delay.
    
    Args:
        func: The function to run
        delay_seconds: Seconds to wait before running
        job_id: Optional unique ID for the job
    
    Returns:
        The job instance
    """
    from datetime import timedelta
    run_time = datetime.now() + timedelta(seconds=delay_seconds)
    
    job = scheduler.add_job(
        func,
        'date',
        run_date=run_time,
        id=job_id or f"once_{func.__name__}_{run_time.timestamp()}",
    )
    logger.info(f"📅 Scheduled one-time job: {job.id} at {run_time}")
    return job

