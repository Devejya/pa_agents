"""
Memory Tools for Yennifer Agent.

Provides tools for the agent to access and save user memories,
interests, and important dates for personalized interactions.

Note: These tools use synchronous database access because LangChain
tools are called synchronously within the agent execution context.

PII Masking:
- Read tools use FULL masking (emails, phones, SSN, cards, etc.)
- Contact lookup tools use FINANCIAL_ONLY (keep email/phone visible)
- Write/save tools don't mask output (they return confirmations)
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_core.tools import tool

from ..core.config import get_settings
from ..core.encryption import get_encryption
from ..core.pii import mask_pii, mask_pii_financial_only

logger = logging.getLogger(__name__)

# Global variable for current user_id (set per request)
_current_user_id: Optional[UUID] = None


def set_memory_user(user_id: UUID):
    """Set the current user ID for memory operations."""
    global _current_user_id
    _current_user_id = user_id


def get_memory_user() -> Optional[UUID]:
    """Get the current user ID."""
    return _current_user_id


def _get_sync_connection():
    """Get a synchronous database connection for tool operations."""
    settings = get_settings()
    # Parse the async URL to sync format
    db_url = settings.database_url
    # asyncpg URL format: postgresql://user:pass@host:port/db
    # psycopg2 uses the same format
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def _get_user_dek_sync(conn, user_id: UUID) -> Optional[bytes]:
    """Get a user's DEK synchronously."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT encryption_key_blob FROM users WHERE id = %s",
            (str(user_id),)
        )
        row = cur.fetchone()
        if row and row['encryption_key_blob']:
            encryption = get_encryption()
            return encryption.decrypt_user_dek(bytes(row['encryption_key_blob']))
    return None


# ============================================================================
# Memory Tools (Synchronous for LangChain compatibility)
# ============================================================================

@tool
def get_user_memories(context: Optional[str] = None, category: Optional[str] = None) -> str:
    """
    Get memories/facts about the user.
    
    Use this to recall things you've learned about the user, like their preferences,
    important information, communication style, etc.
    
    Args:
        context: Optional filter by context ('personal', 'professional', 'preference', etc.)
        category: Optional filter by category (more specific grouping)
    
    Returns:
        List of memories about the user
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            encryption = get_encryption()
            
            # Build query
            query = """
                SELECT id, context, category, fact_key, fact_value_encrypted,
                       source, confidence, created_at
                FROM memories
                WHERE user_id = %s AND is_active = true
                AND (expires_at IS NULL OR expires_at > NOW())
            """
            params = [str(user_id)]
            
            if context:
                query += " AND context = %s"
                params.append(context)
            if category:
                query += " AND category = %s"
                params.append(category)
            
            query += " ORDER BY confidence DESC, created_at DESC LIMIT 20"
            
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            
            if not rows:
                return "No memories found for this user yet."
            
            result = "**User Memories:**\n"
            for row in rows:
                try:
                    fact_value = encryption.decrypt_for_user(
                        user_dek, bytes(row['fact_value_encrypted'])
                    )
                    result += f"- **{row['fact_key']}**: {fact_value}"
                    if row.get('context'):
                        result += f" (context: {row['context']})"
                    result += "\n"
                except Exception as e:
                    logger.error(f"Failed to decrypt memory {row['id']}: {e}")
            
            # Mask PII in memories (may contain sensitive info)
            return mask_pii(result)
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting memories: {e}")
        return f"Error retrieving memories: {str(e)}"


@tool
def save_user_memory(fact_key: str, fact_value: str, context: str = "general") -> str:
    """
    Save a memory/fact about the user for future reference.
    
    Use this to remember important information the user tells you, like:
    - Preferences (preferred coffee, meeting times, communication style)
    - Personal info (birthday, spouse name, pets)
    - Professional info (job title, company, team members)
    - Habits (morning person, likes detailed reports)
    
    Args:
        fact_key: A short key describing the memory (e.g., "preferred_coffee", "spouse_name")
        fact_value: The actual information to remember
        context: Category - 'personal', 'professional', 'preference', 'style', or 'general'
    
    Returns:
        Confirmation message
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            encryption = get_encryption()
            fact_value_encrypted = encryption.encrypt_for_user(user_dek, fact_value)
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO memories (
                        user_id, context, fact_key, fact_value_encrypted, source, confidence
                    )
                    VALUES (%s, %s, %s, %s, 'conversation', 100)
                    ON CONFLICT (user_id, fact_key) DO UPDATE SET
                        fact_value_encrypted = EXCLUDED.fact_value_encrypted,
                        context = EXCLUDED.context,
                        updated_at = NOW()
                """, (str(user_id), context, fact_key, fact_value_encrypted))
                conn.commit()
            
            return f"✓ Remembered: {fact_key} = {fact_value}"
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error saving memory: {e}")
        return f"Error saving memory: {str(e)}"


@tool
def get_user_interests(category: Optional[str] = None, min_level: int = 50) -> str:
    """
    Get the user's interests and hobbies.
    
    Use this to understand what the user likes/dislikes for personalized recommendations
    or conversation.
    
    Args:
        category: Optional filter by category ('hobby', 'topic', 'sport', 'music', 'food', etc.)
        min_level: Minimum interest level (0-100, default 50 = likes and above)
    
    Returns:
        List of user interests with levels
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            encryption = get_encryption()
            
            # Build query
            query = """
                SELECT id, category, interest_level, details_encrypted,
                       source, confidence, created_at
                FROM interests
                WHERE user_id = %s AND interest_level >= %s
            """
            params = [str(user_id), min_level]
            
            if category:
                query += " AND category = %s"
                params.append(category)
            
            query += " ORDER BY interest_level DESC LIMIT 20"
            
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            
            if not rows:
                return "No interests recorded for this user yet."
            
            result = "**User Interests:**\n"
            for row in rows:
                try:
                    import json
                    details = json.loads(encryption.decrypt_for_user(
                        user_dek, bytes(row['details_encrypted'])
                    ))
                    name = details.get('name', 'Unknown')
                    notes = details.get('notes')
                    level = row['interest_level']
                    level_desc = "loves" if level >= 80 else "likes" if level >= 50 else "neutral"
                    result += f"- {name} ({level_desc})"
                    if notes:
                        result += f" - {notes}"
                    result += "\n"
                except Exception as e:
                    logger.error(f"Failed to decrypt interest {row['id']}: {e}")
            
            # Mask PII in interests (notes may contain sensitive info)
            return mask_pii(result)
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting interests: {e}")
        return f"Error retrieving interests: {str(e)}"


@tool
def save_user_interest(name: str, interest_level: int, category: Optional[str] = None, notes: Optional[str] = None) -> str:
    """
    Save a user interest for future reference.
    
    Use this when the user mentions something they like, dislike, or are interested in.
    
    Args:
        name: Name of the interest (e.g., "hiking", "jazz music", "Italian food")
        interest_level: How much they like it (0=dislikes, 50=likes, 100=loves)
        category: Optional category ('hobby', 'topic', 'sport', 'music', 'food', 'travel')
        notes: Optional additional notes
    
    Returns:
        Confirmation message
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            import json
            encryption = get_encryption()
            details = {"name": name, "notes": notes}
            details_encrypted = encryption.encrypt_for_user(user_dek, json.dumps(details))
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO interests (
                        user_id, category, interest_level, details_encrypted,
                        source, confidence, last_mentioned_at
                    )
                    VALUES (%s, %s, %s, %s, 'conversation', 100, NOW())
                """, (str(user_id), category, interest_level, details_encrypted))
                conn.commit()
            
            level_desc = "loves" if interest_level >= 80 else "likes" if interest_level >= 50 else "dislikes" if interest_level < 30 else "neutral"
            return f"✓ Noted: User {level_desc} {name}"
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error saving interest: {e}")
        return f"Error saving interest: {str(e)}"


@tool
def get_upcoming_important_dates(days_ahead: int = 30) -> str:
    """
    Get upcoming important dates for the user.
    
    Use this to proactively remind the user about upcoming birthdays, anniversaries,
    or other important dates. Returns person_id when available for follow-up actions
    like getting their interests for gift suggestions.
    
    Args:
        days_ahead: Number of days to look ahead (default 30)
    
    Returns:
        List of upcoming important dates with person IDs when linked
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            encryption = get_encryption()
            
            # Query for upcoming dates with person info
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT d.id, d.date_type, d.date_value, d.is_recurring,
                           d.title_encrypted, d.notes_encrypted, d.person_id,
                           p.first_name, p.last_name
                    FROM important_dates d
                    LEFT JOIN persons p ON p.id = d.person_id
                    WHERE d.user_id = %s
                    AND (
                        (NOT d.is_recurring AND d.date_value BETWEEN CURRENT_DATE AND CURRENT_DATE + %s)
                        OR
                        (d.is_recurring AND (
                            MAKE_DATE(
                                EXTRACT(YEAR FROM CURRENT_DATE)::int,
                                EXTRACT(MONTH FROM d.date_value)::int,
                                EXTRACT(DAY FROM d.date_value)::int
                            ) BETWEEN CURRENT_DATE AND CURRENT_DATE + %s
                        ))
                    )
                    ORDER BY d.date_value
                    LIMIT 10
                """, (str(user_id), days_ahead, days_ahead))
                rows = cur.fetchall()
            
            if not rows:
                return f"No important dates in the next {days_ahead} days."
            
            result = f"**Upcoming Important Dates (next {days_ahead} days):**\n"
            for row in rows:
                try:
                    title = encryption.decrypt_for_user(
                        user_dek, bytes(row['title_encrypted'])
                    )
                    date_str = row['date_value'].strftime('%B %d')
                    
                    # Include person info if available
                    person_info = ""
                    if row['person_id']:
                        person_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
                        if person_name:
                            person_info = f" [Person: {person_name}, ID: {row['person_id']}]"
                        else:
                            person_info = f" [Person ID: {row['person_id']}]"
                    
                    result += f"- **{title}** ({row['date_type']}) - {date_str}{person_info}"
                    if row['notes_encrypted']:
                        notes = encryption.decrypt_for_user(
                            user_dek, bytes(row['notes_encrypted'])
                        )
                        result += f" ({notes})"
                    result += "\n"
                except Exception as e:
                    logger.error(f"Failed to decrypt date {row['id']}: {e}")
            
            # Mask PII in dates (titles/notes may contain sensitive info)
            return mask_pii(result)
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting dates: {e}")
        return f"Error retrieving dates: {str(e)}"


# ============================================================================
# Relationship & Person Tools
# ============================================================================

@tool
def find_person_by_relationship(relationship_type: str) -> str:
    """
    Find a person in the user's network by their relationship to the user.
    
    Use this to look up family members, friends, or colleagues by relationship type.
    For example: find "wife", "husband", "mother", "father", "cousin", "manager", etc.
    
    This uses recursive search to find relationships through the network.
    
    Args:
        relationship_type: The relationship to search for (e.g., "wife", "mother", "cousin")
    
    Returns:
        Person information including their ID, name, and relationship details
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            # Find the core user's person_id first
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.id as person_id
                    FROM persons p
                    WHERE p.owner_user_id = %s AND p.is_core_user = true
                    LIMIT 1
                """, (str(user_id),))
                core_user_row = cur.fetchone()
            
            if not core_user_row:
                return "Could not find core user profile. Please ensure your profile is set up."
            
            core_person_id = core_user_row['person_id']
            
            # Normalize relationship type for matching
            rel_type_lower = relationship_type.lower().strip()
            
            # Common relationship synonyms
            synonyms = {
                'wife': ['wife', 'spouse', 'partner'],
                'husband': ['husband', 'spouse', 'partner'],
                'spouse': ['spouse', 'wife', 'husband', 'partner'],
                'mother': ['mother', 'mom', 'mum'],
                'father': ['father', 'dad'],
                'sister': ['sister', 'sibling'],
                'brother': ['brother', 'sibling'],
                'daughter': ['daughter', 'child'],
                'son': ['son', 'child'],
                'cousin': ['cousin'],
                'aunt': ['aunt'],
                'uncle': ['uncle'],
                'friend': ['friend'],
                'manager': ['manager', 'boss', 'supervisor'],
                'colleague': ['colleague', 'coworker', 'teammate'],
            }
            
            search_terms = synonyms.get(rel_type_lower, [rel_type_lower])
            
            # Search for direct relationships from core user
            # from_person_id = core user, to_person_id = the person we're looking for
            # to_role = the role of the target person (e.g., "wife")
            with conn.cursor() as cur:
                placeholders = ','.join(['%s'] * len(search_terms))
                cur.execute(f"""
                    SELECT 
                        p.id as person_id,
                        p.name,
                        p.first_name,
                        p.last_name,
                        p.personal_email,
                        r.to_role as relationship_type,
                        r.category
                    FROM relationships r
                    JOIN persons p ON p.id = r.to_person_id
                    WHERE r.from_person_id = %s
                    AND LOWER(r.to_role) IN ({placeholders})
                    AND p.owner_user_id = %s
                    AND r.is_active = true
                    LIMIT 5
                """, (str(core_person_id), *search_terms, str(user_id)))
                rows = cur.fetchall()
            
            if not rows:
                # Try reverse relationship (to_person_id is core user, look at from_role)
                with conn.cursor() as cur:
                    cur.execute(f"""
                        SELECT 
                            p.id as person_id,
                            p.name,
                            p.first_name,
                            p.last_name,
                            p.personal_email,
                            r.from_role as relationship_type,
                            r.category
                        FROM relationships r
                        JOIN persons p ON p.id = r.from_person_id
                        WHERE r.to_person_id = %s
                        AND LOWER(r.from_role) IN ({placeholders})
                        AND p.owner_user_id = %s
                        AND r.is_active = true
                        LIMIT 5
                    """, (str(core_person_id), *search_terms, str(user_id)))
                    rows = cur.fetchall()
            
            if not rows:
                return f"No person found with relationship '{relationship_type}' in your network."
            
            result = f"**Found person(s) with relationship '{relationship_type}':**\n"
            for row in rows:
                name = row['name'] or f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or "Unknown"
                result += f"- **{name}** (ID: {row['person_id']})\n"
                result += f"  - Relationship: {row['relationship_type']}\n"
                if row.get('personal_email'):
                    result += f"  - Email: {row['personal_email']}\n"
                if row.get('category'):
                    result += f"  - Category: {row['category']}\n"
            
            # Use FINANCIAL_ONLY - user expects to see contact info when looking up people
            return mask_pii_financial_only(result)
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error finding person by relationship: {e}")
        return f"Error finding person: {str(e)}"


@tool
def get_person_interests(person_id: str) -> str:
    """
    Get the interests of a specific person in your network.
    
    Use this to find out what gifts someone might like, or to personalize
    recommendations for them.
    
    Args:
        person_id: The UUID of the person (from find_person_by_relationship)
    
    Returns:
        List of the person's interests with levels
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            encryption = get_encryption()
            
            # Get person's name first
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT first_name, last_name
                    FROM persons
                    WHERE id = %s AND owner_user_id = %s
                """, (person_id, str(user_id)))
                person_row = cur.fetchone()
            
            if not person_row:
                return f"Person with ID {person_id} not found in your network."
            
            person_name = f"{person_row['first_name'] or ''} {person_row['last_name'] or ''}".strip() or "This person"
            
            # Get person's interests
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, category, interest_level, details_encrypted,
                           source, confidence, created_at
                    FROM interests
                    WHERE person_id = %s AND user_id = %s
                    ORDER BY interest_level DESC
                    LIMIT 20
                """, (person_id, str(user_id)))
                rows = cur.fetchall()
            
            if not rows:
                return f"No interests recorded for {person_name}. You may want to ask the user about their interests."
            
            result = f"**{person_name}'s Interests:**\n"
            for row in rows:
                try:
                    import json
                    details = json.loads(encryption.decrypt_for_user(
                        user_dek, bytes(row['details_encrypted'])
                    ))
                    name = details.get('name', 'Unknown')
                    notes = details.get('notes')
                    level = row['interest_level']
                    level_desc = "loves" if level >= 80 else "likes" if level >= 50 else "dislikes" if level < 30 else "neutral"
                    result += f"- {name} ({level_desc})"
                    if notes:
                        result += f" - {notes}"
                    result += "\n"
                except Exception as e:
                    logger.error(f"Failed to decrypt interest {row['id']}: {e}")
            
            # Mask PII in interests (notes may contain sensitive info)
            return mask_pii(result)
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting person interests: {e}")
        return f"Error retrieving interests: {str(e)}"


@tool
def save_person_interest(
    person_id: str, 
    name: str, 
    interest_level: int, 
    category: Optional[str] = None, 
    notes: Optional[str] = None
) -> str:
    """
    Save an interest for a specific person in your network.
    
    Use this when the user tells you about what someone else likes or dislikes.
    For example: "My wife loves gardening" or "My dad hates spicy food"
    
    Args:
        person_id: The UUID of the person (from find_person_by_relationship)
        name: Name of the interest (e.g., "gardening", "Italian food", "hiking")
        interest_level: How much they like it (0=dislikes, 50=likes, 100=loves)
        category: Optional category ('hobby', 'topic', 'sport', 'music', 'food', 'travel')
        notes: Optional additional notes
    
    Returns:
        Confirmation message
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            # Verify person exists and belongs to user
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT first_name, last_name
                    FROM persons
                    WHERE id = %s AND owner_user_id = %s
                """, (person_id, str(user_id)))
                person_row = cur.fetchone()
            
            if not person_row:
                return f"Person with ID {person_id} not found in your network."
            
            person_name = f"{person_row['first_name'] or ''} {person_row['last_name'] or ''}".strip() or "This person"
            
            import json
            encryption = get_encryption()
            details = {"name": name, "notes": notes}
            details_encrypted = encryption.encrypt_for_user(user_dek, json.dumps(details))
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO interests (
                        user_id, person_id, category, interest_level, details_encrypted,
                        source, confidence, last_mentioned_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'conversation', 100, NOW())
                """, (str(user_id), person_id, category, interest_level, details_encrypted))
                conn.commit()
            
            level_desc = "loves" if interest_level >= 80 else "likes" if interest_level >= 50 else "dislikes" if interest_level < 30 else "neutral"
            return f"✓ Noted: {person_name} {level_desc} {name}"
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error saving person interest: {e}")
        return f"Error saving interest: {str(e)}"


@tool
def get_important_dates_for_person(person_id: str) -> str:
    """
    Get important dates associated with a specific person.
    
    Use this to find birthdays, anniversaries, or other dates related to someone.
    
    Args:
        person_id: The UUID of the person (from find_person_by_relationship)
    
    Returns:
        List of important dates for this person
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            encryption = get_encryption()
            
            # Get person's name first
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT first_name, last_name, date_of_birth
                    FROM persons
                    WHERE id = %s AND owner_user_id = %s
                """, (person_id, str(user_id)))
                person_row = cur.fetchone()
            
            if not person_row:
                return f"Person with ID {person_id} not found in your network."
            
            person_name = f"{person_row['first_name'] or ''} {person_row['last_name'] or ''}".strip() or "This person"
            
            # Get dates for this person
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, date_type, date_value, is_recurring,
                           title_encrypted, notes_encrypted
                    FROM important_dates
                    WHERE user_id = %s AND person_id = %s
                    ORDER BY date_value
                """, (str(user_id), person_id))
                rows = cur.fetchall()
            
            result_parts = []
            
            # Include birthday from persons table if available
            if person_row['date_of_birth']:
                result_parts.append(f"- **Birthday**: {person_row['date_of_birth'].strftime('%B %d')}")
            
            for row in rows:
                try:
                    title = encryption.decrypt_for_user(
                        user_dek, bytes(row['title_encrypted'])
                    )
                    date_str = row['date_value'].strftime('%B %d')
                    recurring = " (recurring)" if row['is_recurring'] else ""
                    result_parts.append(f"- **{title}** ({row['date_type']}) - {date_str}{recurring}")
                except Exception as e:
                    logger.error(f"Failed to decrypt date {row['id']}: {e}")
            
            if not result_parts:
                return f"No important dates recorded for {person_name}."
            
            result = f"**Important dates for {person_name}:**\n" + "\n".join(result_parts)
            
            # Mask PII in dates (titles may contain sensitive info)
            return mask_pii(result)
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting person dates: {e}")
        return f"Error retrieving dates: {str(e)}"


@tool
def save_important_date_for_person(
    person_id: str,
    title: str,
    date_value: str,
    date_type: str = "birthday",
    is_recurring: bool = True,
    notes: Optional[str] = None
) -> str:
    """
    Save an important date for a specific person.
    
    Use this to record birthdays, anniversaries, or other important dates
    for someone in the user's network.
    
    Args:
        person_id: The UUID of the person (from find_person_by_relationship)
        title: Title of the date (e.g., "Wife's Birthday", "Wedding Anniversary")
        date_value: Date in YYYY-MM-DD format (e.g., "1990-01-15")
        date_type: Type of date - 'birthday', 'anniversary', 'holiday', 'custom'
        is_recurring: Whether this date repeats annually (default True)
        notes: Optional notes (e.g., "Likes surprise parties")
    
    Returns:
        Confirmation message
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            # Verify person exists and belongs to user
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT first_name, last_name
                    FROM persons
                    WHERE id = %s AND owner_user_id = %s
                """, (person_id, str(user_id)))
                person_row = cur.fetchone()
            
            if not person_row:
                return f"Person with ID {person_id} not found in your network."
            
            person_name = f"{person_row['first_name'] or ''} {person_row['last_name'] or ''}".strip() or "This person"
            
            encryption = get_encryption()
            title_encrypted = encryption.encrypt_for_user(user_dek, title)
            notes_encrypted = encryption.encrypt_for_user(user_dek, notes) if notes else None
            
            # Parse date
            from datetime import datetime
            try:
                parsed_date = datetime.strptime(date_value, "%Y-%m-%d").date()
            except ValueError:
                return f"Invalid date format. Please use YYYY-MM-DD (e.g., '1990-01-15')"
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO important_dates (
                        user_id, person_id, date_type, date_value, is_recurring,
                        title_encrypted, notes_encrypted, remind_days_before
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 7)
                """, (str(user_id), person_id, date_type, parsed_date, is_recurring,
                      title_encrypted, notes_encrypted))
                conn.commit()
            
            return f"✓ Saved: {title} for {person_name} on {parsed_date.strftime('%B %d')}"
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error saving important date: {e}")
        return f"Error saving date: {str(e)}"


@tool
def create_person_in_network(
    first_name: str,
    relationship_to_user: str,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Create a new person in the user's network with their relationship.
    
    Use this when the user mentions someone who isn't already in their contacts.
    For example: "my brother Farhan" → create person Farhan with relationship "brother"
    
    Args:
        first_name: Person's first name
        relationship_to_user: How they relate to the user (brother, wife, friend, colleague, etc.)
        last_name: Optional last name
        email: Optional email address
        phone: Optional phone number
        notes: Optional notes about the person
    
    Returns:
        Person ID and confirmation message
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            # First, find the core user's person_id
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id as person_id
                    FROM persons
                    WHERE owner_user_id = %s AND is_core_user = true
                    LIMIT 1
                """, (str(user_id),))
                core_user_row = cur.fetchone()
            
            if not core_user_row:
                return "Error: Could not find core user profile."
            
            core_person_id = core_user_row['person_id']
            
            # Build full name for the 'name' column (required)
            full_name = f"{first_name} {last_name}".strip() if last_name else first_name
            
            # Validate: at least one contact method is required
            if not email and not phone:
                return f"I need at least an email or phone number to add {first_name} to your contacts. Could you provide one?"
            
            # Create the new person
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO persons (
                        owner_user_id, name, first_name, last_name, 
                        personal_email, personal_cell, is_core_user
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, false)
                    RETURNING id
                """, (str(user_id), full_name, first_name, last_name, email, phone))
                person_row = cur.fetchone()
                new_person_id = person_row['id']
            
            # Determine relationship category (valid enum values: family, friends, work, acquaintance)
            rel_lower = relationship_to_user.lower()
            if rel_lower in ('wife', 'husband', 'spouse', 'partner', 'mother', 'father', 
                            'sister', 'brother', 'son', 'daughter', 'cousin', 'aunt', 
                            'uncle', 'grandmother', 'grandfather', 'niece', 'nephew'):
                category = 'family'
            elif rel_lower in ('friend', 'best friend', 'close friend', 'friends'):
                category = 'friends'  # Note: enum value is 'friends' not 'friend'
            elif rel_lower in ('colleague', 'coworker', 'manager', 'boss', 'teammate', 
                              'employee', 'client', 'vendor'):
                category = 'work'  # Note: enum value is 'work' not 'professional'
            else:
                category = 'acquaintance'  # Note: enum value is 'acquaintance' not 'other'
            
            # Determine the reverse role (what the core user is to this person)
            reverse_roles = {
                'wife': 'husband', 'husband': 'wife', 'spouse': 'spouse',
                'mother': 'child', 'father': 'child', 'son': 'parent', 'daughter': 'parent',
                'brother': 'sibling', 'sister': 'sibling',
                'friend': 'friend', 'best friend': 'best friend',
                'colleague': 'colleague', 'coworker': 'coworker',
                'manager': 'direct report', 'boss': 'employee',
                'cousin': 'cousin', 'aunt': 'niece/nephew', 'uncle': 'niece/nephew',
            }
            from_role = reverse_roles.get(rel_lower, 'contact')
            
            # Create the relationship
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO relationships (
                        owner_user_id, from_person_id, to_person_id,
                        category, from_role, to_role, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, true)
                """, (str(user_id), str(core_person_id), str(new_person_id),
                      category, from_role, relationship_to_user))
            
            conn.commit()
            
            full_name = f"{first_name} {last_name}".strip() if last_name else first_name
            return f"✓ Added {full_name} as your {relationship_to_user} (ID: {new_person_id})"
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error creating person: {e}")
        return f"Error creating person: {str(e)}"


@tool
def add_relationship_between_persons(
    person_a_id: str,
    person_b_id: str,
    a_to_b_relationship: str,
) -> str:
    """
    Add a relationship between two people in the network.
    
    Use this when the user describes how two contacts relate to each other.
    For example: "Farhan is Anish's best friend" → person_a=Anish, person_b=Farhan, relationship="best friend"
    
    Args:
        person_a_id: UUID of the first person
        person_b_id: UUID of the second person
        a_to_b_relationship: How person_a relates to person_b (e.g., "best friend", "brother")
    
    Returns:
        Confirmation message
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            # Verify both persons exist and belong to user
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, first_name FROM persons
                    WHERE id IN (%s, %s) AND owner_user_id = %s
                """, (person_a_id, person_b_id, str(user_id)))
                rows = cur.fetchall()
            
            if len(rows) < 2:
                return "Error: One or both persons not found in your network."
            
            # Determine category (valid enum values: family, friends, work, acquaintance)
            rel_lower = a_to_b_relationship.lower()
            if rel_lower in ('wife', 'husband', 'spouse', 'partner', 'mother', 'father',
                            'sister', 'brother', 'son', 'daughter', 'cousin'):
                category = 'family'
            elif rel_lower in ('friend', 'best friend', 'close friend', 'friends'):
                category = 'friends'  # Note: enum value is 'friends' not 'friend'
            elif rel_lower in ('colleague', 'coworker', 'manager', 'boss'):
                category = 'work'  # Note: enum value is 'work' not 'professional'
            else:
                category = 'acquaintance'  # Note: enum value is 'acquaintance' not 'other'
            
            # Create relationship
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO relationships (
                        owner_user_id, from_person_id, to_person_id,
                        category, from_role, to_role, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, true)
                    ON CONFLICT DO NOTHING
                """, (str(user_id), person_a_id, person_b_id,
                      category, a_to_b_relationship, a_to_b_relationship))
            
            conn.commit()
            return f"✓ Added relationship: {a_to_b_relationship}"
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error adding relationship: {e}")
        return f"Error adding relationship: {str(e)}"


# Export tools for the agent
# ============================================================================
# Person Notes Tools
# ============================================================================

@tool
def save_person_note(
    person_id: str,
    text: str,
    category: str = "general",
    related_date: str = None,
    is_time_sensitive: bool = False,
    context: str = None
) -> str:
    """
    Save a note about a person in the user's network.
    
    Use this to record any information about someone that doesn't fit into
    interests or important dates. For example:
    - "Coming to Toronto next week" (travel, with date)
    - "Prefers window seats" (preference)
    - "Owes me $50 from lunch" (reminder)
    
    Args:
        person_id: The UUID of the person
        text: The note content
        category: One of: general, travel, preference, event, reminder, observation, other
        related_date: Optional date in YYYY-MM-DD format (for time-sensitive notes)
        is_time_sensitive: If True, note will auto-archive after related_date passes
        context: Optional additional context
    
    Returns:
        Confirmation message
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    valid_categories = ['general', 'travel', 'preference', 'event', 'reminder', 'observation', 'other']
    if category not in valid_categories:
        category = 'other'
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            # Verify person exists
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT first_name, last_name
                    FROM persons
                    WHERE id = %s AND owner_user_id = %s
                """, (person_id, str(user_id)))
                person_row = cur.fetchone()
            
            if not person_row:
                return f"Person with ID {person_id} not found in your network."
            
            person_name = f"{person_row['first_name'] or ''} {person_row['last_name'] or ''}".strip() or "This person"
            
            import json
            encryption = get_encryption()
            content = {"text": text, "context": context}
            content_encrypted = encryption.encrypt_for_user(user_dek, json.dumps(content))
            
            # Parse date if provided
            date_value = None
            if related_date:
                try:
                    from datetime import datetime
                    date_value = datetime.strptime(related_date, "%Y-%m-%d").date()
                except ValueError:
                    pass  # Invalid date format, skip
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO person_notes (
                        user_id, person_id, content_encrypted, category,
                        related_date, is_time_sensitive, source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'conversation')
                """, (
                    str(user_id), person_id, content_encrypted, category,
                    date_value, is_time_sensitive
                ))
                conn.commit()
            
            date_info = f" (for {related_date})" if related_date else ""
            return f"✓ Noted about {person_name}: {text}{date_info}"
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error saving person note: {e}")
        return f"Error saving note: {str(e)}"


@tool
def get_person_notes(person_id: str, include_expired: bool = False) -> str:
    """
    Get notes about a specific person.
    
    Use this to retrieve any notes or observations about someone.
    By default, expired time-sensitive notes are hidden.
    
    Args:
        person_id: The UUID of the person
        include_expired: If True, also show expired notes
    
    Returns:
        List of notes about the person
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            # Get person's name
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT first_name, last_name
                    FROM persons
                    WHERE id = %s AND owner_user_id = %s
                """, (person_id, str(user_id)))
                person_row = cur.fetchone()
            
            if not person_row:
                return f"Person with ID {person_id} not found in your network."
            
            person_name = f"{person_row['first_name'] or ''} {person_row['last_name'] or ''}".strip() or "This person"
            
            # First, expire old time-sensitive notes
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE person_notes
                    SET status = 'expired', updated_at = NOW()
                    WHERE person_id = %s
                      AND user_id = %s
                      AND status = 'active'
                      AND is_time_sensitive = TRUE
                      AND related_date < CURRENT_DATE
                """, (person_id, str(user_id)))
                conn.commit()
            
            # Build query based on include_expired
            status_filter = "status IN ('active', 'expired')" if include_expired else "status = 'active'"
            
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, content_encrypted, category, related_date, 
                           is_time_sensitive, status, created_at
                    FROM person_notes
                    WHERE person_id = %s AND user_id = %s AND {status_filter}
                    ORDER BY 
                        CASE WHEN related_date IS NOT NULL AND related_date >= CURRENT_DATE 
                             THEN 0 ELSE 1 END,
                        related_date ASC NULLS LAST,
                        created_at DESC
                    LIMIT 20
                """, (person_id, str(user_id)))
                rows = cur.fetchall()
            
            if not rows:
                return f"No notes found for {person_name}."
            
            import json
            encryption = get_encryption()
            
            result_lines = [f"**Notes about {person_name}:**\n"]
            
            for row in rows:
                try:
                    content_json = encryption.decrypt_for_user(user_dek, bytes(row['content_encrypted']))
                    content = json.loads(content_json)
                    text = content.get('text', '')
                    context = content.get('context', '')
                    
                    category = row['category']
                    related_date = row['related_date']
                    status = row['status']
                    
                    note_line = f"- [{category}] {text}"
                    if related_date:
                        note_line += f" (Date: {related_date})"
                    if status == 'expired':
                        note_line += " [EXPIRED]"
                    if context:
                        note_line += f"\n  Context: {context}"
                    
                    result_lines.append(note_line)
                    
                except Exception as e:
                    logger.error(f"Error decrypting note: {e}")
                    continue
            
            # Mask PII in notes (may contain sensitive info)
            return mask_pii('\n'.join(result_lines))
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting person notes: {e}")
        return f"Error getting notes: {str(e)}"


@tool
def get_upcoming_person_notes(days_ahead: int = 7) -> str:
    """
    Get notes with upcoming dates across all people in your network.
    
    Use this to see what's coming up - visits, events, reminders that have dates.
    Notes are surfaced when their related_date is within the specified days.
    
    Args:
        days_ahead: Number of days to look ahead (default 7)
    
    Returns:
        List of upcoming notes with dates
    """
    user_id = get_memory_user()
    if not user_id:
        return "Error: No user context available"
    
    try:
        conn = _get_sync_connection()
        try:
            user_dek = _get_user_dek_sync(conn, user_id)
            if not user_dek:
                return "Error: Could not load user encryption key"
            
            # First, expire old notes
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE person_notes
                    SET status = 'expired', updated_at = NOW()
                    WHERE user_id = %s
                      AND status = 'active'
                      AND is_time_sensitive = TRUE
                      AND related_date < CURRENT_DATE
                """, (str(user_id),))
                conn.commit()
            
            # Get upcoming notes
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT n.id, n.content_encrypted, n.category, n.related_date,
                           p.first_name, p.last_name, p.id as person_id
                    FROM person_notes n
                    JOIN persons p ON n.person_id = p.id
                    WHERE n.user_id = %s
                      AND n.status = 'active'
                      AND n.related_date IS NOT NULL
                      AND n.related_date >= CURRENT_DATE
                      AND n.related_date <= CURRENT_DATE + %s
                    ORDER BY n.related_date ASC
                    LIMIT 20
                """, (str(user_id), days_ahead))
                rows = cur.fetchall()
            
            if not rows:
                return f"No upcoming notes in the next {days_ahead} days."
            
            import json
            from datetime import date
            encryption = get_encryption()
            
            result_lines = [f"**Upcoming notes (next {days_ahead} days):**\n"]
            
            for row in rows:
                try:
                    content_json = encryption.decrypt_for_user(user_dek, bytes(row['content_encrypted']))
                    content = json.loads(content_json)
                    text = content.get('text', '')
                    
                    person_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
                    related_date = row['related_date']
                    category = row['category']
                    
                    # Calculate days until
                    if isinstance(related_date, date):
                        days_until = (related_date - date.today()).days
                        if days_until == 0:
                            time_str = "TODAY"
                        elif days_until == 1:
                            time_str = "Tomorrow"
                        else:
                            time_str = f"In {days_until} days ({related_date})"
                    else:
                        time_str = str(related_date)
                    
                    result_lines.append(f"- **{person_name}**: {text}")
                    result_lines.append(f"  📅 {time_str} | Category: {category}")
                    
                except Exception as e:
                    logger.error(f"Error decrypting note: {e}")
                    continue
            
            # Mask PII in notes (may contain sensitive info)
            return mask_pii('\n'.join(result_lines))
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error getting upcoming notes: {e}")
        return f"Error: {str(e)}"


MEMORY_TOOLS = [
    # User memory tools
    get_user_memories,
    save_user_memory,
    get_user_interests,
    save_user_interest,
    get_upcoming_important_dates,
    # Relationship & person tools
    find_person_by_relationship,
    get_person_interests,
    save_person_interest,
    get_important_dates_for_person,
    save_important_date_for_person,
    # Person notes tools
    save_person_note,
    get_person_notes,
    get_upcoming_person_notes,
    # Person management tools
    create_person_in_network,
    add_relationship_between_persons,
]


# ============================================================================
# User Context Builder (Async version for use in chat routes)
# ============================================================================

async def build_user_context(user_id: UUID) -> str:
    """
    Build a context string with key user information for the agent.
    
    This is used to augment the system prompt with personalized info.
    Uses async DB access since it's called from the chat route.
    
    Args:
        user_id: The user's UUID
    
    Returns:
        Context string with memories and interests summary
    """
    from ..db import get_db_pool
    from ..db.user_data_repository import (
        InterestsRepository,
        ImportantDatesRepository,
        MemoriesRepository,
    )
    
    # Always include current date/time first (LLMs are bad at date arithmetic)
    now = datetime.now()
    context_parts = [
        f"**Current date:** {now.strftime('%A, %B %d, %Y')} at {now.strftime('%I:%M %p')}"
    ]
    
    pool = await get_db_pool()
    if not pool:
        # Return at least the current date even without DB
        return "\n\n--- USER CONTEXT ---\n" + "\n".join(context_parts) + "\n--- END USER CONTEXT ---\n"
    
    try:
        # Get high-confidence memories
        memories_repo = MemoriesRepository(pool)
        memories = await memories_repo.get_memories(user_id=user_id)
        
        if memories:
            key_memories = memories[:10]  # Limit to top 10
            memory_str = "**Key things to remember about this user:**\n"
            for m in key_memories:
                memory_str += f"- {m['fact_key']}: {m['fact_value']}\n"
            context_parts.append(memory_str)
        
        # Get top interests
        interests_repo = InterestsRepository(pool)
        interests = await interests_repo.get_interests(user_id=user_id, min_level=60)
        
        if interests:
            top_interests = interests[:5]  # Top 5 interests
            interest_names = [i.get('name', 'Unknown') for i in top_interests]
            context_parts.append(f"**User interests:** {', '.join(interest_names)}")
        
        # Get upcoming dates (next 7 days)
        dates_repo = ImportantDatesRepository(pool)
        dates = await dates_repo.get_upcoming_dates(user_id=user_id, days_ahead=7)
        
        if dates:
            dates_str = "**Upcoming important dates (next 7 days):**\n"
            for d in dates[:3]:  # Max 3 dates
                dates_str += f"- {d['title']} on {d['date_value'].strftime('%B %d')}\n"
            context_parts.append(dates_str)
        
    except Exception as e:
        logger.error(f"Error building user context: {e}")
    
    if context_parts:
        return "\n\n--- USER CONTEXT ---\n" + "\n".join(context_parts) + "\n--- END USER CONTEXT ---\n"
    
    return ""

