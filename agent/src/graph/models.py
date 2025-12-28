"""
Pydantic models for User Relationship Graph.

These models are designed to be graph-ready for future migration to Neptune/Neo4j.
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
# Interest Model (Embedded in Person)
# ============================================================================

class Interest(BaseModel):
    """
    Interest object embedded in Person node.
    Denormalized for fast reads.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=100)
    type: InterestType
    level: int = Field(..., ge=1, le=100, description="Interest level 1-100")
    monthly_frequency: Optional[int] = Field(None, ge=1, description="Times per month")
    sample_instance: Optional[str] = Field(None, max_length=500)
    sample_instance_date: Optional[date] = None

    @field_validator("name")
    @classmethod
    def lowercase_name(cls, v: str) -> str:
        return v.lower().strip()


# ============================================================================
# Connection Counts Model (Embedded in Relationship)
# ============================================================================

class ConnectionCounts(BaseModel):
    """
    Tracks communication frequency between two people.
    Embedded in Relationship edge.
    """
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
    
    # Text counts (across all platforms)
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
# Person Model (Graph Node)
# ============================================================================

class Person(BaseModel):
    """
    Person node in the relationship graph.
    
    Required fields: id, name, country, and at least one contact method.
    """
    id: UUID = Field(default_factory=uuid4)
    
    # Core identity
    name: str = Field(..., min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    is_core_user: bool = False
    status: PersonStatus = PersonStatus.ACTIVE
    
    # Contact information
    work_email: Optional[str] = Field(None, max_length=254)
    personal_email: Optional[str] = Field(None, max_length=254)
    work_cell: Optional[str] = Field(None, max_length=20)  # E.164 format
    personal_cell: Optional[str] = Field(None, max_length=20)
    secondary_cell: Optional[str] = Field(None, max_length=20)
    
    # Professional info
    company: Optional[str] = Field(None, max_length=200)
    latest_title: Optional[str] = Field(None, max_length=200)
    expertise: Optional[str] = Field(None, max_length=500)
    
    # Location
    address: Optional[str] = Field(None, max_length=500)
    country: str = Field(..., max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    
    # Social
    instagram_handle: Optional[str] = Field(None, max_length=100)
    
    # Demographics
    religion: Optional[str] = Field(None, max_length=100)
    ethnicity: Optional[str] = Field(None, max_length=100)
    country_of_birth: Optional[str] = Field(None, max_length=100)
    city_of_birth: Optional[str] = Field(None, max_length=100)
    
    # Interests (denormalized for fast reads)
    interests: list[Interest] = Field(default_factory=list)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("aliases")
    @classmethod
    def lowercase_aliases(cls, v: list[str]) -> list[str]:
        return [alias.lower().strip() for alias in v]

    @field_validator("work_email", "personal_email")
    @classmethod
    def lowercase_email(cls, v: Optional[str]) -> Optional[str]:
        return v.lower().strip() if v else None

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


# ============================================================================
# Relationship Model (Graph Edge)
# ============================================================================

class Relationship(BaseModel):
    """
    Relationship edge between two Person nodes.
    
    Uses single-edge with role pair for directionality:
    - from_person_id: Source person
    - to_person_id: Target person
    - from_role: What source is to target (e.g., "brother")
    - to_role: What target is to source (e.g., "sister")
    """
    id: UUID = Field(default_factory=uuid4)
    
    # Edge endpoints
    from_person_id: UUID
    to_person_id: UUID
    
    # Relationship type
    category: RelationshipCategory
    from_role: str = Field(..., max_length=100)  # What from_person is to to_person
    to_role: str = Field(..., max_length=100)    # What to_person is to from_person
    
    # Metadata
    connection_counts: ConnectionCounts = Field(default_factory=ConnectionCounts)
    similar_interests: list[str] = Field(default_factory=list)  # Interest names
    
    # Timeline
    first_meeting_date: Optional[date] = None
    length_of_relationship_years: Optional[int] = None
    length_of_relationship_days: Optional[int] = None
    
    # Status (for historical relationships)
    is_active: bool = True
    ended_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("from_role", "to_role")
    @classmethod
    def lowercase_roles(cls, v: str) -> str:
        return v.lower().strip()


# ============================================================================
# Audit Log Model
# ============================================================================

class AuditLog(BaseModel):
    """Audit log entry for PII access tracking."""
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor_id: str  # Who performed the action (agent/user id)
    action: str  # read, write, delete
    resource_type: str  # person, relationship
    resource_id: str
    fields_accessed: list[str] = Field(default_factory=list)
    context: Optional[dict] = None  # Additional metadata

