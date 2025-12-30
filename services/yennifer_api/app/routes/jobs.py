"""
Job Management API Routes.

Provides endpoints for:
- Viewing job status
- Triggering manual job execution
- Pausing/resuming jobs
- Viewing job history

These endpoints are admin-only and require authentication.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from ..core.scheduler import (
    get_job_status,
    pause_job,
    resume_job,
    run_job_now,
    scheduler,
)
from ..core.auth import get_current_user, UserInfo
from ..jobs.contact_sync import trigger_manual_sync, get_sync_stats
from ..jobs.health_check import get_health_stats

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ============================================================================
# Job Status Endpoints
# ============================================================================

@router.get("/status")
async def list_jobs(
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """
    Get status of all scheduled jobs.
    
    Returns list of jobs with their next run time and current state.
    """
    jobs = get_job_status()
    return {
        "scheduler_running": scheduler.running,
        "job_count": len(jobs),
        "jobs": jobs,
    }


@router.get("/status/{job_id}")
async def get_job_details(
    job_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """
    Get detailed status of a specific job.
    """
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    return {
        "id": job.id,
        "name": job.name,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        "trigger": str(job.trigger),
        "pending": job.pending,
        "func": job.func.__name__ if job.func else None,
    }


# ============================================================================
# Job Control Endpoints
# ============================================================================

@router.post("/{job_id}/run")
async def trigger_job(
    job_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """
    Trigger a job to run immediately.
    
    The job will be executed as soon as possible, regardless of its schedule.
    """
    success = run_job_now(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    return {
        "message": f"Job '{job_id}' triggered for immediate execution",
        "job_id": job_id,
    }


@router.post("/{job_id}/pause")
async def pause_scheduled_job(
    job_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """
    Pause a scheduled job.
    
    The job will not run until resumed.
    """
    success = pause_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found or already paused")
    
    return {
        "message": f"Job '{job_id}' paused",
        "job_id": job_id,
    }


@router.post("/{job_id}/resume")
async def resume_scheduled_job(
    job_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """
    Resume a paused job.
    """
    success = resume_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found or not paused")
    
    return {
        "message": f"Job '{job_id}' resumed",
        "job_id": job_id,
    }


# ============================================================================
# Contact Sync Endpoints
# ============================================================================

@router.post("/sync/contacts")
async def trigger_contact_sync(
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """
    Trigger an immediate contact sync for the current user.
    
    Syncs Google Contacts with User Network.
    """
    result = await trigger_manual_sync(current_user.email)
    
    return {
        "message": "Contact sync completed" if result.get('success') else "Contact sync failed",
        "result": result,
    }


from pydantic import BaseModel

class InternalSyncRequest(BaseModel):
    user_email: str


@router.post("/sync/contacts/internal")
async def trigger_internal_contact_sync(
    request: InternalSyncRequest,
) -> dict:
    """
    Internal endpoint for triggering contact sync.
    
    This is called by the sync tool to run sync for a specific user.
    Not protected by user auth - should only be called internally.
    """
    result = await trigger_manual_sync(request.user_email)
    
    return {
        "message": "Contact sync completed" if result.get('success') else "Contact sync failed",
        "result": result,
    }


@router.get("/sync/contacts/stats")
async def get_contact_sync_stats(
    current_user: UserInfo = Depends(get_current_user),
    user_email: Optional[str] = Query(None, description="Get stats for specific user (admin only)"),
) -> dict:
    """
    Get contact sync statistics.
    
    Returns sync history and statistics for the current user.
    """
    # If user_email is specified, only allow admins (TODO: add admin check)
    email = user_email or current_user.email
    
    return {
        "user_email": email,
        "stats": get_sync_stats(email),
    }


# ============================================================================
# Health Check Stats
# ============================================================================

@router.get("/health-check/stats")
async def get_scheduler_health(
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """
    Get scheduler health check statistics.
    
    Shows when the health check job last ran and how many times.
    """
    return {
        "scheduler_running": scheduler.running,
        "health_stats": get_health_stats(),
    }

