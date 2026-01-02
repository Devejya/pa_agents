"""
Integration tests for web search functionality.

These tests require real Google CSE credentials and make actual API calls.
They are skipped if credentials are not configured.

Run with: pytest tests/test_web_search_integration.py -v

Environment variables required:
- GOOGLE_CSE_API_KEY: Google API key
- GOOGLE_CSE_ID: Custom Search Engine ID
"""

import os
import pytest

# Skip all tests in this file if credentials not configured
pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_CSE_API_KEY") or not os.getenv("GOOGLE_CSE_ID"),
    reason="Google CSE credentials not configured (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID required)"
)


class TestGoogleSearchIntegration:
    """Integration tests against real Google Custom Search API."""
    
    @pytest.fixture
    def client(self):
        """Create a real Google Search client."""
        from app.core.google_search_client import GoogleSearchClient
        
        return GoogleSearchClient(
            api_key=os.getenv("GOOGLE_CSE_API_KEY"),
            cse_id=os.getenv("GOOGLE_CSE_ID"),
        )
    
    def test_real_search_returns_results(self, client):
        """Should return results for a common search query."""
        results = client.search("Python programming language", num=3)
        
        assert "items" in results
        assert len(results["items"]) >= 1
        
        # First result should be about Python
        first_result = results["items"][0]
        assert "title" in first_result
        assert "link" in first_result
        assert "snippet" in first_result
    
    def test_search_with_specific_query(self, client):
        """Should return relevant results for specific queries."""
        results = client.search("OpenAI GPT-4 announcement", num=5)
        
        assert "items" in results
        # At least some results should be returned
        assert len(results.get("items", [])) >= 1
    
    def test_search_returns_metadata(self, client):
        """Should include search metadata in response."""
        results = client.search("test query", num=1)
        
        # Response should include search information
        if results.get("items"):
            item = results["items"][0]
            assert "title" in item
            assert "link" in item
            assert "displayLink" in item
    
    def test_search_with_unicode(self, client):
        """Should handle unicode characters in queries."""
        results = client.search("café résumé naïve", num=3)
        
        # Should not raise an error
        assert isinstance(results, dict)
    
    def test_search_with_special_characters(self, client):
        """Should handle special characters in queries."""
        results = client.search("C++ programming language", num=3)
        
        assert isinstance(results, dict)
        # Should return some results
        assert "items" in results or "searchInformation" in results
    
    def test_num_results_respected(self, client):
        """Should respect the num parameter."""
        results = client.search("Python tutorial", num=2)
        
        if "items" in results:
            # Should return at most the requested number
            assert len(results["items"]) <= 2
    
    def test_safe_search_enabled(self, client):
        """Should use safe search by default."""
        # This is mainly a smoke test - safe search is enabled by default
        results = client.search("safe search test", num=1, safe="active")
        
        assert isinstance(results, dict)


class TestWebSearchToolIntegration:
    """Integration tests for the web_search tool with real API."""
    
    @pytest.fixture
    def configure_settings(self, monkeypatch):
        """Configure settings for integration testing."""
        monkeypatch.setenv("GOOGLE_CSE_API_KEY", os.getenv("GOOGLE_CSE_API_KEY"))
        monkeypatch.setenv("GOOGLE_CSE_ID", os.getenv("GOOGLE_CSE_ID"))
        monkeypatch.setenv("GOOGLE_CSE_ENABLED", "true")
        
        # Clear cached settings
        from app.core.config import get_settings
        get_settings.cache_clear()
    
    def test_tool_returns_formatted_results(self, configure_settings):
        """Should return properly formatted search results."""
        from app.core.web_search_tools import web_search
        
        result = web_search.invoke({"query": "Python programming", "max_results": 3})
        
        # Should contain numbered results
        assert "[1]" in result
        assert "URL:" in result
        # Should not be an error message
        assert "failed" not in result.lower()
        assert "disabled" not in result.lower()
    
    def test_tool_handles_no_results(self, configure_settings):
        """Should handle queries with no results gracefully."""
        from app.core.web_search_tools import web_search
        
        # Very obscure query unlikely to have results
        result = web_search.invoke({"query": "xyzzy123456789nonexistentquery", "max_results": 1})
        
        # Should return a message, not crash
        assert isinstance(result, str)
        assert len(result) > 0


class TestEndToEndFlow:
    """End-to-end integration tests simulating agent usage."""
    
    @pytest.fixture
    def configure_settings(self, monkeypatch):
        """Configure settings for integration testing."""
        monkeypatch.setenv("GOOGLE_CSE_API_KEY", os.getenv("GOOGLE_CSE_API_KEY"))
        monkeypatch.setenv("GOOGLE_CSE_ID", os.getenv("GOOGLE_CSE_ID"))
        monkeypatch.setenv("GOOGLE_CSE_ENABLED", "true")
        
        from app.core.config import get_settings
        get_settings.cache_clear()
    
    def test_weather_query_flow(self, configure_settings):
        """Simulate a weather query flow."""
        from app.core.web_search_tools import web_search
        
        # Agent would generate a query like this
        result = web_search.invoke({
            "query": "current weather Toronto Ontario Canada",
            "max_results": 3
        })
        
        # Should get weather-related results
        assert isinstance(result, str)
        assert len(result) > 50  # Should have substantial content
    
    def test_news_query_flow(self, configure_settings):
        """Simulate a news query flow."""
        from app.core.web_search_tools import web_search
        
        result = web_search.invoke({
            "query": "latest technology news AI",
            "max_results": 5
        })
        
        assert isinstance(result, str)
        # Should contain multiple results
        assert "[1]" in result

