"""
LangChain Tools for Google Workspace

These tools wrap the Google Workspace functions for use with LangChain agents.

PII Masking:
- Read tools use FULL masking (emails, phones, SSN, cards, etc.)
- Contact lookup tools use FINANCIAL_ONLY (keep email/phone visible)
- Write/action tools don't mask output (they return confirmations)
"""

from typing import Optional
from langchain_core.tools import tool

from .pii import mask_pii, mask_pii_financial_only, MaskingMode
from ..tools import (
    # Calendar
    list_calendar_events as _list_calendar_events,
    create_calendar_event as _create_calendar_event,
    update_calendar_event as _update_calendar_event,
    get_calendar_event as _get_calendar_event,
    delete_calendar_event as _delete_calendar_event,
    # Gmail
    read_emails as _read_emails,
    get_email_by_id as _get_email_by_id,
    send_email as _send_email,
    search_emails as _search_emails,
    # Contacts
    list_contacts as _list_contacts,
    search_contacts as _search_contacts,
    # Drive
    list_drive_files as _list_drive_files,
    search_drive_files as _search_drive_files,
    get_file_content as _get_file_content,
    create_drive_folder as _create_drive_folder,
    rename_drive_file as _rename_drive_file,
    move_drive_file as _move_drive_file,
    delete_drive_file as _delete_drive_file,
    copy_drive_file as _copy_drive_file,
    # Sheets
    create_spreadsheet as _create_spreadsheet,
    add_sheet_to_spreadsheet as _add_sheet_to_spreadsheet,
    list_spreadsheets as _list_spreadsheets,
    read_spreadsheet as _read_spreadsheet,
    write_to_spreadsheet as _write_to_spreadsheet,
    # Docs
    list_documents as _list_documents,
    read_document as _read_document,
    create_document as _create_document,
    append_to_document as _append_to_document,
    replace_text_in_document as _replace_text_in_document,
    # Slides
    list_presentations as _list_presentations,
    read_presentation as _read_presentation,
    create_presentation as _create_presentation,
    add_slide as _add_slide,
    add_text_to_slide as _add_text_to_slide,
    delete_slide as _delete_slide,
)


# Global variable to hold the current user's email
# This is set by the chat handler before invoking the agent
_current_user_email: Optional[str] = None


def set_current_user(email: str):
    """Set the current user email for tool execution."""
    global _current_user_email
    _current_user_email = email


def get_current_user() -> str:
    """Get the current user email."""
    if not _current_user_email:
        raise ValueError("No user email set. Please authenticate first.")
    return _current_user_email


# ============== Utility Tools ==============

@tool
def get_current_datetime() -> str:
    """
    Get the current date and time. Use this FIRST when creating calendar events 
    to know what dates are valid (today and future dates).
    
    Returns:
        Current date, time, and example ISO format for calendar events.
    """
    from datetime import datetime, timedelta
    
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    next_week = now + timedelta(days=7)
    
    return f"""📅 **Current Date & Time:**
- Today: {now.strftime('%A, %B %d, %Y')}
- Current Time: {now.strftime('%I:%M %p')}

**For calendar events, use these ISO date formats:**
- Today at 2pm: `{now.strftime('%Y-%m-%d')}T14:00:00`
- Tomorrow at 10am: `{tomorrow.strftime('%Y-%m-%d')}T10:00:00`
- Next week same day: `{next_week.strftime('%Y-%m-%d')}T10:00:00`

Always use {now.year} or {now.year + 1} for the year (never use past years like 2024)."""


# ============== Calendar Tools ==============

@tool
def list_calendar_events(days_ahead: int = 7) -> str:
    """
    List upcoming calendar events.
    
    Args:
        days_ahead: Number of days to look ahead (default: 7)
        
    Returns:
        List of upcoming events with title, time, and location
    """
    events = _list_calendar_events(
        user_email=get_current_user(),
        max_results=10,
        days_ahead=days_ahead,
    )
    if not events:
        return "No upcoming events found."
    
    result = "Upcoming calendar events:\n"
    for event in events:
        result += f"\n- **{event['summary']}**\n"
        result += f"  Time: {event['start']} to {event['end']}\n"
        if event['location']:
            result += f"  Location: {event['location']}\n"
        if event['attendees']:
            result += f"  Attendees: {', '.join(event['attendees'])}\n"
    
    # Mask PII (emails in attendees, addresses in location)
    return mask_pii(result)


@tool
def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendee_emails: str = "",
) -> str:
    """
    Create a new calendar event with optional attendees.
    
    IMPORTANT: When the user mentions a person's name (e.g., "meeting with Anish"), 
    you MUST first use lookup_contact_email to find their email address, then pass 
    that email to attendee_emails.
    
    Args:
        summary: Event title
        start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS)
        end_time: End time in ISO format (YYYY-MM-DDTHH:MM:SS)
        description: Event description (optional)
        location: Event location (optional, can be "Google Meet" to add video conferencing)
        attendee_emails: Comma-separated list of attendee email addresses (optional).
                         Example: "john@example.com,jane@example.com"
                         ALWAYS use lookup_contact_email first to get emails for names.
        
    Returns:
        Confirmation with event ID and link. Use the returned event_id for updates.
    """
    from datetime import datetime, timedelta
    
    now = datetime.now()
    
    # Validate dates are not in the past
    try:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00').replace('+00:00', ''))
        if start_dt < now - timedelta(days=1):
            return f"❌ Error: The date {start_time} appears to be in the past. Today is {now.strftime('%B %d, %Y')}. Please use a current or future date like {now.strftime('%Y-%m-%d')}T10:00:00"
    except Exception as e:
        pass
    
    # Parse attendee emails
    attendees = None
    if attendee_emails and attendee_emails.strip():
        attendees = [email.strip() for email in attendee_emails.split(",") if email.strip()]
    
    result = _create_calendar_event(
        user_email=get_current_user(),
        summary=summary,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
        attendees=attendees,
    )
    
    response = f"✅ Event created: **{result['summary']}**\nEvent ID: `{result['id']}`\nLink: {result['html_link']}"
    if attendees:
        response += f"\nAttendees invited: {', '.join(attendees)}"
    response += f"\n\nUse Event ID `{result['id']}` if you need to update this event."
    return response


@tool
def update_calendar_event(
    event_id: str,
    summary: str = "",
    start_time: str = "",
    end_time: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """
    Update an existing calendar event.
    
    IMPORTANT: You must use the exact event_id returned from create_calendar_event.
    
    Args:
        event_id: The exact Event ID from create_calendar_event (e.g., "abc123xyz")
        summary: New title (leave empty to keep current)
        start_time: New start time in ISO format YYYY-MM-DDTHH:MM:SS (leave empty to keep current)
        end_time: New end time in ISO format (leave empty to keep current)
        description: New description (leave empty to keep current)
        location: New location (leave empty to keep current)
        
    Returns:
        Confirmation with updated event info
    """
    result = _update_calendar_event(
        user_email=get_current_user(),
        event_id=event_id,
        summary=summary if summary else None,
        start_time=start_time if start_time else None,
        end_time=end_time if end_time else None,
        description=description if description else None,
        location=location if location else None,
    )
    return f"✅ Event updated: **{result['summary']}**\nLink: {result['html_link']}"


@tool
def delete_calendar_event(event_id: str) -> str:
    """
    Delete a calendar event by ID.
    
    Args:
        event_id: The event ID to delete
        
    Returns:
        Confirmation message
    """
    _delete_calendar_event(user_email=get_current_user(), event_id=event_id)
    return f"✅ Event deleted successfully."


# ============== Gmail Tools ==============

@tool
def read_recent_emails(max_results: int = 10, days_back: int = 7) -> str:
    """
    Read recent emails from inbox.
    
    Args:
        max_results: Maximum number of emails to fetch (default: 10)
        days_back: Only fetch emails from last N days (default: 7)
        
    Returns:
        List of emails with subject, sender, and snippet
    """
    emails = _read_emails(
        user_email=get_current_user(),
        max_results=max_results,
        days_back=days_back,
    )
    if not emails:
        return "No emails found."
    
    result = f"Found {len(emails)} emails:\n"
    for email in emails:
        result += f"\n- **{email['subject']}**\n"
        result += f"  From: {email['from']}\n"
        result += f"  Date: {email['date']}\n"
        result += f"  {email['snippet'][:100]}...\n"
        result += f"  ID: {email['id']}\n"
    
    # Mask PII in email content (addresses, SSN, cards, etc.)
    return mask_pii(result)


@tool
def search_emails(query: str, max_results: int = 10) -> str:
    """
    Search emails using Gmail search query.
    
    Args:
        query: Gmail search query (e.g., "from:john subject:meeting")
        max_results: Maximum results to return (default: 10)
        
    Returns:
        List of matching emails
    """
    emails = _search_emails(
        user_email=get_current_user(),
        query=query,
        max_results=max_results,
    )
    if not emails:
        return f"No emails found matching: {query}"
    
    result = f"Found {len(emails)} emails matching '{query}':\n"
    for email in emails:
        result += f"\n- **{email['subject']}**\n"
        result += f"  From: {email['from']}\n"
        result += f"  Date: {email['date']}\n"
        result += f"  ID: {email['id']}\n"
    
    # Mask PII in email metadata
    return mask_pii(result)


@tool
def get_email_details(email_id: str) -> str:
    """
    Get full details of a specific email by ID.
    
    Args:
        email_id: Gmail message ID
        
    Returns:
        Full email content
    """
    email = _get_email_by_id(user_email=get_current_user(), email_id=email_id)
    
    result = f"**{email['subject']}**\n"
    result += f"From: {email['from']}\n"
    result += f"To: {email['to']}\n"
    result += f"Date: {email['date']}\n\n"
    result += f"{email['body']}"
    
    # Mask PII in full email content (critical - body may contain sensitive data)
    return mask_pii(result)


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        
    Returns:
        Confirmation message
    """
    result = _send_email(
        user_email=get_current_user(),
        to=to,
        subject=subject,
        body=body,
    )
    return f"✅ Email sent to {to}\nSubject: {subject}"


# ============== Contacts Tools ==============

@tool
def list_my_contacts(max_results: int = 20) -> str:
    """
    List contacts from Google Contacts.
    
    Args:
        max_results: Maximum number of contacts (default: 20)
        
    Returns:
        List of contacts with name and email
    """
    contacts = _list_contacts(
        user_email=get_current_user(),
        max_results=max_results,
    )
    if not contacts:
        return "No contacts found."
    
    result = f"Found {len(contacts)} contacts:\n"
    for contact in contacts:
        result += f"\n- **{contact['name']}**"
        if contact['emails']:
            result += f" - {contact['emails'][0]}"
        if contact['organization']:
            result += f" ({contact['organization']})"
        result += "\n"
    
    # Use FINANCIAL_ONLY - keep emails/phones visible for contact queries
    return mask_pii_financial_only(result)


@tool
def search_my_contacts(query: str) -> str:
    """
    Search contacts by name or email.
    
    Args:
        query: Search query (name or email)
        
    Returns:
        Matching contacts
    """
    contacts = _search_contacts(
        user_email=get_current_user(),
        query=query,
    )
    if not contacts:
        return f"No contacts found matching: {query}"
    
    result = f"Contacts matching '{query}':\n"
    for contact in contacts:
        result += f"\n- **{contact['name']}**"
        if contact['emails']:
            result += f"\n  Email: {contact['emails'][0]}"
        if contact['phones']:
            result += f"\n  Phone: {contact['phones'][0]}"
        result += "\n"
    
    # Use FINANCIAL_ONLY - keep emails/phones visible for contact queries
    return mask_pii_financial_only(result)


# ============== Drive Tools ==============

@tool
def list_drive_files(max_results: int = 20) -> str:
    """
    List recent files in Google Drive.
    
    Args:
        max_results: Maximum number of files (default: 20)
        
    Returns:
        List of files with name and type
    """
    files = _list_drive_files(
        user_email=get_current_user(),
        max_results=max_results,
    )
    if not files:
        return "No files found in Drive."
    
    result = "Recent files in Drive:\n\n"
    for i, f in enumerate(files, 1):
        link = f.get('web_link') or f"ID: {f['id']}"
        if f.get('web_link'):
            result += f"{i}. **[{f['name']}]({link})** ({f['mime_type']})\n"
        else:
            result += f"{i}. **{f['name']}** ({f['mime_type']}) - {link}\n"
    return result


@tool
def search_drive(query: str) -> str:
    """
    Search files in Google Drive.
    
    Args:
        query: Search query (file name)
        
    Returns:
        Matching files
    """
    files = _search_drive_files(
        user_email=get_current_user(),
        query=query,
    )
    if not files:
        return f"No files found matching: {query}"
    
    result = f"Files matching '{query}':\n\n"
    for i, f in enumerate(files, 1):
        result += f"{i}. **[{f['name']}]({f['web_link']})**\n"
    return result


@tool
def create_drive_folder(folder_name: str, parent_folder_id: str = "") -> str:
    """
    Create a new folder in Google Drive.
    
    Args:
        folder_name: Name for the new folder
        parent_folder_id: Parent folder ID (leave empty for root)
        
    Returns:
        Created folder info with link
    """
    result = _create_drive_folder(
        user_email=get_current_user(),
        folder_name=folder_name,
        parent_folder_id=parent_folder_id if parent_folder_id else None,
    )
    return f"✅ Folder created: **{result['name']}**\nID: {result['id']}\nLink: {result['web_link']}"


@tool
def rename_drive_file(file_id: str, new_name: str) -> str:
    """
    Rename a file or folder in Google Drive.
    
    Args:
        file_id: File or folder ID to rename
        new_name: New name
        
    Returns:
        Updated file info
    """
    result = _rename_drive_file(
        user_email=get_current_user(),
        file_id=file_id,
        new_name=new_name,
    )
    return f"✅ Renamed to: **{result['name']}**\nLink: {result['web_link']}"


@tool
def move_drive_file(file_id: str, new_parent_id: str) -> str:
    """
    Move a file to a different folder in Google Drive.
    
    Args:
        file_id: File ID to move
        new_parent_id: Destination folder ID
        
    Returns:
        Confirmation
    """
    result = _move_drive_file(
        user_email=get_current_user(),
        file_id=file_id,
        new_parent_id=new_parent_id,
    )
    return f"✅ Moved **{result['name']}** to new folder\nLink: {result['web_link']}"


@tool
def delete_drive_file(file_id: str, permanent: bool = False) -> str:
    """
    Delete a file from Google Drive.
    
    Args:
        file_id: File ID to delete
        permanent: If true, permanently delete. If false, move to trash.
        
    Returns:
        Confirmation
    """
    result = _delete_drive_file(
        user_email=get_current_user(),
        file_id=file_id,
        permanent=permanent,
    )
    action = "permanently deleted" if permanent else "moved to trash"
    return f"✅ File {action}."


@tool
def copy_drive_file(file_id: str, new_name: str = "") -> str:
    """
    Copy a file in Google Drive.
    
    Args:
        file_id: File ID to copy
        new_name: Name for the copy (leave empty to auto-generate)
        
    Returns:
        New file info
    """
    result = _copy_drive_file(
        user_email=get_current_user(),
        file_id=file_id,
        new_name=new_name if new_name else None,
    )
    return f"✅ File copied: **{result['name']}**\nID: {result['id']}\nLink: {result['web_link']}"


# ============== Sheets Tools ==============

@tool
def create_new_spreadsheet(title: str, sheet_names: str = "Sheet1") -> str:
    """
    Create a new Google Spreadsheet.
    
    Args:
        title: Spreadsheet title
        sheet_names: Comma-separated list of sheet names (default: "Sheet1")
        
    Returns:
        Confirmation with link
    """
    # Parse sheet names from comma-separated string
    sheets = [s.strip() for s in sheet_names.split(",") if s.strip()]
    if not sheets:
        sheets = ["Sheet1"]
    
    result = _create_spreadsheet(
        user_email=get_current_user(),
        title=title,
        sheet_names=sheets,
    )
    sheets_list = ", ".join(result["sheets"])
    return f"✅ Spreadsheet created: **{result['title']}**\nSheets: {sheets_list}\nLink: {result['web_link']}"


@tool
def add_sheet_to_spreadsheet(spreadsheet_id: str, sheet_name: str) -> str:
    """
    Add a new sheet tab to an existing spreadsheet.
    
    Args:
        spreadsheet_id: The spreadsheet ID
        sheet_name: Name for the new sheet
        
    Returns:
        Confirmation message
    """
    result = _add_sheet_to_spreadsheet(
        user_email=get_current_user(),
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
    )
    return f"✅ Sheet '{result['sheet_name']}' added to spreadsheet.\nLink: {result['web_link']}"


@tool
def write_spreadsheet_data(spreadsheet_id: str, range_name: str, data: str) -> str:
    """
    Write data to a Google Spreadsheet.
    
    Args:
        spreadsheet_id: The spreadsheet ID
        range_name: Sheet and range to write (e.g., "Sheet1!A1")
        data: Data to write as rows, separated by newlines; columns separated by pipes (|)
              Example: "Name|Age|City\\nJohn|30|NYC\\nJane|25|LA"
        
    Returns:
        Confirmation message
    """
    # Parse the data string into 2D list
    rows = data.strip().split("\n")
    values = [row.split("|") for row in rows]
    
    result = _write_to_spreadsheet(
        user_email=get_current_user(),
        spreadsheet_id=spreadsheet_id,
        range_name=range_name,
        values=values,
    )
    return f"✅ Data written to spreadsheet.\nUpdated {result['updated_cells']} cells in range {result['updated_range']}"


@tool
def list_spreadsheets() -> str:
    """
    List Google Sheets spreadsheets.
    
    Returns:
        List of spreadsheets with links
    """
    sheets = _list_spreadsheets(user_email=get_current_user())
    if not sheets:
        return "No spreadsheets found."
    
    result = "Your spreadsheets:\n\n"
    for i, s in enumerate(sheets, 1):
        link = s.get('web_link') or f"https://docs.google.com/spreadsheets/d/{s['id']}"
        result += f"{i}. **[{s['name']}]({link})**\n"
    return result


@tool
def search_spreadsheets(search_term: str) -> str:
    """
    Search for Google Sheets spreadsheets by name.
    
    IMPORTANT: Always use this tool FIRST before read_spreadsheet_data
    when the user mentions a spreadsheet by name. This returns the
    spreadsheet ID needed for reading data.
    
    Args:
        search_term: Name or partial name to search for (case-insensitive)
        
    Returns:
        Matching spreadsheets with links and IDs
    """
    sheets = _list_spreadsheets(
        user_email=get_current_user(),
        search_query=search_term,
    )
    if not sheets:
        return f"No spreadsheets found matching '{search_term}'. Try list_spreadsheets to see all available spreadsheets."
    
    result = f"Spreadsheets matching '{search_term}':\n\n"
    for i, s in enumerate(sheets, 1):
        link = s.get('web_link') or f"https://docs.google.com/spreadsheets/d/{s['id']}"
        result += f"{i}. **[{s['name']}]({link})** (ID: `{s['id']}`)\n"
    
    result += "\n💡 Use the ID above with read_spreadsheet_data to access the spreadsheet."
    return result


@tool
def read_spreadsheet_data(spreadsheet_id: str, range_name: str = "Sheet1") -> str:
    """
    Read data from a Google Sheets spreadsheet.
    
    IMPORTANT: You must use the actual spreadsheet ID (a long alphanumeric string),
    NOT the spreadsheet name. If you only have the name, use search_spreadsheets
    first to find the ID.
    
    Args:
        spreadsheet_id: The spreadsheet ID (from search_spreadsheets or list_spreadsheets)
        range_name: Sheet name and optional range. CRITICAL SYNTAX:
            - For sheet named "Sheet1": use "Sheet1" or "Sheet1!A1:Z100"
            - For sheets with names like P0, P1, Q1 (that look like cell refs):
              MUST quote the name: "'P1'" or "'P1'!A1:Z100"
            - Common mistake: "P1" alone means cell P1 on first sheet, NOT sheet named P1!
        
    Returns:
        Spreadsheet data as text
        
    Examples:
        - range_name="Sheet1" → reads all of Sheet1
        - range_name="'P1'" → reads all of sheet named "P1" (quoted!)
        - range_name="'P1'!A1:D50" → reads A1:D50 from sheet named "P1"
        - range_name="Tickets!A:Z" → reads columns A-Z from sheet named "Tickets"
    """
    try:
        data = _read_spreadsheet(
            user_email=get_current_user(),
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
        )
    except ValueError as e:
        # Return the helpful error message from the underlying function
        return f"Error: {str(e)}"
    
    result = f"**{data['title']}** - {data['range']}\n"
    result += f"Available sheets: {', '.join(data['sheets'])}\n\n"
    
    # Check if data is empty
    if not data['values']:
        result += "(No data found in this range)\n\n"
        # Provide helpful guidance if the range looks like a cell reference
        # but there are sheets with similar names
        if range_name and not range_name.startswith("'"):
            matching_sheets = [s for s in data['sheets'] if s.upper() == range_name.upper() or 
                             (len(range_name) <= 3 and range_name.upper() in [s.upper() for s in data['sheets']])]
            if matching_sheets or any(s in ['P0', 'P1', 'P2', 'Q1', 'Q2'] for s in data['sheets']):
                result += "💡 **Tip:** If you meant to read a sheet named like 'P1' or 'P0', "
                result += "you must quote the name: range_name=\"'P1'\" or \"'P1'!A1:Z100\"\n"
                result += f"   Available sheets: {', '.join(data['sheets'])}\n"
        return result
    
    for row in data['values'][:20]:  # Limit rows
        result += " | ".join(str(cell) for cell in row) + "\n"
    
    if data['row_count'] > 20:
        result += f"\n... ({data['row_count'] - 20} more rows)"
    
    # Mask PII in spreadsheet data (may contain sensitive information)
    return mask_pii(result)


# ============== Docs Tools ==============

@tool
def list_google_docs() -> str:
    """
    List Google Docs documents.
    
    Returns:
        List of documents with links
    """
    docs = _list_documents(user_email=get_current_user())
    if not docs:
        return "No documents found."
    
    result = "Your documents:\n\n"
    for i, d in enumerate(docs, 1):
        link = d.get('web_link') or f"https://docs.google.com/document/d/{d['id']}"
        result += f"{i}. **[{d['name']}]({link})**\n"
    return result


@tool
def read_google_doc(document_id: str) -> str:
    """
    Read content from a Google Doc.
    
    Args:
        document_id: Document ID
        
    Returns:
        Document content
    """
    doc = _read_document(
        user_email=get_current_user(),
        document_id=document_id,
    )
    result = f"**{doc['title']}**\n\n{doc['content']}"
    
    # Mask PII in document content (critical - docs may contain sensitive data)
    return mask_pii(result)


@tool
def create_google_doc(title: str, content: str = "") -> str:
    """
    Create a new Google Doc.
    
    Args:
        title: Document title
        content: Initial content (optional)
        
    Returns:
        Confirmation with link
    """
    doc = _create_document(
        user_email=get_current_user(),
        title=title,
        content=content,
    )
    return f"✅ Document created: **{doc['title']}**\nLink: {doc['web_link']}"


@tool
def append_to_google_doc(document_id: str, text: str) -> str:
    """
    Append text to the end of a Google Doc.
    
    Args:
        document_id: Document ID
        text: Text to append at the end
        
    Returns:
        Confirmation
    """
    result = _append_to_document(
        user_email=get_current_user(),
        document_id=document_id,
        text=text,
    )
    return f"✅ Text appended to **{result['title']}**\nLink: {result['web_link']}"


@tool
def find_replace_in_doc(document_id: str, find_text: str, replace_text: str) -> str:
    """
    Find and replace text in a Google Doc.
    
    Args:
        document_id: Document ID
        find_text: Text to find
        replace_text: Text to replace with
        
    Returns:
        Number of replacements made
    """
    result = _replace_text_in_document(
        user_email=get_current_user(),
        document_id=document_id,
        find_text=find_text,
        replace_text=replace_text,
    )
    return f"✅ Replaced {result['replacements_made']} occurrence(s) of '{find_text}' with '{replace_text}'\nLink: {result['web_link']}"


# ============== Slides Tools ==============

@tool
def list_presentations() -> str:
    """
    List Google Slides presentations.
    
    Returns:
        List of presentations with links
    """
    slides = _list_presentations(user_email=get_current_user())
    if not slides:
        return "No presentations found."
    
    result = "Your presentations:\n\n"
    for i, s in enumerate(slides, 1):
        link = s.get('web_link') or f"https://docs.google.com/presentation/d/{s['id']}"
        result += f"{i}. **[{s['name']}]({link})**\n"
    return result


@tool
def read_presentation_content(presentation_id: str) -> str:
    """
    Read content from a Google Slides presentation.
    
    Args:
        presentation_id: Presentation ID
        
    Returns:
        Presentation content (slide by slide)
    """
    pres = _read_presentation(
        user_email=get_current_user(),
        presentation_id=presentation_id,
    )
    
    result = f"**{pres['title']}** ({pres['slide_count']} slides)\n"
    for slide in pres['slides']:
        result += f"\n--- Slide {slide['slide_number']} ---\n"
        result += slide['content'] + "\n"
    
    # Mask PII in presentation content
    return mask_pii(result)


@tool
def create_slides_presentation(title: str) -> str:
    """
    Create a new Google Slides presentation.
    
    Args:
        title: Presentation title
        
    Returns:
        Created presentation info with presentation_id and link. Use the presentation_id for adding slides.
    """
    pres = _create_presentation(
        user_email=get_current_user(),
        title=title,
    )
    return f"✅ Presentation created: **{pres['title']}**\n\nPresentation ID: `{pres['presentation_id']}`\nLink: {pres['web_link']}\n\nIMPORTANT: Use Presentation ID `{pres['presentation_id']}` to add slides to this presentation."


@tool
def add_slide_to_presentation(
    presentation_id: str,
    layout: str = "BLANK",
) -> str:
    """
    Add a new slide to a presentation.
    
    Args:
        presentation_id: Presentation ID
        layout: Slide layout (BLANK, TITLE, TITLE_AND_BODY, SECTION_HEADER, etc.)
        
    Returns:
        New slide info
    """
    result = _add_slide(
        user_email=get_current_user(),
        presentation_id=presentation_id,
        layout=layout,
    )
    return f"✅ Slide added to presentation\nSlide ID: {result['slide_id']}\nLayout: {result['layout']}\nLink: {result['web_link']}"


@tool
def add_text_to_presentation_slide(
    presentation_id: str,
    slide_id: str,
    text: str,
    x: float = 100,
    y: float = 100,
    width: float = 400,
    height: float = 100,
) -> str:
    """
    Add a text box to a slide.
    
    Args:
        presentation_id: Presentation ID
        slide_id: Slide object ID (get from add_slide_to_presentation or read_presentation_content)
        text: Text content to add
        x: X position in points (default: 100)
        y: Y position in points (default: 100)
        width: Text box width in points (default: 400)
        height: Text box height in points (default: 100)
        
    Returns:
        Confirmation
    """
    result = _add_text_to_slide(
        user_email=get_current_user(),
        presentation_id=presentation_id,
        slide_id=slide_id,
        text=text,
        x=x,
        y=y,
        width=width,
        height=height,
    )
    return f"✅ Text added to slide\nElement ID: {result['element_id']}\nLink: {result['web_link']}"


@tool
def delete_presentation_slide(presentation_id: str, slide_id: str) -> str:
    """
    Delete a slide from a presentation.
    
    Args:
        presentation_id: Presentation ID
        slide_id: Slide object ID to delete
        
    Returns:
        Confirmation
    """
    _delete_slide(
        user_email=get_current_user(),
        presentation_id=presentation_id,
        slide_id=slide_id,
    )
    return f"✅ Slide deleted from presentation"


# ============================================================================
# Contact Sync Tool (User Network Integration)
# ============================================================================

@tool
def sync_contacts_to_database() -> str:
    """
    Sync and import Google Contacts to Yennifer's database.
    
    This tool syncs/stores/saves/imports the user's Google Contacts into Yennifer's 
    contact database, enabling relationship management and intelligent assistance.
    
    ALWAYS use this tool when the user asks to:
    - "sync contacts" or "sync my contacts"
    - "store contacts" or "store my contacts in database"
    - "save contacts to database"
    - "import contacts" or "import my Google contacts"
    - "update contact database"
    - "add contacts to your database"
    
    Returns:
        Confirmation that sync has been triggered.
    """
    import threading
    import requests
    
    user_email = get_current_user()
    if not user_email:
        return "❌ Unable to sync: No authenticated user. Please log in first."
    
    def run_sync():
        """Run sync in background thread via internal HTTP call."""
        try:
            # Trigger sync via internal jobs API endpoint
            response = requests.post(
                "http://127.0.0.1:8000/api/v1/jobs/sync/contacts/internal",
                json={"user_email": user_email},
                timeout=300,
            )
            if response.ok:
                result = response.json()
                print(f"Sync result for {user_email}: {result}")
            else:
                print(f"Sync failed for {user_email}: {response.text}")
        except Exception as e:
            print(f"Sync error for {user_email}: {e}")
    
    # Start sync in background thread
    thread = threading.Thread(target=run_sync, daemon=True)
    thread.start()
    
    return (
        "✅ Contact sync has been started! "
        "Your Google Contacts are being imported into my database. "
        "You'll receive an email notification when the sync is complete. "
        "You can check the Contacts page in a minute to see your synced contacts."
    )


# ============================================================================
# User Profile Tool (User Network Integration)
# ============================================================================

@tool
def get_my_profile() -> str:
    """
    Get the current user's profile information.
    
    Use this tool when the user asks about themselves, such as:
    - "Who am I?"
    - "What do you know about me?"
    - "What's my profile?"
    - "Tell me about myself"
    - "What information do you have about me?"
    
    Returns:
        The user's profile information including name, email, company, title, etc.
    """
    import requests
    
    user_email = get_current_user()
    if not user_email:
        return "I don't have access to your profile information. Please log in first."
    
    try:
        # Call the User Network API to get core user profile
        from ..core.config import get_settings
        settings = get_settings()
        
        response = requests.get(
            f"{settings.user_network_api_url}/api/v1/persons/core-user",
            headers={
                "X-API-Key": settings.user_network_api_key,
                "Content-Type": "application/json"
            },
            timeout=10,
        )
        
        if response.status_code == 404:
            return f"I know your email is {user_email}, but I don't have additional profile information stored yet. You can tell me more about yourself!"
        
        if not response.ok:
            return f"I know your email is {user_email}, but I couldn't retrieve your full profile right now."
        
        profile = response.json()
        
        # Build a friendly response
        parts = []
        
        name = profile.get('name') or f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        if name and name != user_email:
            parts.append(f"**Name:** {name}")
        
        parts.append(f"**Email:** {user_email}")
        
        if profile.get('company'):
            parts.append(f"**Company:** {profile.get('company')}")
        
        if profile.get('latest_title'):
            parts.append(f"**Title:** {profile.get('latest_title')}")
        
        if profile.get('city') or profile.get('country'):
            location = ", ".join(filter(None, [profile.get('city'), profile.get('country')]))
            parts.append(f"**Location:** {location}")
        
        if profile.get('personal_cell') or profile.get('work_cell'):
            phone = profile.get('personal_cell') or profile.get('work_cell')
            parts.append(f"**Phone:** {phone}")
        
        if profile.get('interests'):
            interests = profile.get('interests')
            if isinstance(interests, list) and interests:
                parts.append(f"**Interests:** {', '.join([i.get('name', str(i)) if isinstance(i, dict) else str(i) for i in interests])}")
        
        if parts:
            result = "Here's what I know about you:\n\n" + "\n".join(parts)
        else:
            result = f"I know your email is {user_email}, but I don't have much other information stored about you yet."
        
        # Use FINANCIAL_ONLY - user expects to see their own contact info
        return mask_pii_financial_only(result)
            
    except Exception as e:
        return f"I know your email is {user_email}, but I encountered an error retrieving your profile: {str(e)}"


@tool
def lookup_contact_email(name: str) -> str:
    """
    Look up a contact's email address by their name from the User Network database.
    
    IMPORTANT: Use this tool BEFORE creating calendar events or sending emails when 
    the user mentions a person by name. This finds their email so you can invite them.
    
    Args:
        name: The person's name to look up (e.g., "Anish", "Mark Ryan", "John Smith")
        
    Returns:
        The contact's email address if found, or a message if not found.
        
    Example usage:
        - User says "set up a meeting with Anish"
        - First call lookup_contact_email("Anish") to get their email
        - Then use that email in create_calendar_event's attendee_emails parameter
    """
    import requests
    
    user_email = get_current_user()
    if not user_email:
        return "Unable to look up contacts: Please log in first."
    
    try:
        from ..core.config import get_settings
        settings = get_settings()
        
        # Search the User Network API for contacts matching the name
        response = requests.get(
            f"{settings.user_network_api_url}/api/v1/persons",
            headers={
                "X-API-Key": settings.user_network_api_key,
                "Content-Type": "application/json"
            },
            params={"limit": 100},
            timeout=10,
        )
        
        if not response.ok:
            return f"Could not search contacts: API error {response.status_code}"
        
        persons = response.json()
        
        # Search for matching contacts (case-insensitive)
        name_lower = name.lower().strip()
        matches = []
        
        for person in persons:
            # Skip the core user (don't match against yourself)
            if person.get('is_core_user'):
                continue
                
            # Check various name fields
            full_name = person.get('name', '') or ''
            first_name = person.get('first_name', '') or ''
            last_name = person.get('last_name', '') or ''
            
            # Build searchable names
            person_names = [
                full_name.lower(),
                first_name.lower(),
                last_name.lower(),
                f"{first_name} {last_name}".lower().strip(),
            ]
            
            # Check for match
            if any(name_lower in pn or pn in name_lower for pn in person_names if pn):
                # Get the best email
                email = person.get('work_email') or person.get('personal_email')
                if email:
                    display_name = full_name or f"{first_name} {last_name}".strip() or email
                    matches.append({
                        'name': display_name,
                        'email': email,
                        'company': person.get('company'),
                    })
        
        if not matches:
            return f"No contact found with name '{name}'. Try searching with a different spelling or check the Contacts page."
        
        if len(matches) == 1:
            m = matches[0]
            result = f"Found contact: **{m['name']}**\nEmail: {m['email']}"
            if m['company']:
                result += f"\nCompany: {m['company']}"
            result += f"\n\n✅ Use email `{m['email']}` when creating calendar events or sending emails."
            # Use FINANCIAL_ONLY - user expects to see contact info
            return mask_pii_financial_only(result)
        
        # Multiple matches
        result = f"Found {len(matches)} contacts matching '{name}':\n"
        for m in matches:
            result += f"\n- **{m['name']}**: {m['email']}"
            if m['company']:
                result += f" ({m['company']})"
        result += "\n\nPlease specify which contact's email you'd like to use."
        # Use FINANCIAL_ONLY - user expects to see contact info
        return mask_pii_financial_only(result)
        
    except Exception as e:
        return f"Error looking up contact: {str(e)}"


# Export all tools
WORKSPACE_TOOLS = [
    # Utility
    get_current_datetime,
    get_my_profile,  # User profile from User Network
    lookup_contact_email,  # Look up contact email by name (for calendar invites, emails)
    # Calendar
    list_calendar_events,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    # Gmail
    read_recent_emails,
    search_emails,
    get_email_details,
    send_email,
    # Contacts
    list_my_contacts,
    search_my_contacts,
    sync_contacts_to_database,  # Sync Google Contacts to User Network
    # Drive
    list_drive_files,
    search_drive,
    create_drive_folder,
    rename_drive_file,
    move_drive_file,
    delete_drive_file,
    copy_drive_file,
    # Sheets
    create_new_spreadsheet,
    add_sheet_to_spreadsheet,
    write_spreadsheet_data,
    list_spreadsheets,
    search_spreadsheets,  # Search by name to find spreadsheet ID
    read_spreadsheet_data,
    # Docs
    list_google_docs,
    read_google_doc,
    create_google_doc,
    append_to_google_doc,
    find_replace_in_doc,
    # Slides
    list_presentations,
    read_presentation_content,
    create_slides_presentation,
    add_slide_to_presentation,
    add_text_to_presentation_slide,
    delete_presentation_slide,
]

