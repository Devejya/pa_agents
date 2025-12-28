"""
Profile Discovery Tools

Extract user profile and contacts from emails to bootstrap the User Network.
"""

import json
import os
import re
from typing import Optional

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ..auth import get_gmail_service
from .read_emails import read_emails, _get_header, _decode_body
from .user_network import (
    _get_client,
    _run_async,
    add_new_contact,
    add_relationship,
    _categorize_relationship,
)
from ..graph.client import UserNetworkClientError


# ============================================================================
# Relationship Type Mapping
# ============================================================================

def _map_role_to_category(role: str) -> str:
    """Map a user-provided relationship role to a valid API category.
    
    Valid categories: family, friends, work, acquaintance
    """
    if not role:
        return "acquaintance"
    return _categorize_relationship(role)


# ============================================================================
# Email Fetching for Profile Discovery
# ============================================================================

def _fetch_sent_emails(max_results: int = 50) -> list[dict]:
    """Fetch sent emails for profile analysis."""
    service = get_gmail_service()
    
    # Fetch sent messages
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["SENT"],
    ).execute()
    
    messages = results.get("messages", [])
    
    if not messages:
        return []
    
    emails = []
    for msg in messages[:max_results]:
        try:
            full_msg = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()
            
            headers = full_msg.get("payload", {}).get("headers", [])
            
            email_data = {
                "id": msg["id"],
                "from": _get_header(headers, "From"),
                "to": _get_header(headers, "To"),
                "subject": _get_header(headers, "Subject"),
                "body": _decode_body(full_msg.get("payload", {})),
                "type": "sent",
            }
            emails.append(email_data)
        except Exception:
            continue
    
    return emails


def _fetch_received_emails(max_results: int = 50) -> list[dict]:
    """Fetch received emails to extract contact info from their signatures."""
    service = get_gmail_service()
    
    # Fetch inbox messages
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["INBOX"],
    ).execute()
    
    messages = results.get("messages", [])
    
    if not messages:
        return []
    
    emails = []
    for msg in messages[:max_results]:
        try:
            full_msg = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()
            
            headers = full_msg.get("payload", {}).get("headers", [])
            
            email_data = {
                "id": msg["id"],
                "from": _get_header(headers, "From"),
                "to": _get_header(headers, "To"),
                "subject": _get_header(headers, "Subject"),
                "body": _decode_body(full_msg.get("payload", {})),
                "type": "received",
            }
            emails.append(email_data)
        except Exception:
            continue
    
    return emails


def _parse_email_address(email_str: str) -> dict:
    """
    Parse email string to extract display name and email address.
    
    Examples:
        "John Doe <john@example.com>" -> {"name": "John Doe", "email": "john@example.com"}
        "john@example.com" -> {"name": None, "email": "john@example.com"}
    """
    import re
    
    # Pattern: "Display Name" <email@domain.com> or Display Name <email@domain.com>
    match = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', email_str.strip())
    if match:
        return {"name": match.group(1).strip(), "email": match.group(2).strip()}
    
    # Just email address
    email_match = re.match(r'^([^\s<>]+@[^\s<>]+)$', email_str.strip())
    if email_match:
        return {"name": None, "email": email_match.group(1)}
    
    return {"name": None, "email": email_str.strip()}


def _extract_signature_from_body(body: str) -> str:
    """Extract signature from email body (usually last few lines)."""
    if not body:
        return ""
    
    lines = body.strip().split("\n")
    
    # Look for common signature patterns
    sig_start = None
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Common signature starters
        if line_lower.startswith(("thanks", "best", "regards", "cheers", "sincerely", "-", "—")):
            sig_start = i
            break
    
    if sig_start is not None:
        return "\n".join(lines[sig_start:sig_start + 5])
    
    # Fallback: last 5 lines
    return "\n".join(lines[-5:]) if len(lines) > 5 else body


def _extract_signature_info(sent_emails: list[dict], received_emails: list[dict] = None) -> dict:
    """
    Extract profile and contact info from emails.
    
    - From SENT emails: extract user's signature (their name, phone, etc.)
    - From RECEIVED emails: extract contact info (sender names, their signatures)
    """
    user_signatures = []
    from_addresses = set()
    
    # Contacts dict: email -> {name, signatures, frequency}
    contacts = {}
    
    # Process SENT emails (for user's own info)
    for email in sent_emails:
        # Collect user's from addresses
        from_addr = email.get("from", "")
        if from_addr:
            parsed = _parse_email_address(from_addr)
            from_addresses.add(from_addr)
        
        # Extract user's signature from their sent emails
        body = email.get("body", "")
        if body:
            sig = _extract_signature_from_body(body)
            if sig:
                user_signatures.append(sig)
        
        # Track recipients
        to_addr = email.get("to", "")
        if to_addr:
            parsed = _parse_email_address(to_addr)
            email_addr = parsed["email"].lower()
            
            if email_addr not in contacts:
                contacts[email_addr] = {
                    "email": parsed["email"],
                    "display_name": parsed["name"],
                    "signatures": [],
                    "frequency": 0,
                }
            contacts[email_addr]["frequency"] += 1
            # Update display name if we find one
            if parsed["name"] and not contacts[email_addr]["display_name"]:
                contacts[email_addr]["display_name"] = parsed["name"]
    
    # Process RECEIVED emails (for contact info)
    if received_emails:
        for email in received_emails:
            from_addr = email.get("from", "")
            if from_addr:
                parsed = _parse_email_address(from_addr)
                email_addr = parsed["email"].lower()
                
                if email_addr not in contacts:
                    contacts[email_addr] = {
                        "email": parsed["email"],
                        "display_name": parsed["name"],
                        "signatures": [],
                        "frequency": 0,
                    }
                
                # Update display name from email header
                if parsed["name"]:
                    contacts[email_addr]["display_name"] = parsed["name"]
                
                # Extract their signature from the email body
                body = email.get("body", "")
                if body:
                    sig = _extract_signature_from_body(body)
                    if sig and sig not in contacts[email_addr]["signatures"]:
                        contacts[email_addr]["signatures"].append(sig)
    
    # Convert contacts to list format for LLM
    contact_list = []
    for email_addr, info in contacts.items():
        contact_list.append({
            "email": info["email"],
            "display_name": info["display_name"],
            "signatures": info["signatures"][:3],  # Limit signatures
            "frequency": info["frequency"],
        })
    
    # Sort by frequency
    contact_list.sort(key=lambda x: -x["frequency"])
    
    return {
        "from_addresses": list(from_addresses),
        "user_signatures": user_signatures[:10],
        "contacts": contact_list[:30],  # Top 30 contacts
    }


# ============================================================================
# LLM-based Profile Extraction
# ============================================================================

def _extract_profile_with_llm(email_data: dict) -> dict:
    """Use LLM to extract profile information from email data."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    prompt = f"""Extract profile information from this email data. 

CRITICAL: Only extract information that is EXPLICITLY present in the data below. 
DO NOT invent, hallucinate, or assume any names, emails, or details that are not directly stated.
If information is not available, use null.

=== CORE USER'S EMAIL ADDRESSES ===
{json.dumps(email_data['from_addresses'], indent=2)}

=== CORE USER'S EMAIL SIGNATURES (from their sent emails) ===
{json.dumps(email_data.get('user_signatures', [])[:10], indent=2)}

=== CONTACTS (people the user emails or receives email from) ===
Each contact includes:
- email: their email address
- display_name: name from email header (may be null)
- signatures: signatures extracted from their emails (may be empty)
- frequency: number of emails exchanged

{json.dumps(email_data.get('contacts', [])[:20], indent=2)}

=== EXTRACTION RULES ===
1. For contact names, PREFER the signature over display_name (signatures are more accurate)
2. Look for patterns like "- Name", "Thanks, Name", "Best, Name" in signatures
3. If a signature says "- LB", the name is "LB", not the display_name
4. If no name can be determined, set name to null
5. Only include contacts with frequency >= 1

Return this exact JSON structure (use null for unknown fields, not empty strings):
{{
    "core_user": {{
        "name": null,
        "personal_email": null,
        "work_email": null,
        "personal_cell": null,
        "work_cell": null,
        "company": null,
        "latest_title": null,
        "city": null,
        "country": null,
        "confidence": "low"
    }},
    "discovered_contacts": []
}}

Return ONLY valid JSON, no explanation or markdown."""

    response = llm.invoke(prompt)
    
    try:
        # Clean up response (remove markdown code blocks if present)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "core_user": {"name": "Unknown", "confidence": "low"},
            "discovered_contacts": [],
            "error": "Failed to parse LLM response"
        }


# ============================================================================
# Profile Discovery Tool
# ============================================================================

@tool
def analyze_emails_for_profile(num_emails: int = 50) -> str:
    """
    Analyze your emails to discover your profile information and contacts.
    
    This tool reads your recent sent AND received emails and extracts:
    - Your name, email, phone from your signatures
    - Your job title and company
    - Contact names from their email signatures (more accurate than display names)
    - Frequently contacted people
    
    The results are presented for your review BEFORE saving to the database.
    Use save_discovered_profile() to save after reviewing.
    
    Args:
        num_emails: Number of emails to analyze per type (default 50)
        
    Returns:
        Discovered profile information and contacts for review.
        
    Example:
        User: "Set up my profile from my emails"
        → analyze_emails_for_profile(num_emails=100)
    """
    try:
        # Step 1: Fetch both sent and received emails
        sent_emails = _fetch_sent_emails(max_results=num_emails)
        received_emails = _fetch_received_emails(max_results=num_emails)
        
        if not sent_emails and not received_emails:
            return "❌ No emails found. Please ensure Gmail access is configured."
        
        # Step 2: Extract raw data from emails (both sent and received)
        email_data = _extract_signature_info(sent_emails, received_emails)
        
        if not email_data["from_addresses"]:
            return "❌ Could not extract email addresses from emails."
        
        # Step 3: Use LLM to extract structured profile
        profile = _extract_profile_with_llm(email_data)
        
        # Step 4: Format results for user review
        output = ["# 📧 Profile Discovery Results\n"]
        output.append(f"*Analyzed {len(sent_emails)} sent + {len(received_emails)} received emails*\n")
        
        # Core user profile
        core = profile.get("core_user", {})
        output.append("## Your Profile (Core User)\n")
        output.append(f"**Name:** {core.get('name', 'Not found')}")
        
        if core.get("work_email"):
            output.append(f"**Work Email:** {core.get('work_email')}")
        if core.get("personal_email"):
            output.append(f"**Personal Email:** {core.get('personal_email')}")
        if core.get("work_cell"):
            output.append(f"**Work Phone:** {core.get('work_cell')}")
        if core.get("personal_cell"):
            output.append(f"**Personal Phone:** {core.get('personal_cell')}")
        if core.get("company"):
            output.append(f"**Company:** {core.get('company')}")
        if core.get("latest_title"):
            output.append(f"**Title:** {core.get('latest_title')}")
        if core.get("city") or core.get("country"):
            location = ", ".join(filter(None, [core.get("city"), core.get("country")]))
            output.append(f"**Location:** {location}")
        
        output.append(f"\n*Confidence: {core.get('confidence', 'unknown')}*\n")
        
        # Discovered contacts
        contacts = profile.get("discovered_contacts", [])
        if contacts:
            output.append(f"\n## Discovered Contacts ({len(contacts)} found)\n")
            for i, contact in enumerate(contacts[:15], 1):  # Show top 15
                name = contact.get("name", "Unknown")
                email = contact.get("email", "")
                rel = contact.get("likely_relationship", "unknown")
                freq = contact.get("frequency", "?")
                output.append(f"{i}. **{name}** ({email})")
                output.append(f"   Likely: {rel} | Emails: {freq}")
        
        # Instructions
        output.append("\n---")
        output.append("\n## Next Steps")
        output.append("1. Review the information above")
        output.append("2. Tell me any corrections needed")
        output.append("3. Say **'Save my profile'** to create your core user")
        output.append("4. Optionally: **'Also add the contacts'** to add discovered people")
        
        # Store discovered data for later save (using a simple approach)
        # In production, use a proper session/cache
        _store_discovered_profile(profile)
        
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ Error analyzing emails: {str(e)}"


# ============================================================================
# Profile Storage (Temporary)
# ============================================================================

_DISCOVERED_PROFILE = {}

def _store_discovered_profile(profile: dict):
    """Store discovered profile for later confirmation."""
    global _DISCOVERED_PROFILE
    _DISCOVERED_PROFILE = profile

def _get_discovered_profile() -> dict:
    """Retrieve stored discovered profile."""
    global _DISCOVERED_PROFILE
    return _DISCOVERED_PROFILE

def _update_discovered_contact(contact_name: str, updates: dict) -> bool:
    """Update a contact in the discovered profile.
    
    Args:
        contact_name: Name of contact to update (case-insensitive match)
        updates: Dict of fields to update (e.g., relationship, city)
    
    Returns:
        True if contact was found and updated, False otherwise
    """
    global _DISCOVERED_PROFILE
    contacts = _DISCOVERED_PROFILE.get("discovered_contacts", [])
    
    for contact in contacts:
        if contact.get("name", "").lower() == contact_name.lower():
            contact.update(updates)
            return True
    return False

def _update_core_user(updates: dict):
    """Update the core user in the discovered profile."""
    global _DISCOVERED_PROFILE
    if "core_user" not in _DISCOVERED_PROFILE:
        _DISCOVERED_PROFILE["core_user"] = {}
    _DISCOVERED_PROFILE["core_user"].update(updates)


@tool
def update_discovered_profile(
    core_user_name: Optional[str] = None,
    contact_updates: Optional[str] = None,
) -> str:
    """
    Update the discovered profile with user-provided information.
    
    Call this BEFORE save_discovered_profile() when the user provides
    corrections or additional information about themselves or contacts.
    
    Args:
        core_user_name: The user's actual name (if different from discovered)
        contact_updates: JSON string of contact updates. Supported fields:
            - name: Contact name to update (required)
            - relationship: How they relate to user (friend, manager, sister, etc.)
            - city: City where they live
            - country: Country where they live
            - company: Where they work
            - title: Their job title
            - interests: List of interests/hobbies (e.g., ["cricket", "traveling"])
            - phone: Their phone number
    
    Returns:
        Confirmation of updates made.
    
    Examples:
        User: "My name is Raj"
        → update_discovered_profile(core_user_name="Raj")
        
        User: "John is my manager at Google, Sarah is my sister in Boston who loves yoga"
        → update_discovered_profile(contact_updates='[
            {"name": "John", "relationship": "manager", "company": "Google"}, 
            {"name": "Sarah", "relationship": "sister", "city": "Boston", "interests": ["yoga"]}
        ]')
        
        User: "Anish is from Delhi and loves cricket"
        → update_discovered_profile(contact_updates='[{"name": "Anish", "city": "Delhi", "interests": ["cricket"]}]')
    """
    profile = _get_discovered_profile()
    if not profile:
        return "❌ No discovered profile. Run 'setup my profile' first."
    
    results = []
    
    if core_user_name:
        _update_core_user({"name": core_user_name})
        results.append(f"✅ Set your name to: **{core_user_name}**")
    
    if contact_updates:
        try:
            updates_list = json.loads(contact_updates)
            for update in updates_list:
                contact_name = update.get("name")
                if not contact_name:
                    continue
                    
                # Build update dict - support all common fields
                update_dict = {}
                if update.get("relationship"):
                    update_dict["likely_relationship"] = update["relationship"]
                    update_dict["relationship_role"] = update["relationship"]
                if update.get("city"):
                    update_dict["city"] = update["city"]
                if update.get("country"):
                    update_dict["country"] = update["country"]
                if update.get("company"):
                    update_dict["company"] = update["company"]
                if update.get("title"):
                    update_dict["title"] = update["title"]
                if update.get("interests"):
                    update_dict["interests"] = update["interests"]
                if update.get("phone"):
                    update_dict["phone"] = update["phone"]
                    
                if _update_discovered_contact(contact_name, update_dict):
                    # Build description of what was updated
                    parts = []
                    if update.get("relationship"):
                        parts.append(update["relationship"])
                    if update.get("city"):
                        parts.append(f"in {update['city']}")
                    if update.get("company"):
                        parts.append(f"at {update['company']}")
                    if update.get("interests"):
                        interests_str = ", ".join(update["interests"][:3])
                        parts.append(f"likes {interests_str}")
                    
                    desc = " ".join(parts) if parts else "updated"
                    results.append(f"✅ Updated **{contact_name}**: {desc}")
                else:
                    results.append(f"⚠️ Contact **{contact_name}** not found in discovered contacts")
        except json.JSONDecodeError:
            results.append("⚠️ Could not parse contact updates")
    
    if not results:
        return "ℹ️ No updates provided."
    
    return "\n".join(results)


# ============================================================================
# Save Profile Tool
# ============================================================================

@tool
def save_discovered_profile(
    include_contacts: bool = False,
    name_override: Optional[str] = None,
    email_override: Optional[str] = None,
    phone_override: Optional[str] = None,
) -> str:
    """
    Save the discovered profile to the User Network database.
    
    Call this AFTER reviewing results from analyze_emails_for_profile().
    
    Args:
        include_contacts: Also save discovered contacts (default False)
        name_override: Override the discovered name
        email_override: Override the discovered email  
        phone_override: Override the discovered phone
        
    Returns:
        Confirmation of what was saved, OR
        a message asking for missing required information.
        
    Example:
        User: "Save my profile"
        → save_discovered_profile()
        
        User: "Save my profile but my name is John Smith"
        → save_discovered_profile(name_override="John Smith")
        
        User: "Save my profile and add the contacts"
        → save_discovered_profile(include_contacts=True)
    """
    profile = _get_discovered_profile()
    
    if not profile:
        return "❌ No discovered profile found. Please run 'setup my profile' first to analyze your emails."
    
    # ===== VALIDATION: Check we have minimum required data =====
    core = profile.get("core_user", {})
    
    # Check name
    name = name_override or core.get("name")
    if not name or name == "Unknown" or name == "None" or name is None:
        return (
            "⚠️ I couldn't determine your name from the emails.\n\n"
            "Please tell me your name so I can save your profile.\n"
            "Example: \"My name is John Smith\""
        )
    
    # Check at least one contact method
    has_email = email_override or core.get("work_email") or core.get("personal_email")
    has_phone = phone_override or core.get("personal_cell") or core.get("work_cell")
    
    if not has_email and not has_phone:
        return (
            f"⚠️ I need at least one way to identify you in the system.\n\n"
            f"Please provide your email or phone number.\n"
            f"Example: \"My email is {name.lower().replace(' ', '.')}@example.com\""
        )
    
    async def _save():
        client = _get_client()
        results = []
        
        try:
            # Check if core user already exists
            existing_core = await client.get_core_user()
            
            # Prepare core user data
            person_data = {
                "name": name,
                "is_core_user": True,
                "status": "active",
            }
            
            # Add optional fields - prioritize overrides
            if email_override:
                person_data["personal_email"] = email_override
            if core.get("work_email"):
                person_data["work_email"] = core["work_email"]
            if core.get("personal_email") and not email_override:
                person_data["personal_email"] = core["personal_email"]
            
            if phone_override:
                person_data["personal_cell"] = phone_override
            if core.get("work_cell"):
                person_data["work_cell"] = core["work_cell"]
            if core.get("personal_cell") and not phone_override:
                person_data["personal_cell"] = core["personal_cell"]
            
            if core.get("company"):
                person_data["company"] = core["company"]
            if core.get("latest_title"):
                person_data["latest_title"] = core["latest_title"]
            if core.get("city"):
                person_data["city"] = core["city"]
            if core.get("country"):
                person_data["country"] = core["country"]
            
            # Create or update core user
            if existing_core:
                await client.update_person(existing_core["id"], person_data)
                results.append(f"✅ Updated core user: **{person_data['name']}**")
                core_user_id = existing_core["id"]
            else:
                result = await client.create_person(person_data)
                results.append(f"✅ Created core user: **{person_data['name']}**")
                core_user_id = result["id"]
            
            # Optionally add discovered contacts
            if include_contacts:
                contacts = profile.get("discovered_contacts", [])
                added = 0
                skipped = 0
                
                for contact in contacts[:20]:  # Limit to 20 contacts
                    try:
                        # Skip contacts without email (required for creation)
                        email = contact.get("email")
                        if not email:
                            skipped += 1
                            continue
                        
                        contact_name = contact.get("name") or "Unknown"
                        # Skip if name is just "Unknown" and no useful info
                        if contact_name == "Unknown" or contact_name is None:
                            skipped += 1
                            continue
                        
                        contact_data = {
                            "name": contact_name,
                            "status": "active",
                        }
                        
                        # Add email - assume work email for common domains
                        if "@" in email:
                            contact_data["work_email"] = email
                        
                        # Add location info if provided by user
                        if contact.get("city"):
                            contact_data["city"] = contact["city"]
                        if contact.get("country"):
                            contact_data["country"] = contact["country"]
                        
                        # Add professional info if provided
                        if contact.get("company"):
                            contact_data["company"] = contact["company"]
                        if contact.get("title"):
                            contact_data["latest_title"] = contact["title"]
                        
                        # Add phone if provided
                        if contact.get("phone"):
                            contact_data["personal_cell"] = contact["phone"]
                        
                        # Add interests if provided (stored as JSONB array)
                        if contact.get("interests"):
                            # Format interests for the API - requires name, type, and level
                            interests_list = contact["interests"]
                            if isinstance(interests_list, list):
                                contact_data["interests"] = [
                                    {"name": i, "type": "other", "level": 50} 
                                    for i in interests_list
                                ]
                        
                        # Create contact
                        contact_result = await client.create_person(contact_data)
                        
                        # Create relationship to core user
                        # Use relationship_role if provided by user, else likely_relationship
                        rel_role = contact.get("relationship_role") or contact.get("likely_relationship", "contact")
                        rel_type = _map_role_to_category(rel_role)
                        
                        await client.create_relationship({
                            "from_person_id": str(core_user_id),
                            "to_person_id": str(contact_result["id"]),
                            "category": rel_type,
                            "from_role": "self",
                            "to_role": rel_role.lower(),
                        })
                        
                        added += 1
                    except Exception as e:
                        # Log but continue with other contacts
                        skipped += 1
                        continue
                
                if added > 0:
                    results.append(f"✅ Added {added} contacts to your network")
                if skipped > 0:
                    results.append(f"ℹ️ Skipped {skipped} contacts (missing name or email)")
            
            # Clear stored profile
            _store_discovered_profile({})
            
            return "\n".join(results)
            
        except UserNetworkClientError as e:
            return f"❌ Failed to save profile: {str(e)}"
        finally:
            await client.close()
    
    return _run_async(_save())


# ============================================================================
# Tool Collection
# ============================================================================

PROFILE_DISCOVERY_TOOLS = [
    analyze_emails_for_profile,
    update_discovered_profile,
    save_discovered_profile,
]

