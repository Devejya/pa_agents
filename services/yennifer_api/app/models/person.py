"""
Pydantic models for Person operations.
Used by both LangChain tools and API endpoints.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import date
from enum import Enum


class RelationshipCategory(str, Enum):
    """Valid relationship categories."""
    FAMILY = "family"
    FRIENDS = "friends"
    WORK = "work"
    ACQUAINTANCE = "acquaintance"


class ImportantDateType(str, Enum):
    """Types of important dates."""
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    WEDDING_ANNIVERSARY = "wedding_anniversary"
    WORK_ANNIVERSARY = "work_anniversary"
    GRADUATION = "graduation"
    MEMORIAL = "memorial"
    OTHER = "other"


class ImportantDateInput(BaseModel):
    """Input model for an important date."""
    date_value: str = Field(..., description="Date in YYYY-MM-DD or MM-DD format")
    date_type: ImportantDateType = Field(..., description="Type of the date")
    title: Optional[str] = Field(None, description="Title/name for the date")
    notes: Optional[str] = Field(None, description="Additional notes")
    is_recurring: Optional[bool] = Field(None, description="If None, inferred from date format")
    
    @validator('is_recurring', always=True)
    def infer_recurring(cls, v, values):
        if v is not None:
            return v
        # Infer from date format: MM-DD is recurring, YYYY-MM-DD is not
        date_value = values.get('date_value', '')
        return len(date_value) == 5  # "MM-DD" format


class InterestInput(BaseModel):
    """Input model for a person's interest."""
    name: str = Field(..., description="Name of the interest")
    level: int = Field(70, ge=0, le=100, description="Interest level 0-100")
    notes: Optional[str] = Field(None, description="Additional notes about this interest")


class PersonCreateInput(BaseModel):
    """
    Input model for creating a person.
    Used internally by tools - flat params are converted to this model.
    """
    # Identity (required)
    first_name: str = Field(..., min_length=1, description="Person's first name")
    last_name: Optional[str] = Field(None, description="Person's last name")
    aliases: Optional[List[str]] = Field(None, description="Alternative names/nicknames")
    
    # Relationship to user
    relationship_to_user: Optional[str] = Field(None, description="How they relate to user (nephew, friend, coworker)")
    
    # Demographics
    age: Optional[int] = Field(None, ge=0, le=150, description="Person's age (used to compute birth_year)")
    birth_year: Optional[int] = Field(None, ge=1900, le=2100, description="Year of birth")
    birthday_date: Optional[str] = Field(None, description="Birthday in MM-DD format")
    
    # Location
    location_city: Optional[str] = Field(None, description="City where they live")
    location_state: Optional[str] = Field(None, description="State/province")
    location_country: Optional[str] = Field(None, description="Country")
    
    # Work
    company: Optional[str] = Field(None, description="Company they work at")
    title: Optional[str] = Field(None, description="Job title")
    
    # Contact (optional - placeholder generated if not provided)
    phone: Optional[str] = Field(None, description="Phone number")
    email: Optional[str] = Field(None, description="Email address")
    
    # Enrichment
    interests: Optional[str] = Field(None, description="Comma-separated interests")
    
    # Important date (single, for simplicity in tool)
    important_date: Optional[str] = Field(None, description="Date in YYYY-MM-DD or MM-DD format")
    important_date_type: Optional[str] = Field(None, description="Type: birthday, anniversary, graduation, etc.")
    important_date_notes: Optional[str] = Field(None, description="Notes about the date")
    
    # Notes
    notes: Optional[str] = Field(None, description="Additional notes about the person")
    
    def get_interests_list(self) -> List[str]:
        """Parse comma-separated interests into list."""
        if not self.interests:
            return []
        return [i.strip() for i in self.interests.split(',') if i.strip()]
    
    def get_full_name(self) -> str:
        """Get full name from first + last."""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name


class PersonCandidate(BaseModel):
    """A person candidate returned from disambiguation search."""
    person_id: str
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    
    # All relationships to user
    relationships: List[dict] = Field(default_factory=list)
    
    # Location
    city: Optional[str] = None
    country: Optional[str] = None
    
    # Work
    company: Optional[str] = None
    title: Optional[str] = None
    
    # Contact status
    has_real_phone: bool = False
    has_real_email: bool = False
    
    # Scoring
    confidence: float = 0.0
    
    # For display
    distinguishing_info: str = ""
    
    def format_for_display(self) -> str:
        """Format candidate for user display during disambiguation."""
        lines = [f"**{self.name}**"]
        
        # Relationships
        if self.relationships:
            rel_strs = [r.get('to_role', 'contact') for r in self.relationships]
            lines.append(f"  ({', '.join(rel_strs)})")
        
        # Location
        if self.city or self.country:
            loc = ', '.join(filter(None, [self.city, self.country]))
            lines.append(f"  📍 {loc}")
        
        # Work
        if self.company or self.title:
            work = ' at '.join(filter(None, [self.title, self.company]))
            lines.append(f"  💼 {work}")
        
        # Contact status
        if self.has_real_phone:
            lines.append("  📞 Has phone")
        elif self.has_real_email:
            lines.append("  📧 Has email")
        else:
            lines.append("  ⚠️ No contact info")
        
        return '\n'.join(lines)


class MergeConflict(BaseModel):
    """A conflict found when merging two persons."""
    field: str
    keep_value: Optional[str] = None
    merge_value: Optional[str] = None
    
    def format_for_user(self) -> str:
        return f"- {self.field}: '{self.keep_value}' vs '{self.merge_value}'"


class PersonMergeInput(BaseModel):
    """Input model for merging two persons."""
    keep_person_id: str = Field(..., description="ID of person to keep")
    merge_person_id: str = Field(..., description="ID of person to merge into keep")
    
    # Conflict resolutions (user choices)
    phone_choice: Optional[str] = Field(None, description="'keep', 'merge', or 'both'")
    email_choice: Optional[str] = Field(None, description="'keep', 'merge', or 'both'")
    birthday_choice: Optional[str] = Field(None, description="'keep' or 'merge'")
    company_choice: Optional[str] = Field(None, description="'keep' or 'merge'")
    title_choice: Optional[str] = Field(None, description="'keep' or 'merge'")


# Relationship pairs that conflict (cannot both be true)
CONFLICTING_RELATIONSHIP_PAIRS = [
    ('father', 'brother'),
    ('father', 'son'),
    ('father', 'uncle'),
    ('father', 'cousin'),
    ('father', 'nephew'),
    ('mother', 'sister'),
    ('mother', 'daughter'),
    ('mother', 'aunt'),
    ('mother', 'cousin'),
    ('mother', 'niece'),
    ('brother', 'father'),
    ('brother', 'son'),
    ('sister', 'mother'),
    ('sister', 'daughter'),
    ('spouse', 'sibling'),
    ('spouse', 'parent'),
    ('spouse', 'child'),
    ('manager', 'direct_report'),
    ('grandparent', 'sibling'),
    ('grandparent', 'parent'),
]


def detect_relationship_conflicts(relationships: List[str]) -> List[tuple]:
    """Return list of conflicting relationship pairs found."""
    conflicts = []
    rel_lower = [r.lower() for r in relationships]
    
    for r1 in rel_lower:
        for r2 in rel_lower:
            if r1 != r2 and (r1, r2) in CONFLICTING_RELATIONSHIP_PAIRS:
                if (r2, r1) not in conflicts:  # Avoid duplicates
                    conflicts.append((r1, r2))
    
    return conflicts

