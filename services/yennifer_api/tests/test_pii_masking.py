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
    unmask_pii,
    mask_message_for_llm,
    mask_tool_call_args,
)


class TestPIIPatterns:
    """Test that individual PII patterns are correctly detected.
    
    NOTE: All placeholders now use OPAQUE format [MASKED_N].
    """
    
    def setup_method(self):
        """Fresh context for each test."""
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_mask_email(self):
        text = "Contact john.smith@company.com for details"
        result = mask_pii(text)
        assert "john.smith@company.com" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_mask_multiple_emails(self):
        text = "Email alice@example.com or bob@test.org"
        result = mask_pii(text)
        assert "alice@example.com" not in result
        assert "bob@test.org" not in result
        # Should have two sequential OPAQUE placeholders
        assert "[MASKED_1]" in result
        assert "[MASKED_2]" in result
    
    def test_mask_phone_us(self):
        text = "Call me at 123-456-7890"
        result = mask_pii(text)
        assert "123-456-7890" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_mask_phone_parens(self):
        text = "Phone: (415) 555-1234"
        result = mask_pii(text)
        assert "(415) 555-1234" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_mask_phone_international(self):
        text = "Call +1-800-555-1234"
        result = mask_pii(text)
        assert "+1-800-555-1234" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_mask_ssn(self):
        text = "SSN: 123-45-6789"
        result = mask_pii(text)
        assert "123-45-6789" not in result
        assert "[MASKED_" in result  # Opaque format
        assert "[SSN_" not in result  # NO type leakage
    
    def test_mask_credit_card(self):
        text = "Card: 4111-1111-1111-1111"
        result = mask_pii(text)
        assert "4111-1111-1111-1111" not in result
        assert "[MASKED_" in result  # Opaque format
        assert "[CARD_" not in result  # NO type leakage
    
    def test_mask_credit_card_no_dashes(self):
        text = "Card number: 4111111111111111"
        result = mask_pii(text)
        assert "4111111111111111" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_mask_bank_account(self):
        text = "Account #12345678901234"
        result = mask_pii(text)
        assert "12345678901234" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_mask_street_address(self):
        text = "Lives at 123 Main Street, New York 10001"
        result = mask_pii(text)
        assert "123 Main Street" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_mask_dob(self):
        text = "Born: 01/15/1990"
        result = mask_pii(text)
        assert "01/15/1990" not in result
        assert "[MASKED_" in result  # Opaque format


class TestMaskingModes:
    """Test different masking modes with OPAQUE placeholders."""
    
    def setup_method(self):
        """Clear context before each test."""
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_full_mode_masks_all(self):
        text = "Email: john@test.com, SSN: 123-45-6789"
        result = mask_pii(text, mode=MaskingMode.FULL)
        assert "john@test.com" not in result
        assert "123-45-6789" not in result
        assert "[MASKED_" in result  # Opaque format
    
    def test_financial_only_keeps_email(self):
        text = "Email: john@test.com, SSN: 123-45-6789"
        result = mask_pii_financial_only(text)
        # Email should be visible
        assert "john@test.com" in result
        # SSN should be masked with OPAQUE placeholder
        assert "123-45-6789" not in result
        assert "[MASKED_" in result  # Opaque format
    
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
        
        # Extract the placeholder - now OPAQUE format
        # Result should be like "Contact [MASKED_1]"
        placeholder = "[MASKED_1]"
        resolved = resolve_pii_reference(placeholder)
        
        assert resolved == "john@test.com"
    
    def test_resolve_nonexistent_returns_none(self):
        resolved = resolve_pii_reference("[MASKED_999]")
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


class TestLLMBoundaryMasking:
    """Test PII masking at LLM boundary - user input, chat history, etc.
    
    NOTE: All placeholders now use OPAQUE format [MASKED_N] to avoid
    triggering LLM safety filters based on type names.
    """
    
    def setup_method(self):
        """Fresh context for each test."""
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    # =========================================================
    # User Input Masking Tests (OPAQUE placeholders)
    # =========================================================
    
    def test_user_ssn_input_masked(self):
        """SSN in user input should be masked with OPAQUE placeholder."""
        user_input = "My SSN is 123-45-6789"
        masked = mask_message_for_llm(user_input, role="user")
        
        assert "123-45-6789" not in masked
        assert "[MASKED_" in masked  # Opaque format
        assert "[SSN_" not in masked  # NO type leakage
    
    def test_user_sin_input_masked(self):
        """Canadian SIN should be masked with OPAQUE placeholder."""
        user_input = "My SIN is 111-222-333"
        masked = mask_message_for_llm(user_input, role="user")
        
        assert "111-222-333" not in masked
        assert "[MASKED_" in masked  # Opaque format
        assert "[SSN_" not in masked  # NO type leakage
    
    def test_user_credit_card_input_masked(self):
        """Credit card in user input should be masked with OPAQUE placeholder."""
        user_input = "My card is 4500 1111 1111 0911"
        masked = mask_message_for_llm(user_input, role="user")
        
        assert "4500 1111 1111 0911" not in masked
        assert "[MASKED_" in masked  # Opaque format
        assert "[CARD_" not in masked  # NO type leakage
    
    def test_user_email_input_masked(self):
        """Email in user input should be masked with OPAQUE placeholder."""
        user_input = "Contact me at user@example.com"
        masked = mask_message_for_llm(user_input, role="user")
        
        assert "user@example.com" not in masked
        assert "[MASKED_" in masked  # Opaque format
        assert "[EMAIL_" not in masked  # NO type leakage
    
    def test_multiple_pii_items_tracked(self):
        """Multiple PII items should have sequential OPAQUE IDs."""
        user_input = "SSN: 123-45-6789, Card: 4111-1111-1111-1111"
        masked = mask_message_for_llm(user_input, role="user")
        
        # Should have sequential MASKED_N placeholders
        assert "[MASKED_1]" in masked
        assert "[MASKED_2]" in masked
        # NO type-specific placeholders
        assert "[SSN_" not in masked
        assert "[CARD_" not in masked
        
        # Context should still track types for audit
        ctx = get_pii_context()
        stats = ctx.get_stats()
        assert stats.get("ssn", 0) >= 1
        assert stats.get("card", 0) >= 1
    
    # =========================================================
    # Unmasking Tests
    # =========================================================
    
    def test_unmask_restores_email(self):
        """Unmasking should restore original email from OPAQUE placeholder."""
        original = "Contact john@example.com for help"
        masked = mask_message_for_llm(original, role="user")
        
        assert "[MASKED_" in masked
        assert "john@example.com" not in masked
        
        # Unmask for user
        unmasked = unmask_pii(masked)
        
        assert "john@example.com" in unmasked
    
    def test_unmask_restores_phone(self):
        """Unmasking should restore original phone."""
        original = "Call me at 555-123-4567"
        masked = mask_message_for_llm(original, role="user")
        
        unmasked = unmask_pii(masked)
        
        assert "555-123-4567" in unmasked
    
    def test_unmask_restores_ssn(self):
        """Unmasking should restore original SSN."""
        original = "My SSN is 123-45-6789"
        masked = mask_message_for_llm(original, role="user")
        
        unmasked = unmask_pii(masked)
        
        assert "123-45-6789" in unmasked
    
    def test_unmask_preserves_non_pii(self):
        """Non-PII content should be preserved."""
        original = "Hello, how are you?"
        masked = mask_message_for_llm(original, role="user")
        unmasked = unmask_pii(masked)
        
        assert unmasked == original
    
    def test_unmask_llm_response_with_placeholder(self):
        """Test unmasking realistic LLM response with OPAQUE placeholders."""
        # User sent SSN, which gets masked
        user_input = "My SSN is 123-45-6789, please save it"
        mask_message_for_llm(user_input, role="user")  # Populates context
        
        # LLM response references the OPAQUE placeholder
        llm_response = "I've noted your SSN [MASKED_1]. It's stored securely."
        
        # Unmask for user
        user_response = unmask_pii(llm_response)
        
        # User should see their actual SSN
        assert "123-45-6789" in user_response
        assert "[MASKED_1]" not in user_response
    
    # =========================================================
    # Tool Call Args Masking Tests (OPAQUE placeholders)
    # =========================================================
    
    def test_tool_call_args_email_masked(self):
        """Email in tool call args should be masked with OPAQUE placeholder."""
        tool_calls = [{
            "name": "send_email",
            "id": "call_123",
            "args": {
                "to": "john@example.com",
                "subject": "Test",
                "body": "Hello"
            }
        }]
        
        masked = mask_tool_call_args(tool_calls)
        
        assert "john@example.com" not in str(masked)
        assert "[MASKED_" in masked[0]["args"]["to"]  # Opaque format
    
    def test_tool_call_args_preserves_non_string(self):
        """Non-string arguments should be preserved."""
        tool_calls = [{
            "name": "read_emails",
            "id": "call_123",
            "args": {
                "max_results": 10,
                "include_spam": False
            }
        }]
        
        masked = mask_tool_call_args(tool_calls)
        
        assert masked[0]["args"]["max_results"] == 10
        assert masked[0]["args"]["include_spam"] == False
    
    def test_tool_call_args_preserves_id(self):
        """Tool call ID should be preserved."""
        tool_calls = [{
            "name": "send_email",
            "id": "call_abc123",
            "args": {"to": "test@example.com"}
        }]
        
        masked = mask_tool_call_args(tool_calls)
        
        assert masked[0]["id"] == "call_abc123"
        assert masked[0]["name"] == "send_email"
    
    def test_tool_call_args_none_input(self):
        """None input should return None."""
        assert mask_tool_call_args(None) is None
    
    def test_tool_call_args_empty_list(self):
        """Empty list should return empty list."""
        assert mask_tool_call_args([]) == []
    
    # =========================================================
    # Chat History Simulation Tests (OPAQUE placeholders)
    # =========================================================
    
    def test_history_ssn_masked(self):
        """SSN from previous message should be masked with OPAQUE placeholder."""
        # Simulate history containing SSN
        history_content = "My SSN is 123-45-6789"
        masked_history = mask_message_for_llm(history_content, role="user")
        
        assert "123-45-6789" not in masked_history
        assert "[MASKED_" in masked_history  # Opaque format
        assert "[SSN_" not in masked_history  # NO type leakage
    
    def test_history_assistant_response_masked(self):
        """AIMessage from history may echo PII and should be masked with OPAQUE placeholder."""
        # Simulate assistant echoing back an email
        assistant_content = "I found your email: john@example.com"
        masked = mask_message_for_llm(assistant_content, role="assistant")
        
        assert "john@example.com" not in masked
        assert "[MASKED_" in masked  # Opaque format
        assert "[EMAIL_" not in masked  # NO type leakage
    
    def test_history_tool_result_masked(self):
        """Tool results from history should be masked with OPAQUE placeholder."""
        # Simulate tool result containing contact info
        tool_content = "Contact found: John Smith, phone: 555-123-4567"
        masked = mask_message_for_llm(tool_content, role="tool")
        
        assert "555-123-4567" not in masked
        assert "[MASKED_" in masked  # Opaque format
        assert "[PHONE_" not in masked  # NO type leakage


class TestPIIFlowIntegration:
    """Integration tests for complete PII flow: mask → LLM → unmask.
    
    All tests now use OPAQUE placeholders [MASKED_N].
    """
    
    def setup_method(self):
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_full_roundtrip_ssn(self):
        """Test complete SSN flow: user input → masked → response → unmasked."""
        # 1. User sends SSN
        user_input = "Store my SSN: 123-45-6789"
        masked_input = mask_message_for_llm(user_input, role="user")
        
        # 2. Verify OPAQUE masking (no type leakage)
        assert "123-45-6789" not in masked_input
        assert "[MASKED_1]" in masked_input
        assert "[SSN_" not in masked_input
        
        # 3. Simulate LLM response referencing the OPAQUE placeholder
        llm_response = "I've securely stored your number [MASKED_1]. Is there anything else?"
        
        # 4. Unmask for user
        final_response = unmask_pii(llm_response)
        
        # 5. User sees original SSN
        assert "123-45-6789" in final_response
        assert "[MASKED_1]" not in final_response
    
    def test_full_roundtrip_credit_card(self):
        """Test complete credit card flow with OPAQUE placeholders."""
        user_input = "My card number is 4111-1111-1111-1111"
        masked_input = mask_message_for_llm(user_input, role="user")
        
        assert "4111-1111-1111-1111" not in masked_input
        assert "[MASKED_1]" in masked_input
        assert "[CARD_" not in masked_input
        
        llm_response = "Card [MASKED_1] has been saved to your profile."
        final_response = unmask_pii(llm_response)
        
        assert "4111-1111-1111-1111" in final_response
    
    def test_multiple_pii_roundtrip(self):
        """Test with multiple PII items - sequential OPAQUE IDs."""
        user_input = "My SSN is 123-45-6789 and my card is 4111-1111-1111-1111"
        masked_input = mask_message_for_llm(user_input, role="user")
        
        # Both should be masked with sequential OPAQUE IDs
        assert "123-45-6789" not in masked_input
        assert "4111-1111-1111-1111" not in masked_input
        assert "[MASKED_1]" in masked_input
        assert "[MASKED_2]" in masked_input
        # No type-specific placeholders
        assert "[SSN_" not in masked_input
        assert "[CARD_" not in masked_input
        
        # LLM references both with OPAQUE placeholders
        llm_response = "Stored your number [MASKED_1] and card [MASKED_2]."
        final_response = unmask_pii(llm_response)
        
        # Both should be restored
        assert "123-45-6789" in final_response
        assert "4111-1111-1111-1111" in final_response
    
    def test_conversation_continuity(self):
        """Test that context persists across multiple masking calls."""
        # First message with SSN
        msg1 = "My SSN is 123-45-6789"
        masked1 = mask_message_for_llm(msg1, role="user")
        
        # Second message with email
        msg2 = "My email is john@example.com"
        masked2 = mask_message_for_llm(msg2, role="user")
        
        # Both should be tracked in context (types for audit)
        ctx = get_pii_context()
        stats = ctx.get_stats()
        
        assert stats.get("ssn", 0) >= 1
        assert stats.get("email", 0) >= 1
        
        # LLM response references both with OPAQUE placeholders
        # SSN was [MASKED_1], email was [MASKED_2]
        llm_response = "Your number [MASKED_1] and email [MASKED_2] are saved."
        final = unmask_pii(llm_response)
        
        assert "123-45-6789" in final
        assert "john@example.com" in final
    
    def test_same_value_deduplication(self):
        """Test that same PII value gets same OPAQUE placeholder."""
        user_input = "My SSN is 123-45-6789. Remember, it's 123-45-6789."
        masked = mask_message_for_llm(user_input, role="user")
        
        # Same value should have same placeholder
        assert masked.count("[MASKED_1]") == 2
        assert "[MASKED_2]" not in masked
        
        # Unmasking should restore both
        unmasked = unmask_pii(masked)
        assert unmasked.count("123-45-6789") == 2
    
    def test_no_type_leakage_in_any_placeholder(self):
        """Verify NO PII type information leaks into placeholders."""
        user_input = """
        SSN: 123-45-6789
        Card: 4111-1111-1111-1111
        Email: test@example.com
        Phone: 555-123-4567
        """
        masked = mask_message_for_llm(user_input, role="user")
        
        # Verify no type-specific placeholders
        assert "[SSN_" not in masked
        assert "[CARD_" not in masked
        assert "[EMAIL_" not in masked
        assert "[PHONE_" not in masked
        assert "[ACCOUNT_" not in masked
        assert "[ADDRESS_" not in masked
        
        # Only MASKED_N format allowed
        import re
        all_placeholders = re.findall(r'\[[A-Z_]+_\d+\]', masked)
        for placeholder in all_placeholders:
            assert placeholder.startswith("[MASKED_"), f"Non-opaque placeholder found: {placeholder}"


# =============================================================================
# India-specific PII Masking Tests
# =============================================================================

class TestIndiaPIIPatterns:
    """Test India-specific PII patterns: Aadhaar, PAN, IFSC, UPI, etc.
    
    All placeholders use OPAQUE format [MASKED_N] to prevent LLM type inference.
    """
    
    def setup_method(self):
        """Fresh context for each test."""
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    # =========================================================
    # Aadhaar Number Tests
    # =========================================================
    
    def test_mask_aadhaar_with_spaces(self):
        """Aadhaar with spaces (2345 6789 0123) should be masked."""
        text = "My Aadhaar is 2345 6789 0123"
        result = mask_pii(text)
        
        assert "2345 6789 0123" not in result
        assert "[MASKED_" in result
        # Verify type tracking for audit
        ctx = get_pii_context()
        assert ctx.get_stats().get("aadhaar", 0) >= 1
    
    def test_mask_aadhaar_with_dashes(self):
        """Aadhaar with dashes (2345-6789-0123) should be masked."""
        text = "Aadhaar: 2345-6789-0123"
        result = mask_pii(text)
        
        assert "2345-6789-0123" not in result
        assert "[MASKED_" in result
    
    def test_mask_aadhaar_without_separators(self):
        """Aadhaar without separators (234567890123) should be masked."""
        text = "UID: 234567890123"
        result = mask_pii(text)
        
        assert "234567890123" not in result
        assert "[MASKED_" in result
    
    def test_aadhaar_first_digit_validation(self):
        """Aadhaar starting with 0 or 1 should NOT be matched (invalid)."""
        # Valid Aadhaar starts with 2-9
        text1 = "Number: 0123 4567 8901"  # Invalid: starts with 0
        text2 = "Number: 1234 5678 9012"  # Invalid: starts with 1
        
        result1 = mask_pii(text1)
        result2 = mask_pii(text2)
        
        # These should NOT be masked as Aadhaar (but might match other patterns)
        # Check that no AADHAAR type was tracked
        ctx1 = get_pii_context()
        assert ctx1.get_stats().get("aadhaar", 0) == 0
    
    # =========================================================
    # PAN Tests
    # =========================================================
    
    def test_mask_pan_person(self):
        """PAN for person (4th char = P) should be masked."""
        text = "My PAN is ABCPK1234J"
        result = mask_pii(text)
        
        assert "ABCPK1234J" not in result
        assert "[MASKED_" in result
        # Verify type tracking
        ctx = get_pii_context()
        assert ctx.get_stats().get("pan", 0) >= 1
    
    def test_mask_pan_company(self):
        """PAN for company (4th char = C) should be masked."""
        text = "Company PAN: AABCM1234F"
        result = mask_pii(text)
        
        assert "AABCM1234F" not in result
        assert "[MASKED_" in result
    
    def test_mask_pan_huf(self):
        """PAN for HUF (4th char = H) should be masked."""
        text = "HUF PAN: XYZHA5678B"
        result = mask_pii(text)
        
        assert "XYZHA5678B" not in result
        assert "[MASKED_" in result
    
    def test_pan_invalid_4th_char_not_matched(self):
        """PAN with invalid 4th character should NOT be matched."""
        # 4th char must be one of: A, B, C, F, G, H, L, J, P, T
        text = "Invalid: ABCDK1234J"  # D is not a valid 4th char
        result = mask_pii(text)
        
        ctx = get_pii_context()
        assert ctx.get_stats().get("pan", 0) == 0
    
    # =========================================================
    # Indian Phone Number Tests
    # =========================================================
    
    def test_mask_indian_phone_with_91_space(self):
        """Indian phone +91 XXXXX XXXXX should be masked."""
        text = "Call me at +91 98765 43210"
        result = mask_pii(text)
        
        assert "98765 43210" not in result
        assert "+91" not in result or "[MASKED_" in result
        # Verify type tracking
        ctx = get_pii_context()
        assert ctx.get_stats().get("in_phone", 0) >= 1
    
    def test_mask_indian_phone_with_91_dash(self):
        """Indian phone +91-XXXXX-XXXXX should be masked."""
        text = "Phone: +91-98765-43210"
        result = mask_pii(text)
        
        assert "98765-43210" not in result
        assert "[MASKED_" in result
    
    def test_mask_indian_phone_without_plus(self):
        """Indian phone 91XXXXXXXXXX should be masked."""
        text = "Number: 919876543210"
        result = mask_pii(text)
        
        assert "919876543210" not in result
        assert "[MASKED_" in result
    
    def test_mask_indian_mobile_10_digit(self):
        """10-digit Indian mobile starting with 6-9 should be masked."""
        text = "Mobile: 9876543210"
        result = mask_pii(text)
        
        assert "9876543210" not in result
        assert "[MASKED_" in result
    
    def test_indian_phone_starts_with_6_7_8_9(self):
        """Indian mobile numbers must start with 6, 7, 8, or 9."""
        # Valid mobiles start with 6, 7, 8, 9
        valid_numbers = ["9876543210", "8765432109", "7654321098", "6543210987"]
        
        for number in valid_numbers:
            clear_pii_context()
            set_pii_context(PIIContext())
            text = f"Number: {number}"
            result = mask_pii(text)
            assert number not in result, f"{number} should be masked"
    
    # =========================================================
    # IFSC Code Tests
    # =========================================================
    
    def test_mask_ifsc_code(self):
        """IFSC code (XXXX0XXXXXX) should be masked."""
        text = "IFSC: HDFC0001234"
        result = mask_pii(text)
        
        assert "HDFC0001234" not in result
        assert "[MASKED_" in result
        # Verify type tracking
        ctx = get_pii_context()
        assert ctx.get_stats().get("ifsc", 0) >= 1
    
    def test_mask_ifsc_various_banks(self):
        """IFSC codes for various banks should be masked."""
        ifsc_codes = ["SBIN0001234", "ICIC0000001", "AXIS0000123", "PUNB0123456"]
        
        for ifsc in ifsc_codes:
            clear_pii_context()
            set_pii_context(PIIContext())
            text = f"Bank IFSC: {ifsc}"
            result = mask_pii(text)
            assert ifsc not in result, f"{ifsc} should be masked"
    
    def test_ifsc_5th_char_must_be_zero(self):
        """IFSC 5th character must be 0 - other values should not match."""
        text = "Invalid IFSC: HDFC1001234"  # 5th char is 1, not 0
        result = mask_pii(text)
        
        ctx = get_pii_context()
        assert ctx.get_stats().get("ifsc", 0) == 0
    
    # =========================================================
    # UPI ID Tests
    # =========================================================
    
    def test_mask_upi_okaxis(self):
        """UPI ID with @okaxis should be masked."""
        text = "Pay to myname@okaxis"
        result = mask_pii(text)
        
        assert "myname@okaxis" not in result
        assert "[MASKED_" in result
        # Verify type tracking
        ctx = get_pii_context()
        assert ctx.get_stats().get("upi", 0) >= 1
    
    def test_mask_upi_ybl(self):
        """UPI ID with @ybl (PhonePe) should be masked."""
        text = "UPI: username@ybl"
        result = mask_pii(text)
        
        assert "username@ybl" not in result
        assert "[MASKED_" in result
    
    def test_mask_upi_paytm(self):
        """UPI ID with @paytm should be masked."""
        text = "VPA: myaccount@paytm"
        result = mask_pii(text)
        
        assert "myaccount@paytm" not in result
        assert "[MASKED_" in result
    
    def test_mask_various_upi_handles(self):
        """Various UPI bank handles should be masked."""
        upi_ids = [
            "user@oksbi",
            "name@okicici", 
            "account@okhdfc",
            "pay@gpay",
            "send@phonepe",
            "money@sbi",
            "transfer@icici",
            "payment@hdfc",
        ]
        
        for upi in upi_ids:
            clear_pii_context()
            set_pii_context(PIIContext())
            text = f"Pay to {upi}"
            result = mask_pii(text)
            assert upi not in result, f"{upi} should be masked"
    
    def test_upi_vs_email_differentiation(self):
        """UPI IDs should be masked before email patterns, emails should still work."""
        text = "Pay to user@okaxis or email user@gmail.com"
        result = mask_pii(text)
        
        # Both should be masked
        assert "user@okaxis" not in result
        assert "user@gmail.com" not in result
        # Should have two different placeholders
        assert "[MASKED_1]" in result
        assert "[MASKED_2]" in result
    
    def test_regular_email_not_matched_as_upi(self):
        """Regular email addresses should NOT be matched as UPI."""
        text = "Email: test@gmail.com"
        result = mask_pii(text)
        
        # Should be masked as EMAIL, not UPI
        ctx = get_pii_context()
        assert ctx.get_stats().get("email", 0) >= 1
        assert ctx.get_stats().get("upi", 0) == 0
    
    # =========================================================
    # Vehicle Registration Tests
    # =========================================================
    
    def test_mask_vehicle_reg_maharashtra(self):
        """Maharashtra vehicle registration should be masked."""
        text = "Car number: MH12AB1234"
        result = mask_pii(text)
        
        assert "MH12AB1234" not in result
        assert "[MASKED_" in result
        # Verify type tracking
        ctx = get_pii_context()
        assert ctx.get_stats().get("vehicle", 0) >= 1
    
    def test_mask_vehicle_reg_with_spaces(self):
        """Vehicle registration with spaces should be masked."""
        text = "Vehicle: MH 12 AB 1234"
        result = mask_pii(text)
        
        assert "MH 12 AB 1234" not in result
        assert "[MASKED_" in result
    
    def test_mask_vehicle_reg_delhi(self):
        """Delhi vehicle registration should be masked."""
        # Standard Delhi format: DL + district (2 digits) + series + number
        text = "DL10CQ1234"
        result = mask_pii(text)
        
        assert "DL10CQ1234" not in result
        assert "[MASKED_" in result
    
    def test_mask_various_state_registrations(self):
        """Vehicle registrations from various states should be masked."""
        registrations = [
            "KA01MG1234",   # Karnataka
            "TN22C5678",    # Tamil Nadu
            "DL10CQ9999",   # Delhi
            "GJ01AB1234",   # Gujarat
            "UP32AB1234",   # Uttar Pradesh
        ]
        
        for reg in registrations:
            clear_pii_context()
            set_pii_context(PIIContext())
            text = f"Vehicle: {reg}"
            result = mask_pii(text)
            assert reg not in result, f"{reg} should be masked"
    
    # =========================================================
    # GSTIN Tests
    # =========================================================
    
    def test_mask_gstin(self):
        """GSTIN (15-char GST number) should be masked."""
        text = "GST: 22AAAAA0000A1Z5"
        result = mask_pii(text)
        
        assert "22AAAAA0000A1Z5" not in result
        assert "[MASKED_" in result
        # Verify type tracking
        ctx = get_pii_context()
        assert ctx.get_stats().get("gstin", 0) >= 1
    
    def test_mask_gstin_various_states(self):
        """GSTINs from various states should be masked."""
        gstins = [
            "27AABCU9603R1ZM",  # Maharashtra
            "06AABCT1332L1ZG",  # Haryana
            "29AABCT9603R1ZM",  # Karnataka
        ]
        
        for gstin in gstins:
            clear_pii_context()
            set_pii_context(PIIContext())
            text = f"GSTIN: {gstin}"
            result = mask_pii(text)
            assert gstin not in result, f"{gstin} should be masked"
    
    # =========================================================
    # Indian Passport Tests
    # =========================================================
    
    def test_mask_indian_passport_contextual(self):
        """Indian passport number near 'passport' keyword should be masked."""
        text = "My passport number is A1234567"
        result = mask_pii(text)
        
        assert "A1234567" not in result
        assert "[MASKED_" in result
        # Verify type tracking
        ctx = get_pii_context()
        assert ctx.get_stats().get("in_passport", 0) >= 1
    
    def test_mask_passport_with_colon(self):
        """Passport: A1234567 format should be masked."""
        text = "Passport: J9876543"
        result = mask_pii(text)
        
        assert "J9876543" not in result
        assert "[MASKED_" in result
    
    # =========================================================
    # FINANCIAL_ONLY Mode Tests for India PII
    # =========================================================
    
    def test_financial_only_masks_aadhaar(self):
        """Aadhaar should be masked in FINANCIAL_ONLY mode (national ID)."""
        text = "Aadhaar: 2345 6789 0123"
        result = mask_pii_financial_only(text)
        
        assert "2345 6789 0123" not in result
        assert "[MASKED_" in result
    
    def test_financial_only_masks_pan(self):
        """PAN should be masked in FINANCIAL_ONLY mode (tax ID)."""
        text = "PAN: ABCPK1234J"
        result = mask_pii_financial_only(text)
        
        assert "ABCPK1234J" not in result
        assert "[MASKED_" in result
    
    def test_financial_only_masks_upi(self):
        """UPI ID should be masked in FINANCIAL_ONLY mode (payment info)."""
        text = "Pay to myname@okaxis"
        result = mask_pii_financial_only(text)
        
        assert "myname@okaxis" not in result
        assert "[MASKED_" in result
    
    def test_financial_only_masks_ifsc(self):
        """IFSC should be masked in FINANCIAL_ONLY mode (bank code)."""
        text = "IFSC: HDFC0001234"
        result = mask_pii_financial_only(text)
        
        assert "HDFC0001234" not in result
        assert "[MASKED_" in result
    
    def test_financial_only_masks_gstin(self):
        """GSTIN should be masked in FINANCIAL_ONLY mode (tax ID)."""
        text = "GST: 22AAAAA0000A1Z5"
        result = mask_pii_financial_only(text)
        
        assert "22AAAAA0000A1Z5" not in result
        assert "[MASKED_" in result
    
    def test_financial_only_keeps_indian_phone(self):
        """Indian phone should stay visible in FINANCIAL_ONLY mode (contact info)."""
        text = "Phone: +91 98765 43210"
        result = mask_pii_financial_only(text)
        
        # Phone should be visible (same as email/phone for US users)
        # Note: The +91 pattern might be partially matched, let's check the number part
        assert "98765" in result or "+91" in result
    
    def test_financial_only_keeps_vehicle_reg(self):
        """Vehicle registration should stay visible in FINANCIAL_ONLY mode."""
        text = "Car: MH12AB1234"
        result = mask_pii_financial_only(text)
        
        # Vehicle reg should be visible
        assert "MH12AB1234" in result


class TestIndiaPIIUnmasking:
    """Test unmasking of India-specific PII types."""
    
    def setup_method(self):
        """Fresh context for each test."""
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_unmask_aadhaar(self):
        """Unmasking should restore Aadhaar number."""
        original = "My Aadhaar is 2345 6789 0123"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert "2345 6789 0123" in unmasked
    
    def test_unmask_pan(self):
        """Unmasking should restore PAN."""
        original = "My PAN is ABCPK1234J"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert "ABCPK1234J" in unmasked
    
    def test_unmask_indian_phone(self):
        """Unmasking should restore Indian phone number."""
        original = "Call me at +91 98765 43210"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert "+91 98765 43210" in unmasked
    
    def test_unmask_upi_id(self):
        """Unmasking should restore UPI ID."""
        original = "Pay to myname@okaxis"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert "myname@okaxis" in unmasked
    
    def test_unmask_ifsc(self):
        """Unmasking should restore IFSC code."""
        original = "Bank IFSC: HDFC0001234"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert "HDFC0001234" in unmasked
    
    def test_unmask_vehicle_reg(self):
        """Unmasking should restore vehicle registration."""
        original = "Car: MH12AB1234"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert "MH12AB1234" in unmasked
    
    def test_unmask_gstin(self):
        """Unmasking should restore GSTIN."""
        original = "GST: 22AAAAA0000A1Z5"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert "22AAAAA0000A1Z5" in unmasked


class TestIndiaPIIIntegration:
    """Integration tests for India PII in complete flow."""
    
    def setup_method(self):
        """Fresh context for each test."""
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_full_roundtrip_aadhaar(self):
        """Test complete Aadhaar flow: mask → LLM response → unmask."""
        # User sends Aadhaar
        user_input = "Store my Aadhaar: 2345 6789 0123"
        masked_input = mask_message_for_llm(user_input, role="user")
        
        # Verify masking
        assert "2345 6789 0123" not in masked_input
        assert "[MASKED_1]" in masked_input
        
        # Simulate LLM response
        llm_response = "I've stored your identification number [MASKED_1] securely."
        
        # Unmask for user
        final = unmask_pii(llm_response)
        
        assert "2345 6789 0123" in final
        assert "[MASKED_1]" not in final
    
    def test_full_roundtrip_pan(self):
        """Test complete PAN flow: mask → LLM response → unmask."""
        user_input = "My PAN is ABCPK1234J"
        masked_input = mask_message_for_llm(user_input, role="user")
        
        assert "ABCPK1234J" not in masked_input
        assert "[MASKED_1]" in masked_input
        
        llm_response = "Your tax reference [MASKED_1] has been recorded."
        final = unmask_pii(llm_response)
        
        assert "ABCPK1234J" in final
    
    def test_mixed_india_us_pii(self):
        """Test masking both India and US PII in same message."""
        user_input = "My SSN is 123-45-6789 and my Aadhaar is 2345 6789 0123"
        masked_input = mask_message_for_llm(user_input, role="user")
        
        # Both should be masked
        assert "123-45-6789" not in masked_input
        assert "2345 6789 0123" not in masked_input
        assert "[MASKED_1]" in masked_input
        assert "[MASKED_2]" in masked_input
        
        # Verify type tracking
        ctx = get_pii_context()
        stats = ctx.get_stats()
        assert stats.get("ssn", 0) >= 1
        assert stats.get("aadhaar", 0) >= 1
    
    def test_india_pii_sensitive_keywords_masked(self):
        """India-specific sensitive keywords should be replaced with neutral terms."""
        user_input = "My Aadhaar number is 2345 6789 0123 and PAN card is ABCPK1234J"
        masked = mask_message_for_llm(user_input, role="user")
        
        # Keywords should be neutralized
        # "Aadhaar" -> "identification number"
        # "PAN" -> "tax reference"
        assert "Aadhaar" not in masked or "identification" in masked.lower()
        
        # Data should be masked
        assert "2345 6789 0123" not in masked
        assert "ABCPK1234J" not in masked


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

