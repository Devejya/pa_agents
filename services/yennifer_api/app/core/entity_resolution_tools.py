"""
LangChain Tools for Entity Resolution

Provides tools for:
- Finding person candidates with disambiguation
- Creating persons with placeholder support
- Updating contact info
- Boosting relevance on confirmation
- Adding relationships to existing persons

PII Masking:
- find_person_candidates uses FINANCIAL_ONLY (shows contact status, not actual contact)
- Write/update tools don't mask output (they return confirmations)
"""

import logging
from datetime import datetime
from typing import Optional
from langchain.tools import tool

from app.core.entity_resolution import (
    find_person_candidates_db,
    create_person_with_data,
    boost_person_relevance_db,
    update_contact_info_db,
    check_real_contact_info,
)
from app.core.pii import mask_pii_financial_only
from app.models.person import PersonCreateInput, PersonCandidate

logger = logging.getLogger(__name__)

# Store user_id in thread-local or context
_current_user_id: Optional[str] = None


def set_entity_resolution_user(user_id: str):
    """Set the current user ID for entity resolution tools."""
    global _current_user_id
    _current_user_id = user_id


def get_entity_resolution_user() -> Optional[str]:
    """Get the current user ID."""
    return _current_user_id


# ============================================================
# Tool: Find Person Candidates
# ============================================================

@tool
def find_person_candidates(
    name: str,
    relationship_hint: str = None,
    location_hint: str = None,
    company_hint: str = None,
    interest_hint: str = None
) -> str:
    """
    Search for matching persons in the user's network with confidence scores.
    
    ALWAYS call this tool FIRST when a user mentions someone by name to check
    if they already exist in the network before creating a new record.
    
    Args:
        name: Person's name to search for (required)
        relationship_hint: How they relate to user (e.g., "nephew", "friend", "coworker")
        location_hint: City or country to filter by
        company_hint: Company to filter by
        interest_hint: Interest to filter by
    
    Returns:
        - If 0 matches: "No matches found for {name}"
        - If 1+ matches: List of candidates with confidence scores and details
    
    Example:
        find_person_candidates(name="Frank", relationship_hint="nephew")
        -> Returns candidates named Frank who are user's nephew
    """
    user_id = get_entity_resolution_user()
    if not user_id:
        return "Error: User context not set"
    
    try:
        candidates = find_person_candidates_db(
            user_id=user_id,
            name=name,
            relationship_hint=relationship_hint,
            location_hint=location_hint,
            company_hint=company_hint,
            interest_hint=interest_hint
        )
        
        if not candidates:
            return f"No matches found for '{name}' in the network."
        
        # Format results
        result_lines = [f"Found {len(candidates)} candidate(s) for '{name}':\n"]
        
        for i, c in enumerate(candidates, 1):
            result_lines.append(f"\n{i}. **{c.name}** (confidence: {c.confidence:.0f}%)")
            
            # Relationships
            if c.relationships:
                rel_strs = [r.get('to_role', 'contact') for r in c.relationships]
                result_lines.append(f"   Relationship: {', '.join(rel_strs)}")
            
            # Location
            if c.city or c.country:
                loc = ', '.join(filter(None, [c.city, c.country]))
                result_lines.append(f"   Location: {loc}")
            
            # Work
            if c.company or c.title:
                work = ' at '.join(filter(None, [c.title, c.company]))
                result_lines.append(f"   Work: {work}")
            
            # Contact status
            if c.has_real_phone and c.has_real_email:
                result_lines.append("   Contact: Has phone and email")
            elif c.has_real_phone:
                result_lines.append("   Contact: Has phone only")
            elif c.has_real_email:
                result_lines.append("   Contact: Has email only")
            else:
                result_lines.append("   Contact: ⚠️ No real contact info (placeholder)")
            
            result_lines.append(f"   ID: {c.person_id}")
        
        # Use FINANCIAL_ONLY - user expects to see contact status when looking up people
        return mask_pii_financial_only('\n'.join(result_lines))
        
    except Exception as e:
        logger.error(f"Error finding candidates: {e}")
        return f"Error searching for '{name}': {str(e)}"


# ============================================================
# Tool: Create Person
# ============================================================

@tool
def create_person_in_network(
    first_name: str,
    last_name: str = None,
    relationship_to_user: str = None,
    age: int = None,
    birthday_date: str = None,
    location_city: str = None,
    location_country: str = None,
    company: str = None,
    title: str = None,
    phone: str = None,
    email: str = None,
    interests: str = None,
    important_date: str = None,
    important_date_type: str = None,
    important_date_notes: str = None,
    notes: str = None
) -> str:
    """
    Create a new person in the user's network.
    
    IMPORTANT: Always call find_person_candidates FIRST to check if person
    already exists before creating a new record.
    
    If no phone or email is provided, a placeholder will be generated.
    The agent will ask for real contact info when needed (e.g., to message them).
    
    Args:
        first_name: Person's first name (required)
        last_name: Person's last name
        relationship_to_user: How they relate to user (nephew, friend, coworker, etc.)
        age: Person's age in years (birth_year will be computed automatically)
        birthday_date: Birthday in MM-DD format (e.g., "01-15" for Jan 15)
        location_city: City where they live
        location_country: Country where they live
        company: Company they work at
        title: Job title
        phone: Phone number (optional - placeholder generated if not provided)
        email: Email address (optional)
        interests: Comma-separated list of interests (e.g., "hiking, coffee, photography")
        important_date: Important date in YYYY-MM-DD or MM-DD format
        important_date_type: Type of date (birthday, anniversary, graduation, etc.)
        important_date_notes: Notes about the date
        notes: Additional notes about the person
    
    Returns:
        Confirmation message with person_id and summary
    
    Example:
        create_person_in_network(
            first_name="Frank",
            relationship_to_user="nephew",
            age=22,
            birthday_date="01-15",
            location_city="Toronto",
            interests="hiking, coffee"
        )
    """
    user_id = get_entity_resolution_user()
    if not user_id:
        return "Error: User context not set"
    
    try:
        # Compute birth_year from age using current date
        birth_year = None
        if age is not None:
            current_year = datetime.now().year
            birth_year = current_year - age
        
        # Convert flat params to model
        data = PersonCreateInput(
            first_name=first_name,
            last_name=last_name,
            relationship_to_user=relationship_to_user,
            age=age,
            birth_year=birth_year,
            birthday_date=birthday_date,
            location_city=location_city,
            location_country=location_country,
            company=company,
            title=title,
            phone=phone,
            email=email,
            interests=interests,
            important_date=important_date,
            important_date_type=important_date_type,
            important_date_notes=important_date_notes,
            notes=notes
        )
        
        person_id, message = create_person_with_data(user_id, data)
        
        if person_id:
            return f"✓ {message}\nPerson ID: {person_id}"
        else:
            return f"❌ {message}"
            
    except Exception as e:
        logger.error(f"Error creating person: {e}")
        return f"Error creating {first_name}: {str(e)}"


# ============================================================
# Tool: Boost Person Relevance
# ============================================================

@tool
def confirm_person_selection(person_id: str) -> str:
    """
    Call this when user confirms or selects a person from disambiguation.
    Boosts the person's relevance score for better future matching.
    
    Args:
        person_id: The UUID of the confirmed person
    
    Returns:
        Confirmation message
    """
    user_id = get_entity_resolution_user()
    if not user_id:
        return "Error: User context not set"
    
    try:
        success = boost_person_relevance_db(user_id, person_id)
        if success:
            return f"✓ Noted. I'll remember this preference for future interactions."
        else:
            return "Could not update preference."
    except Exception as e:
        logger.error(f"Error boosting relevance: {e}")
        return f"Error: {str(e)}"


# ============================================================
# Tool: Update Contact Info
# ============================================================

@tool
def update_person_contact(
    person_id: str,
    phone: str = None,
    email: str = None
) -> str:
    """
    Update a person's contact information (phone or email).
    Use this when user provides real contact info for someone with placeholder.
    
    Args:
        person_id: The UUID of the person to update
        phone: New phone number
        email: New email address
    
    Returns:
        Confirmation message
    """
    user_id = get_entity_resolution_user()
    if not user_id:
        return "Error: User context not set"
    
    try:
        success, message = update_contact_info_db(user_id, person_id, phone, email)
        if success:
            return f"✓ {message}"
        else:
            return f"❌ {message}"
    except Exception as e:
        logger.error(f"Error updating contact: {e}")
        return f"Error: {str(e)}"


# ============================================================
# Tool: Check Contact Info
# ============================================================

@tool
def check_person_has_contact(person_id: str) -> str:
    """
    Check if a person has real (non-placeholder) contact information.
    Use this before attempting to message, call, or email someone.
    
    Args:
        person_id: The UUID of the person to check
    
    Returns:
        Status of phone and email availability
    """
    user_id = get_entity_resolution_user()
    if not user_id:
        return "Error: User context not set"
    
    try:
        has_phone, has_email = check_real_contact_info(user_id, person_id)
        
        if has_phone and has_email:
            return "✓ Person has both phone and email on file."
        elif has_phone:
            return "✓ Person has phone on file. ⚠️ No email."
        elif has_email:
            return "✓ Person has email on file. ⚠️ No phone."
        else:
            return "⚠️ No real contact info. Need to ask user for phone or email."
            
    except Exception as e:
        logger.error(f"Error checking contact: {e}")
        return f"Error: {str(e)}"


# ============================================================
# Costly Actions List (for reference in prompts)
# ============================================================

COSTLY_ACTIONS = {
    'send_message',
    'send_email', 
    'make_call',
    'create_event_with_attendees',
    'send_gift',
    'make_purchase',
    'book_reservation',
    'send_sms',
    'send_whatsapp',
}


# ============================================================
# Export all tools
# ============================================================

ENTITY_RESOLUTION_TOOLS = [
    find_person_candidates,
    create_person_in_network,
    confirm_person_selection,
    update_person_contact,
    check_person_has_contact,
]

