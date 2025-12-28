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
    name: str = Field(..., min_length=1, max_length=200)
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

    @field_validator("aliases")
    @classmethod
    def lowercase_aliases(cls, v: list[str]) -> list[str]:
        return [alias.lower().strip() for alias in v]

    @field_validator("work_email", "personal_email")
    @classmethod
    def lowercase_email(cls, v: Optional[str]) -> Optional[str]:
        return v.lower().strip() if v else None


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
    name: Optional[str] = Field(None, min_length=1, max_length=200)
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

