"""
Entity Resolution Module

Handles:
- Person disambiguation (finding matching candidates)
- Confidence scoring
- Placeholder generation
- Person creation with enrichment
- Person merging
"""

import json
import logging
import uuid
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from difflib import SequenceMatcher

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import get_settings
from app.core.encryption import get_encryption
from app.models.person import (
    PersonCreateInput,
    PersonCandidate,
    PersonMergeInput,
    MergeConflict,
    RelationshipCategory,
    CONFLICTING_RELATIONSHIP_PAIRS,
    detect_relationship_conflicts,
)

logger = logging.getLogger(__name__)

# ============================================================
# Confidence Scoring Constants
# ============================================================

RELATIONSHIP_CATEGORY_SCORES = {
    'family': 90,
    'friends': 70,
    'work': 50,
    'acquaintance': 30,
    'unknown': 10,
}

# Common nickname mappings
NICKNAME_MAP = {
    'bob': ['robert', 'bobby', 'rob'],
    'robert': ['bob', 'bobby', 'rob'],
    'bill': ['william', 'billy', 'will'],
    'william': ['bill', 'billy', 'will'],
    'mike': ['michael', 'mick', 'mikey'],
    'michael': ['mike', 'mick', 'mikey'],
    'jim': ['james', 'jimmy', 'jamie'],
    'james': ['jim', 'jimmy', 'jamie'],
    'dave': ['david', 'davey'],
    'david': ['dave', 'davey'],
    'tom': ['thomas', 'tommy'],
    'thomas': ['tom', 'tommy'],
    'chris': ['christopher', 'kristopher'],
    'christopher': ['chris'],
    'dan': ['daniel', 'danny'],
    'daniel': ['dan', 'danny'],
    'joe': ['joseph', 'joey'],
    'joseph': ['joe', 'joey'],
    'sam': ['samuel', 'sammy', 'samantha'],
    'samuel': ['sam', 'sammy'],
    'samantha': ['sam', 'sammy'],
    'alex': ['alexander', 'alexandra', 'alexis'],
    'alexander': ['alex', 'xander'],
    'alexandra': ['alex', 'alexa'],
    'nick': ['nicholas', 'nicky'],
    'nicholas': ['nick', 'nicky'],
    'kate': ['katherine', 'katie', 'kathy'],
    'katherine': ['kate', 'katie', 'kathy'],
    'liz': ['elizabeth', 'lizzy', 'beth'],
    'elizabeth': ['liz', 'lizzy', 'beth', 'betty'],
    'jen': ['jennifer', 'jenny'],
    'jennifer': ['jen', 'jenny'],
    'matt': ['matthew', 'matty'],
    'matthew': ['matt', 'matty'],
    'steve': ['steven', 'stephen'],
    'steven': ['steve'],
    'stephen': ['steve'],
    'tony': ['anthony'],
    'anthony': ['tony'],
    'ed': ['edward', 'eddie', 'ted'],
    'edward': ['ed', 'eddie', 'ted', 'teddy'],
    'frank': ['francis', 'frankie'],
    'francis': ['frank', 'frankie'],
    'dick': ['richard', 'rick', 'ricky'],
    'richard': ['dick', 'rick', 'ricky', 'rich'],
    'chuck': ['charles', 'charlie'],
    'charles': ['chuck', 'charlie'],
    'meg': ['margaret', 'maggie', 'peggy'],
    'margaret': ['meg', 'maggie', 'peggy'],
}


# ============================================================
# Confidence Scoring Functions
# ============================================================

def calculate_name_score(query_name: str, person_name: str, aliases: List[str] = None) -> float:
    """
    Calculate name match score (0-100).
    Checks exact match, case-insensitive, nicknames, fuzzy match.
    """
    query_lower = query_name.lower().strip()
    person_lower = person_name.lower().strip()
    
    # Exact match
    if query_lower == person_lower:
        return 100.0
    
    # Check aliases
    if aliases:
        for alias in aliases:
            if query_lower == alias.lower():
                return 95.0
    
    # Check nickname mapping
    query_nicknames = NICKNAME_MAP.get(query_lower, [])
    if person_lower in query_nicknames:
        return 85.0
    
    person_nicknames = NICKNAME_MAP.get(person_lower, [])
    if query_lower in person_nicknames:
        return 85.0
    
    # Fuzzy match using SequenceMatcher
    ratio = SequenceMatcher(None, query_lower, person_lower).ratio()
    
    if ratio >= 0.9:
        return 80.0
    elif ratio >= 0.8:
        return 70.0
    elif ratio >= 0.6:
        return 50.0
    elif ratio >= 0.4:
        return 30.0
    
    # Check if query is contained in person name or vice versa
    if query_lower in person_lower or person_lower in query_lower:
        return 60.0
    
    return 10.0


def calculate_relationship_score(
    relationships: List[dict],
    relationship_hint: Optional[str] = None
) -> float:
    """
    Calculate relationship match score (0-100).
    Uses best matching relationship from all relationships to user.
    """
    if not relationships:
        return RELATIONSHIP_CATEGORY_SCORES['unknown']
    
    best_score = 0.0
    
    for rel in relationships:
        category = rel.get('category', 'acquaintance')
        to_role = rel.get('to_role', '').lower()
        strength = rel.get('strength', 50) / 100.0  # Normalize to 0-1
        
        # Base score from category
        base_score = RELATIONSHIP_CATEGORY_SCORES.get(category, 30)
        
        # Specificity bonus if hint matches
        specificity_bonus = 0
        if relationship_hint:
            hint_lower = relationship_hint.lower()
            if hint_lower == to_role:
                specificity_bonus = 30  # Exact match
            elif hint_lower in to_role or to_role in hint_lower:
                specificity_bonus = 15  # Partial match
            elif category == 'family' and hint_lower in ('family', 'relative'):
                specificity_bonus = 10  # Category match
            elif category == 'friends' and hint_lower in ('friend', 'friends'):
                specificity_bonus = 10
            elif category == 'work' and hint_lower in ('colleague', 'coworker', 'work'):
                specificity_bonus = 10
        
        combined = (base_score + specificity_bonus) * strength
        best_score = max(best_score, combined)
    
    return min(best_score, 100.0)


def calculate_recency_score(last_interacted_at: Optional[datetime]) -> float:
    """Calculate recency score based on last interaction (0-100)."""
    if last_interacted_at is None:
        return 20.0
    
    now = datetime.utcnow()
    delta = now - last_interacted_at
    days_ago = delta.days
    
    if days_ago <= 1:
        return 100.0  # Today/yesterday
    elif days_ago <= 7:
        return 80.0   # This week
    elif days_ago <= 30:
        return 60.0   # This month
    elif days_ago <= 90:
        return 40.0   # This quarter
    else:
        return 20.0   # Older


def calculate_frequency_score(interaction_count: int) -> float:
    """Calculate frequency score based on interaction count (0-100)."""
    if interaction_count >= 50:
        return 100.0
    elif interaction_count >= 20:
        return 80.0
    elif interaction_count >= 10:
        return 60.0
    elif interaction_count >= 5:
        return 40.0
    elif interaction_count >= 1:
        return 20.0
    else:
        return 10.0


def calculate_context_score(
    person: dict,
    location_hint: Optional[str] = None,
    company_hint: Optional[str] = None,
    interest_hint: Optional[str] = None,
    interests: List[dict] = None
) -> float:
    """Calculate context match score (0-100)."""
    scores = []
    
    # Location match
    if location_hint:
        location_lower = location_hint.lower()
        person_city = (person.get('city') or '').lower()
        person_country = (person.get('country') or '').lower()
        
        if location_lower in person_city or person_city in location_lower:
            scores.append(80.0)
        elif location_lower in person_country or person_country in location_lower:
            scores.append(60.0)
    
    # Company match
    if company_hint:
        company_lower = company_hint.lower()
        person_company = (person.get('company') or '').lower()
        
        if company_lower in person_company or person_company in company_lower:
            scores.append(80.0)
    
    # Interest match
    if interest_hint and interests:
        interest_lower = interest_hint.lower()
        for interest in interests:
            interest_name = (interest.get('name') or '').lower()
            if interest_lower in interest_name or interest_name in interest_lower:
                scores.append(70.0)
                break
    
    if scores:
        return sum(scores) / len(scores)
    
    return 0.0


def calculate_confidence(
    person: dict,
    relationships: List[dict],
    query_name: str,
    relationship_hint: Optional[str] = None,
    location_hint: Optional[str] = None,
    company_hint: Optional[str] = None,
    interest_hint: Optional[str] = None,
    interests: List[dict] = None
) -> float:
    """
    Calculate overall confidence score (0-100).
    
    Weights:
    - Name match: 30%
    - Relationship match: 25%
    - Recency: 15%
    - Frequency: 15%
    - Context: 15%
    """
    name_score = calculate_name_score(
        query_name,
        person.get('name', ''),
        person.get('aliases', [])
    )
    
    rel_score = calculate_relationship_score(relationships, relationship_hint)
    recency = calculate_recency_score(person.get('last_interacted_at'))
    frequency = calculate_frequency_score(person.get('interaction_count', 0))
    context = calculate_context_score(
        person, location_hint, company_hint, interest_hint, interests
    )
    
    confidence = (
        name_score * 0.30 +
        rel_score * 0.25 +
        recency * 0.15 +
        frequency * 0.15 +
        context * 0.15
    )
    
    return min(confidence, 100.0)


# ============================================================
# Database Operations
# ============================================================

def get_sync_connection():
    """Get a synchronous database connection."""
    settings = get_settings()
    return psycopg2.connect(settings.database_url, cursor_factory=RealDictCursor)


def generate_placeholder_phone() -> str:
    """Generate a clearly fake, unique placeholder phone number."""
    # Format: +0-000-000-XXXX where XXXX is random
    random_suffix = str(uuid.uuid4().int)[:4]
    return f"+0-000-000-{random_suffix}"


def generate_placeholder_email() -> str:
    """Generate a clearly fake, unique placeholder email."""
    random_id = str(uuid.uuid4())[:8]
    return f"placeholder-{random_id}@fake.internal"


def find_person_candidates_db(
    user_id: str,
    name: str,
    relationship_hint: Optional[str] = None,
    location_hint: Optional[str] = None,
    company_hint: Optional[str] = None,
    interest_hint: Optional[str] = None
) -> List[PersonCandidate]:
    """
    Search for matching persons with confidence scores.
    Returns candidates sorted by confidence (highest first).
    """
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            # Get all persons for this user that might match
            # Use broad search, then filter/score in Python
            cur.execute("""
                SELECT 
                    p.id, p.name, p.first_name, p.last_name, p.aliases,
                    p.city, p.state, p.country, p.company, p.latest_title,
                    p.personal_email, p.work_email, p.personal_cell, p.work_cell,
                    p.is_placeholder_phone, p.is_placeholder_email,
                    p.last_interacted_at, p.interaction_count
                FROM persons p
                WHERE p.owner_user_id = %s
                AND (
                    LOWER(p.name) LIKE %s
                    OR LOWER(p.first_name) LIKE %s
                    OR EXISTS (
                        SELECT 1 FROM unnest(p.aliases) AS alias
                        WHERE LOWER(alias) LIKE %s
                    )
                )
            """, (
                user_id,
                f"%{name.lower()}%",
                f"%{name.lower()}%",
                f"%{name.lower()}%"
            ))
            
            persons = cur.fetchall()
            
            candidates = []
            for person in persons:
                person_id = str(person['id'])
                
                # Get relationships for this person
                cur.execute("""
                    SELECT 
                        r.id, r.from_role, r.to_role, r.category, 
                        r.strength, r.last_referenced_at, r.reference_count
                    FROM relationships r
                    WHERE r.to_person_id = %s
                    AND r.owner_user_id = %s
                """, (person_id, user_id))
                relationships = cur.fetchall()
                
                # Get interests for context matching
                cur.execute("""
                    SELECT name, interest_level
                    FROM interests
                    WHERE person_id = %s
                """, (person_id,))
                interests = cur.fetchall()
                
                # Calculate confidence
                confidence = calculate_confidence(
                    person=dict(person),
                    relationships=[dict(r) for r in relationships],
                    query_name=name,
                    relationship_hint=relationship_hint,
                    location_hint=location_hint,
                    company_hint=company_hint,
                    interest_hint=interest_hint,
                    interests=[dict(i) for i in interests]
                )
                
                # Determine contact status
                has_real_phone = (
                    (person['personal_cell'] or person['work_cell']) and
                    not person.get('is_placeholder_phone', False)
                )
                has_real_email = (
                    (person['personal_email'] or person['work_email']) and
                    not person.get('is_placeholder_email', False)
                )
                
                # Build distinguishing info
                dist_parts = []
                if relationships:
                    rel_strs = [r['to_role'] for r in relationships if r.get('to_role')]
                    if rel_strs:
                        dist_parts.append(f"your {', '.join(rel_strs)}")
                if person['city']:
                    dist_parts.append(f"in {person['city']}")
                if person['company']:
                    dist_parts.append(f"at {person['company']}")
                
                candidate = PersonCandidate(
                    person_id=person_id,
                    name=person['name'] or f"{person['first_name']} {person['last_name'] or ''}".strip(),
                    first_name=person['first_name'],
                    last_name=person['last_name'],
                    aliases=person['aliases'] or [],
                    relationships=[dict(r) for r in relationships],
                    city=person['city'],
                    country=person['country'],
                    company=person['company'],
                    title=person['latest_title'],
                    has_real_phone=has_real_phone,
                    has_real_email=has_real_email,
                    confidence=confidence,
                    distinguishing_info=' '.join(dist_parts) if dist_parts else ''
                )
                
                candidates.append(candidate)
            
            # Sort by confidence (highest first)
            candidates.sort(key=lambda c: c.confidence, reverse=True)
            
            return candidates
            
    finally:
        conn.close()


def create_person_with_data(
    user_id: str,
    data: PersonCreateInput
) -> Tuple[str, str]:
    """
    Create a person with all provided data.
    Returns (person_id, summary_message).
    """
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            # Get core user's person_id
            cur.execute("""
                SELECT p.id FROM persons p
                JOIN users u ON u.id = %s
                WHERE p.owner_user_id = %s AND p.is_core_user = true
                LIMIT 1
            """, (user_id, user_id))
            core_row = cur.fetchone()
            
            if not core_row:
                # Fallback: find by email
                cur.execute("""
                    SELECT p.id FROM persons p
                    WHERE p.owner_user_id = %s AND p.is_core_user = true
                    LIMIT 1
                """, (user_id,))
                core_row = cur.fetchone()
            
            if not core_row:
                return None, "Could not find your profile. Please try again."
            
            core_person_id = core_row['id']
            
            # Determine phone/email (use placeholder if not provided)
            phone = data.phone
            email = data.email
            is_placeholder_phone = False
            is_placeholder_email = False
            
            if not phone and not email:
                phone = generate_placeholder_phone()
                is_placeholder_phone = True
            
            # Full name
            full_name = data.get_full_name()
            
            # Create person (notes not stored in persons table)
            cur.execute("""
                INSERT INTO persons (
                    owner_user_id, name, first_name, last_name, aliases,
                    city, state, country, company, latest_title,
                    personal_email, personal_cell, 
                    is_placeholder_phone, is_placeholder_email,
                    birth_year, is_core_user
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)
                RETURNING id
            """, (
                user_id, full_name, data.first_name, data.last_name,
                data.aliases or [],
                data.location_city, data.location_state, data.location_country,
                data.company, data.title,
                email, phone,
                is_placeholder_phone, is_placeholder_email,
                data.birth_year
            ))
            person_row = cur.fetchone()
            person_id = str(person_row['id'])
            
            # Create relationship if specified
            if data.relationship_to_user:
                # Determine category
                rel_lower = data.relationship_to_user.lower()
                if rel_lower in ('wife', 'husband', 'spouse', 'partner', 'mother', 'father',
                                'sister', 'brother', 'son', 'daughter', 'cousin', 'aunt',
                                'uncle', 'grandmother', 'grandfather', 'niece', 'nephew'):
                    category = 'family'
                elif rel_lower in ('friend', 'best friend', 'close friend', 'friends'):
                    category = 'friends'
                elif rel_lower in ('colleague', 'coworker', 'manager', 'boss', 'teammate'):
                    category = 'work'
                else:
                    category = 'acquaintance'
                
                # Initial strength based on category
                initial_strength = RELATIONSHIP_CATEGORY_SCORES.get(category, 50)
                
                cur.execute("""
                    INSERT INTO relationships (
                        owner_user_id, from_person_id, to_person_id,
                        from_role, to_role, category, strength
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, core_person_id, person_id,
                    'user', data.relationship_to_user, category, initial_strength
                ))
            
            # Save interests (properly encrypted)
            interests_saved = 0
            interests_to_save = data.get_interests_list()
            if interests_to_save:
                # Get user's DEK for encryption
                cur.execute(
                    "SELECT encryption_key_blob FROM users WHERE id = %s",
                    (user_id,)
                )
                user_row = cur.fetchone()
                if user_row and user_row['encryption_key_blob']:
                    encryption = get_encryption()
                    user_dek = encryption.decrypt_user_dek(bytes(user_row['encryption_key_blob']))
                    
                    for interest_name in interests_to_save:
                        details = {"name": interest_name}
                        details_encrypted = encryption.encrypt_for_user(user_dek, json.dumps(details))
                        cur.execute("""
                            INSERT INTO interests (user_id, person_id, interest_level, details_encrypted)
                            VALUES (%s, %s, %s, %s)
                        """, (user_id, person_id, 70, details_encrypted))
                        interests_saved += 1
                else:
                    logger.warning(f"Cannot save interests for user {user_id}: no encryption key")
            
            # Save birthday if provided (encrypted)
            if data.birthday_date:
                # Need user_dek for encryption - get it if not already fetched
                if 'user_dek' not in locals():
                    cur.execute(
                        "SELECT encryption_key_blob FROM users WHERE id = %s",
                        (user_id,)
                    )
                    user_row = cur.fetchone()
                    if user_row and user_row['encryption_key_blob']:
                        encryption = get_encryption()
                        user_dek = encryption.decrypt_user_dek(bytes(user_row['encryption_key_blob']))
                
                if 'user_dek' in locals():
                    title_encrypted = encryption.encrypt_for_user(user_dek, 'Birthday')
                    cur.execute("""
                        INSERT INTO important_dates (
                            user_id, person_id, date_value, is_recurring, title_encrypted
                        )
                        VALUES (%s, %s, %s, true, %s)
                    """, (user_id, person_id, data.birthday_date, title_encrypted))
                else:
                    logger.warning(f"Cannot save birthday for user {user_id}: no encryption key")
            
            # Save other important date if provided (encrypted)
            if data.important_date:
                # Need user_dek for encryption - get it if not already fetched
                if 'user_dek' not in locals():
                    cur.execute(
                        "SELECT encryption_key_blob FROM users WHERE id = %s",
                        (user_id,)
                    )
                    user_row = cur.fetchone()
                    if user_row and user_row['encryption_key_blob']:
                        encryption = get_encryption()
                        user_dek = encryption.decrypt_user_dek(bytes(user_row['encryption_key_blob']))
                
                if 'user_dek' in locals():
                    is_recurring = len(data.important_date) == 5  # MM-DD format
                    title_encrypted = encryption.encrypt_for_user(
                        user_dek, 
                        data.important_date_type or 'Important Date'
                    )
                    notes_encrypted = None
                    if data.important_date_notes:
                        notes_encrypted = encryption.encrypt_for_user(user_dek, data.important_date_notes)
                    
                    cur.execute("""
                        INSERT INTO important_dates (
                            user_id, person_id, date_value, is_recurring, 
                            title_encrypted, notes_encrypted
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        user_id, person_id, data.important_date, is_recurring,
                        title_encrypted, notes_encrypted
                    ))
                else:
                    logger.warning(f"Cannot save important date for user {user_id}: no encryption key")
            
            conn.commit()
            
            # Build summary
            summary_parts = [f"Added {full_name}"]
            if data.relationship_to_user:
                summary_parts.append(f"as your {data.relationship_to_user}")
            if interests_saved > 0:
                summary_parts.append(f"with {interests_saved} interest(s)")
            if data.birthday_date:
                summary_parts.append(f"birthday on {data.birthday_date}")
            if is_placeholder_phone:
                summary_parts.append("(I'll ask for contact info when needed)")
            
            return person_id, '. '.join(summary_parts) + '.'
            
    except Exception as e:
        logger.error(f"Error creating person: {e}")
        conn.rollback()
        return None, f"Error creating {data.first_name}: {str(e)}"
    finally:
        conn.close()


def boost_person_relevance_db(user_id: str, person_id: str) -> bool:
    """
    Increment interaction count and update last_interacted_at.
    Called when user selects/confirms a person.
    """
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE persons
                SET interaction_count = COALESCE(interaction_count, 0) + 1,
                    last_interacted_at = NOW()
                WHERE id = %s AND owner_user_id = %s
            """, (person_id, user_id))
            
            # Also boost the relationship reference count
            cur.execute("""
                UPDATE relationships
                SET reference_count = COALESCE(reference_count, 0) + 1,
                    last_referenced_at = NOW()
                WHERE to_person_id = %s AND owner_user_id = %s
            """, (person_id, user_id))
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error boosting relevance: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_contact_info_db(
    user_id: str,
    person_id: str,
    phone: Optional[str] = None,
    email: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Update person's contact info, replacing placeholder if exists.
    """
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            updates = []
            params = []
            
            if phone:
                updates.append("personal_cell = %s")
                updates.append("is_placeholder_phone = false")
                params.append(phone)
            
            if email:
                updates.append("personal_email = %s")
                updates.append("is_placeholder_email = false")
                params.append(email)
            
            if not updates:
                return False, "No contact info provided"
            
            params.extend([person_id, user_id])
            
            cur.execute(f"""
                UPDATE persons
                SET {', '.join(updates)}
                WHERE id = %s AND owner_user_id = %s
                RETURNING name
            """, params)
            
            result = cur.fetchone()
            if not result:
                return False, "Person not found"
            
            conn.commit()
            return True, f"Updated contact info for {result['name']}"
            
    except Exception as e:
        logger.error(f"Error updating contact info: {e}")
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def check_real_contact_info(user_id: str, person_id: str) -> Tuple[bool, bool]:
    """
    Check if person has real (non-placeholder) phone and email.
    Returns (has_real_phone, has_real_email).
    """
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    personal_cell, work_cell, is_placeholder_phone,
                    personal_email, work_email, is_placeholder_email
                FROM persons
                WHERE id = %s AND owner_user_id = %s
            """, (person_id, user_id))
            
            row = cur.fetchone()
            if not row:
                return False, False
            
            has_real_phone = (
                (row['personal_cell'] or row['work_cell']) and
                not row.get('is_placeholder_phone', False)
            )
            has_real_email = (
                (row['personal_email'] or row['work_email']) and
                not row.get('is_placeholder_email', False)
            )
            
            return has_real_phone, has_real_email
            
    finally:
        conn.close()

