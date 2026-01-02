"""
Web Search Tools for Yennifer Agent.

Provides a web search tool using Google Custom Search API
for the agent to fetch real-time information from the web.

PII Masking:
- Search results are masked using FULL masking mode
"""

import logging
from dataclasses import dataclass
from typing import List

from langchain_core.tools import tool

from .config import get_settings
from .google_search_client import GoogleSearchClient, GoogleSearchError
from .pii import mask_pii

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Structured search result."""
    title: str
    url: str
    snippet: str
    domain: str


def _sanitize_query(query: str) -> str:
    """
    Sanitize and validate search query.
    
    Args:
        query: Raw search query from agent
    
    Returns:
        Sanitized query safe for API call
    """
    if not query:
        return ""
    
    # Strip excessive whitespace
    query = " ".join(query.split())
    
    # Truncate to API limit (2048 chars)
    if len(query) > 2048:
        query = query[:2048]
    
    # Remove null bytes and control characters
    query = "".join(c for c in query if c.isprintable())
    
    return query


def _parse_results(raw_response: dict) -> List[SearchResult]:
    """
    Parse Google CSE response into structured results.
    
    Args:
        raw_response: Raw JSON response from Google API
    
    Returns:
        List of SearchResult objects
    """
    items = raw_response.get("items", [])
    results = []
    
    for item in items:
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            domain=item.get("displayLink", ""),
        ))
    
    return results


def _format_for_llm(results: List[SearchResult]) -> str:
    """
    Format results as readable text for LLM consumption.
    
    Args:
        results: List of parsed search results
    
    Returns:
        Formatted string for agent to process
    """
    if not results:
        return "No search results found."
    
    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(
            f"[{i}] {r.title}\n"
            f"    URL: {r.url}\n"
            f"    {r.snippet}"
        )
    
    return "\n\n".join(formatted)


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web for current information using Google.
    
    Use this tool when you need:
    - Current news or events
    - Real-time data (weather, stock prices, sports scores)
    - Recent information not in your training data
    - Facts that may have changed recently
    
    DO NOT use for:
    - User's personal information (use memory/calendar tools)
    - Historical facts you already know
    - Subjective opinions or recommendations
    
    Args:
        query: Search query - be specific and include relevant context
        max_results: Number of results to return (1-10, default 5)
    
    Returns:
        Search results with titles, URLs, and snippets
    
    Example queries:
    - "current weather Toronto January 2026"
    - "latest news OpenAI"
    - "Tesla stock price today"
    """
    settings = get_settings()
    
    # Check if web search is enabled and configured
    if not settings.google_cse_enabled:
        return "Web search is currently disabled."
    
    if not settings.google_cse_api_key or not settings.google_cse_id:
        logger.warning("Web search called but Google CSE credentials not configured")
        return "Web search is not configured. Please contact the administrator."
    
    # Sanitize query
    clean_query = _sanitize_query(query)
    if not clean_query:
        return "Please provide a search query."
    
    # Clamp max_results to valid range
    max_results = max(1, min(10, max_results))
    
    # Execute search
    client = GoogleSearchClient(
        api_key=settings.google_cse_api_key,
        cse_id=settings.google_cse_id,
    )
    
    try:
        raw_results = client.search(clean_query, num=max_results)
        parsed = _parse_results(raw_results)
        formatted = _format_for_llm(parsed)
        
        # Apply PII masking (in case search results contain sensitive data)
        return mask_pii(formatted)
        
    except GoogleSearchError as e:
        logger.error(f"Web search failed for query '{clean_query[:50]}': {e}")
        return f"Search failed: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in web search: {e}")
        return "An unexpected error occurred while searching. Please try again."


# Export for agent.py
WEB_SEARCH_TOOLS = [web_search]

