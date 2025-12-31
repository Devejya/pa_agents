"""
Pydantic models for Yennifer API.
"""

from .person import (
    PersonCreateInput,
    PersonCandidate,
    PersonMergeInput,
    ImportantDateInput,
    InterestInput,
    MergeConflict,
    RelationshipCategory,
    ImportantDateType,
    CONFLICTING_RELATIONSHIP_PAIRS,
    detect_relationship_conflicts,
)

__all__ = [
    'PersonCreateInput',
    'PersonCandidate',
    'PersonMergeInput',
    'ImportantDateInput',
    'InterestInput',
    'MergeConflict',
    'RelationshipCategory',
    'ImportantDateType',
    'CONFLICTING_RELATIONSHIP_PAIRS',
    'detect_relationship_conflicts',
]

