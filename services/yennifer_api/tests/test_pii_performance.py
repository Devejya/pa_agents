"""
Performance Tests for PII Masking

Run with: pytest tests/test_pii_performance.py -v
"""

import time
import pytest
from app.core.pii import (
    PIIContext,
    mask_pii,
    mask_message_for_llm,
    mask_tool_call_args,
    unmask_pii,
    set_pii_context,
    clear_pii_context,
)


class TestPIIMaskingPerformance:
    """Test that PII masking is fast enough for production use."""
    
    def setup_method(self):
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_mask_pii_performance_simple(self):
        """Simple text masking should be <1ms per call."""
        text = "Contact john@example.com for details"
        
        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            clear_pii_context()
            set_pii_context(PIIContext())
            mask_pii(text)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        
        avg_ms = elapsed / iterations
        print(f"\nSimple text masking: {avg_ms:.3f}ms per call")
        assert avg_ms < 1, f"Masking took {avg_ms:.3f}ms, expected <1ms"
    
    def test_mask_pii_performance_complex(self):
        """Complex text with multiple PII should be <5ms per call."""
        text = """
        Meeting Notes:
        - Attendee: john.smith@company.com (415-555-1234)
        - SSN on file: 123-45-6789
        - Credit Card: 4111-1111-1111-1111
        - Address: 123 Main Street, San Francisco, CA 94102
        - Emergency contact: jane@example.org (+1-800-555-9876)
        - Bank Account #1234567890123456
        """
        
        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            clear_pii_context()
            set_pii_context(PIIContext())
            mask_pii(text)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        
        avg_ms = elapsed / iterations
        print(f"\nComplex text masking: {avg_ms:.3f}ms per call")
        assert avg_ms < 5, f"Masking took {avg_ms:.3f}ms, expected <5ms"
    
    def test_mask_message_for_llm_performance(self):
        """mask_message_for_llm should add minimal overhead."""
        text = "My SSN is 123-45-6789 and email is user@test.com"
        
        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            clear_pii_context()
            set_pii_context(PIIContext())
            mask_message_for_llm(text, role="user")
        elapsed = (time.perf_counter() - start) * 1000  # ms
        
        avg_ms = elapsed / iterations
        print(f"\nmask_message_for_llm: {avg_ms:.3f}ms per call")
        assert avg_ms < 2, f"Masking took {avg_ms:.3f}ms, expected <2ms"
    
    def test_unmask_pii_performance(self):
        """Unmasking should be <1ms per call."""
        # First mask some content
        mask_pii("Email: test@example.com, SSN: 123-45-6789")
        
        masked_response = "Your email [EMAIL_1] and SSN [SSN_1] are saved."
        
        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            unmask_pii(masked_response)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        
        avg_ms = elapsed / iterations
        print(f"\nUnmasking: {avg_ms:.3f}ms per call")
        assert avg_ms < 1, f"Unmasking took {avg_ms:.3f}ms, expected <1ms"
    
    def test_mask_tool_call_args_performance(self):
        """Tool call args masking should be <2ms per call."""
        tool_calls = [
            {
                "name": "send_email",
                "id": "call_123",
                "args": {
                    "to": "john@example.com",
                    "cc": "jane@example.com",
                    "subject": "Meeting about SSN 123-45-6789",
                    "body": "Please call 555-123-4567"
                }
            }
        ]
        
        start = time.perf_counter()
        iterations = 500
        for _ in range(iterations):
            clear_pii_context()
            set_pii_context(PIIContext())
            mask_tool_call_args(tool_calls)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        
        avg_ms = elapsed / iterations
        print(f"\nTool call args masking: {avg_ms:.3f}ms per call")
        assert avg_ms < 2, f"Masking took {avg_ms:.3f}ms, expected <2ms"
    
    def test_chat_history_masking_simulation(self):
        """Simulated chat history masking should be <10ms for 10 messages."""
        # Simulate a chat history with various PII
        messages = [
            "My email is user@example.com",
            "Got it! I've noted your email [EMAIL_1].",
            "Also my phone is 555-123-4567",
            "Thanks, phone [PHONE_1] recorded.",
            "My SSN is 123-45-6789 for the form",
            "I've securely stored your SSN [SSN_1].",
            "Can you look up john@work.com?",
            "Found: John Smith at [EMAIL_2]",
            "Send him a message at 800-555-1234",
            "Message sent to [PHONE_2].",
        ]
        
        start = time.perf_counter()
        iterations = 50
        for _ in range(iterations):
            clear_pii_context()
            set_pii_context(PIIContext())
            for msg in messages:
                mask_message_for_llm(msg, role="user")
        elapsed = (time.perf_counter() - start) * 1000  # ms
        
        avg_ms = elapsed / iterations
        print(f"\n10-message history masking: {avg_ms:.3f}ms per history")
        assert avg_ms < 10, f"History masking took {avg_ms:.3f}ms, expected <10ms"
    
    def test_end_to_end_latency_estimate(self):
        """
        Estimate total PII latency for a typical chat request.
        
        Simulates:
        1. Mask user input
        2. Mask 5 history messages
        3. Unmask response
        
        Target: <20ms total (negligible vs LLM latency)
        """
        user_input = "My card is 4111-1111-1111-1111 and email is test@example.com"
        history = [
            "Hello, I'm your assistant",
            "My SSN is 123-45-6789",
            "I've saved your SSN [SSN_1]",
            "Can you read my emails?",
            "Found 5 emails from john@work.com",
        ]
        response = "Card [CARD_1] saved. Your email [EMAIL_1] is on file."
        
        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            clear_pii_context()
            set_pii_context(PIIContext())
            
            # 1. Mask user input
            mask_message_for_llm(user_input, role="user")
            
            # 2. Mask history
            for msg in history:
                mask_message_for_llm(msg, role="user")
            
            # 3. Unmask response
            unmask_pii(response)
        
        elapsed = (time.perf_counter() - start) * 1000  # ms
        avg_ms = elapsed / iterations
        
        print(f"\n=== End-to-End Latency Estimate ===")
        print(f"Total PII processing: {avg_ms:.3f}ms per request")
        print(f"(Target: <20ms, typical LLM call: 1000-3000ms)")
        
        assert avg_ms < 20, f"E2E took {avg_ms:.3f}ms, expected <20ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

