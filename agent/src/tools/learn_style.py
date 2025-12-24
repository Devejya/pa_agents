"""
Writing Style Learning Tools

Analyzes sent emails to learn the user's writing style.
Supports context-specific styles (professional, family, recruiters, etc.)
Style profiles are encrypted and stored locally.
"""

import base64
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from bs4 import BeautifulSoup

from ..auth import get_gmail_service
from ..crypto import save_style_profile, load_style_profile, profile_exists, delete_profile
from ..pii import mask_pii

# Style context categories (same as memory contexts for consistency)
STYLE_CATEGORIES = [
    "professional_work",
    "recruiters_jobs",
    "family_friends",
    "services_utilities",
    "medical_health",
    "financial_banking",
    "shopping_retail",
    "other",
]


def _get_header(headers: list, name: str) -> str:
    """Get header value by name."""
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _fetch_sent_emails_with_metadata(max_results: int = 50) -> list[dict]:
    """
    Fetch sent emails with recipient metadata for categorization.
    
    Returns list of dicts with: body, to, subject, snippet
    """
    service = get_gmail_service()
    
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["SENT"],
    ).execute()
    
    messages = results.get("messages", [])
    
    if not messages:
        return []
    
    emails = []
    for msg in messages:
        try:
            full_msg = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()
            
            payload = full_msg.get("payload", {})
            headers = payload.get("headers", [])
            
            # Extract body
            body = ""
            if "body" in payload and payload["body"].get("data"):
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
            elif "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain" and part["body"].get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        break
                    elif part.get("mimeType") == "text/html" and part["body"].get("data"):
                        html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                        soup = BeautifulSoup(html, "html.parser")
                        body = soup.get_text(separator="\n", strip=True)
            
            if body:
                emails.append({
                    "body": body[:1500],
                    "to": _get_header(headers, "To"),
                    "subject": _get_header(headers, "Subject"),
                    "snippet": full_msg.get("snippet", "")[:200],
                })
        except Exception:
            continue
    
    return emails


def _categorize_email(to: str, subject: str, body: str) -> str:
    """
    Auto-categorize an email based on recipient and content.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body
        
    Returns:
        Category string from STYLE_CATEGORIES
    """
    combined = f"{to} {subject} {body}".lower()
    
    # Domain-based categorization
    to_lower = to.lower()
    
    # Recruiters / Jobs
    if any(kw in to_lower for kw in ["recruit", "talent", "hiring", "hr@", "careers@", "jobs@"]):
        return "recruiters_jobs"
    if any(kw in combined for kw in ["interview", "job opportunity", "position", "resume", "application"]):
        return "recruiters_jobs"
    
    # Professional / Work
    if any(kw in combined for kw in ["meeting", "project", "deadline", "report", "quarterly", "sync"]):
        return "professional_work"
    
    # Medical / Health
    if any(kw in combined for kw in ["doctor", "appointment", "clinic", "dental", "health", "prescription", "patient"]):
        return "medical_health"
    
    # Financial / Banking
    if any(kw in combined for kw in ["bank", "account", "payment", "invoice", "transaction", "statement"]):
        return "financial_banking"
    
    # Services / Utilities
    if any(kw in combined for kw in ["service", "support", "subscription", "utility", "bill", "customer"]):
        return "services_utilities"
    
    # Shopping / Retail
    if any(kw in combined for kw in ["order", "delivery", "shipping", "purchase", "return", "refund"]):
        return "shopping_retail"
    
    # Family / Friends - check for informal patterns
    if any(kw in combined for kw in ["love", "miss you", "birthday", "holiday", "weekend", "hang out", "catch up"]):
        return "family_friends"
    
    # Check for personal email domains (likely friends/family)
    personal_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"]
    if any(domain in to_lower for domain in personal_domains):
        # Could be personal, but default to other if not clear
        pass
    
    return "other"


def _categorize_emails_with_llm(emails: list[dict]) -> list[dict]:
    """
    Use LLM to categorize emails more accurately.
    
    Args:
        emails: List of email dicts
        
    Returns:
        Same list with 'category' field added
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an email categorizer. For each email, determine its category based on 
the recipient and content. Categories:
- professional_work: Work colleagues, business communications
- recruiters_jobs: Job applications, recruiters, career-related
- family_friends: Personal emails to family and friends
- services_utilities: Customer service, utilities, subscriptions
- medical_health: Healthcare providers, medical appointments
- financial_banking: Banks, financial services
- shopping_retail: Online shopping, orders, deliveries
- other: Doesn't fit other categories

Return JSON array with category for each email:
{{"categories": ["category1", "category2", ...]}}"""),
        ("user", """Categorize these emails:

{emails}

Return ONLY valid JSON."""),
    ])
    
    # Prepare masked email summaries
    email_summaries = []
    for i, email in enumerate(emails):
        masked_to = mask_pii(email["to"])
        masked_subject = mask_pii(email["subject"])
        email_summaries.append(f"{i+1}. To: {masked_to}, Subject: {masked_subject}")
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({"emails": "\n".join(email_summaries)})
        categories = result.get("categories", [])
        
        for i, email in enumerate(emails):
            if i < len(categories) and categories[i] in STYLE_CATEGORIES:
                email["category"] = categories[i]
            else:
                # Fallback to rule-based
                email["category"] = _categorize_email(email["to"], email["subject"], email["body"])
    except Exception:
        # Fallback to rule-based categorization
        for email in emails:
            email["category"] = _categorize_email(email["to"], email["subject"], email["body"])
    
    return emails


def _analyze_style_for_emails(emails: list[dict], category: str) -> dict:
    """
    Analyze writing style for a group of emails.
    
    Args:
        emails: List of email dicts
        category: Category name for context
        
    Returns:
        Style profile dict
    """
    # Prepare masked email samples
    email_samples = []
    for i, email in enumerate(emails[:10], 1):  # Limit to 10 per category
        masked_body = mask_pii(email["body"])
        email_samples.append(f"--- Email {i} ---\n{masked_body}")
    
    combined_text = "\n\n".join(email_samples)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a writing style analyst. Analyze the provided email samples for the {category} context.

Extract ONLY abstract style patterns. DO NOT include actual content, names, or identifying info.

Return JSON:
{{
    "tone": "description of tone",
    "greeting_patterns": ["pattern1", "pattern2"],
    "signoff_patterns": ["pattern1", "pattern2"],
    "formality_level": 1-10,
    "typical_length": "short/medium/long",
    "sentence_style": "description",
    "common_phrases": ["phrase1", "phrase2"],
    "uses_emojis": true/false,
    "punctuation_notes": "patterns",
    "overall_personality": "2-3 sentence description"
}}"""),
        ("user", """Analyze the writing style in these {category} emails:

{emails}

Return ONLY valid JSON."""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        return chain.invoke({"category": category, "emails": combined_text})
    except Exception:
        return {}


def analyze_contextual_styles(num_emails: int = 50) -> dict:
    """
    Analyze sent emails and learn styles for different contexts.
    
    Automatically categorizes emails and creates separate style profiles
    for each context type (professional, personal, recruiters, etc.)
    
    Args:
        num_emails: Number of sent emails to analyze
        
    Returns:
        Dict with status and learned styles summary
    """
    # Fetch emails with metadata
    emails = _fetch_sent_emails_with_metadata(max_results=num_emails)
    
    if not emails:
        return {
            "status": "error",
            "error": "No sent emails found. Send some emails first so I can learn your style.",
        }
    
    # Categorize emails using LLM
    categorized_emails = _categorize_emails_with_llm(emails)
    
    # Group by category
    by_category = {}
    for email in categorized_emails:
        cat = email.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(email)
    
    # Analyze style for each category with enough emails
    MIN_EMAILS_FOR_STYLE = 2
    
    styles = {}
    categories_analyzed = []
    
    for category, cat_emails in by_category.items():
        if len(cat_emails) >= MIN_EMAILS_FOR_STYLE:
            style = _analyze_style_for_emails(cat_emails, category)
            if style:
                styles[category] = style
                styles[category]["_email_count"] = len(cat_emails)
                categories_analyzed.append(f"{category} ({len(cat_emails)} emails)")
    
    # ALWAYS create a "default" style from ALL emails (even if no category has 2+ emails)
    # This ensures we learn SOMETHING even with few emails
    if len(emails) >= 1:
        all_style = _analyze_style_for_emails(emails[:15], "general")
        if all_style:
            styles["default"] = all_style
            styles["default"]["_email_count"] = len(emails)
            if "default" not in [c.split(" ")[0] for c in categories_analyzed]:
                categories_analyzed.append(f"default ({len(emails)} emails)")
    
    if not styles:
        return {
            "status": "warning",
            "message": "Could not analyze any emails. Try again later.",
            "email_distribution": {cat: len(emails) for cat, emails in by_category.items()},
        }
    
    # Build the new profile structure
    profile = {
        "_metadata": {
            "version": "2.0",  # New version for contextual styles
            "created_at": datetime.now().isoformat(),
            "total_emails_analyzed": len(emails),
            "categories_learned": list(styles.keys()),
        },
        "default": styles.get("default", {}),
        "contexts": {k: v for k, v in styles.items() if k != "default"},
    }
    
    # Save the profile
    try:
        save_style_profile(profile)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to save style profile: {str(e)}",
        }
    
    return {
        "status": "success",
        "message": f"Analyzed {len(emails)} emails across {len(styles)} contexts.",
        "categories_learned": categories_analyzed,
        "email_distribution": {cat: len(emails) for cat, emails in by_category.items()},
    }


def get_style_for_context(context: str = "default") -> dict | None:
    """
    Get style profile for a specific context.
    
    Args:
        context: Context category (e.g., "professional_work", "family_friends")
                 Use "default" for general style.
                 
    Returns:
        Style profile dict or None
    """
    profile = load_style_profile()
    
    if not profile:
        return None
    
    # Check version
    version = profile.get("_metadata", {}).get("version", "1.0")
    
    if version == "2.0":
        # New contextual format
        if context == "default":
            return profile.get("default")
        return profile.get("contexts", {}).get(context) or profile.get("default")
    else:
        # Old format - return as default
        return profile


def get_style_profile() -> dict | None:
    """
    Load the user's style profile if it exists.
    
    Returns:
        Full style profile dict or None
    """
    return load_style_profile()


def clear_style_profile() -> dict:
    """
    Delete the stored style profile.
    
    Returns:
        Status dict
    """
    if delete_profile():
        return {
            "status": "success",
            "message": "Style profile deleted. I'll use default style for drafts.",
        }
    return {
        "status": "info",
        "message": "No style profile found to delete.",
    }


def get_contextual_style_status() -> dict:
    """
    Get detailed status of all learned styles.
    
    Returns:
        Status information for all contexts
    """
    profile = load_style_profile()
    
    if not profile:
        return {
            "has_profile": False,
            "message": "No style profile found. Use 'learn my style' to create one.",
        }
    
    metadata = profile.get("_metadata", {})
    version = metadata.get("version", "1.0")
    
    if version == "2.0":
        # New contextual format
        contexts_info = {}
        
        # Default style
        default = profile.get("default", {})
        if default:
            contexts_info["default"] = {
                "tone": default.get("tone", "unknown"),
                "formality_level": default.get("formality_level", "unknown"),
                "email_count": default.get("_email_count", "unknown"),
            }
        
        # Context-specific styles
        for context, style in profile.get("contexts", {}).items():
            contexts_info[context] = {
                "tone": style.get("tone", "unknown"),
                "formality_level": style.get("formality_level", "unknown"),
                "email_count": style.get("_email_count", "unknown"),
                "greeting_patterns": style.get("greeting_patterns", []),
                "signoff_patterns": style.get("signoff_patterns", []),
            }
        
        return {
            "has_profile": True,
            "version": "2.0 (contextual)",
            "total_emails_analyzed": metadata.get("total_emails_analyzed", "unknown"),
            "created_at": metadata.get("created_at", "unknown"),
            "contexts_learned": metadata.get("categories_learned", []),
            "styles": contexts_info,
        }
    else:
        # Old format
        return {
            "has_profile": True,
            "version": "1.0 (single style)",
            "emails_analyzed": metadata.get("emails_analyzed", "unknown"),
            "created_at": metadata.get("created_at", "unknown"),
            "tone": profile.get("tone", "unknown"),
            "formality_level": profile.get("formality_level", "unknown"),
            "note": "Run 'learn my style' again to upgrade to contextual styles.",
        }


# Keep old function for backwards compatibility
def analyze_writing_style(num_emails: int = 50) -> dict:
    """
    Analyze sent emails to learn the user's writing style.
    Now delegates to contextual style learning.
    
    Args:
        num_emails: Number of sent emails to analyze
        
    Returns:
        Dict with status and style profile summary
    """
    return analyze_contextual_styles(num_emails=num_emails)


def get_style_status() -> dict:
    """
    Check if a style profile exists and get info.
    Delegates to contextual status.
    """
    return get_contextual_style_status()


def should_refresh_styles() -> bool:
    """
    Check if styles should be refreshed.
    
    Returns True if:
    - No profile exists
    - Profile is older than 7 days
    - Profile was created with very few emails
    """
    from datetime import datetime, timedelta
    
    profile = load_style_profile()
    
    if not profile:
        return True
    
    metadata = profile.get("_metadata", {})
    
    # Check age
    created_str = metadata.get("created_at")
    if created_str:
        try:
            created = datetime.fromisoformat(created_str)
            if datetime.now() - created > timedelta(days=7):
                return True
        except ValueError:
            pass
    
    # Check email count (refresh if learned from very few emails)
    total_analyzed = metadata.get("total_emails_analyzed", 0)
    if total_analyzed < 5:
        return True
    
    return False


def auto_refresh_styles_if_needed(silent: bool = True) -> dict | None:
    """
    Automatically refresh style profiles if they're stale or missing.
    Called on agent startup.
    
    Args:
        silent: If True, only refresh without returning verbose output
        
    Returns:
        Result dict if refreshed, None if no refresh needed
    """
    if not should_refresh_styles():
        return None
    
    result = analyze_contextual_styles(num_emails=50)
    
    if silent:
        if result.get("status") == "success":
            return {"refreshed": True, "message": "Style profile updated"}
        return None
    
    return result
