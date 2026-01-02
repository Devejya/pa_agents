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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

