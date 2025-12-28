"""
Google Drive Tools

Functions for accessing Google Drive files and folders.
"""

from typing import Optional

from ..core.google_services import get_drive_service


def list_drive_files(
    user_email: str,
    max_results: int = 20,
    folder_id: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> list[dict]:
    """
    List files in Google Drive.
    
    Args:
        user_email: User's email for authentication
        max_results: Maximum number of files to return
        folder_id: Folder ID to list files from (optional)
        mime_type: Filter by MIME type (optional)
        
    Returns:
        List of file dictionaries
    """
    service = get_drive_service(user_email)
    
    query_parts = []
    if folder_id:
        query_parts.append(f"'{folder_id}' in parents")
    if mime_type:
        query_parts.append(f"mimeType='{mime_type}'")
    query_parts.append("trashed=false")
    
    query = " and ".join(query_parts)
    
    results = service.files().list(
        pageSize=max_results,
        q=query,
        fields="files(id, name, mimeType, createdTime, modifiedTime, size, webViewLink, owners)",
        orderBy="modifiedTime desc",
    ).execute()
    
    files = results.get("files", [])
    
    return [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "mime_type": f.get("mimeType"),
            "created_time": f.get("createdTime"),
            "modified_time": f.get("modifiedTime"),
            "size": f.get("size"),
            "web_link": f.get("webViewLink"),
            "owners": [o.get("displayName") for o in f.get("owners", [])],
        }
        for f in files
    ]


def search_drive_files(
    user_email: str,
    query: str,
    max_results: int = 20,
) -> list[dict]:
    """
    Search files in Google Drive.
    
    Args:
        user_email: User's email for authentication
        query: Search query (file name or content)
        max_results: Maximum results to return
        
    Returns:
        List of matching file dictionaries
    """
    service = get_drive_service(user_email)
    
    # Build search query
    search_query = f"name contains '{query}' and trashed=false"
    
    results = service.files().list(
        pageSize=max_results,
        q=search_query,
        fields="files(id, name, mimeType, createdTime, modifiedTime, size, webViewLink)",
        orderBy="modifiedTime desc",
    ).execute()
    
    files = results.get("files", [])
    
    return [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "mime_type": f.get("mimeType"),
            "created_time": f.get("createdTime"),
            "modified_time": f.get("modifiedTime"),
            "size": f.get("size"),
            "web_link": f.get("webViewLink"),
        }
        for f in files
    ]


def get_file_content(
    user_email: str,
    file_id: str,
) -> dict:
    """
    Get file metadata and content (for text-based files).
    
    Args:
        user_email: User's email for authentication
        file_id: File ID
        
    Returns:
        File metadata and content (if available)
    """
    service = get_drive_service(user_email)
    
    # Get file metadata
    file_metadata = service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, createdTime, modifiedTime, size, webViewLink, description",
    ).execute()
    
    result = {
        "id": file_metadata.get("id"),
        "name": file_metadata.get("name"),
        "mime_type": file_metadata.get("mimeType"),
        "created_time": file_metadata.get("createdTime"),
        "modified_time": file_metadata.get("modifiedTime"),
        "size": file_metadata.get("size"),
        "web_link": file_metadata.get("webViewLink"),
        "description": file_metadata.get("description"),
        "content": None,
    }
    
    # Try to export content for Google Workspace files
    mime_type = file_metadata.get("mimeType", "")
    
    try:
        if mime_type == "application/vnd.google-apps.document":
            # Export Google Doc as plain text
            content = service.files().export(
                fileId=file_id,
                mimeType="text/plain"
            ).execute()
            result["content"] = content.decode("utf-8")[:10000]  # Limit size
        elif mime_type == "application/vnd.google-apps.spreadsheet":
            result["content"] = "[Spreadsheet - use Sheets tools to read content]"
        elif mime_type == "application/vnd.google-apps.presentation":
            result["content"] = "[Presentation - use Slides tools to read content]"
        elif mime_type.startswith("text/"):
            # Download text files
            content = service.files().get_media(fileId=file_id).execute()
            result["content"] = content.decode("utf-8")[:10000]
    except Exception as e:
        result["content"] = f"[Unable to read content: {str(e)}]"
    
    return result


def create_drive_folder(
    user_email: str,
    folder_name: str,
    parent_folder_id: Optional[str] = None,
) -> dict:
    """
    Create a new folder in Google Drive.
    
    Args:
        user_email: User's email for authentication
        folder_name: Name for the new folder
        parent_folder_id: Parent folder ID (optional, defaults to root)
        
    Returns:
        Created folder info
    """
    service = get_drive_service(user_email)
    
    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    
    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]
    
    folder = service.files().create(
        body=file_metadata,
        fields="id, name, webViewLink",
    ).execute()
    
    return {
        "id": folder.get("id"),
        "name": folder.get("name"),
        "web_link": folder.get("webViewLink"),
        "status": "created",
    }


def rename_drive_file(
    user_email: str,
    file_id: str,
    new_name: str,
) -> dict:
    """
    Rename a file or folder in Google Drive.
    
    Args:
        user_email: User's email for authentication
        file_id: File or folder ID
        new_name: New name for the file
        
    Returns:
        Updated file info
    """
    service = get_drive_service(user_email)
    
    file_metadata = {"name": new_name}
    
    updated_file = service.files().update(
        fileId=file_id,
        body=file_metadata,
        fields="id, name, webViewLink",
    ).execute()
    
    return {
        "id": updated_file.get("id"),
        "name": updated_file.get("name"),
        "web_link": updated_file.get("webViewLink"),
        "status": "renamed",
    }


def move_drive_file(
    user_email: str,
    file_id: str,
    new_parent_id: str,
) -> dict:
    """
    Move a file to a different folder in Google Drive.
    
    Args:
        user_email: User's email for authentication
        file_id: File ID to move
        new_parent_id: Destination folder ID
        
    Returns:
        Updated file info
    """
    service = get_drive_service(user_email)
    
    # Get current parents
    file = service.files().get(
        fileId=file_id,
        fields="parents",
    ).execute()
    
    previous_parents = ",".join(file.get("parents", []))
    
    # Move file
    updated_file = service.files().update(
        fileId=file_id,
        addParents=new_parent_id,
        removeParents=previous_parents,
        fields="id, name, parents, webViewLink",
    ).execute()
    
    return {
        "id": updated_file.get("id"),
        "name": updated_file.get("name"),
        "new_parent": new_parent_id,
        "web_link": updated_file.get("webViewLink"),
        "status": "moved",
    }


def delete_drive_file(
    user_email: str,
    file_id: str,
    permanent: bool = False,
) -> dict:
    """
    Delete a file from Google Drive (move to trash or permanently delete).
    
    Args:
        user_email: User's email for authentication
        file_id: File ID to delete
        permanent: If True, permanently delete. If False, move to trash.
        
    Returns:
        Confirmation
    """
    service = get_drive_service(user_email)
    
    if permanent:
        service.files().delete(fileId=file_id).execute()
    else:
        # Move to trash
        service.files().update(
            fileId=file_id,
            body={"trashed": True},
        ).execute()
    
    return {
        "id": file_id,
        "status": "permanently_deleted" if permanent else "trashed",
    }


def copy_drive_file(
    user_email: str,
    file_id: str,
    new_name: Optional[str] = None,
) -> dict:
    """
    Copy a file in Google Drive.
    
    Args:
        user_email: User's email for authentication
        file_id: File ID to copy
        new_name: Name for the copy (optional)
        
    Returns:
        New file info
    """
    service = get_drive_service(user_email)
    
    file_metadata = {}
    if new_name:
        file_metadata["name"] = new_name
    
    copied_file = service.files().copy(
        fileId=file_id,
        body=file_metadata,
        fields="id, name, webViewLink",
    ).execute()
    
    return {
        "id": copied_file.get("id"),
        "name": copied_file.get("name"),
        "web_link": copied_file.get("webViewLink"),
        "status": "copied",
    }

