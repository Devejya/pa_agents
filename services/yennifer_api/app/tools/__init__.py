"""
Google Workspace Tools for Yennifer

Provides LangChain-compatible tools for interacting with Google services.
"""

from .calendar_tools import (
    list_calendar_events,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    get_calendar_event,
)

from .gmail_tools import (
    read_emails,
    get_email_by_id,
    send_email,
    search_emails,
)

from .contacts_tools import (
    list_contacts,
    search_contacts,
    get_contact,
)

from .drive_tools import (
    list_drive_files,
    search_drive_files,
    get_file_content,
    create_drive_folder,
    rename_drive_file,
    move_drive_file,
    delete_drive_file,
    copy_drive_file,
)

from .sheets_tools import (
    create_spreadsheet,
    add_sheet_to_spreadsheet,
    read_spreadsheet,
    write_to_spreadsheet,
    list_spreadsheets,
)

from .docs_tools import (
    read_document,
    create_document,
    list_documents,
    append_to_document,
    replace_text_in_document,
    insert_text_at_position,
)

from .slides_tools import (
    read_presentation,
    list_presentations,
    create_presentation,
    add_slide,
    add_text_to_slide,
    delete_slide,
)

__all__ = [
    # Calendar
    "list_calendar_events",
    "create_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "get_calendar_event",
    # Gmail
    "read_emails",
    "get_email_by_id",
    "send_email",
    "search_emails",
    # Contacts
    "list_contacts",
    "search_contacts",
    "get_contact",
    # Drive
    "list_drive_files",
    "search_drive_files",
    "get_file_content",
    "create_drive_folder",
    "rename_drive_file",
    "move_drive_file",
    "delete_drive_file",
    "copy_drive_file",
    # Sheets
    "create_spreadsheet",
    "add_sheet_to_spreadsheet",
    "read_spreadsheet",
    "write_to_spreadsheet",
    "list_spreadsheets",
    # Docs
    "read_document",
    "create_document",
    "list_documents",
    "append_to_document",
    "replace_text_in_document",
    "insert_text_at_position",
    # Slides
    "read_presentation",
    "list_presentations",
    "create_presentation",
    "add_slide",
    "add_text_to_slide",
    "delete_slide",
]

