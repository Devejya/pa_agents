"""
Gmail Tools

Functions for reading and sending emails via Gmail API.
"""

import base64
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Optional

from bs4 import BeautifulSoup

from ..core.google_services import get_gmail_service


# Gmail category label mappings
# These are the internal label IDs Gmail uses for category tabs
GMAIL_CATEGORIES = {
    "CATEGORY_PERSONAL": "primary",
    "CATEGORY_SOCIAL": "social",
    "CATEGORY_PROMOTIONS": "promotions",
    "CATEGORY_UPDATES": "updates",
    "CATEGORY_FORUMS": "forums",
}


def _get_category(labels: list) -> str:
    """
    Extract Gmail category from label IDs.
    
    Args:
        labels: List of Gmail label IDs from the message
        
    Returns:
        Category name (primary, social, promotions, updates, forums)
        Defaults to "primary" if no category label found
    """
    for label in labels:
        if label in GMAIL_CATEGORIES:
            return GMAIL_CATEGORIES[label]
    return "primary"  # Default if no category label


def _decode_body(payload: dict) -> str:
    """Extract and decode email body from payload."""
    body = ""
    
    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
    elif "parts" in payload:
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain" and part["body"].get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                break
            elif mime_type == "text/html" and part["body"].get("data"):
                html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                soup = BeautifulSoup(html, "html.parser")
                body = soup.get_text(separator="\n", strip=True)
    
    return body[:5000]  # Limit body length for LLM context


def _get_header(headers: list, name: str) -> str:
    """Get header value by name."""
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]
    return ""


def read_emails(
    user_email: str,
    max_results: int = 10,
    query: str = "",
    days_back: Optional[int] = None,
    unread_only: bool = False,
    category: Optional[str] = None,
) -> list[dict]:
    """
    Read emails from Gmail inbox.
    
    Args:
        user_email: User's email for authentication
        max_results: Maximum number of emails to fetch (default 10)
        query: Gmail search query (e.g., "from:boss@company.com")
        days_back: Only fetch emails from last N days
        unread_only: Only fetch unread emails
        category: Filter by Gmail category (primary, social, promotions, updates, forums)
        
    Returns:
        List of email dictionaries
    """
    service = get_gmail_service(user_email)
    
    # Build query
    query_parts = [query] if query else []
    
    if days_back:
        date_after = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        query_parts.append(f"after:{date_after}")
    
    if unread_only:
        query_parts.append("is:unread")
    
    # Add category filter if specified
    if category:
        query_parts.append(f"category:{category}")
    
    final_query = " ".join(query_parts)
    
    # Fetch message list
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        q=final_query if final_query else None,
    ).execute()
    
    messages = results.get("messages", [])
    
    if not messages:
        return []
    
    # Fetch full message details
    emails = []
    for msg in messages:
        full_msg = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()
        
        headers = full_msg.get("payload", {}).get("headers", [])
        label_ids = full_msg.get("labelIds", [])
        
        email_data = {
            "id": msg["id"],
            "thread_id": full_msg.get("threadId"),
            "subject": _get_header(headers, "Subject"),
            "from": _get_header(headers, "From"),
            "to": _get_header(headers, "To"),
            "date": _get_header(headers, "Date"),
            "snippet": full_msg.get("snippet", ""),
            "body": _decode_body(full_msg.get("payload", {})),
            "labels": label_ids,
            "is_unread": "UNREAD" in label_ids,
            "category": _get_category(label_ids),
        }
        emails.append(email_data)
    
    return emails


def get_email_by_id(user_email: str, email_id: str) -> dict:
    """
    Get a specific email by its ID.
    
    Args:
        user_email: User's email for authentication
        email_id: Gmail message ID
        
    Returns:
        Email dictionary with full details
    """
    service = get_gmail_service(user_email)
    
    full_msg = service.users().messages().get(
        userId="me",
        id=email_id,
        format="full"
    ).execute()
    
    headers = full_msg.get("payload", {}).get("headers", [])
    label_ids = full_msg.get("labelIds", [])
    
    return {
        "id": email_id,
        "thread_id": full_msg.get("threadId"),
        "subject": _get_header(headers, "Subject"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "date": _get_header(headers, "Date"),
        "snippet": full_msg.get("snippet", ""),
        "body": _decode_body(full_msg.get("payload", {})),
        "labels": label_ids,
        "is_unread": "UNREAD" in label_ids,
        "category": _get_category(label_ids),
    }


def search_emails(
    user_email: str,
    query: str,
    max_results: int = 20,
) -> list[dict]:
    """
    Search emails using Gmail query syntax.
    
    Args:
        user_email: User's email for authentication
        query: Gmail search query (e.g., "from:john subject:meeting")
        max_results: Maximum results to return
        
    Returns:
        List of email dictionaries
    """
    return read_emails(user_email, max_results=max_results, query=query)


def send_email(
    user_email: str,
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> dict:
    """
    Send an email.
    
    Args:
        user_email: User's email for authentication
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
        
    Returns:
        Sent message info
    """
    service = get_gmail_service(user_email)
    
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    
    sent_message = service.users().messages().send(
        userId="me",
        body={"raw": raw_message}
    ).execute()
    
    return {
        "id": sent_message.get("id"),
        "thread_id": sent_message.get("threadId"),
        "status": "sent",
        "to": to,
        "subject": subject,
    }

