"""
Test script for Gmail category parsing and filtering.

Run with: 
    cd services/yennifer_api
    python -m pytest tests/test_gmail_category.py -v

Or for manual testing:
    cd services/yennifer_api
    python tests/test_gmail_category.py
"""

import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_gmail_category_imports():
    """Test that Gmail category functions can be imported."""
    from app.tools.gmail_tools import (
        GMAIL_CATEGORIES,
        _get_category,
    )
    print("✅ All imports successful")


def test_category_mapping_completeness():
    """Test that all Gmail categories are mapped."""
    from app.tools.gmail_tools import GMAIL_CATEGORIES
    
    expected_categories = {
        "CATEGORY_PERSONAL": "primary",
        "CATEGORY_SOCIAL": "social",
        "CATEGORY_PROMOTIONS": "promotions",
        "CATEGORY_UPDATES": "updates",
        "CATEGORY_FORUMS": "forums",
    }
    
    assert GMAIL_CATEGORIES == expected_categories, "Category mapping should match expected values"
    print("✅ All 5 Gmail categories are mapped correctly")


def test_get_category_primary():
    """Test extraction of Primary category from labels."""
    from app.tools.gmail_tools import _get_category
    
    labels = ["INBOX", "CATEGORY_PERSONAL", "UNREAD"]
    assert _get_category(labels) == "primary"
    print("✅ CATEGORY_PERSONAL correctly maps to 'primary'")


def test_get_category_social():
    """Test extraction of Social category from labels."""
    from app.tools.gmail_tools import _get_category
    
    labels = ["INBOX", "CATEGORY_SOCIAL", "UNREAD"]
    assert _get_category(labels) == "social"
    print("✅ CATEGORY_SOCIAL correctly maps to 'social'")


def test_get_category_promotions():
    """Test extraction of Promotions category from labels."""
    from app.tools.gmail_tools import _get_category
    
    labels = ["INBOX", "CATEGORY_PROMOTIONS"]
    assert _get_category(labels) == "promotions"
    print("✅ CATEGORY_PROMOTIONS correctly maps to 'promotions'")


def test_get_category_updates():
    """Test extraction of Updates category from labels."""
    from app.tools.gmail_tools import _get_category
    
    labels = ["INBOX", "CATEGORY_UPDATES", "IMPORTANT"]
    assert _get_category(labels) == "updates"
    print("✅ CATEGORY_UPDATES correctly maps to 'updates'")


def test_get_category_forums():
    """Test extraction of Forums category from labels."""
    from app.tools.gmail_tools import _get_category
    
    labels = ["CATEGORY_FORUMS", "INBOX"]
    assert _get_category(labels) == "forums"
    print("✅ CATEGORY_FORUMS correctly maps to 'forums'")


def test_get_category_default():
    """Test default category when no category label is present."""
    from app.tools.gmail_tools import _get_category
    
    # Empty labels
    assert _get_category([]) == "primary"
    
    # Labels without any CATEGORY_ label
    labels = ["INBOX", "UNREAD", "IMPORTANT"]
    assert _get_category(labels) == "primary"
    
    # Only INBOX
    assert _get_category(["INBOX"]) == "primary"
    
    print("✅ Default category is 'primary' when no category label found")


def test_get_category_multiple_labels():
    """Test that category is correctly extracted when mixed with other labels."""
    from app.tools.gmail_tools import _get_category
    
    # Primary with many other labels
    labels = ["INBOX", "UNREAD", "IMPORTANT", "STARRED", "CATEGORY_PERSONAL", "Label_123"]
    assert _get_category(labels) == "primary"
    
    # Promotions buried in labels
    labels = ["UNREAD", "Label_456", "CATEGORY_PROMOTIONS", "INBOX"]
    assert _get_category(labels) == "promotions"
    
    print("✅ Category correctly extracted from mixed label lists")


def test_get_category_with_user_labels():
    """Test that user-created labels don't affect category detection."""
    from app.tools.gmail_tools import _get_category
    
    # User label that starts with CATEGORY but isn't a real category
    labels = ["INBOX", "CATEGORY_CUSTOM_USER_LABEL", "UNREAD"]
    result = _get_category(labels)
    # Should default to primary since CATEGORY_CUSTOM_USER_LABEL is not a valid category
    assert result == "primary"
    
    # User label with valid category also present
    labels = ["INBOX", "Label_Work", "CATEGORY_UPDATES", "Label_Urgent"]
    assert _get_category(labels) == "updates"
    
    print("✅ User labels don't interfere with category detection")


def test_read_emails_category_parameter_docstring():
    """Test that read_emails function has category parameter documented."""
    from app.tools.gmail_tools import read_emails
    
    docstring = read_emails.__doc__
    assert "category" in docstring, "category parameter should be documented"
    assert "primary" in docstring.lower() or "gmail category" in docstring.lower(), \
        "docstring should mention category filtering"
    
    print("✅ read_emails has category parameter documented")


def test_read_emails_function_signature():
    """Test that read_emails accepts category parameter."""
    import inspect
    from app.tools.gmail_tools import read_emails
    
    sig = inspect.signature(read_emails)
    params = list(sig.parameters.keys())
    
    assert "category" in params, "read_emails should have category parameter"
    
    # Check default value is None
    category_param = sig.parameters["category"]
    assert category_param.default is None, "category should default to None"
    
    print("✅ read_emails accepts category parameter with None default")


# Manual test runner
if __name__ == "__main__":
    print("Running Gmail Category Tests...\n")
    
    test_gmail_category_imports()
    test_category_mapping_completeness()
    test_get_category_primary()
    test_get_category_social()
    test_get_category_promotions()
    test_get_category_updates()
    test_get_category_forums()
    test_get_category_default()
    test_get_category_multiple_labels()
    test_get_category_with_user_labels()
    test_read_emails_category_parameter_docstring()
    test_read_emails_function_signature()
    
    print("\n✅ All Gmail category tests passed!")

