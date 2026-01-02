"""
Integration tests for Gmail category-aware email tools.

These tests verify:
1. Tool registration in WORKSPACE_TOOLS
2. Tool function signatures and docstrings
3. Query building with category parameter
4. End-to-end mock API interactions

Run with: 
    cd services/yennifer_api
    python -m pytest tests/test_gmail_category_integration.py -v

Or for manual testing:
    cd services/yennifer_api
    python tests/test_gmail_category_integration.py
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_read_important_emails_tool_exists():
    """Test that read_important_emails tool is registered."""
    from app.core.workspace_tools import WORKSPACE_TOOLS
    
    tool_names = [tool.name for tool in WORKSPACE_TOOLS]
    assert "read_important_emails" in tool_names, \
        "read_important_emails should be in WORKSPACE_TOOLS"
    print("✅ read_important_emails tool is registered")


def test_read_recent_emails_tool_exists():
    """Test that read_recent_emails tool is registered."""
    from app.core.workspace_tools import WORKSPACE_TOOLS
    
    tool_names = [tool.name for tool in WORKSPACE_TOOLS]
    assert "read_recent_emails" in tool_names, \
        "read_recent_emails should be in WORKSPACE_TOOLS"
    print("✅ read_recent_emails tool is registered")


def test_read_important_emails_docstring():
    """Test read_important_emails has proper docstring for agent guidance."""
    from app.core.workspace_tools import read_important_emails
    
    docstring = read_important_emails.description
    
    # Should mention important/urgent keywords
    assert "important" in docstring.lower(), \
        "Docstring should mention 'important'"
    
    # Should mention Primary inbox
    assert "primary" in docstring.lower(), \
        "Docstring should mention 'Primary' inbox"
    
    # Should explain what it excludes
    assert "promotions" in docstring.lower() or "excludes" in docstring.lower(), \
        "Docstring should explain what categories are excluded"
    
    print("✅ read_important_emails has proper docstring for agent guidance")


def test_read_recent_emails_docstring_mentions_category():
    """Test read_recent_emails mentions category in output."""
    from app.core.workspace_tools import read_recent_emails
    
    docstring = read_recent_emails.description
    
    # Should mention category in output
    assert "category" in docstring.lower(), \
        "Docstring should mention category in output"
    
    # Should recommend read_important_emails for important queries
    assert "read_important_emails" in docstring or "important" in docstring.lower(), \
        "Docstring should reference read_important_emails for important queries"
    
    print("✅ read_recent_emails docstring mentions category and alternative tool")


def test_query_building_with_category():
    """Test that category parameter is correctly added to Gmail query."""
    from app.tools.gmail_tools import read_emails
    
    # Mock the Gmail service
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages
    mock_messages.list.return_value.execute.return_value = {"messages": []}
    
    with patch("app.tools.gmail_tools.get_gmail_service", return_value=mock_service):
        # Call with category parameter
        read_emails(
            user_email="test@example.com",
            max_results=5,
            category="primary"
        )
        
        # Verify the query includes category:primary
        call_args = mock_messages.list.call_args
        query = call_args.kwargs.get("q") or (call_args.args[0] if call_args.args else None)
        
        # The query should include category:primary
        assert "category:primary" in str(call_args), \
            f"Query should include category:primary, got: {call_args}"
    
    print("✅ Category parameter correctly added to Gmail query")


def test_query_building_with_category_and_other_filters():
    """Test category works with other query filters."""
    from app.tools.gmail_tools import read_emails
    from datetime import datetime, timedelta
    
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages
    mock_messages.list.return_value.execute.return_value = {"messages": []}
    
    with patch("app.tools.gmail_tools.get_gmail_service", return_value=mock_service):
        # Call with category AND days_back AND unread_only
        read_emails(
            user_email="test@example.com",
            max_results=5,
            days_back=7,
            unread_only=True,
            category="promotions"
        )
        
        # Verify the query includes all filters
        call_args = mock_messages.list.call_args
        query_str = str(call_args)
        
        assert "category:promotions" in query_str, "Should include category filter"
        assert "is:unread" in query_str, "Should include unread filter"
        assert "after:" in query_str, "Should include date filter"
    
    print("✅ Category works correctly with other query filters")


def test_query_building_without_category():
    """Test that no category filter is added when category is None."""
    from app.tools.gmail_tools import read_emails
    
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages
    mock_messages.list.return_value.execute.return_value = {"messages": []}
    
    with patch("app.tools.gmail_tools.get_gmail_service", return_value=mock_service):
        # Call WITHOUT category parameter
        read_emails(
            user_email="test@example.com",
            max_results=5,
        )
        
        # Verify the query does NOT include category:
        call_args = mock_messages.list.call_args
        query_str = str(call_args)
        
        assert "category:" not in query_str, \
            f"Query should NOT include category filter when None, got: {query_str}"
    
    print("✅ No category filter when category parameter is None")


def test_email_response_includes_category():
    """Test that email response dict includes category field."""
    from app.tools.gmail_tools import read_emails
    
    # Create mock Gmail API response
    mock_message = {
        "id": "msg123",
        "threadId": "thread456",
        "labelIds": ["INBOX", "CATEGORY_PROMOTIONS", "UNREAD"],
        "snippet": "Test email snippet",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Date", "value": "Fri, 02 Jan 2026 10:00:00 -0500"},
            ],
            "body": {"data": "VGVzdCBib2R5"}  # Base64 encoded "Test body"
        }
    }
    
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages
    mock_messages.list.return_value.execute.return_value = {"messages": [{"id": "msg123"}]}
    mock_messages.get.return_value.execute.return_value = mock_message
    
    with patch("app.tools.gmail_tools.get_gmail_service", return_value=mock_service):
        emails = read_emails(user_email="test@example.com", max_results=1)
        
        assert len(emails) == 1, "Should return one email"
        assert "category" in emails[0], "Email should have category field"
        assert emails[0]["category"] == "promotions", \
            f"Category should be 'promotions', got: {emails[0]['category']}"
    
    print("✅ Email response includes correct category field")


def test_email_response_primary_category():
    """Test Primary category detection in email response."""
    from app.tools.gmail_tools import read_emails
    
    mock_message = {
        "id": "msg123",
        "threadId": "thread456",
        "labelIds": ["INBOX", "CATEGORY_PERSONAL", "IMPORTANT"],
        "snippet": "Important email",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Meeting Tomorrow"},
                {"name": "From", "value": "boss@company.com"},
                {"name": "To", "value": "me@company.com"},
                {"name": "Date", "value": "Fri, 02 Jan 2026 09:00:00 -0500"},
            ],
            "body": {"data": "TWVldGluZyBkZXRhaWxz"}
        }
    }
    
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages
    mock_messages.list.return_value.execute.return_value = {"messages": [{"id": "msg123"}]}
    mock_messages.get.return_value.execute.return_value = mock_message
    
    with patch("app.tools.gmail_tools.get_gmail_service", return_value=mock_service):
        emails = read_emails(user_email="test@example.com", max_results=1)
        
        assert emails[0]["category"] == "primary", \
            f"Category should be 'primary', got: {emails[0]['category']}"
    
    print("✅ Primary category correctly detected")


def test_get_email_by_id_includes_category():
    """Test that get_email_by_id also returns category."""
    from app.tools.gmail_tools import get_email_by_id
    
    mock_message = {
        "id": "msg123",
        "threadId": "thread456",
        "labelIds": ["INBOX", "CATEGORY_SOCIAL"],
        "snippet": "Social notification",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "New follower!"},
                {"name": "From", "value": "notifications@social.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Date", "value": "Fri, 02 Jan 2026 08:00:00 -0500"},
            ],
            "body": {"data": "U29jaWFsIHVwZGF0ZQ=="}
        }
    }
    
    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value.messages.return_value = mock_messages
    mock_messages.get.return_value.execute.return_value = mock_message
    
    with patch("app.tools.gmail_tools.get_gmail_service", return_value=mock_service):
        email = get_email_by_id(user_email="test@example.com", email_id="msg123")
        
        assert "category" in email, "Email should have category field"
        assert email["category"] == "social", \
            f"Category should be 'social', got: {email['category']}"
    
    print("✅ get_email_by_id includes category field")


def test_system_prompt_includes_email_guidance():
    """Test that system prompt includes email prioritization guidance."""
    # Read the agent.py file directly to avoid import dependency issues
    agent_file = os.path.join(os.path.dirname(__file__), "..", "app", "core", "agent.py")
    
    with open(agent_file, "r") as f:
        agent_content = f.read()
    
    # Check for email prioritization section
    assert "read_important_emails" in agent_content, \
        "System prompt should mention read_important_emails tool"
    
    assert "Primary" in agent_content or "primary" in agent_content, \
        "System prompt should mention Primary inbox"
    
    assert "promotions" in agent_content.lower() or "excludes" in agent_content.lower(), \
        "System prompt should explain category filtering"
    
    print("✅ System prompt includes email prioritization guidance")


# Manual test runner
if __name__ == "__main__":
    print("Running Gmail Category Integration Tests...\n")
    
    test_read_important_emails_tool_exists()
    test_read_recent_emails_tool_exists()
    test_read_important_emails_docstring()
    test_read_recent_emails_docstring_mentions_category()
    test_query_building_with_category()
    test_query_building_with_category_and_other_filters()
    test_query_building_without_category()
    test_email_response_includes_category()
    test_email_response_primary_category()
    test_get_email_by_id_includes_category()
    test_system_prompt_includes_email_guidance()
    
    print("\n✅ All Gmail category integration tests passed!")

