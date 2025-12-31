"""
User Data API routes - Interests, Important Dates, Tasks, and Memories.

All endpoints require authentication and data is encrypted per-user.
"""

import logging
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..core.auth import TokenData, get_current_user
from ..core.audit import get_audit_logger, AuditAction, ResourceType
from ..middleware import get_client_ip
from ..db import get_db_pool
from ..db.user_data_repository import (
    InterestsRepository,
    ImportantDatesRepository,
    UserTasksRepository,
    MemoriesRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-data", tags=["user-data"])


# ============================================================================
# Pydantic Models
# ============================================================================

# --- Interests ---

class InterestCreate(BaseModel):
    """Request model for creating an interest."""
    name: str = Field(..., min_length=1, max_length=200)
    interest_level: int = Field(..., ge=0, le=100, description="0=dislikes, 50=likes, 100=loves")
    category: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=1000)
    source: str = Field("user_stated", max_length=100)


class InterestResponse(BaseModel):
    """Response model for an interest."""
    id: UUID
    name: str
    interest_level: int
    category: Optional[str]
    notes: Optional[str]
    source: str
    confidence: int
    created_at: datetime
    last_mentioned_at: Optional[datetime] = None


class InterestUpdate(BaseModel):
    """Request model for updating interest level."""
    interest_level: int = Field(..., ge=0, le=100)


# --- Important Dates ---

class ImportantDateCreate(BaseModel):
    """Request model for creating an important date."""
    title: str = Field(..., min_length=1, max_length=200)
    date_value: date
    date_type: str = Field("custom", max_length=50)
    is_recurring: bool = True
    person_id: Optional[UUID] = None
    notes: Optional[str] = Field(None, max_length=1000)
    remind_days_before: int = Field(7, ge=0, le=365)


class ImportantDateResponse(BaseModel):
    """Response model for an important date."""
    id: UUID
    title: str
    date_value: date
    date_type: str
    is_recurring: bool
    person_id: Optional[UUID]
    notes: Optional[str]
    remind_days_before: int
    created_at: datetime


# --- User Tasks ---

class TaskCreate(BaseModel):
    """Request model for creating a task."""
    title: str = Field(..., min_length=1, max_length=200)
    task_type: str = Field("scheduled", max_length=50)
    description: Optional[str] = Field(None, max_length=2000)
    scheduled_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    schedule_cron: Optional[str] = Field(None, max_length=100)
    priority: int = Field(50, ge=0, le=100)


class TaskResponse(BaseModel):
    """Response model for a task."""
    id: UUID
    title: str
    description: Optional[str]
    task_type: str
    status: str
    priority: int
    scheduled_at: Optional[datetime]
    due_at: Optional[datetime]
    schedule_cron: Optional[str]
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class TaskStatusUpdate(BaseModel):
    """Request model for updating task status."""
    status: str = Field(..., pattern="^(pending|in_progress|completed|failed|cancelled)$")
    result: Optional[str] = None
    error_message: Optional[str] = None


# --- Memories ---

class MemoryCreate(BaseModel):
    """Request model for creating a memory."""
    fact_key: str = Field(..., min_length=1, max_length=255)
    fact_value: str = Field(..., min_length=1, max_length=5000)
    context: str = Field("general", max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    source: str = Field("user_stated", max_length=100)
    person_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None


class MemoryResponse(BaseModel):
    """Response model for a memory."""
    id: UUID
    fact_key: str
    fact_value: str
    context: str
    category: Optional[str]
    source: str
    confidence: int
    person_id: Optional[UUID]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime


# ============================================================================
# Interests Endpoints
# ============================================================================

@router.post("/interests", response_model=InterestResponse, status_code=status.HTTP_201_CREATED)
async def create_interest(
    interest: InterestCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new interest for the current user."""
    pool = await get_db_pool()
    repo = InterestsRepository(pool)
    audit = get_audit_logger()
    
    try:
        result = await repo.add_interest(
            user_id=current_user.user_id,
            name=interest.name,
            interest_level=interest.interest_level,
            category=interest.category,
            notes=interest.notes,
            source=interest.source,
        )
        
        await audit.log_data_access(
            user_id=current_user.user_id,
            resource_type="interests",
            resource_id=str(result["id"]),
            action=AuditAction.CREATE,
            details={"category": interest.category},
            ip_address=get_client_ip(),
        )
        
        return InterestResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/interests", response_model=List[InterestResponse])
async def list_interests(
    category: Optional[str] = Query(None),
    min_level: int = Query(0, ge=0, le=100),
    current_user: TokenData = Depends(get_current_user),
):
    """Get all interests for the current user."""
    pool = await get_db_pool()
    repo = InterestsRepository(pool)
    
    interests = await repo.get_interests(
        user_id=current_user.user_id,
        category=category,
        min_level=min_level,
    )
    
    return [InterestResponse(**i) for i in interests]


@router.patch("/interests/{interest_id}", response_model=dict)
async def update_interest(
    interest_id: UUID,
    update: InterestUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update an interest's level."""
    pool = await get_db_pool()
    repo = InterestsRepository(pool)
    audit = get_audit_logger()
    
    success = await repo.update_interest_level(
        user_id=current_user.user_id,
        interest_id=interest_id,
        new_level=update.interest_level,
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interest not found")
    
    await audit.log_data_access(
        user_id=current_user.user_id,
        resource_type="interests",
        resource_id=str(interest_id),
        action=AuditAction.UPDATE,
        ip_address=get_client_ip(),
    )
    
    return {"success": True}


@router.delete("/interests/{interest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interest(
    interest_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete an interest."""
    pool = await get_db_pool()
    repo = InterestsRepository(pool)
    audit = get_audit_logger()
    
    success = await repo.delete_interest(
        user_id=current_user.user_id,
        interest_id=interest_id,
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interest not found")
    
    await audit.log_data_access(
        user_id=current_user.user_id,
        resource_type="interests",
        resource_id=str(interest_id),
        action=AuditAction.DELETE,
        ip_address=get_client_ip(),
    )


# ============================================================================
# Important Dates Endpoints
# ============================================================================

@router.post("/dates", response_model=ImportantDateResponse, status_code=status.HTTP_201_CREATED)
async def create_important_date(
    date_data: ImportantDateCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new important date for the current user."""
    pool = await get_db_pool()
    repo = ImportantDatesRepository(pool)
    audit = get_audit_logger()
    
    try:
        result = await repo.add_date(
            user_id=current_user.user_id,
            title=date_data.title,
            date_value=date_data.date_value,
            date_type=date_data.date_type,
            is_recurring=date_data.is_recurring,
            person_id=date_data.person_id,
            notes=date_data.notes,
            remind_days_before=date_data.remind_days_before,
        )
        
        await audit.log_data_access(
            user_id=current_user.user_id,
            resource_type="important_dates",
            resource_id=str(result["id"]),
            action=AuditAction.CREATE,
            details={"date_type": date_data.date_type},
            ip_address=get_client_ip(),
        )
        
        return ImportantDateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/dates", response_model=List[ImportantDateResponse])
async def list_important_dates(
    date_type: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """Get all important dates for the current user."""
    pool = await get_db_pool()
    repo = ImportantDatesRepository(pool)
    
    dates = await repo.get_dates(
        user_id=current_user.user_id,
        date_type=date_type,
    )
    
    return [ImportantDateResponse(**d) for d in dates]


@router.get("/dates/upcoming", response_model=List[ImportantDateResponse])
async def get_upcoming_dates(
    days_ahead: int = Query(30, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
):
    """Get upcoming important dates within the specified number of days."""
    pool = await get_db_pool()
    repo = ImportantDatesRepository(pool)
    
    dates = await repo.get_upcoming_dates(
        user_id=current_user.user_id,
        days_ahead=days_ahead,
    )
    
    return [ImportantDateResponse(**d) for d in dates]


@router.delete("/dates/{date_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_important_date(
    date_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete an important date."""
    pool = await get_db_pool()
    repo = ImportantDatesRepository(pool)
    audit = get_audit_logger()
    
    success = await repo.delete_date(
        user_id=current_user.user_id,
        date_id=date_id,
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Date not found")
    
    await audit.log_data_access(
        user_id=current_user.user_id,
        resource_type="important_dates",
        resource_id=str(date_id),
        action=AuditAction.DELETE,
        ip_address=get_client_ip(),
    )


# ============================================================================
# User Tasks Endpoints
# ============================================================================

@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new task for the current user."""
    pool = await get_db_pool()
    repo = UserTasksRepository(pool)
    audit = get_audit_logger()
    
    try:
        result = await repo.create_task(
            user_id=current_user.user_id,
            title=task.title,
            task_type=task.task_type,
            description=task.description,
            scheduled_at=task.scheduled_at,
            due_at=task.due_at,
            schedule_cron=task.schedule_cron,
            priority=task.priority,
        )
        
        await audit.log_data_access(
            user_id=current_user.user_id,
            resource_type="user_tasks",
            resource_id=str(result["id"]),
            action=AuditAction.CREATE,
            details={"task_type": task.task_type},
            ip_address=get_client_ip(),
        )
        
        return TaskResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks(
    status_filter: Optional[str] = Query(None, alias="status"),
    task_type: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """Get all tasks for the current user."""
    pool = await get_db_pool()
    repo = UserTasksRepository(pool)
    
    tasks = await repo.get_tasks(
        user_id=current_user.user_id,
        status=status_filter,
        task_type=task_type,
    )
    
    return [TaskResponse(**t) for t in tasks]


@router.patch("/tasks/{task_id}/status", response_model=dict)
async def update_task_status(
    task_id: UUID,
    update: TaskStatusUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update a task's status."""
    pool = await get_db_pool()
    repo = UserTasksRepository(pool)
    audit = get_audit_logger()
    
    success = await repo.update_task_status(
        user_id=current_user.user_id,
        task_id=task_id,
        status=update.status,
        result=update.result,
        error_message=update.error_message,
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    await audit.log_data_access(
        user_id=current_user.user_id,
        resource_type="user_tasks",
        resource_id=str(task_id),
        action=AuditAction.UPDATE,
        details={"new_status": update.status},
        ip_address=get_client_ip(),
    )
    
    return {"success": True}


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a task."""
    pool = await get_db_pool()
    repo = UserTasksRepository(pool)
    audit = get_audit_logger()
    
    success = await repo.delete_task(
        user_id=current_user.user_id,
        task_id=task_id,
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    await audit.log_data_access(
        user_id=current_user.user_id,
        resource_type="user_tasks",
        resource_id=str(task_id),
        action=AuditAction.DELETE,
        ip_address=get_client_ip(),
    )


# ============================================================================
# Memories Endpoints
# ============================================================================

@router.post("/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    memory: MemoryCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create or update a memory for the current user (upsert by fact_key)."""
    pool = await get_db_pool()
    repo = MemoriesRepository(pool)
    audit = get_audit_logger()
    
    try:
        result = await repo.add_memory(
            user_id=current_user.user_id,
            fact_key=memory.fact_key,
            fact_value=memory.fact_value,
            context=memory.context,
            category=memory.category,
            source=memory.source,
            person_id=memory.person_id,
            expires_at=memory.expires_at,
        )
        
        await audit.log_data_access(
            user_id=current_user.user_id,
            resource_type="memories",
            resource_id=str(result["id"]),
            action=AuditAction.CREATE,
            details={"context": memory.context, "fact_key": memory.fact_key},
            ip_address=get_client_ip(),
        )
        
        return MemoryResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/memories", response_model=List[MemoryResponse])
async def list_memories(
    context: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    person_id: Optional[UUID] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """Get all memories for the current user."""
    pool = await get_db_pool()
    repo = MemoriesRepository(pool)
    
    memories = await repo.get_memories(
        user_id=current_user.user_id,
        context=context,
        category=category,
        person_id=person_id,
    )
    
    return [MemoryResponse(**m) for m in memories]


@router.get("/memories/{fact_key}", response_model=MemoryResponse)
async def get_memory(
    fact_key: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get a specific memory by fact_key."""
    pool = await get_db_pool()
    repo = MemoriesRepository(pool)
    
    memory = await repo.get_memory(
        user_id=current_user.user_id,
        fact_key=fact_key,
    )
    
    if not memory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    
    return MemoryResponse(**memory)


@router.delete("/memories/{fact_key}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_memory(
    fact_key: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Deactivate a memory (soft delete)."""
    pool = await get_db_pool()
    repo = MemoriesRepository(pool)
    audit = get_audit_logger()
    
    success = await repo.deactivate_memory(
        user_id=current_user.user_id,
        fact_key=fact_key,
    )
    
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    
    await audit.log_data_access(
        user_id=current_user.user_id,
        resource_type="memories",
        details={"fact_key": fact_key},
        action=AuditAction.DELETE,
        ip_address=get_client_ip(),
    )

