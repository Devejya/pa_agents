"""
Google Sheets Tools

Functions for reading and writing Google Sheets.
"""

from typing import Any, Optional

from ..core.google_services import get_sheets_service, get_drive_service


def create_spreadsheet(
    user_email: str,
    title: str,
    sheet_names: Optional[list[str]] = None,
    initial_data: Optional[dict[str, list[list[Any]]]] = None,
) -> dict:
    """
    Create a new Google Spreadsheet.
    
    Args:
        user_email: User's email for authentication
        title: Spreadsheet title
        sheet_names: Optional list of sheet names to create (default: ["Sheet1"])
        initial_data: Optional dict mapping sheet names to 2D list of values
        
    Returns:
        Created spreadsheet info including ID and link
    """
    service = get_sheets_service(user_email)
    
    # Prepare sheets
    if not sheet_names:
        sheet_names = ["Sheet1"]
    
    sheets = [
        {"properties": {"title": name}}
        for name in sheet_names
    ]
    
    # Create spreadsheet
    spreadsheet_body = {
        "properties": {"title": title},
        "sheets": sheets,
    }
    
    spreadsheet = service.spreadsheets().create(body=spreadsheet_body).execute()
    spreadsheet_id = spreadsheet.get("spreadsheetId")
    
    # Add initial data if provided
    if initial_data:
        for sheet_name, values in initial_data.items():
            if values:
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                ).execute()
    
    return {
        "spreadsheet_id": spreadsheet_id,
        "title": title,
        "sheets": sheet_names,
        "web_link": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        "status": "created",
    }


def add_sheet_to_spreadsheet(
    user_email: str,
    spreadsheet_id: str,
    sheet_name: str,
    initial_data: Optional[list[list[Any]]] = None,
) -> dict:
    """
    Add a new sheet tab to an existing spreadsheet.
    
    Args:
        user_email: User's email for authentication
        spreadsheet_id: Existing spreadsheet ID
        sheet_name: Name for the new sheet
        initial_data: Optional 2D list of initial values
        
    Returns:
        Result info including sheet ID
    """
    service = get_sheets_service(user_email)
    
    # Add new sheet
    request_body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": sheet_name,
                    }
                }
            }
        ]
    }
    
    response = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=request_body,
    ).execute()
    
    new_sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]
    
    # Add initial data if provided
    if initial_data:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": initial_data},
        ).execute()
    
    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "sheet_id": new_sheet_id,
        "web_link": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        "status": "added",
    }


def list_spreadsheets(
    user_email: str,
    max_results: int = 20,
) -> list[dict]:
    """
    List Google Sheets spreadsheets in Drive.
    
    Args:
        user_email: User's email for authentication
        max_results: Maximum number of spreadsheets to return
        
    Returns:
        List of spreadsheet dictionaries
    """
    service = get_drive_service(user_email)
    
    results = service.files().list(
        pageSize=max_results,
        q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
        fields="files(id, name, createdTime, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc",
    ).execute()
    
    files = results.get("files", [])
    
    return [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "created_time": f.get("createdTime"),
            "modified_time": f.get("modifiedTime"),
            "web_link": f.get("webViewLink"),
        }
        for f in files
    ]


def read_spreadsheet(
    user_email: str,
    spreadsheet_id: str,
    range_name: str = "Sheet1",
) -> dict:
    """
    Read data from a Google Sheets spreadsheet.
    
    Args:
        user_email: User's email for authentication
        spreadsheet_id: Spreadsheet ID
        range_name: Sheet and range to read (e.g., "Sheet1!A1:D10")
        
    Returns:
        Spreadsheet data including values
    """
    service = get_sheets_service(user_email)
    
    # Get spreadsheet metadata
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
    ).execute()
    
    # Get values
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()
    
    values = result.get("values", [])
    
    return {
        "spreadsheet_id": spreadsheet_id,
        "title": spreadsheet.get("properties", {}).get("title"),
        "sheets": [s.get("properties", {}).get("title") for s in spreadsheet.get("sheets", [])],
        "range": result.get("range"),
        "values": values,
        "row_count": len(values),
        "web_link": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
    }


def write_to_spreadsheet(
    user_email: str,
    spreadsheet_id: str,
    range_name: str,
    values: list[list[Any]],
    value_input_option: str = "USER_ENTERED",
) -> dict:
    """
    Write data to a Google Sheets spreadsheet.
    
    Args:
        user_email: User's email for authentication
        spreadsheet_id: Spreadsheet ID
        range_name: Sheet and range to write (e.g., "Sheet1!A1")
        values: 2D list of values to write
        value_input_option: How to interpret values ("RAW" or "USER_ENTERED")
        
    Returns:
        Update result
    """
    service = get_sheets_service(user_email)
    
    body = {
        "values": values,
    }
    
    result = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption=value_input_option,
        body=body,
    ).execute()
    
    return {
        "spreadsheet_id": spreadsheet_id,
        "updated_range": result.get("updatedRange"),
        "updated_rows": result.get("updatedRows"),
        "updated_columns": result.get("updatedColumns"),
        "updated_cells": result.get("updatedCells"),
        "status": "success",
    }

