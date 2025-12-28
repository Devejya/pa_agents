"""
Gmail OAuth Authentication Module

Handles OAuth 2.0 flow for Gmail API access.
Tokens are stored locally - no data leaves your machine.
"""

import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Gmail API scopes - defines what permissions we request
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",   # Read emails
    "https://www.googleapis.com/auth/gmail.compose",    # Create drafts
    "https://www.googleapis.com/auth/gmail.modify",     # Modify labels
]


def get_gmail_credentials(
    credentials_path: str = "../SECRETS/google_oath_credentials.json",
    token_path: str = "./token.json"
) -> Credentials:
    """
    Get or refresh Gmail API credentials.
    
    First run: Opens browser for OAuth consent flow.
    Subsequent runs: Uses saved token (refreshes if expired).
    
    Args:
        credentials_path: Path to Google OAuth credentials JSON
        token_path: Path to store/load the auth token
        
    Returns:
        Valid Google OAuth credentials
    """
    creds = None
    
    # Resolve paths relative to this file's directory
    base_dir = Path(__file__).parent.parent
    credentials_file = base_dir / credentials_path
    token_file = base_dir / token_path
    
    # Check for existing token
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            creds.refresh(Request())
        else:
            # Run OAuth flow (opens browser)
            if not credentials_file.exists():
                raise FileNotFoundError(
                    f"Credentials file not found at {credentials_file}\n"
                    "Please ensure you've downloaded OAuth credentials from Google Cloud Console."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_file), 
                SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save token for next run
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as token:
            token.write(creds.to_json())
        print(f"✅ Token saved to {token_file}")
    
    return creds


def get_gmail_service():
    """
    Build and return Gmail API service client.
    
    Returns:
        Gmail API service instance
    """
    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    return service


def verify_connection() -> dict:
    """
    Verify Gmail API connection by fetching profile info.
    
    Returns:
        Dict with email address and connection status
    """
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        return {
            "status": "connected",
            "email": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal"),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


