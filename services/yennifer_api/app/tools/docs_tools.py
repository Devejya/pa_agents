"""
Google Docs Tools

Functions for reading and creating Google Docs.
"""

from typing import Optional

from ..core.google_services import get_docs_service, get_drive_service


def list_documents(
    user_email: str,
    max_results: int = 20,
) -> list[dict]:
    """
    List Google Docs documents in Drive.
    
    Args:
        user_email: User's email for authentication
        max_results: Maximum number of documents to return
        
    Returns:
        List of document dictionaries
    """
    service = get_drive_service(user_email)
    
    results = service.files().list(
        pageSize=max_results,
        q="mimeType='application/vnd.google-apps.document' and trashed=false",
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


def _extract_text_from_doc(document: dict) -> str:
    """Extract plain text content from a Google Doc."""
    text_parts = []
    
    body = document.get("body", {})
    content = body.get("content", [])
    
    for element in content:
        if "paragraph" in element:
            paragraph = element["paragraph"]
            for elem in paragraph.get("elements", []):
                if "textRun" in elem:
                    text_parts.append(elem["textRun"].get("content", ""))
    
    return "".join(text_parts)


def read_document(
    user_email: str,
    document_id: str,
) -> dict:
    """
    Read a Google Doc document.
    
    Args:
        user_email: User's email for authentication
        document_id: Document ID
        
    Returns:
        Document metadata and content
    """
    service = get_docs_service(user_email)
    
    document = service.documents().get(documentId=document_id).execute()
    
    # Extract text content
    text_content = _extract_text_from_doc(document)
    
    return {
        "document_id": document_id,
        "title": document.get("title"),
        "content": text_content[:10000],  # Limit size for LLM context
        "web_link": f"https://docs.google.com/document/d/{document_id}",
    }


def create_document(
    user_email: str,
    title: str,
    content: Optional[str] = None,
) -> dict:
    """
    Create a new Google Doc document.
    
    Args:
        user_email: User's email for authentication
        title: Document title
        content: Initial content (optional)
        
    Returns:
        Created document info
    """
    service = get_docs_service(user_email)
    
    # Create empty document
    document = service.documents().create(body={"title": title}).execute()
    document_id = document.get("documentId")
    
    # Add content if provided
    if content:
        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": content,
                }
            }
        ]
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()
    
    return {
        "document_id": document_id,
        "title": title,
        "web_link": f"https://docs.google.com/document/d/{document_id}",
        "status": "created",
    }


def append_to_document(
    user_email: str,
    document_id: str,
    text: str,
) -> dict:
    """
    Append text to the end of a Google Doc.
    
    Args:
        user_email: User's email for authentication
        document_id: Document ID
        text: Text to append
        
    Returns:
        Updated document info
    """
    service = get_docs_service(user_email)
    
    # Get current document to find end index
    document = service.documents().get(documentId=document_id).execute()
    
    # Find the end of the document
    body_content = document.get("body", {}).get("content", [])
    end_index = 1
    for element in body_content:
        if "endIndex" in element:
            end_index = max(end_index, element["endIndex"])
    
    # Insert text at the end (before the final newline)
    requests = [
        {
            "insertText": {
                "location": {"index": end_index - 1},
                "text": "\n" + text,
            }
        }
    ]
    
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": requests},
    ).execute()
    
    return {
        "document_id": document_id,
        "title": document.get("title"),
        "web_link": f"https://docs.google.com/document/d/{document_id}",
        "status": "appended",
    }


def replace_text_in_document(
    user_email: str,
    document_id: str,
    find_text: str,
    replace_text: str,
    match_case: bool = True,
) -> dict:
    """
    Find and replace text in a Google Doc.
    
    Args:
        user_email: User's email for authentication
        document_id: Document ID
        find_text: Text to find
        replace_text: Text to replace with
        match_case: Whether to match case (default: True)
        
    Returns:
        Update result
    """
    service = get_docs_service(user_email)
    
    requests = [
        {
            "replaceAllText": {
                "containsText": {
                    "text": find_text,
                    "matchCase": match_case,
                },
                "replaceText": replace_text,
            }
        }
    ]
    
    result = service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": requests},
    ).execute()
    
    # Count replacements
    replacements_made = 0
    for reply in result.get("replies", []):
        if "replaceAllText" in reply:
            replacements_made = reply["replaceAllText"].get("occurrencesChanged", 0)
    
    return {
        "document_id": document_id,
        "find_text": find_text,
        "replace_text": replace_text,
        "replacements_made": replacements_made,
        "web_link": f"https://docs.google.com/document/d/{document_id}",
        "status": "replaced",
    }


def insert_text_at_position(
    user_email: str,
    document_id: str,
    text: str,
    index: int = 1,
) -> dict:
    """
    Insert text at a specific position in a Google Doc.
    
    Args:
        user_email: User's email for authentication
        document_id: Document ID
        text: Text to insert
        index: Character index to insert at (1-based, 1 = start of document)
        
    Returns:
        Update result
    """
    service = get_docs_service(user_email)
    
    requests = [
        {
            "insertText": {
                "location": {"index": index},
                "text": text,
            }
        }
    ]
    
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": requests},
    ).execute()
    
    # Get updated document title
    document = service.documents().get(documentId=document_id).execute()
    
    return {
        "document_id": document_id,
        "title": document.get("title"),
        "inserted_at": index,
        "web_link": f"https://docs.google.com/document/d/{document_id}",
        "status": "inserted",
    }

