"""
Google Slides Tools

Functions for reading, creating, and modifying Google Slides presentations.
"""

from typing import Optional

from ..core.google_services import get_slides_service, get_drive_service


def list_presentations(
    user_email: str,
    max_results: int = 20,
) -> list[dict]:
    """
    List Google Slides presentations in Drive.
    
    Args:
        user_email: User's email for authentication
        max_results: Maximum number of presentations to return
        
    Returns:
        List of presentation dictionaries
    """
    service = get_drive_service(user_email)
    
    results = service.files().list(
        pageSize=max_results,
        q="mimeType='application/vnd.google-apps.presentation' and trashed=false",
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


def _extract_text_from_element(element: dict) -> str:
    """Extract text from a page element."""
    text_parts = []
    
    if "shape" in element:
        shape = element["shape"]
        if "text" in shape:
            for text_elem in shape["text"].get("textElements", []):
                if "textRun" in text_elem:
                    text_parts.append(text_elem["textRun"].get("content", ""))
    
    return "".join(text_parts)


def read_presentation(
    user_email: str,
    presentation_id: str,
) -> dict:
    """
    Read a Google Slides presentation.
    
    Args:
        user_email: User's email for authentication
        presentation_id: Presentation ID
        
    Returns:
        Presentation metadata and slide content
    """
    service = get_slides_service(user_email)
    
    presentation = service.presentations().get(
        presentationId=presentation_id
    ).execute()
    
    slides_data = []
    for i, slide in enumerate(presentation.get("slides", []), 1):
        slide_text = []
        for element in slide.get("pageElements", []):
            text = _extract_text_from_element(element)
            if text.strip():
                slide_text.append(text.strip())
        
        slides_data.append({
            "slide_number": i,
            "object_id": slide.get("objectId"),
            "content": "\n".join(slide_text),
        })
    
    return {
        "presentation_id": presentation_id,
        "title": presentation.get("title"),
        "slide_count": len(slides_data),
        "slides": slides_data,
        "web_link": f"https://docs.google.com/presentation/d/{presentation_id}",
    }


def create_presentation(
    user_email: str,
    title: str,
) -> dict:
    """
    Create a new Google Slides presentation.
    
    Args:
        user_email: User's email for authentication
        title: Presentation title
        
    Returns:
        Created presentation info
    """
    service = get_slides_service(user_email)
    
    presentation = service.presentations().create(
        body={"title": title}
    ).execute()
    
    presentation_id = presentation.get("presentationId")
    
    return {
        "presentation_id": presentation_id,
        "title": title,
        "slide_count": 1,  # New presentations have 1 blank slide
        "web_link": f"https://docs.google.com/presentation/d/{presentation_id}",
        "status": "created",
    }


def add_slide(
    user_email: str,
    presentation_id: str,
    layout: str = "BLANK",
    insertion_index: Optional[int] = None,
) -> dict:
    """
    Add a new slide to a presentation.
    
    Args:
        user_email: User's email for authentication
        presentation_id: Presentation ID
        layout: Slide layout type (BLANK, TITLE, TITLE_AND_BODY, etc.)
        insertion_index: Where to insert (None = at end)
        
    Returns:
        Added slide info
    """
    service = get_slides_service(user_email)
    
    # Map simple layout names to predefined layouts
    layout_mapping = {
        "BLANK": "BLANK",
        "TITLE": "TITLE",
        "TITLE_AND_BODY": "TITLE_AND_BODY",
        "TITLE_ONLY": "TITLE_ONLY",
        "ONE_COLUMN_TEXT": "ONE_COLUMN_TEXT",
        "MAIN_POINT": "MAIN_POINT",
        "SECTION_HEADER": "SECTION_HEADER",
        "SECTION_TITLE_AND_DESCRIPTION": "SECTION_TITLE_AND_DESCRIPTION",
        "CAPTION_ONLY": "CAPTION_ONLY",
        "BIG_NUMBER": "BIG_NUMBER",
    }
    
    predefined_layout = layout_mapping.get(layout.upper(), "BLANK")
    
    request = {
        "createSlide": {
            "slideLayoutReference": {
                "predefinedLayout": predefined_layout,
            }
        }
    }
    
    if insertion_index is not None:
        request["createSlide"]["insertionIndex"] = insertion_index
    
    result = service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": [request]},
    ).execute()
    
    # Get the new slide ID
    new_slide_id = result["replies"][0]["createSlide"]["objectId"]
    
    return {
        "presentation_id": presentation_id,
        "slide_id": new_slide_id,
        "layout": predefined_layout,
        "web_link": f"https://docs.google.com/presentation/d/{presentation_id}",
        "status": "slide_added",
    }


def add_text_to_slide(
    user_email: str,
    presentation_id: str,
    slide_id: str,
    text: str,
    x: float = 100,
    y: float = 100,
    width: float = 400,
    height: float = 100,
) -> dict:
    """
    Add a text box to a slide.
    
    Args:
        user_email: User's email for authentication
        presentation_id: Presentation ID
        slide_id: Slide object ID
        text: Text to add
        x: X position in points (default: 100)
        y: Y position in points (default: 100)
        width: Text box width in points (default: 400)
        height: Text box height in points (default: 100)
        
    Returns:
        Result info
    """
    service = get_slides_service(user_email)
    
    # Generate a unique ID for the text box
    import uuid
    element_id = f"textbox_{uuid.uuid4().hex[:8]}"
    
    requests = [
        # Create shape (text box)
        {
            "createShape": {
                "objectId": element_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "height": {"magnitude": height, "unit": "PT"},
                        "width": {"magnitude": width, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": x,
                        "translateY": y,
                        "unit": "PT",
                    },
                },
            }
        },
        # Insert text into the shape
        {
            "insertText": {
                "objectId": element_id,
                "insertionIndex": 0,
                "text": text,
            }
        },
    ]
    
    service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests},
    ).execute()
    
    return {
        "presentation_id": presentation_id,
        "slide_id": slide_id,
        "element_id": element_id,
        "text": text[:100] + "..." if len(text) > 100 else text,
        "web_link": f"https://docs.google.com/presentation/d/{presentation_id}",
        "status": "text_added",
    }


def delete_slide(
    user_email: str,
    presentation_id: str,
    slide_id: str,
) -> dict:
    """
    Delete a slide from a presentation.
    
    Args:
        user_email: User's email for authentication
        presentation_id: Presentation ID
        slide_id: Slide object ID to delete
        
    Returns:
        Confirmation
    """
    service = get_slides_service(user_email)
    
    requests = [
        {
            "deleteObject": {
                "objectId": slide_id,
            }
        }
    ]
    
    service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests},
    ).execute()
    
    return {
        "presentation_id": presentation_id,
        "slide_id": slide_id,
        "status": "deleted",
    }

