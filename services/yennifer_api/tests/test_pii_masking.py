"""
Tests for PII Masking Module

Run with: pytest tests/test_pii_masking.py -v
"""

import pytest
from app.core.pii import (
    PIIContext,
    MaskingMode,
    PIIType,
    mask_pii,
    mask_pii_financial_only,
    mask_pii_in_dict,
    resolve_pii_reference,
    set_pii_context,
    clear_pii_context,
    get_pii_context,
)


class TestPIIPatterns:
    """Test that individual PII patterns are correctly detected."""
    
    def test_mask_email(self):
        text = "Contact john.smith@company.com for details"
        result = mask_pii(text)
        assert "john.smith@company.com" not in result
        assert "[EMAIL_" in result
    
    def test_mask_multiple_emails(self):
        # Clear context to get fresh counters
        clear_pii_context()
        
        text = "Email alice@example.com or bob@test.org"
        result = mask_pii(text)
        assert "alice@example.com" not in result
        assert "bob@test.org" not in result
        # Should have two email placeholders (counter may vary based on test order)
        assert result.count("[EMAIL_") == 2
    
    def test_mask_phone_us(self):
        text = "Call me at 123-456-7890"
        result = mask_pii(text)
        assert "123-456-7890" not in result
        assert "[PHONE_" in result
    
    def test_mask_phone_parens(self):
        text = "Phone: (415) 555-1234"
        result = mask_pii(text)
        assert "(415) 555-1234" not in result
        assert "[PHONE_" in result
    
    def test_mask_phone_international(self):
        text = "Call +1-800-555-1234"
        result = mask_pii(text)
        assert "+1-800-555-1234" not in result
        assert "[PHONE_" in result
    
    def test_mask_ssn(self):
        text = "SSN: 123-45-6789"
        result = mask_pii(text)
        assert "123-45-6789" not in result
        assert "[SSN_" in result
    
    def test_mask_credit_card(self):
        text = "Card: 4111-1111-1111-1111"
        result = mask_pii(text)
        assert "4111-1111-1111-1111" not in result
        assert "[CARD_" in result
    
    def test_mask_credit_card_no_dashes(self):
        text = "Card number: 4111111111111111"
        result = mask_pii(text)
        assert "4111111111111111" not in result
        assert "[CARD_" in result
    
    def test_mask_bank_account(self):
        text = "Account #12345678901234"
        result = mask_pii(text)
        assert "12345678901234" not in result
        assert "[ACCOUNT_" in result
    
    def test_mask_street_address(self):
        text = "Lives at 123 Main Street, New York 10001"
        result = mask_pii(text)
        assert "123 Main Street" not in result
        assert "[ADDRESS_" in result
    
    def test_mask_dob(self):
        text = "Born: 01/15/1990"
        result = mask_pii(text)
        assert "01/15/1990" not in result
        assert "[DOB_" in result


class TestMaskingModes:
    """Test different masking modes."""
    
    def setup_method(self):
        """Clear context before each test."""
        clear_pii_context()
    
    def test_full_mode_masks_all(self):
        text = "Email: john@test.com, SSN: 123-45-6789"
        result = mask_pii(text, mode=MaskingMode.FULL)
        assert "john@test.com" not in result
        assert "123-45-6789" not in result
    
    def test_financial_only_keeps_email(self):
        text = "Email: john@test.com, SSN: 123-45-6789"
        result = mask_pii_financial_only(text)
        # Email should be visible
        assert "john@test.com" in result
        # SSN should be masked
        assert "123-45-6789" not in result
        assert "[SSN_" in result
    
    def test_financial_only_keeps_phone(self):
        text = "Phone: 415-555-1234, Card: 4111-1111-1111-1111"
        result = mask_pii_financial_only(text)
        # Phone should be visible
        assert "415-555-1234" in result
        # Card should be masked
        assert "4111-1111-1111-1111" not in result


class TestPIIContext:
    """Test PIIContext tracking and resolution."""
    
    def setup_method(self):
        """Fresh context for each test."""
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_context_tracks_masked_items(self):
        text = "Email: alice@example.com"
        mask_pii(text)
        
        ctx = get_pii_context()
        stats = ctx.get_stats()
        
        assert stats["total"] >= 1
        assert stats.get("email", 0) >= 1
    
    def test_resolve_masked_email(self):
        text = "Contact john@test.com"
        result = mask_pii(text)
        
        # Extract the placeholder
        # Result should be like "Contact [EMAIL_1]"
        placeholder = "[EMAIL_1]"
        resolved = resolve_pii_reference(placeholder)
        
        assert resolved == "john@test.com"
    
    def test_resolve_nonexistent_returns_none(self):
        resolved = resolve_pii_reference("[EMAIL_999]")
        assert resolved is None
    
    def test_context_isolation(self):
        """Test that different contexts are isolated."""
        ctx1 = PIIContext()
        set_pii_context(ctx1)
        
        mask_pii("Email: one@test.com")
        assert ctx1.get_stats()["total"] >= 1
        
        # New context should be clean
        ctx2 = PIIContext()
        set_pii_context(ctx2)
        
        assert ctx2.get_stats()["total"] == 0


class TestMaskPIIInDict:
    """Test dictionary masking."""
    
    def setup_method(self):
        clear_pii_context()
    
    def test_mask_dict_values(self):
        data = {
            "subject": "Meeting",
            "from": "john@test.com",
            "body": "My SSN is 123-45-6789",
        }
        result = mask_pii_in_dict(data)
        
        # Subject shouldn't have masking
        assert result["subject"] == "Meeting"
        
        # From should have masked email
        assert "john@test.com" not in result["from"]
        
        # Body should have masked SSN
        assert "123-45-6789" not in result["body"]
    
    def test_mask_specific_keys_only(self):
        data = {
            "subject": "Meeting about SSN 123-45-6789",
            "body": "SSN: 123-45-6789",
        }
        result = mask_pii_in_dict(data, keys_to_mask=["body"])
        
        # Subject should NOT be masked (not in keys_to_mask)
        assert "123-45-6789" in result["subject"]
        
        # Body SHOULD be masked
        assert "123-45-6789" not in result["body"]
    
    def test_mask_nested_dict(self):
        data = {
            "email": {
                "from": "alice@test.com",
                "to": "bob@test.com",
            }
        }
        result = mask_pii_in_dict(data)
        
        assert "alice@test.com" not in result["email"]["from"]
        assert "bob@test.com" not in result["email"]["to"]


class TestEdgeCases:
    """Test edge cases and robustness."""
    
    def test_empty_string(self):
        assert mask_pii("") == ""
    
    def test_none_string(self):
        assert mask_pii(None) is None
    
    def test_no_pii(self):
        text = "This is a normal message without PII"
        assert mask_pii(text) == text
    
    def test_already_masked_not_double_masked(self):
        """Ensure already masked items aren't re-masked."""
        text = "Contact [EMAIL_1] for details"
        result = mask_pii(text)
        assert result == text  # Should be unchanged
    
    def test_mixed_content(self):
        text = """
        Meeting Notes:
        - Attendee: john@company.com (415-555-1234)
        - Topic: Budget review
        - Card ending: 4111-1111-1111-1111
        - Reference: Doc #12345
        """
        result = mask_pii(text)
        
        # All PII should be masked
        assert "john@company.com" not in result
        assert "415-555-1234" not in result
        assert "4111-1111-1111-1111" not in result
        
        # Non-PII should remain
        assert "Meeting Notes" in result
        assert "Budget review" in result
        assert "Doc #12345" in result


class TestAuditLog:
    """Test audit logging functionality."""
    
    def setup_method(self):
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_audit_log_format(self):
        text = "Email: john@test.com, Phone: 415-555-1234"
        mask_pii(text)
        
        ctx = get_pii_context()
        audit = ctx.get_audit_log()
        
        assert len(audit) >= 2
        
        # Check audit entry structure
        for entry in audit:
            assert "type" in entry
            assert "placeholder" in entry
            assert "masked_at" in entry
            # Should NOT contain original value
            assert "original_value" not in entry


class TestPIIAuditLogger:
    """Test PII audit logging functionality."""
    
    def test_audit_logger_queues_entries(self):
        from app.core.pii_audit import PIIAuditLogger
        
        logger = PIIAuditLogger()
        
        stats = {"total": 5, "email": 2, "phone": 1, "ssn": 1, "card": 1}
        logger.log_masking_event(
            user_id=None,
            request_id="req-123",
            endpoint="/api/v1/chat",
            tool_name="read_email",
            stats=stats,
            masking_mode="full",
        )
        
        assert len(logger._pending_entries) == 1
        entry = logger._pending_entries[0]
        assert entry["total_masked"] == 5
        assert entry["emails_masked"] == 2
        assert entry["tool_name"] == "read_email"
    
    def test_audit_logger_skips_zero_masked(self):
        from app.core.pii_audit import PIIAuditLogger
        
        logger = PIIAuditLogger()
        
        stats = {"total": 0}
        logger.log_masking_event(
            user_id=None,
            request_id="req-123",
            endpoint="/api/v1/chat",
            tool_name="read_email",
            stats=stats,
        )
        
        # Should not queue entry if nothing was masked
        assert len(logger._pending_entries) == 0
    
    def test_audit_logger_disable(self):
        from app.core.pii_audit import PIIAuditLogger
        
        logger = PIIAuditLogger()
        logger.disable()
        
        stats = {"total": 5, "email": 2}
        logger.log_masking_event(
            user_id=None,
            request_id="req-123",
            endpoint="/api/v1/chat",
            tool_name="read_email",
            stats=stats,
        )
        
        # Should not queue when disabled
        assert len(logger._pending_entries) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

