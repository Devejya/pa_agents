"""
Google Calendar Tools

Functions for managing Google Calendar events.
"""

from datetime import datetime, timedelta
from typing import Any, Optional

from ..core.google_services import get_calendar_service


def list_calendar_events(
    user_email: str,
    max_results: int = 10,
    days_ahead: int = 7,
    calendar_id: str = "primary",
) -> list[dict]:
    """
    List upcoming calendar events.
    
    Args:
        user_email: User's email for authentication
        max_results: Maximum number of events to return
        days_ahead: Number of days to look ahead
        calendar_id: Calendar ID (default: primary)
        
    Returns:
        List of event dictionaries
    """
    service = get_calendar_service(user_email)
    
    now = datetime.utcnow().isoformat() + "Z"
    time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
    
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=now,
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    
    events = events_result.get("items", [])
    
    return [
        {
            "id": event.get("id"),
            "summary": event.get("summary", "No title"),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "start": event.get("start", {}).get("dateTime") or event.get("start", {}).get("date"),
            "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
            "attendees": [a.get("email") for a in event.get("attendees", [])],
            "status": event.get("status"),
            "html_link": event.get("htmlLink"),
        }
        for event in events
    ]


def get_calendar_event(
    user_email: str,
    event_id: str,
    calendar_id: str = "primary",
) -> dict:
    """
    Get a specific calendar event by ID.
    
    Args:
        user_email: User's email for authentication
        event_id: Event ID
        calendar_id: Calendar ID (default: primary)
        
    Returns:
        Event dictionary
    """
    service = get_calendar_service(user_email)
    
    event = service.events().get(
        calendarId=calendar_id,
        eventId=event_id,
    ).execute()
    
    return {
        "id": event.get("id"),
        "summary": event.get("summary", "No title"),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "start": event.get("start", {}).get("dateTime") or event.get("start", {}).get("date"),
        "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
        "attendees": [
            {"email": a.get("email"), "response": a.get("responseStatus")}
            for a in event.get("attendees", [])
        ],
        "status": event.get("status"),
        "html_link": event.get("htmlLink"),
        "created": event.get("created"),
        "updated": event.get("updated"),
    }


def create_calendar_event(
    user_email: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: Optional[list[str]] = None,
    calendar_id: str = "primary",
    send_notifications: bool = True,
) -> dict:
    """
    Create a new calendar event.
    
    Args:
        user_email: User's email for authentication
        summary: Event title
        start_time: Start time in ISO format (e.g., "2024-01-15T10:00:00")
        end_time: End time in ISO format
        description: Event description
        location: Event location
        attendees: List of attendee email addresses
        calendar_id: Calendar ID (default: primary)
        send_notifications: Whether to send email notifications to attendees
        
    Returns:
        Created event dictionary
    """
    service = get_calendar_service(user_email)
    
    event_body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {
            "dateTime": start_time,
            "timeZone": "America/New_York",  # TODO: Make configurable
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "America/New_York",
        },
    }
    
    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]
    
    event = service.events().insert(
        calendarId=calendar_id,
        body=event_body,
        sendUpdates="all" if send_notifications else "none",
    ).execute()
    
    return {
        "id": event.get("id"),
        "summary": event.get("summary"),
        "html_link": event.get("htmlLink"),
        "start": event.get("start", {}).get("dateTime"),
        "end": event.get("end", {}).get("dateTime"),
        "status": "created",
    }


def update_calendar_event(
    user_email: str,
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    calendar_id: str = "primary",
    send_notifications: bool = True,
) -> dict:
    """
    Update an existing calendar event.
    
    Args:
        user_email: User's email for authentication
        event_id: Event ID to update
        summary: New event title (optional)
        start_time: New start time in ISO format (optional)
        end_time: New end time in ISO format (optional)
        description: New description (optional)
        location: New location (optional)
        calendar_id: Calendar ID (default: primary)
        send_notifications: Whether to send update notifications
        
    Returns:
        Updated event dictionary
    """
    service = get_calendar_service(user_email)
    
    # Get existing event
    event = service.events().get(
        calendarId=calendar_id,
        eventId=event_id,
    ).execute()
    
    # Update fields
    if summary is not None:
        event["summary"] = summary
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location
    if start_time is not None:
        event["start"] = {"dateTime": start_time, "timeZone": "America/New_York"}
    if end_time is not None:
        event["end"] = {"dateTime": end_time, "timeZone": "America/New_York"}
    
    updated_event = service.events().update(
        calendarId=calendar_id,
        eventId=event_id,
        body=event,
        sendUpdates="all" if send_notifications else "none",
    ).execute()
    
    return {
        "id": updated_event.get("id"),
        "summary": updated_event.get("summary"),
        "html_link": updated_event.get("htmlLink"),
        "status": "updated",
    }


def delete_calendar_event(
    user_email: str,
    event_id: str,
    calendar_id: str = "primary",
    send_notifications: bool = True,
) -> dict:
    """
    Delete a calendar event.
    
    Args:
        user_email: User's email for authentication
        event_id: Event ID to delete
        calendar_id: Calendar ID (default: primary)
        send_notifications: Whether to send cancellation notifications
        
    Returns:
        Confirmation dictionary
    """
    service = get_calendar_service(user_email)
    
    service.events().delete(
        calendarId=calendar_id,
        eventId=event_id,
        sendUpdates="all" if send_notifications else "none",
    ).execute()
    
    return {
        "id": event_id,
        "status": "deleted",
    }

