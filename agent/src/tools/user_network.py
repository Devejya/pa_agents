"""
User Network Tools for LangChain Agent.

These tools allow the agent to query the User Network service
to get information about the user's contacts and relationships.
"""

import asyncio
import os
from typing import Optional

from langchain_core.tools import tool

from ..graph.client import UserNetworkClient, UserNetworkClientError


def _get_client() -> UserNetworkClient:
    """Get a configured UserNetworkClient instance."""
    base_url = os.getenv("USER_NETWORK_URL", "http://localhost:8001")
    api_key = os.getenv("USER_NETWORK_API_KEY", "")
    return UserNetworkClient(base_url=base_url, api_key=api_key)


def _run_async(coro):
    """Run an async coroutine in a sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ============================================================================
# Contact Lookup Tools
# ============================================================================

@tool
def get_contact_by_relationship(relationship: str) -> str:
    """
    Get contact information for someone based on their relationship to the user.
    
    Use this when the user asks for contact info using a relationship term like
    "my sister", "my mother", "my manager", etc.
    
    Args:
        relationship: The relationship type (e.g., "sister", "mother", "manager", "brother")
        
    Returns:
        Contact information including phone numbers and emails.
        
    Examples:
        - "What is my sister's phone number?" → relationship="sister"
        - "Get my mom's email" → relationship="mother"
        - "Call my manager" → relationship="manager"
    """
    async def _fetch():
        client = _get_client()
        try:
            contacts = await client.get_contact_by_role(relationship)
            if not contacts:
                return f"No {relationship} found in your contacts."
            
            results = []
            for contact in contacts:
                info = [f"**{contact['name']}** ({contact['relationship']})"]
                if contact.get('personal_cell'):
                    info.append(f"  - Personal cell: {contact['personal_cell']}")
                if contact.get('work_cell'):
                    info.append(f"  - Work cell: {contact['work_cell']}")
                if contact.get('personal_email'):
                    info.append(f"  - Personal email: {contact['personal_email']}")
                if contact.get('work_email'):
                    info.append(f"  - Work email: {contact['work_email']}")
                results.append("\n".join(info))
            
            return "\n\n".join(results)
        except UserNetworkClientError as e:
            return f"Error looking up {relationship}: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_fetch())


@tool
def get_contact_by_name(name: str) -> str:
    """
    Get contact information for someone by their name.
    
    Use this when the user asks for contact info using a person's name.
    
    Args:
        name: The person's name or nickname (e.g., "Alice", "John", "Mom")
        
    Returns:
        Contact information including phone numbers and emails.
        
    Examples:
        - "What is Alice's phone number?" → name="Alice"
        - "Get John's email" → name="John"
    """
    async def _fetch():
        client = _get_client()
        try:
            contacts = await client.get_contact_by_name(name)
            if not contacts:
                return f"No contact named '{name}' found."
            
            results = []
            for contact in contacts:
                rel = f" ({contact['relationship']})" if contact.get('relationship') else ""
                info = [f"**{contact['name']}**{rel}"]
                if contact.get('personal_cell'):
                    info.append(f"  - Personal cell: {contact['personal_cell']}")
                if contact.get('work_cell'):
                    info.append(f"  - Work cell: {contact['work_cell']}")
                if contact.get('personal_email'):
                    info.append(f"  - Personal email: {contact['personal_email']}")
                if contact.get('work_email'):
                    info.append(f"  - Work email: {contact['work_email']}")
                results.append("\n".join(info))
            
            return "\n\n".join(results)
        except UserNetworkClientError as e:
            return f"Error looking up '{name}': {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_fetch())


# ============================================================================
# Interest/Preference Tools
# ============================================================================

@tool
def get_interests_by_relationship(relationship: str) -> str:
    """
    Get interests and preferences for someone based on their relationship to the user.
    
    Use this when the user needs to know what someone likes, for gift ideas,
    conversation topics, or activity suggestions.
    
    Args:
        relationship: The relationship type (e.g., "sister", "mother", "friend")
        
    Returns:
        The person's interests, hobbies, and preferences.
        
    Examples:
        - "What does my mom like?" → relationship="mother"
        - "What are my sister's hobbies?" → relationship="sister"
        - "What gift should I get for my brother?" → relationship="brother"
    """
    async def _fetch():
        client = _get_client()
        try:
            results = await client.get_interests_by_role(relationship)
            if not results:
                return f"No {relationship} found in your contacts."
            
            output = []
            for person in results:
                info = [f"**{person['name']}** ({person['relationship']})"]
                
                if person.get('interests'):
                    info.append("  Interests:")
                    for interest in sorted(person['interests'], key=lambda x: -x.get('level', 0)):
                        level = interest.get('level', 0)
                        info.append(f"    - {interest['name']} ({interest['type']}) - Level: {level}/100")
                else:
                    info.append("  No interests recorded.")
                
                if person.get('expertise'):
                    info.append(f"  Expertise: {person['expertise']}")
                if person.get('city') and person.get('country'):
                    info.append(f"  Location: {person['city']}, {person['country']}")
                
                output.append("\n".join(info))
            
            return "\n\n".join(output)
        except UserNetworkClientError as e:
            return f"Error looking up {relationship}'s interests: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_fetch())


@tool
def get_interests_by_name(name: str) -> str:
    """
    Get interests and preferences for someone by their name.
    
    Use this when the user needs to know what a specific person likes.
    
    Args:
        name: The person's name or nickname
        
    Returns:
        The person's interests, hobbies, and preferences.
        
    Examples:
        - "What does Rajesh like?" → name="Rajesh"
        - "What are Priya's hobbies?" → name="Priya"
    """
    async def _fetch():
        client = _get_client()
        try:
            results = await client.get_interests_by_name(name)
            if not results:
                return f"No contact named '{name}' found."
            
            output = []
            for person in results:
                rel = f" ({person['relationship']})" if person.get('relationship') else ""
                info = [f"**{person['name']}**{rel}"]
                
                if person.get('interests'):
                    info.append("  Interests:")
                    for interest in sorted(person['interests'], key=lambda x: -x.get('level', 0)):
                        level = interest.get('level', 0)
                        info.append(f"    - {interest['name']} ({interest['type']}) - Level: {level}/100")
                else:
                    info.append("  No interests recorded.")
                
                if person.get('expertise'):
                    info.append(f"  Expertise: {person['expertise']}")
                if person.get('city') and person.get('country'):
                    info.append(f"  Location: {person['city']}, {person['country']}")
                
                output.append("\n".join(info))
            
            return "\n\n".join(output)
        except UserNetworkClientError as e:
            return f"Error looking up '{name}': {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_fetch())


# ============================================================================
# Relationship Traversal Tool
# ============================================================================

@tool
def find_related_person(relationship_path: str) -> str:
    """
    Find a person by traversing relationships from the user.
    
    Use this for complex relationship queries like "my sister's husband"
    or "my brother's wife's mother".
    
    Args:
        relationship_path: Comma-separated path of relationships 
                          (e.g., "sister,husband" for "my sister's husband")
        
    Returns:
        Information about the person at the end of the relationship path.
        
    Examples:
        - "Who is my sister's husband?" → relationship_path="sister,husband"
        - "What is my brother's wife's phone number?" → relationship_path="brother,wife"
        - "My cousin's mother" → relationship_path="cousin,mother"
    """
    async def _fetch():
        client = _get_client()
        try:
            path = [r.strip() for r in relationship_path.split(",")]
            results = await client.traverse(path)
            
            if not results:
                path_str = "'s ".join(path)
                return f"Could not find your {path_str}."
            
            output = []
            for person in results:
                info = [f"**{person['name']}**"]
                info.append(f"  Relationship path: {' → '.join(path)}")
                
                if person.get('personal_cell'):
                    info.append(f"  Personal cell: {person['personal_cell']}")
                if person.get('work_cell'):
                    info.append(f"  Work cell: {person['work_cell']}")
                if person.get('personal_email'):
                    info.append(f"  Personal email: {person['personal_email']}")
                if person.get('work_email'):
                    info.append(f"  Work email: {person['work_email']}")
                
                if person.get('interests'):
                    info.append("  Interests:")
                    for interest in person['interests'][:5]:  # Top 5
                        info.append(f"    - {interest.get('name', 'Unknown')}")
                
                if person.get('city') and person.get('country'):
                    info.append(f"  Location: {person['city']}, {person['country']}")
                
                output.append("\n".join(info))
            
            return "\n\n".join(output)
        except UserNetworkClientError as e:
            return f"Error traversing relationships: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_fetch())


# ============================================================================
# Communication History Tool
# ============================================================================

@tool
def get_most_contacted_people(limit: int = 5) -> str:
    """
    Get the people the user has contacted most recently.
    
    Use this when the user asks about their recent communications
    or who they've been in touch with.
    
    Args:
        limit: Maximum number of people to return (default 5)
        
    Returns:
        List of most contacted people with communication stats.
        
    Examples:
        - "Who have I talked to most this week?"
        - "My recent contacts"
    """
    async def _fetch():
        client = _get_client()
        try:
            results = await client.get_most_contacted(limit)
            if not results:
                return "No recent communication data available."
            
            output = ["**Most Contacted This Week:**\n"]
            for i, person in enumerate(results, 1):
                rel = f" ({person['relationship']})" if person.get('relationship') else ""
                stats = []
                if person.get('texts_this_week', 0) > 0:
                    stats.append(f"{person['texts_this_week']} texts")
                if person.get('calls_this_week', 0) > 0:
                    stats.append(f"{person['calls_this_week']} calls")
                if person.get('meets_this_week', 0) > 0:
                    stats.append(f"{person['meets_this_week']} meetings")
                
                stats_str = ", ".join(stats) if stats else "No recent activity"
                output.append(f"{i}. **{person['name']}**{rel} - {stats_str}")
            
            return "\n".join(output)
        except UserNetworkClientError as e:
            return f"Error getting contact history: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_fetch())


# ============================================================================
# CREATE/UPDATE Person Tools
# ============================================================================

@tool
def add_new_contact(
    name: str,
    relationship_to_user: Optional[str] = None,
    personal_cell: Optional[str] = None,
    work_cell: Optional[str] = None,
    personal_email: Optional[str] = None,
    work_email: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Add a new person to the user's contact network.
    
    Use this when:
    - The user mentions a new person who should be saved
    - The user explicitly asks to add someone
    - The agent discovers a new contact from emails/messages
    
    IMPORTANT: At least one contact method (phone or email) is required.
    If missing, ask the user before calling this tool.
    
    Args:
        name: Full name of the person (REQUIRED)
        relationship_to_user: How they relate to the user (e.g., "daughter", "manager", "friend")
        personal_cell: Personal phone number (at least one contact method required)
        work_cell: Work phone number (at least one contact method required)
        personal_email: Personal email address (at least one contact method required)
        work_email: Work email address (at least one contact method required)
        company: Company/organization they work for
        title: Job title
        city: City they live in
        country: Country they live in
        notes: Any additional notes about the person
        
    Returns:
        Confirmation message with the created contact details, OR
        a message asking for missing required information.
        
    Examples:
        - User: "Add my daughter Maya, her cell is 555-1234"
          → add_new_contact(name="Maya", relationship_to_user="daughter", personal_cell="555-1234")
        - Agent discovers "Bob" is user's manager from email
          → add_new_contact(name="Bob", relationship_to_user="manager", work_email="bob@company.com")
    """
    # ===== VALIDATION: Check required fields before API call =====
    missing_fields = []
    
    # Name is required
    if not name or not name.strip():
        missing_fields.append("name")
    
    # At least one contact method required
    has_contact = any([personal_cell, work_cell, personal_email, work_email])
    if not has_contact:
        return (
            f"⚠️ To add **{name or 'this contact'}**, I need at least one way to reach them.\n\n"
            f"Please provide one of the following:\n"
            f"  • Phone number (personal or work)\n"
            f"  • Email address (personal or work)\n\n"
            f"Example: \"Their email is {name.lower().replace(' ', '.')}@example.com\" or \"Their phone is 555-1234\""
        )
    
    # Title requires company
    if title and not company:
        return (
            f"⚠️ You mentioned **{name}**'s title is \"{title}\", but I need to know their company too.\n\n"
            f"What company does {name} work for?"
        )
    
    async def _create():
        client = _get_client()
        try:
            # Build person data
            person_data = {"name": name.strip()}
            
            if personal_cell:
                person_data["personal_cell"] = personal_cell
            if work_cell:
                person_data["work_cell"] = work_cell
            if personal_email:
                person_data["personal_email"] = personal_email
            if work_email:
                person_data["work_email"] = work_email
            if company:
                person_data["company"] = company
            if title:
                person_data["latest_title"] = title
            if city:
                person_data["city"] = city
            if country:
                person_data["country"] = country
            if notes:
                person_data["notes"] = notes
            
            # Create the person
            result = await client.create_person(person_data)
            person_id = result.get("id")
            
            # If relationship specified, get core user and create relationship
            if relationship_to_user and person_id:
                core_user = await client.get_core_user()
                if core_user:
                    rel_data = {
                        "from_person_id": str(core_user["id"]),
                        "to_person_id": str(person_id),
                        "category": _categorize_relationship(relationship_to_user),
                        "from_role": "self",
                        "to_role": relationship_to_user.lower(),
                    }
                    await client.create_relationship(rel_data)
            
            # Format response
            response = [f"✅ Added **{name}** to your contacts."]
            if relationship_to_user:
                response.append(f"   Relationship: {relationship_to_user}")
            if personal_cell or work_cell:
                response.append(f"   Phone: {personal_cell or work_cell}")
            if personal_email or work_email:
                response.append(f"   Email: {personal_email or work_email}")
            
            return "\n".join(response)
            
        except UserNetworkClientError as e:
            return f"❌ Failed to add contact: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_create())


@tool
def update_contact_info(
    name: str,
    personal_cell: Optional[str] = None,
    work_cell: Optional[str] = None,
    personal_email: Optional[str] = None,
    work_email: Optional[str] = None,
    company: Optional[str] = None,
    title: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Update information for an existing contact.
    
    Use this when:
    - The user provides updated info about someone
    - The user corrects information about a contact
    - New information is discovered about an existing contact
    
    Args:
        name: Name of the person to update (used to find them)
        personal_cell: New personal phone number
        work_cell: New work phone number
        personal_email: New personal email
        work_email: New work email
        company: New company
        title: New job title
        city: New city
        country: New country
        notes: Additional notes to add
        
    Returns:
        Confirmation of the update.
        
    Examples:
        - "Update Maya's phone to 555-9999"
          → update_contact_info(name="Maya", personal_cell="555-9999")
        - "Bob now works at Acme Corp as CTO"
          → update_contact_info(name="Bob", company="Acme Corp", title="CTO")
    """
    async def _update():
        client = _get_client()
        try:
            # Find the person by name
            matches = await client.find_person_by_name(name)
            if not matches:
                return f"❌ No contact named '{name}' found."
            
            if len(matches) > 1:
                names = ", ".join([m["name"] for m in matches])
                return f"⚠️ Multiple contacts found: {names}. Please be more specific."
            
            person = matches[0]
            person_id = person["id"]
            
            # Build update data (only include provided fields)
            update_data = {}
            if personal_cell is not None:
                update_data["personal_cell"] = personal_cell
            if work_cell is not None:
                update_data["work_cell"] = work_cell
            if personal_email is not None:
                update_data["personal_email"] = personal_email
            if work_email is not None:
                update_data["work_email"] = work_email
            if company is not None:
                update_data["company"] = company
            if title is not None:
                update_data["latest_title"] = title
            if city is not None:
                update_data["city"] = city
            if country is not None:
                update_data["country"] = country
            if notes is not None:
                # Append to existing notes
                existing_notes = person.get("notes", "")
                update_data["notes"] = f"{existing_notes}\n{notes}".strip() if existing_notes else notes
            
            if not update_data:
                return "⚠️ No updates provided."
            
            # Perform update
            await client.update_person(person_id, update_data)
            
            # Format response
            updates = []
            if personal_cell:
                updates.append(f"personal cell → {personal_cell}")
            if work_cell:
                updates.append(f"work cell → {work_cell}")
            if personal_email:
                updates.append(f"personal email → {personal_email}")
            if work_email:
                updates.append(f"work email → {work_email}")
            if company:
                updates.append(f"company → {company}")
            if title:
                updates.append(f"title → {title}")
            if city:
                updates.append(f"city → {city}")
            if country:
                updates.append(f"country → {country}")
            if notes:
                updates.append("notes updated")
            
            return f"✅ Updated **{person['name']}**: {', '.join(updates)}"
            
        except UserNetworkClientError as e:
            return f"❌ Failed to update contact: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_update())


@tool
def add_relationship(
    person_name: str,
    related_to_name: str,
    relationship_type: str,
    person_role: str,
    related_to_role: str,
) -> str:
    """
    Add a relationship between two people in the network.
    
    Use this when:
    - Discovering how two contacts are related
    - The user mentions a relationship between people
    
    IMPORTANT: All fields are required. If any are missing, ask the user.
    
    Args:
        person_name: Name of the first person (REQUIRED)
        related_to_name: Name of the second person (REQUIRED)
        relationship_type: Type of relationship - must be one of: family, work, friends, romantic, acquaintance (REQUIRED)
        person_role: First person's role in relationship (e.g., "husband", "manager", "friend") (REQUIRED)
        related_to_role: Second person's role (e.g., "wife", "direct_report", "friend") (REQUIRED)
        
    Returns:
        Confirmation of the relationship created, OR
        a message asking for missing required information.
        
    Examples:
        - "Emma is Carol's daughter"
          → add_relationship(person_name="Emma", related_to_name="Carol", 
                            relationship_type="family", person_role="daughter", related_to_role="mother")
        - "Bob manages Alice"
          → add_relationship(person_name="Bob", related_to_name="Alice",
                            relationship_type="work", person_role="manager", related_to_role="direct_report")
    """
    # ===== VALIDATION: Check required fields before API call =====
    missing = []
    if not person_name or not person_name.strip():
        missing.append("first person's name")
    if not related_to_name or not related_to_name.strip():
        missing.append("second person's name")
    if not relationship_type or not relationship_type.strip():
        missing.append("relationship type (family, work, friends, romantic, or acquaintance)")
    if not person_role or not person_role.strip():
        missing.append(f"what {person_name or 'the first person'} is to {related_to_name or 'the second person'}")
    if not related_to_role or not related_to_role.strip():
        missing.append(f"what {related_to_name or 'the second person'} is to {person_name or 'the first person'}")
    
    if missing:
        return (
            f"⚠️ To add this relationship, I need more information:\n\n"
            f"Missing: {', '.join(missing)}\n\n"
            f"Please provide the missing details."
        )
    
    # Validate relationship_type
    valid_types = ["family", "work", "friends", "romantic", "acquaintance"]
    if relationship_type.lower() not in valid_types:
        return (
            f"⚠️ Invalid relationship type: \"{relationship_type}\"\n\n"
            f"Please use one of: {', '.join(valid_types)}"
        )
    
    async def _create_rel():
        client = _get_client()
        try:
            # Find both people
            person_matches = await client.find_person_by_name(person_name)
            related_matches = await client.find_person_by_name(related_to_name)
            
            if not person_matches:
                return f"❌ No contact named '{person_name}' found."
            if not related_matches:
                return f"❌ No contact named '{related_to_name}' found."
            
            person = person_matches[0]
            related_to = related_matches[0]
            
            # Create relationship
            rel_data = {
                "from_person_id": str(person["id"]),
                "to_person_id": str(related_to["id"]),
                "category": relationship_type.lower(),
                "from_role": person_role.lower(),
                "to_role": related_to_role.lower(),
            }
            
            await client.create_relationship(rel_data)
            
            return f"✅ Added relationship: **{person['name']}** ({person_role}) ↔ **{related_to['name']}** ({related_to_role})"
            
        except UserNetworkClientError as e:
            return f"❌ Failed to add relationship: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_create_rel())


@tool  
def add_interest_to_contact(
    name: str,
    interest_name: str,
    interest_type: str = "other",
    level: int = 50,
) -> str:
    """
    Add an interest or hobby to a contact.
    
    Use this when:
    - Learning what someone likes or is interested in
    - The user mentions someone's hobbies or preferences
    - Useful for gift suggestions later
    
    Args:
        name: Name of the person (REQUIRED)
        interest_name: The interest/hobby (e.g., "skiing", "cooking", "jazz music") (REQUIRED)
        interest_type: Category - sport, videogame, arts, crafts, reading, writing, fiction, 
                       travel, food, tv, movies, music, outdoors, technology, other (default: other)
        level: Interest level 1-100 (50=moderate, 80+=passionate, default: 50)
        
    Returns:
        Confirmation of the interest added, OR
        a message asking for missing required information.
        
    Examples:
        - "Alice loves skiing"
          → add_interest_to_contact(name="Alice", interest_name="skiing", interest_type="sport", level=90)
        - "Bob is interested in jazz"
          → add_interest_to_contact(name="Bob", interest_name="jazz music", interest_type="music", level=70)
    """
    # ===== VALIDATION: Check required fields before API call =====
    if not name or not name.strip():
        return "⚠️ I need to know whose interest to add. What's the person's name?"
    
    if not interest_name or not interest_name.strip():
        return f"⚠️ What is **{name}** interested in? Please tell me the interest or hobby."
    
    # Validate interest_type
    valid_types = [
        "sport", "videogame", "arts", "crafts", "reading", "writing", 
        "fiction", "travel", "food", "tv", "movies", "music", 
        "outdoors", "technology", "other"
    ]
    if interest_type.lower() not in valid_types:
        # Auto-correct to "other" instead of failing
        interest_type = "other"
    
    # Validate level
    if not isinstance(level, int) or level < 1 or level > 100:
        level = 50  # Default to moderate
    
    async def _add_interest():
        client = _get_client()
        try:
            # Find the person
            matches = await client.find_person_by_name(name)
            if not matches:
                return f"❌ No contact named '{name}' found. Would you like me to add them first?"
            
            person = matches[0]
            
            # Use atomic add_interest endpoint (safe for parallel calls)
            result = await client.add_interest(
                person["id"], 
                interest_name, 
                interest_type.lower(), 
                level
            )
            
            return f"✅ Added interest to **{result['name']}**: {interest_name} ({interest_type}, level: {level}/100)"
            
        except UserNetworkClientError as e:
            return f"❌ Failed to add interest: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_add_interest())


@tool
def deactivate_contact(name: str, reason: Optional[str] = None) -> str:
    """
    Mark a contact as inactive (soft delete).
    
    Use this when:
    - A contact is no longer relevant
    - Someone has passed away
    - The user wants to remove someone from active contacts
    
    Note: This doesn't permanently delete - the contact can be reactivated.
    
    Args:
        name: Name of the person to deactivate
        reason: Optional reason for deactivation
        
    Returns:
        Confirmation of deactivation.
        
    Examples:
        - "Remove John from my contacts"
          → deactivate_contact(name="John")
        - "Mark Uncle Bob as inactive, he passed away"
          → deactivate_contact(name="Uncle Bob", reason="deceased")
    """
    async def _deactivate():
        client = _get_client()
        try:
            matches = await client.find_person_by_name(name)
            if not matches:
                return f"❌ No contact named '{name}' found."
            
            if len(matches) > 1:
                names = ", ".join([m["name"] for m in matches])
                return f"⚠️ Multiple contacts found: {names}. Please be more specific."
            
            person = matches[0]
            
            # Update status to inactive
            update_data = {"status": "inactive"}
            if reason:
                existing_notes = person.get("notes", "")
                update_data["notes"] = f"{existing_notes}\nDeactivated: {reason}".strip()
            
            await client.update_person(person["id"], update_data)
            
            return f"✅ Marked **{person['name']}** as inactive." + (f" Reason: {reason}" if reason else "")
            
        except UserNetworkClientError as e:
            return f"❌ Failed to deactivate contact: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_deactivate())


def _categorize_relationship(role: str) -> str:
    """Helper to categorize relationship type from role.
    
    Returns one of: family, friends, work, acquaintance
    (These match the RelationshipCategory enum in the API)
    """
    role_lower = role.lower()
    
    # Family includes blood relatives and romantic partners (spouse, partner, etc.)
    family_roles = {
        "mother", "father", "mom", "dad", "parent", "son", "daughter", "child",
        "brother", "sister", "sibling", "grandmother", "grandfather", "grandma", 
        "grandpa", "grandparent", "grandson", "granddaughter", "grandchild",
        "aunt", "uncle", "cousin", "niece", "nephew", "in-law", "step",
        # Romantic partners are considered family
        "wife", "husband", "spouse", "partner", "boyfriend", "girlfriend",
        "fiancé", "fiancée", "fiance", "ex"
    }
    
    work_roles = {
        "manager", "boss", "supervisor", "director", "ceo", "cto", "cfo",
        "coworker", "colleague", "employee", "direct_report", "mentor", "mentee",
        "client", "vendor", "investor", "recruiter"
    }
    
    if any(r in role_lower for r in family_roles):
        return "family"
    elif any(r in role_lower for r in work_roles):
        return "work"
    elif "friend" in role_lower:
        return "friends"  # Note: API uses plural "friends"
    else:
        return "acquaintance"


# ============================================================================
# Search Tool
# ============================================================================

@tool
def search_contacts(query: str) -> str:
    """
    Search across all contacts by name, expertise, interests, or company.
    
    Use this for general searches when looking for someone with specific
    characteristics or skills.
    
    Args:
        query: Search term (e.g., "engineer", "yoga", "Google")
        
    Returns:
        List of matching contacts.
        
    Examples:
        - "Find someone who knows about skiing"
        - "Who works at Google?"
        - "Find contacts interested in cooking"
    """
    async def _fetch():
        client = _get_client()
        try:
            results = await client.search_persons(query)
            if not results:
                return f"No contacts found matching '{query}'."
            
            output = [f"**Contacts matching '{query}':**\n"]
            for person in results[:10]:  # Limit to 10 results
                info = [f"- **{person.get('name', 'Unknown')}**"]
                if person.get('latest_title') and person.get('company'):
                    info.append(f"  {person['latest_title']} at {person['company']}")
                if person.get('expertise'):
                    info.append(f"  Expertise: {person['expertise']}")
                output.append(" ".join(info))
            
            return "\n".join(output)
        except UserNetworkClientError as e:
            return f"Error searching contacts: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_fetch())


# ============================================================================
# Tool Collection
# ============================================================================

# Read-only tools for querying the network
USER_NETWORK_READ_TOOLS = [
    get_contact_by_relationship,
    get_contact_by_name,
    get_interests_by_relationship,
    get_interests_by_name,
    find_related_person,
    get_most_contacted_people,
    search_contacts,
]

# Write tools for modifying the network
USER_NETWORK_WRITE_TOOLS = [
    add_new_contact,
    update_contact_info,
    add_relationship,
    add_interest_to_contact,
    deactivate_contact,
]

# All user network tools for easy import
USER_NETWORK_TOOLS = USER_NETWORK_READ_TOOLS + USER_NETWORK_WRITE_TOOLS

