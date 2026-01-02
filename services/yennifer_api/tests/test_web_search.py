"""
Unit tests for web search functionality.

Tests cover:
- Query sanitization
- Result parsing
- LLM formatting
- Google Search client
- Web search tool
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from app.core.web_search_tools import (
    _sanitize_query,
    _parse_results,
    _format_for_llm,
    SearchResult,
    web_search,
)
from app.core.google_search_client import GoogleSearchClient, GoogleSearchError


class TestQuerySanitization:
    """Test query sanitization logic."""
    
    def test_strips_whitespace(self):
        """Should normalize multiple spaces to single space."""
        assert _sanitize_query("  hello   world  ") == "hello world"
    
    def test_truncates_long_queries(self):
        """Should truncate queries over 2048 characters."""
        long_query = "a" * 3000
        result = _sanitize_query(long_query)
        assert len(result) == 2048
    
    def test_removes_control_characters(self):
        """Should remove null bytes and control characters."""
        assert _sanitize_query("hello\x00world") == "helloworld"
        assert _sanitize_query("test\x01\x02\x03") == "test"
    
    def test_preserves_unicode(self):
        """Should preserve valid unicode characters."""
        assert _sanitize_query("café résumé") == "café résumé"
        assert _sanitize_query("日本語 テスト") == "日本語 テスト"
    
    def test_handles_empty_query(self):
        """Should handle empty or None queries."""
        assert _sanitize_query("") == ""
        assert _sanitize_query("   ") == ""
    
    def test_handles_tabs_and_newlines(self):
        """Should normalize tabs and newlines to spaces."""
        assert _sanitize_query("hello\tworld\ntest") == "hello world test"


class TestResultParsing:
    """Test result parsing logic."""
    
    def test_parses_valid_response(self):
        """Should parse a valid Google CSE response."""
        raw = {
            "items": [
                {
                    "title": "Test Title",
                    "link": "https://example.com",
                    "snippet": "Test snippet text",
                    "displayLink": "example.com",
                }
            ]
        }
        results = _parse_results(raw)
        
        assert len(results) == 1
        assert results[0].title == "Test Title"
        assert results[0].url == "https://example.com"
        assert results[0].snippet == "Test snippet text"
        assert results[0].domain == "example.com"
    
    def test_parses_multiple_results(self):
        """Should parse multiple results correctly."""
        raw = {
            "items": [
                {"title": "Result 1", "link": "https://a.com", "snippet": "Snippet 1", "displayLink": "a.com"},
                {"title": "Result 2", "link": "https://b.com", "snippet": "Snippet 2", "displayLink": "b.com"},
                {"title": "Result 3", "link": "https://c.com", "snippet": "Snippet 3", "displayLink": "c.com"},
            ]
        }
        results = _parse_results(raw)
        
        assert len(results) == 3
        assert results[0].title == "Result 1"
        assert results[2].title == "Result 3"
    
    def test_handles_empty_response(self):
        """Should return empty list for empty responses."""
        assert _parse_results({}) == []
        assert _parse_results({"items": []}) == []
    
    def test_handles_missing_fields(self):
        """Should handle results with missing optional fields."""
        raw = {"items": [{"title": "Only Title"}]}
        results = _parse_results(raw)
        
        assert len(results) == 1
        assert results[0].title == "Only Title"
        assert results[0].url == ""
        assert results[0].snippet == ""
        assert results[0].domain == ""
    
    def test_handles_none_values(self):
        """Should handle None values in fields."""
        raw = {"items": [{"title": None, "link": None, "snippet": None, "displayLink": None}]}
        results = _parse_results(raw)
        
        assert len(results) == 1
        # get() with default "" handles None


class TestLLMFormatting:
    """Test output formatting for LLM."""
    
    def test_formats_single_result(self):
        """Should format a single result correctly."""
        results = [SearchResult("Test Title", "https://test.com", "Test snippet", "test.com")]
        formatted = _format_for_llm(results)
        
        assert "[1] Test Title" in formatted
        assert "URL: https://test.com" in formatted
        assert "Test snippet" in formatted
    
    def test_formats_multiple_results(self):
        """Should format multiple results with numbering."""
        results = [
            SearchResult("Title 1", "https://a.com", "Snippet 1", "a.com"),
            SearchResult("Title 2", "https://b.com", "Snippet 2", "b.com"),
        ]
        formatted = _format_for_llm(results)
        
        assert "[1] Title 1" in formatted
        assert "[2] Title 2" in formatted
        assert "https://a.com" in formatted
        assert "https://b.com" in formatted
    
    def test_handles_empty_results(self):
        """Should return appropriate message for no results."""
        assert _format_for_llm([]) == "No search results found."
    
    def test_preserves_special_characters(self):
        """Should preserve special characters in results."""
        results = [SearchResult("Test & \"Title\"", "https://test.com?q=a&b=c", "Snippet <html>", "test.com")]
        formatted = _format_for_llm(results)
        
        assert "Test & \"Title\"" in formatted
        assert "q=a&b=c" in formatted


class TestGoogleSearchClient:
    """Test Google CSE client."""
    
    @patch('app.core.google_search_client.build')
    def test_successful_search(self, mock_build):
        """Should execute search and return results."""
        mock_service = MagicMock()
        mock_service.cse().list().execute.return_value = {
            "items": [{"title": "Test", "link": "https://test.com"}]
        }
        mock_build.return_value = mock_service
        
        client = GoogleSearchClient("test-api-key", "test-cse-id")
        result = client.search("test query")
        
        assert "items" in result
        assert len(result["items"]) == 1
        mock_service.cse().list.assert_called()
    
    @patch('app.core.google_search_client.build')
    def test_empty_query_returns_empty(self, mock_build):
        """Should return empty results for empty query."""
        client = GoogleSearchClient("test-api-key", "test-cse-id")
        result = client.search("")
        
        assert result == {"items": []}
        mock_build.assert_not_called()
    
    @patch('app.core.google_search_client.build')
    def test_clamps_num_results(self, mock_build):
        """Should clamp num to valid range (1-10)."""
        mock_service = MagicMock()
        mock_service.cse().list().execute.return_value = {"items": []}
        mock_build.return_value = mock_service
        
        client = GoogleSearchClient("key", "cse")
        
        # Test lower bound
        client.search("test", num=0)
        call_args = mock_service.cse().list.call_args
        assert call_args[1]["num"] == 1
        
        # Reset mock
        mock_service.reset_mock()
        
        # Test upper bound
        client.search("test", num=100)
        call_args = mock_service.cse().list.call_args
        assert call_args[1]["num"] == 10
    
    @patch('app.core.google_search_client.build')
    def test_rate_limit_error(self, mock_build):
        """Should raise GoogleSearchError on rate limit."""
        from googleapiclient.errors import HttpError
        
        mock_service = MagicMock()
        mock_resp = Mock()
        mock_resp.status = 429
        mock_service.cse().list().execute.side_effect = HttpError(mock_resp, b"Rate limited")
        mock_build.return_value = mock_service
        
        client = GoogleSearchClient("key", "cse")
        
        with pytest.raises(GoogleSearchError) as exc_info:
            client.search("test")
        
        assert "Rate limit" in str(exc_info.value)
    
    @patch('app.core.google_search_client.build')
    def test_quota_exceeded_error(self, mock_build):
        """Should raise GoogleSearchError on quota exceeded."""
        from googleapiclient.errors import HttpError
        
        mock_service = MagicMock()
        mock_resp = Mock()
        mock_resp.status = 403
        mock_service.cse().list().execute.side_effect = HttpError(mock_resp, b"Quota exceeded")
        mock_build.return_value = mock_service
        
        client = GoogleSearchClient("key", "cse")
        
        with pytest.raises(GoogleSearchError) as exc_info:
            client.search("test")
        
        assert "quota" in str(exc_info.value).lower() or "credentials" in str(exc_info.value).lower()
    
    @patch('app.core.google_search_client.build')
    def test_lazy_service_initialization(self, mock_build):
        """Should lazily initialize the Google API service."""
        mock_build.return_value = MagicMock()
        
        client = GoogleSearchClient("key", "cse")
        
        # Service not built yet
        mock_build.assert_not_called()
        
        # Access service property
        _ = client.service
        
        # Now it should be built
        mock_build.assert_called_once()
        
        # Access again - should not rebuild
        _ = client.service
        mock_build.assert_called_once()


class TestWebSearchTool:
    """Test the LangChain tool wrapper."""
    
    @patch('app.core.web_search_tools.GoogleSearchClient')
    @patch('app.core.web_search_tools.get_settings')
    @patch('app.core.web_search_tools.mask_pii')
    def test_successful_search(self, mock_mask_pii, mock_get_settings, mock_client_class):
        """Should execute search and return formatted results."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.google_cse_enabled = True
        mock_settings.google_cse_api_key = "test-key"
        mock_settings.google_cse_id = "test-cse"
        mock_get_settings.return_value = mock_settings
        
        mock_client = Mock()
        mock_client.search.return_value = {
            "items": [
                {"title": "Test Result", "link": "https://test.com", "snippet": "Test snippet", "displayLink": "test.com"}
            ]
        }
        mock_client_class.return_value = mock_client
        
        mock_mask_pii.side_effect = lambda x: x  # Pass through
        
        result = web_search.invoke({"query": "test query"})
        
        assert "Test Result" in result
        assert "https://test.com" in result
        mock_client.search.assert_called_once()
    
    @patch('app.core.web_search_tools.get_settings')
    def test_disabled_returns_message(self, mock_get_settings):
        """Should return disabled message when feature is off."""
        mock_settings = Mock()
        mock_settings.google_cse_enabled = False
        mock_get_settings.return_value = mock_settings
        
        result = web_search.invoke({"query": "test"})
        
        assert "disabled" in result.lower()
    
    @patch('app.core.web_search_tools.get_settings')
    def test_unconfigured_returns_message(self, mock_get_settings):
        """Should return configuration message when credentials missing."""
        mock_settings = Mock()
        mock_settings.google_cse_enabled = True
        mock_settings.google_cse_api_key = ""
        mock_settings.google_cse_id = ""
        mock_get_settings.return_value = mock_settings
        
        result = web_search.invoke({"query": "test"})
        
        assert "not configured" in result.lower()
    
    @patch('app.core.web_search_tools.get_settings')
    def test_empty_query_returns_message(self, mock_get_settings):
        """Should return message for empty query."""
        mock_settings = Mock()
        mock_settings.google_cse_enabled = True
        mock_settings.google_cse_api_key = "key"
        mock_settings.google_cse_id = "cse"
        mock_get_settings.return_value = mock_settings
        
        result = web_search.invoke({"query": ""})
        
        assert "provide a search query" in result.lower()
    
    @patch('app.core.web_search_tools.GoogleSearchClient')
    @patch('app.core.web_search_tools.get_settings')
    def test_search_error_returns_message(self, mock_get_settings, mock_client_class):
        """Should return error message on search failure."""
        mock_settings = Mock()
        mock_settings.google_cse_enabled = True
        mock_settings.google_cse_api_key = "key"
        mock_settings.google_cse_id = "cse"
        mock_get_settings.return_value = mock_settings
        
        mock_client = Mock()
        mock_client.search.side_effect = GoogleSearchError("API quota exceeded")
        mock_client_class.return_value = mock_client
        
        result = web_search.invoke({"query": "test"})
        
        assert "failed" in result.lower()
        assert "quota" in result.lower()
    
    @patch('app.core.web_search_tools.GoogleSearchClient')
    @patch('app.core.web_search_tools.get_settings')
    @patch('app.core.web_search_tools.mask_pii')
    def test_pii_masking_applied(self, mock_mask_pii, mock_get_settings, mock_client_class):
        """Should apply PII masking to results."""
        mock_settings = Mock()
        mock_settings.google_cse_enabled = True
        mock_settings.google_cse_api_key = "key"
        mock_settings.google_cse_id = "cse"
        mock_get_settings.return_value = mock_settings
        
        mock_client = Mock()
        mock_client.search.return_value = {"items": [{"title": "Test", "link": "https://test.com", "snippet": "Contains email@test.com", "displayLink": "test.com"}]}
        mock_client_class.return_value = mock_client
        
        mock_mask_pii.return_value = "[MASKED]"
        
        result = web_search.invoke({"query": "test"})
        
        mock_mask_pii.assert_called_once()
        assert result == "[MASKED]"
    
    @patch('app.core.web_search_tools.GoogleSearchClient')
    @patch('app.core.web_search_tools.get_settings')
    @patch('app.core.web_search_tools.mask_pii')
    def test_max_results_clamped(self, mock_mask_pii, mock_get_settings, mock_client_class):
        """Should clamp max_results to valid range."""
        mock_settings = Mock()
        mock_settings.google_cse_enabled = True
        mock_settings.google_cse_api_key = "key"
        mock_settings.google_cse_id = "cse"
        mock_get_settings.return_value = mock_settings
        
        mock_client = Mock()
        mock_client.search.return_value = {"items": []}
        mock_client_class.return_value = mock_client
        
        mock_mask_pii.side_effect = lambda x: x
        
        # Test with value above max
        web_search.invoke({"query": "test", "max_results": 100})
        mock_client.search.assert_called_with("test", num=10)
        
        mock_client.reset_mock()
        
        # Test with value below min
        web_search.invoke({"query": "test", "max_results": -5})
        mock_client.search.assert_called_with("test", num=1)

