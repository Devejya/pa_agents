"""
Pydantic models for User Network Service.

These models define the data structures for persons, relationships, and interests.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# Enums
# ============================================================================

class PersonStatus(str, Enum):
    """Status of a person in the graph."""
    ACTIVE = "active"
    DECEASED = "deceased"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class RelationshipCategory(str, Enum):
    """High-level relationship categories."""
    FAMILY = "family"
    FRIENDS = "friends"
    WORK = "work"
    ACQUAINTANCE = "acquaintance"


class InterestType(str, Enum):
    """Types of interests."""
    SPORT = "sport"
    VIDEOGAME = "videogame"
    ARTS = "arts"
    CRAFTS = "crafts"
    READING = "reading"
    WRITING = "writing"
    FICTION = "fiction"
    TRAVEL = "travel"
    FOOD = "food"
    TV = "tv"
    MOVIES = "movies"
    MUSIC = "music"
    OUTDOORS = "outdoors"
    TECHNOLOGY = "technology"
    OTHER = "other"


# ============================================================================
# Interest Model
# ============================================================================

class Interest(BaseModel):
    """Interest object embedded in Person."""
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=100)
    type: InterestType
    level: int = Field(..., ge=1, le=100, description="Interest level 1-100")
    monthly_frequency: Optional[int] = Field(None, ge=1)
    sample_instance: Optional[str] = Field(None, max_length=500)
    sample_instance_date: Optional[date] = None

    @field_validator("name")
    @classmethod
    def lowercase_name(cls, v: str) -> str:
        return v.lower().strip()


class InterestCreate(BaseModel):
    """Schema for creating an interest."""
    name: str = Field(..., min_length=1, max_length=100)
    type: InterestType
    level: int = Field(..., ge=1, le=100)
    monthly_frequency: Optional[int] = Field(None, ge=1)
    sample_instance: Optional[str] = Field(None, max_length=500)
    sample_instance_date: Optional[date] = None


# ============================================================================
# Connection Counts Model
# ============================================================================

class ConnectionCounts(BaseModel):
    """Tracks communication frequency between two people."""
    id: UUID = Field(default_factory=uuid4)
    
    # Call counts
    call_count_past_year: int = 0
    call_count_past_six_months: int = 0
    call_count_past_three_months: int = 0
    call_count_past_one_month: int = 0
    call_count_past_one_week: int = 0
    call_count_past_one_day: int = 0
    
    # Meet counts
    meet_count_past_six_months: int = 0
    meet_count_past_three_months: int = 0
    meet_count_past_one_month: int = 0
    meet_count_past_one_week: int = 0
    meet_count_past_one_day: int = 0
    
    # Text counts
    text_count_past_six_months: int = 0
    text_count_past_three_months: int = 0
    text_count_past_one_month: int = 0
    text_count_past_one_week: int = 0
    text_count_past_one_day: int = 0
    
    # Last interaction timestamps
    last_call_at: Optional[datetime] = None
    last_text_at: Optional[datetime] = None
    last_meet_at: Optional[datetime] = None


# ============================================================================
# Person Models
# ============================================================================

class PersonBase(BaseModel):
    """Base person fields."""
    # Name fields (split for better sync support)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    middle_names: Optional[str] = Field(None, max_length=255)
    name: Optional[str] = Field(None, max_length=200)  # Computed/legacy field
    
    aliases: list[str] = Field(default_factory=list)
    is_core_user: bool = False
    status: PersonStatus = PersonStatus.ACTIVE
    
    # Contact information
    work_email: Optional[str] = Field(None, max_length=254)
    personal_email: Optional[str] = Field(None, max_length=254)
    work_cell: Optional[str] = Field(None, max_length=20)
    personal_cell: Optional[str] = Field(None, max_length=20)
    secondary_cell: Optional[str] = Field(None, max_length=20)
    
    # Professional info
    company: Optional[str] = Field(None, max_length=200)
    latest_title: Optional[str] = Field(None, max_length=200)
    expertise: Optional[str] = Field(None, max_length=500)
    
    # Location
    address: Optional[str] = Field(None, max_length=500)
    country: Optional[str] = Field(None, max_length=100)  # Made optional for discovered contacts
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    
    # Social
    instagram_handle: Optional[str] = Field(None, max_length=100)
    
    # Demographics
    religion: Optional[str] = Field(None, max_length=100)
    ethnicity: Optional[str] = Field(None, max_length=100)
    country_of_birth: Optional[str] = Field(None, max_length=100)
    city_of_birth: Optional[str] = Field(None, max_length=100)
    date_of_birth: Optional[date] = None

    @field_validator("aliases")
    @classmethod
    def lowercase_aliases(cls, v: list[str]) -> list[str]:
        return [alias.lower().strip() for alias in v]

    @field_validator("work_email", "personal_email")
    @classmethod
    def lowercase_email(cls, v: Optional[str]) -> Optional[str]:
        return v.lower().strip() if v else None

    @model_validator(mode="after")
    def compute_full_name(self):
        """Compute the full name from name parts if not provided."""
        if not self.name:
            parts = [self.first_name]
            if self.middle_names:
                parts.append(self.middle_names)
            if self.last_name:
                parts.append(self.last_name)
            self.name = " ".join(parts)
        return self


class PersonCreate(PersonBase):
    """Schema for creating a person."""
    interests: list[InterestCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contact_method(self):
        """Ensure at least one contact method is provided."""
        has_contact = any([
            self.personal_cell,
            self.work_cell,
            self.work_email,
            self.personal_email,
        ])
        if not has_contact:
            raise ValueError(
                "At least one contact method required: "
                "personal_cell, work_cell, work_email, or personal_email"
            )
        return self

    @model_validator(mode="after")
    def validate_title_requires_company(self):
        """If latest_title is set, company should also be set."""
        if self.latest_title and not self.company:
            raise ValueError("company is required when latest_title is provided")
        return self


class PersonUpdate(BaseModel):
    """Schema for updating a person (all fields optional)."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    middle_names: Optional[str] = Field(None, max_length=255)
    name: Optional[str] = Field(None, min_length=1, max_length=200)  # Legacy/computed
    aliases: Optional[list[str]] = None
    status: Optional[PersonStatus] = None
    work_email: Optional[str] = Field(None, max_length=254)
    personal_email: Optional[str] = Field(None, max_length=254)
    work_cell: Optional[str] = Field(None, max_length=20)
    personal_cell: Optional[str] = Field(None, max_length=20)
    secondary_cell: Optional[str] = Field(None, max_length=20)
    company: Optional[str] = Field(None, max_length=200)
    latest_title: Optional[str] = Field(None, max_length=200)
    expertise: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = Field(None, max_length=500)
    country: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    instagram_handle: Optional[str] = Field(None, max_length=100)
    religion: Optional[str] = Field(None, max_length=100)
    ethnicity: Optional[str] = Field(None, max_length=100)
    country_of_birth: Optional[str] = Field(None, max_length=100)
    city_of_birth: Optional[str] = Field(None, max_length=100)
    date_of_birth: Optional[date] = None
    interests: Optional[list[InterestCreate]] = None


class Person(PersonBase):
    """Full person model with all fields."""
    id: UUID
    interests: list[Interest] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Relationship Models
# ============================================================================

class RelationshipBase(BaseModel):
    """Base relationship fields."""
    category: RelationshipCategory
    from_role: str = Field(..., max_length=100)
    to_role: str = Field(..., max_length=100)
    similar_interests: list[str] = Field(default_factory=list)
    first_meeting_date: Optional[date] = None
    length_of_relationship_years: Optional[int] = None
    length_of_relationship_days: Optional[int] = None

    @field_validator("from_role", "to_role")
    @classmethod
    def lowercase_roles(cls, v: str) -> str:
        return v.lower().strip()


class RelationshipCreate(RelationshipBase):
    """Schema for creating a relationship."""
    from_person_id: UUID
    to_person_id: UUID


class RelationshipUpdate(BaseModel):
    """Schema for updating a relationship."""
    category: Optional[RelationshipCategory] = None
    from_role: Optional[str] = Field(None, max_length=100)
    to_role: Optional[str] = Field(None, max_length=100)
    similar_interests: Optional[list[str]] = None
    first_meeting_date: Optional[date] = None
    is_active: Optional[bool] = None


class Relationship(RelationshipBase):
    """Full relationship model with all fields."""
    id: UUID
    from_person_id: UUID
    to_person_id: UUID
    connection_counts: ConnectionCounts = Field(default_factory=ConnectionCounts)
    is_active: bool = True
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Query Response Models
# ============================================================================

class ContactInfo(BaseModel):
    """Contact information response."""
    id: UUID
    name: str
    relationship: Optional[str] = None
    personal_cell: Optional[str] = None
    work_cell: Optional[str] = None
    secondary_cell: Optional[str] = None
    personal_email: Optional[str] = None
    work_email: Optional[str] = None


class PersonInterests(BaseModel):
    """Person with interests response."""
    id: UUID
    name: str
    relationship: Optional[str] = None
    interests: list[Interest]
    expertise: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None


class TraversalResult(BaseModel):
    """Result of a graph traversal."""
    person: Person
    path: list[str]
    depth: int


class MostContactedPerson(BaseModel):
    """Most contacted person this week."""
    id: UUID
    name: str
    relationship: Optional[str] = None
    texts_this_week: int = 0
    calls_this_week: int = 0
    meets_this_week: int = 0


# ============================================================================
# Sync Models (for contact synchronization)
# ============================================================================

class SyncProvider(str, Enum):
    """Supported sync providers."""
    GOOGLE = "google"
    APPLE = "apple"
    MICROSOFT = "microsoft"
    LINKEDIN = "linkedin"
    MANUAL = "manual"


class SyncStatus(str, Enum):
    """Sync status values."""
    IDLE = "idle"
    SYNCING = "syncing"
    FAILED = "failed"
    PAUSED = "paused"


class ExternalIdSyncStatus(str, Enum):
    """Sync status for individual external IDs."""
    SYNCED = "synced"
    PENDING_PUSH = "pending_push"  # Local changes need to be pushed
    PENDING_PULL = "pending_pull"  # Remote changes need to be pulled
    CONFLICT = "conflict"  # Manual resolution needed


class ConflictType(str, Enum):
    """Types of sync conflicts."""
    DUPLICATE_MATCH = "duplicate_match"  # Multiple matches found
    FIELD_CONFLICT = "field_conflict"    # Same field has different values
    MERGE_REQUIRED = "merge_required"    # Records need manual merge


class ConflictStatus(str, Enum):
    """Status of sync conflicts."""
    PENDING = "pending"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ResolutionType(str, Enum):
    """How a conflict was resolved."""
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"
    MERGE = "merge"
    CREATE_NEW = "create_new"


# ============================================================================
# Person External ID Models
# ============================================================================

class PersonExternalIdBase(BaseModel):
    """Base model for external IDs."""
    provider: SyncProvider
    external_id: str = Field(..., max_length=500)
    external_metadata: dict = Field(default_factory=dict)


class PersonExternalIdCreate(PersonExternalIdBase):
    """Schema for creating an external ID."""
    person_id: UUID


class PersonExternalId(PersonExternalIdBase):
    """Full external ID model."""
    id: UUID
    person_id: UUID
    last_synced_at: Optional[datetime] = None
    sync_status: ExternalIdSyncStatus = ExternalIdSyncStatus.SYNCED
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Sync State Models
# ============================================================================

class SyncStateBase(BaseModel):
    """Base sync state fields."""
    user_id: str = Field(..., max_length=255)
    provider: str = Field(..., max_length=50)  # e.g., 'google_contacts'


class SyncStateCreate(SyncStateBase):
    """Schema for creating sync state."""
    pass


class SyncStateUpdate(BaseModel):
    """Schema for updating sync state."""
    sync_token: Optional[str] = None
    sync_status: Optional[SyncStatus] = None
    error_message: Optional[str] = None
    consecutive_failures: Optional[int] = None
    last_full_sync_at: Optional[datetime] = None
    last_incremental_sync_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None
    total_synced_count: Optional[int] = None
    last_sync_added: Optional[int] = None
    last_sync_updated: Optional[int] = None
    last_sync_deleted: Optional[int] = None


class SyncState(SyncStateBase):
    """Full sync state model."""
    id: UUID
    sync_token: Optional[str] = None
    last_full_sync_at: Optional[datetime] = None
    last_incremental_sync_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None
    sync_status: SyncStatus = SyncStatus.IDLE
    error_message: Optional[str] = None
    consecutive_failures: int = 0
    total_synced_count: int = 0
    last_sync_added: int = 0
    last_sync_updated: int = 0
    last_sync_deleted: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Sync Conflict Models
# ============================================================================

class SyncConflictBase(BaseModel):
    """Base sync conflict fields."""
    user_id: str = Field(..., max_length=255)
    provider: SyncProvider
    conflict_type: ConflictType
    local_data: dict
    remote_data: dict
    suggested_resolution: Optional[dict] = None


class SyncConflictCreate(SyncConflictBase):
    """Schema for creating a sync conflict."""
    person_id: Optional[UUID] = None
    external_id: Optional[str] = None


class SyncConflict(SyncConflictBase):
    """Full sync conflict model."""
    id: UUID
    person_id: Optional[UUID] = None
    external_id: Optional[str] = None
    status: ConflictStatus = ConflictStatus.PENDING
    resolution_type: Optional[ResolutionType] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Sync Log Models
# ============================================================================

class SyncLogCreate(BaseModel):
    """Schema for creating a sync log entry."""
    user_id: str = Field(..., max_length=255)
    provider: str = Field(..., max_length=50)
    sync_type: str = Field(..., max_length=50)  # 'full', 'incremental', 'manual'
    direction: str = Field(..., max_length=50)  # 'pull', 'push', 'bidirectional'
    started_at: datetime


class SyncLogUpdate(BaseModel):
    """Schema for updating a sync log entry."""
    status: Optional[str] = None
    records_processed: Optional[int] = None
    records_added: Optional[int] = None
    records_updated: Optional[int] = None
    records_failed: Optional[int] = None
    conflicts_created: Optional[int] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None


class SyncLog(BaseModel):
    """Full sync log model."""
    id: UUID
    user_id: str
    provider: str
    sync_type: str
    direction: str
    status: str
    records_processed: int = 0
    records_added: int = 0
    records_updated: int = 0
    records_failed: int = 0
    conflicts_created: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True

