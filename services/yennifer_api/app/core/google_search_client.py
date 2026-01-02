"""
Google Custom Search API Client.

Provides a client wrapper for the Google Custom Search API
with error handling and logging.
"""

import logging
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleSearchError(Exception):
    """Custom exception for Google Search errors."""
    pass


class GoogleSearchClient:
    """Client for Google Custom Search API."""
    
    def __init__(self, api_key: str, cse_id: str):
        """
        Initialize the Google Search client.
        
        Args:
            api_key: Google API key from Cloud Console
            cse_id: Custom Search Engine ID from Programmable Search Engine
        """
        self.api_key = api_key
        self.cse_id = cse_id
        self._service = None
    
    @property
    def service(self):
        """Lazy initialization of Google API service."""
        if self._service is None:
            self._service = build(
                "customsearch", "v1",
                developerKey=self.api_key,
                cache_discovery=False,
            )
        return self._service
    
    def search(
        self,
        query: str,
        num: int = 5,
        start: int = 1,
        language: str = "en",
        safe: str = "active",
    ) -> dict:
        """
        Execute a search query.
        
        Args:
            query: Search query string
            num: Number of results (1-10)
            start: Starting index for pagination
            language: Language code (e.g., "en", "fr")
            safe: Safe search level ("active", "off")
        
        Returns:
            Raw API response dict
        
        Raises:
            GoogleSearchError: If the API call fails
        """
        if not query or not query.strip():
            return {"items": []}
        
        # Clamp num to API limits
        num = max(1, min(10, num))
        
        try:
            result = self.service.cse().list(
                q=query,
                cx=self.cse_id,
                num=num,
                start=start,
                lr=f"lang_{language}",
                safe=safe,
            ).execute()
            
            result_count = len(result.get("items", []))
            query_preview = query[:50] + "..." if len(query) > 50 else query
            logger.info(f"Search completed: query='{query_preview}', results={result_count}")
            return result
            
        except HttpError as e:
            logger.error(f"Google Search API error: {e}")
            if e.resp.status == 429:
                raise GoogleSearchError("Rate limit exceeded. Please try again later.")
            elif e.resp.status == 403:
                raise GoogleSearchError("API quota exceeded or invalid credentials.")
            elif e.resp.status == 400:
                raise GoogleSearchError(f"Invalid search request: {e.reason}")
            else:
                raise GoogleSearchError(f"Search failed: {e.reason}")
        except Exception as e:
            logger.error(f"Unexpected search error: {e}")
            raise GoogleSearchError(f"Search failed: {str(e)}")

