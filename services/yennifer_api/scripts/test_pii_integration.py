#!/usr/bin/env python3
"""
PII Masking Integration Test Script

This script tests PII masking with the real agent (without making actual LLM calls).
It verifies that the masking/unmasking flow works correctly.

Run with:
    cd services/yennifer_api
    ./venv/bin/python scripts/test_pii_integration.py

For manual QA with real LLM calls, start the server and use the webapp.
"""

import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.pii import (
    PIIContext,
    set_pii_context,
    clear_pii_context,
    mask_pii,
    mask_message_for_llm,
    unmask_pii,
    get_pii_context,
)


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name: str, passed: bool, details: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {name}")
    if details:
        print(f"         {details}")


def test_tc1_ssn_storage():
    """TC-1: User Provides SSN - Should Store Securely"""
    print_header("TC-1: User Provides SSN")
    
    clear_pii_context()
    set_pii_context(PIIContext())
    
    # User sends SIN
    user_input = "My SIN is 111-222-333"
    masked = mask_message_for_llm(user_input, role="user")
    
    # Verify masking
    ssn_masked = "111-222-333" not in masked
    placeholder_present = "[SSN_" in masked
    
    print(f"  User input: {user_input}")
    print(f"  Masked:     {masked}")
    
    print_result("SSN is masked before LLM", ssn_masked)
    print_result("Placeholder created", placeholder_present)
    
    # Simulate LLM response
    llm_response = "I've securely stored your SIN [SSN_1]."
    unmasked_response = unmask_pii(llm_response)
    
    sin_restored = "111-222-333" in unmasked_response
    print(f"  LLM Response: {llm_response}")
    print(f"  User sees:    {unmasked_response}")
    print_result("SIN restored for user", sin_restored)
    
    return ssn_masked and placeholder_present and sin_restored


def test_tc2_credit_card():
    """TC-2: User Provides Credit Card - Should Store Securely"""
    print_header("TC-2: User Provides Credit Card")
    
    clear_pii_context()
    set_pii_context(PIIContext())
    
    # User sends card
    user_input = "My card is 4500 1111 1111 0911"
    masked = mask_message_for_llm(user_input, role="user")
    
    # Verify masking
    card_masked = "4500 1111 1111 0911" not in masked
    placeholder_present = "[CARD_" in masked
    
    print(f"  User input: {user_input}")
    print(f"  Masked:     {masked}")
    
    print_result("Card is masked before LLM", card_masked)
    print_result("Placeholder created", placeholder_present)
    
    # Simulate LLM response
    llm_response = "Card [CARD_1] has been saved to your profile."
    unmasked_response = unmask_pii(llm_response)
    
    card_restored = "4500 1111 1111 0911" in unmasked_response
    print(f"  LLM Response: {llm_response}")
    print(f"  User sees:    {unmasked_response}")
    print_result("Card restored for user", card_restored)
    
    return card_masked and placeholder_present and card_restored


def test_tc3_cross_session_history():
    """TC-3: Cross-Session PII - Should Be Masked in History"""
    print_header("TC-3: Cross-Session PII (History Masking)")
    
    clear_pii_context()
    set_pii_context(PIIContext())
    
    # Session A: User sends email
    msg1 = "My email is test@secret.com"
    masked1 = mask_message_for_llm(msg1, role="user")
    
    print(f"  Session A message: {msg1}")
    print(f"  Masked for LLM:    {masked1}")
    
    email_masked = "test@secret.com" not in masked1
    print_result("Email masked in first message", email_masked)
    
    # Simulate history being restored (Session B)
    # History contains the original (unmasked) message
    history = [
        {"role": "user", "content": "My email is test@secret.com"},
        {"role": "assistant", "content": "Got it! I've saved test@secret.com."},
    ]
    
    print("\n  Simulating session restoration...")
    print("  History (from DB):")
    for h in history:
        print(f"    {h['role']}: {h['content']}")
    
    # Re-mask history for new LLM call
    clear_pii_context()
    set_pii_context(PIIContext())
    
    masked_history = []
    for h in history:
        masked_content = mask_message_for_llm(h["content"], role=h["role"])
        masked_history.append({"role": h["role"], "content": masked_content})
    
    print("\n  Masked history for LLM:")
    for h in masked_history:
        print(f"    {h['role']}: {h['content']}")
    
    history_masked = all("test@secret.com" not in h["content"] for h in masked_history)
    print_result("All history PII masked before LLM", history_masked)
    
    # User asks about their email
    user_query = "What's my email?"
    masked_query = mask_message_for_llm(user_query, role="user")
    
    # LLM uses the placeholder from context
    llm_response = "Your email is [EMAIL_1]."
    unmasked_response = unmask_pii(llm_response)
    
    email_restored = "test@secret.com" in unmasked_response
    print(f"\n  User query: {user_query}")
    print(f"  LLM response: {llm_response}")
    print(f"  User sees: {unmasked_response}")
    print_result("Email correctly restored", email_restored)
    
    return email_masked and history_masked and email_restored


def test_tc4_tool_results():
    """TC-4: Tool Results with PII - Should Be Masked"""
    print_header("TC-4: Tool Results with PII")
    
    clear_pii_context()
    set_pii_context(PIIContext())
    
    # Simulate tool result from read_email
    tool_result = """
    Email from: john.smith@company.com
    Subject: Meeting notes
    Body: Please call me at 555-123-4567. My SSN is 987-65-4321.
    """
    
    # Tool already masks output (existing implementation)
    masked_result = mask_pii(tool_result)
    
    print("  Raw tool result:")
    print(f"    {tool_result.strip()}")
    print("\n  Masked for LLM:")
    print(f"    {masked_result.strip()}")
    
    email_masked = "john.smith@company.com" not in masked_result
    phone_masked = "555-123-4567" not in masked_result
    ssn_masked = "987-65-4321" not in masked_result
    
    print_result("Email masked", email_masked)
    print_result("Phone masked", phone_masked)
    print_result("SSN masked", ssn_masked)
    
    # LLM summarizes using placeholders
    llm_response = "The email from [EMAIL_1] asks you to call [PHONE_1]. Contains SSN [SSN_1]."
    unmasked_response = unmask_pii(llm_response)
    
    print(f"\n  LLM Response: {llm_response}")
    print(f"  User sees:    {unmasked_response}")
    
    restored = all([
        "john.smith@company.com" in unmasked_response,
        "555-123-4567" in unmasked_response,
        "987-65-4321" in unmasked_response,
    ])
    print_result("All PII restored for user", restored)
    
    return email_masked and phone_masked and ssn_masked and restored


def test_tc5_followup_questions():
    """TC-5: PII in Follow-up Questions"""
    print_header("TC-5: PII in Follow-up Questions")
    
    clear_pii_context()
    set_pii_context(PIIContext())
    
    # First message with SSN
    msg1 = "My SSN is 123-45-6789"
    masked1 = mask_message_for_llm(msg1, role="user")
    
    print(f"  Message 1: {msg1}")
    print(f"  Masked:    {masked1}")
    
    # LLM response
    response1 = "Saved your SSN [SSN_1]."
    
    # Simulate history update (stored unmasked)
    history = [
        {"role": "user", "content": msg1},
        {"role": "assistant", "content": "Saved your SSN [SSN_1]."},
    ]
    
    # Second message - follow up
    msg2 = "What SSN did I tell you?"
    
    # Re-mask history for second LLM call
    print("\n  Simulating second request...")
    
    # Clear and create fresh context
    clear_pii_context()
    set_pii_context(PIIContext())
    
    # Mask history
    for h in history:
        mask_message_for_llm(h["content"], role=h["role"])
    
    # Mask new message
    masked2 = mask_message_for_llm(msg2, role="user")
    print(f"  Message 2: {msg2}")
    print(f"  Masked:    {masked2}")
    
    # Check that SSN in history is masked
    ctx = get_pii_context()
    stats = ctx.get_stats()
    print(f"  Context stats: {stats}")
    
    ssn_tracked = stats.get("ssn", 0) >= 1
    print_result("SSN tracked in context", ssn_tracked)
    
    # LLM response references the SSN
    llm_response2 = "You told me your SSN is [SSN_1]."
    unmasked2 = unmask_pii(llm_response2)
    
    print(f"\n  LLM Response: {llm_response2}")
    print(f"  User sees:    {unmasked2}")
    
    ssn_restored = "123-45-6789" in unmasked2
    print_result("SSN correctly restored", ssn_restored)
    
    return ssn_tracked and ssn_restored


def test_pii_stats():
    """Test PII context statistics"""
    print_header("PII Context Statistics")
    
    clear_pii_context()
    set_pii_context(PIIContext())
    
    text = """
    Contact: john@example.com, jane@test.org
    Phone: 555-123-4567
    SSN: 123-45-6789
    Card: 4111-1111-1111-1111
    """
    
    mask_pii(text)
    
    ctx = get_pii_context()
    stats = ctx.get_stats()
    
    print(f"  Stats: {stats}")
    
    expected = {
        "email": 2,
        "phone": 1,
        "ssn": 1,
        "card": 1,
    }
    
    all_correct = True
    for key, expected_count in expected.items():
        actual = stats.get(key, 0)
        correct = actual >= expected_count
        all_correct = all_correct and correct
        print_result(f"{key}: {actual} (expected >={expected_count})", correct)
    
    return all_correct


def main():
    print("\n" + "=" * 60)
    print("  PII MASKING INTEGRATION TESTS")
    print("=" * 60)
    
    results = []
    
    # Run all test cases
    results.append(("TC-1: SSN Storage", test_tc1_ssn_storage()))
    results.append(("TC-2: Credit Card", test_tc2_credit_card()))
    results.append(("TC-3: Cross-Session", test_tc3_cross_session_history()))
    results.append(("TC-4: Tool Results", test_tc4_tool_results()))
    results.append(("TC-5: Follow-up Questions", test_tc5_followup_questions()))
    results.append(("Statistics", test_pii_stats()))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} | {name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 All integration tests passed!")
        return 0
    else:
        print("\n  ⚠️  Some tests failed. Please review.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

