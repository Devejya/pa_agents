"""
Google Workspace API Routes

Provides REST endpoints for Google Workspace tools.
These can also be used by the agent internally.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.auth import TokenData, get_current_user
from ..tools import (
    # Calendar
    list_calendar_events,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    get_calendar_event,
    # Gmail
    read_emails,
    get_email_by_id,
    send_email,
    search_emails,
    # Contacts
    list_contacts,
    search_contacts,
    get_contact,
    # Drive
    list_drive_files,
    search_drive_files,
    get_file_content,
    # Sheets
    read_spreadsheet,
    write_to_spreadsheet,
    list_spreadsheets,
    # Docs
    read_document,
    create_document,
    list_documents,
    # Slides
    read_presentation,
    list_presentations,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


# ============== Calendar Endpoints ==============

@router.get("/calendar/events")
async def api_list_calendar_events(
    max_results: int = Query(10, le=50),
    days_ahead: int = Query(7, le=30),
    current_user: TokenData = Depends(get_current_user),
):
    """List upcoming calendar events."""
    try:
        return list_calendar_events(
            user_email=current_user.email,
            max_results=max_results,
            days_ahead=days_ahead,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateEventRequest(BaseModel):
    summary: str
    start_time: str
    end_time: str
    description: str = ""
    location: str = ""
    attendees: Optional[list[str]] = None


@router.post("/calendar/events")
async def api_create_calendar_event(
    request: CreateEventRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new calendar event."""
    try:
        return create_calendar_event(
            user_email=current_user.email,
            summary=request.summary,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
            location=request.location,
            attendees=request.attendees,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/events/{event_id}")
async def api_get_calendar_event(
    event_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get a specific calendar event."""
    try:
        return get_calendar_event(
            user_email=current_user.email,
            event_id=event_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/calendar/events/{event_id}")
async def api_delete_calendar_event(
    event_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a calendar event."""
    try:
        return delete_calendar_event(
            user_email=current_user.email,
            event_id=event_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Gmail Endpoints ==============

@router.get("/gmail/messages")
async def api_read_emails(
    max_results: int = Query(10, le=50),
    query: str = Query(""),
    days_back: Optional[int] = Query(None),
    unread_only: bool = Query(False),
    current_user: TokenData = Depends(get_current_user),
):
    """Read emails from inbox."""
    try:
        return read_emails(
            user_email=current_user.email,
            max_results=max_results,
            query=query,
            days_back=days_back,
            unread_only=unread_only,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gmail/messages/{message_id}")
async def api_get_email(
    message_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get a specific email."""
    try:
        return get_email_by_id(
            user_email=current_user.email,
            email_id=message_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    cc: Optional[str] = None
    bcc: Optional[str] = None


@router.post("/gmail/send")
async def api_send_email(
    request: SendEmailRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Send an email."""
    try:
        return send_email(
            user_email=current_user.email,
            to=request.to,
            subject=request.subject,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Contacts Endpoints ==============

@router.get("/contacts")
async def api_list_contacts(
    max_results: int = Query(100, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    """List contacts."""
    try:
        return list_contacts(
            user_email=current_user.email,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/search")
async def api_search_contacts(
    query: str,
    max_results: int = Query(10, le=50),
    current_user: TokenData = Depends(get_current_user),
):
    """Search contacts."""
    try:
        return search_contacts(
            user_email=current_user.email,
            query=query,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Drive Endpoints ==============

@router.get("/drive/files")
async def api_list_drive_files(
    max_results: int = Query(20, le=100),
    folder_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """List Drive files."""
    try:
        return list_drive_files(
            user_email=current_user.email,
            max_results=max_results,
            folder_id=folder_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drive/search")
async def api_search_drive_files(
    query: str,
    max_results: int = Query(20, le=100),
    current_user: TokenData = Depends(get_current_user),
):
    """Search Drive files."""
    try:
        return search_drive_files(
            user_email=current_user.email,
            query=query,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drive/files/{file_id}")
async def api_get_file_content(
    file_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get file metadata and content."""
    try:
        return get_file_content(
            user_email=current_user.email,
            file_id=file_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Sheets Endpoints ==============

@router.get("/sheets")
async def api_list_spreadsheets(
    max_results: int = Query(20, le=100),
    current_user: TokenData = Depends(get_current_user),
):
    """List spreadsheets."""
    try:
        return list_spreadsheets(
            user_email=current_user.email,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sheets/{spreadsheet_id}")
async def api_read_spreadsheet(
    spreadsheet_id: str,
    range_name: str = Query("Sheet1"),
    current_user: TokenData = Depends(get_current_user),
):
    """Read spreadsheet data."""
    try:
        return read_spreadsheet(
            user_email=current_user.email,
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class WriteSheetRequest(BaseModel):
    range_name: str
    values: list[list[Any]]


@router.post("/sheets/{spreadsheet_id}")
async def api_write_to_spreadsheet(
    spreadsheet_id: str,
    request: WriteSheetRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Write to spreadsheet."""
    try:
        return write_to_spreadsheet(
            user_email=current_user.email,
            spreadsheet_id=spreadsheet_id,
            range_name=request.range_name,
            values=request.values,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Docs Endpoints ==============

@router.get("/docs")
async def api_list_documents(
    max_results: int = Query(20, le=100),
    current_user: TokenData = Depends(get_current_user),
):
    """List documents."""
    try:
        return list_documents(
            user_email=current_user.email,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/docs/{document_id}")
async def api_read_document(
    document_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Read document content."""
    try:
        return read_document(
            user_email=current_user.email,
            document_id=document_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateDocRequest(BaseModel):
    title: str
    content: Optional[str] = None


@router.post("/docs")
async def api_create_document(
    request: CreateDocRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new document."""
    try:
        return create_document(
            user_email=current_user.email,
            title=request.title,
            content=request.content,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Slides Endpoints ==============

@router.get("/slides")
async def api_list_presentations(
    max_results: int = Query(20, le=100),
    current_user: TokenData = Depends(get_current_user),
):
    """List presentations."""
    try:
        return list_presentations(
            user_email=current_user.email,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slides/{presentation_id}")
async def api_read_presentation(
    presentation_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Read presentation content."""
    try:
        return read_presentation(
            user_email=current_user.email,
            presentation_id=presentation_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

