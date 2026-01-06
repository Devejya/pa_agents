"""
Email Reading Tools

Fetch and parse emails from Gmail.
"""

import base64
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from ..auth import get_gmail_service


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
    max_results: int = 10,
    query: str = "",
    days_back: Optional[int] = None,
    unread_only: bool = False,
) -> list[dict]:
    """
    Read emails from Gmail inbox.
    
    Args:
        max_results: Maximum number of emails to fetch (default 10)
        query: Gmail search query (e.g., "from:boss@company.com")
        days_back: Only fetch emails from last N days
        unread_only: Only fetch unread emails
        
    Returns:
        List of email dictionaries with id, subject, from, date, snippet, body
    """
    service = get_gmail_service()
    
    # Build query
    query_parts = [query] if query else []
    
    if days_back:
        date_after = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        query_parts.append(f"after:{date_after}")
    
    if unread_only:
        query_parts.append("is:unread")
    
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
        
        email_data = {
            "id": msg["id"],
            "thread_id": full_msg.get("threadId"),
            "subject": _get_header(headers, "Subject"),
            "from": _get_header(headers, "From"),
            "to": _get_header(headers, "To"),
            "date": _get_header(headers, "Date"),
            "snippet": full_msg.get("snippet", ""),
            "body": _decode_body(full_msg.get("payload", {})),
            "labels": full_msg.get("labelIds", []),
            "is_unread": "UNREAD" in full_msg.get("labelIds", []),
        }
        emails.append(email_data)
    
    return emails


def get_email_by_id(email_id: str) -> dict:
    """
    Get a specific email by its ID.
    
    Args:
        email_id: Gmail message ID
        
    Returns:
        Email dictionary with full details
    """
    service = get_gmail_service()
    
    full_msg = service.users().messages().get(
        userId="me",
        id=email_id,
        format="full"
    ).execute()
    
    headers = full_msg.get("payload", {}).get("headers", [])
    
    return {
        "id": email_id,
        "thread_id": full_msg.get("threadId"),
        "subject": _get_header(headers, "Subject"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "date": _get_header(headers, "Date"),
        "snippet": full_msg.get("snippet", ""),
        "body": _decode_body(full_msg.get("payload", {})),
        "labels": full_msg.get("labelIds", []),
        "is_unread": "UNREAD" in full_msg.get("labelIds", []),
    }



