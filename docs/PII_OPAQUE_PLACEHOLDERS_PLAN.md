# PII Opaque Placeholders Implementation Plan

## ✅ STATUS: IMPLEMENTED AND DEPLOYED

**Deployment Date:** January 2, 2026

## Problem Statement

Current PII masking uses **semantic placeholders** like `[SSN_1]`, `[CARD_1]`, `[EMAIL_1]`.  
While these mask the actual data, OpenAI's safety filters still trigger because:

1. The placeholder name reveals the data type (SSN, CARD)
2. Combined with user context ("remember my SIN"), the LLM refuses

**Evidence from production testing:**
- User: "Please note down this number for my records: 111-222-333"
- Masked: "Please note down this number for my records: [SSN_1]"
- LLM Response: "I'm sorry, but I can't store sensitive information like Social Security Numbers (SSNs)"

The LLM recognized `[SSN_1]` as an SSN placeholder and refused.

---

## Solution: Opaque Placeholders

Replace semantic placeholders with **opaque, type-agnostic placeholders**:

| Current (Semantic) | New (Opaque) |
|--------------------|--------------|
| `[SSN_1]` | `[MASKED_1]` |
| `[CARD_1]` | `[MASKED_2]` |
| `[EMAIL_1]` | `[MASKED_3]` |
| `[PHONE_1]` | `[MASKED_4]` |

The internal `PIIContext` still tracks the original type for:
- Audit logging
- Statistics
- Compliance reporting

But the LLM only sees `[MASKED_N]` placeholders.

---

## Architecture

### Current Flow (Semantic)
```
User Input: "My SSN is 123-45-6789"
     ↓
Masked:     "My SSN is [SSN_1]"  ← Type revealed!
     ↓
LLM sees:   "[SSN_1]" → Recognizes as SSN → REFUSES
```

### New Flow (Two-Stage Masking)
```
User Input: "My SIN is 123-45-6789"
     ↓
Stage 1 - Data Masking:   "My SIN is [MASKED_1]"
     ↓
Stage 2 - Keyword Masking: "My reference number is [MASKED_1]"  ← Type AND keyword hidden!
     ↓
LLM sees:   "My reference number is [MASKED_1]" → Generic everything → PROCESSES
     ↓
Response:   "I've noted your reference number [MASKED_1]"
     ↓
Unmasked:   "I've noted your reference number 123-45-6789"  ← User sees original
```

### Keyword Masking (Stage 2)

In addition to masking PII data, we also mask **sensitive keywords** that trigger LLM safety filters:

| Keyword | Replacement |
|---------|-------------|
| SIN | reference number |
| SSN | reference number |
| Social Insurance Number | reference number |
| Social Security Number | reference number |
| credit card number | payment reference |
| card number | payment reference |
| bank account number | account reference |
| account number | account reference |

---

## Implementation Plan

### Phase 1: Update PII Module (`pii.py`)

#### 1.1 Add Global Counter for Opaque IDs

```python
# Global counter for opaque placeholder IDs (per-request)
# Reset at the start of each request via PIIContext

class PIIContext:
    def __init__(self):
        self._masked_items: Dict[str, str] = {}  # placeholder → original
        self._placeholder_types: Dict[str, str] = {}  # placeholder → type (for audit)
        self._next_id: int = 1  # Global counter for MASKED_N
        
    def add_masked_item(self, original: str, pii_type: str) -> str:
        """
        Add a masked item and return its opaque placeholder.
        
        Args:
            original: The original PII value
            pii_type: The type of PII (ssn, email, card, etc.) - for audit only
            
        Returns:
            Opaque placeholder like [MASKED_1]
        """
        # Check if already masked
        for placeholder, value in self._masked_items.items():
            if value == original:
                return placeholder
        
        # Create new opaque placeholder
        placeholder = f"[MASKED_{self._next_id}]"
        self._next_id += 1
        
        self._masked_items[placeholder] = original
        self._placeholder_types[placeholder] = pii_type
        
        return placeholder
```

#### 1.2 Update `mask_pii()` Function

```python
def mask_pii(text: str, mode: MaskingMode = MaskingMode.FULL) -> str:
    """
    Mask PII in text using opaque placeholders.
    
    All PII types now use [MASKED_N] format to avoid triggering
    LLM safety filters based on placeholder names.
    """
    if not text:
        return text
    
    ctx = get_pii_context()
    if not ctx:
        return text
    
    result = text
    rules = MASKING_RULES.get(mode, MASKING_RULES[MaskingMode.FULL])
    
    for pii_type in rules:
        if pii_type not in PII_PATTERNS:
            continue
            
        pattern = PII_PATTERNS[pii_type]
        
        def replace_with_opaque(match):
            original = match.group(0)
            # Returns [MASKED_N] instead of [TYPE_N]
            return ctx.add_masked_item(original, pii_type)
        
        result = pattern.sub(replace_with_opaque, result)
    
    return result
```

#### 1.3 Update `unmask_pii()` Function

```python
def unmask_pii(text: str) -> str:
    """
    Replace opaque placeholders with original values.
    
    Handles both old format [TYPE_N] and new format [MASKED_N].
    """
    ctx = get_pii_context()
    if not ctx:
        return text
    
    result = text
    
    # New opaque format: [MASKED_N]
    opaque_pattern = re.compile(r'\[MASKED_(\d+)\]')
    for match in opaque_pattern.finditer(text):
        placeholder = match.group(0)
        original = ctx._masked_items.get(placeholder)
        if original:
            result = result.replace(placeholder, original)
    
    # Legacy format: [TYPE_N] (for backwards compatibility)
    legacy_pattern = re.compile(r'\[([A-Z_]+)_(\d+)\]')
    for match in legacy_pattern.finditer(text):
        placeholder = match.group(0)
        original = ctx._masked_items.get(placeholder)
        if original:
            result = result.replace(placeholder, original)
    
    return result
```

#### 1.4 Update Statistics to Track Types

```python
class PIIContext:
    def get_stats(self) -> Dict[str, int]:
        """Get statistics by PII type (for audit/logging)."""
        stats = {"total": len(self._masked_items)}
        
        # Count by type using _placeholder_types
        for placeholder, pii_type in self._placeholder_types.items():
            stats[pii_type] = stats.get(pii_type, 0) + 1
        
        return stats
```

---

### Phase 2: Update Tests (`test_pii_masking.py`)

#### 2.1 Update Existing Tests for Opaque Format

```python
class TestOpaquePlaceholders:
    """Test opaque placeholder format [MASKED_N]."""
    
    def setup_method(self):
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_ssn_uses_opaque_placeholder(self):
        """SSN should be masked as [MASKED_N], not [SSN_N]."""
        result = mask_pii("My SSN is 123-45-6789")
        
        assert "123-45-6789" not in result
        assert "[MASKED_" in result
        assert "[SSN_" not in result  # Should NOT have type in placeholder
    
    def test_card_uses_opaque_placeholder(self):
        """Credit card should be masked as [MASKED_N]."""
        result = mask_pii("Card: 4111-1111-1111-1111")
        
        assert "4111-1111-1111-1111" not in result
        assert "[MASKED_" in result
        assert "[CARD_" not in result
    
    def test_multiple_types_sequential_ids(self):
        """Different PII types should have sequential MASKED IDs."""
        result = mask_pii("SSN: 123-45-6789, Card: 4111-1111-1111-1111, Email: test@example.com")
        
        assert "[MASKED_1]" in result
        assert "[MASKED_2]" in result
        assert "[MASKED_3]" in result
        # No type-specific placeholders
        assert "[SSN_" not in result
        assert "[CARD_" not in result
        assert "[EMAIL_" not in result
    
    def test_same_value_same_placeholder(self):
        """Same PII value should get same placeholder."""
        result = mask_pii("SSN 123-45-6789 appears twice: 123-45-6789")
        
        # Should only have one MASKED_1
        assert result.count("[MASKED_1]") == 2
        assert "[MASKED_2]" not in result
    
    def test_stats_still_track_types(self):
        """Statistics should still track PII types for audit."""
        mask_pii("SSN: 123-45-6789, Card: 4111-1111-1111-1111")
        
        ctx = get_pii_context()
        stats = ctx.get_stats()
        
        assert stats["total"] == 2
        assert stats.get("ssn", 0) == 1
        assert stats.get("card", 0) == 1
    
    def test_unmask_opaque_placeholder(self):
        """Unmasking should work with opaque placeholders."""
        original = "My SSN is 123-45-6789"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert unmasked == original
    
    def test_unmask_in_llm_response(self):
        """LLM response with opaque placeholder should unmask correctly."""
        # Mask user input
        mask_pii("My SSN is 123-45-6789")
        
        # Simulate LLM response using opaque placeholder
        llm_response = "I've saved your number [MASKED_1] securely."
        unmasked = unmask_pii(llm_response)
        
        assert "123-45-6789" in unmasked
        assert "[MASKED_1]" not in unmasked
```

#### 2.2 Add Integration Tests

```python
class TestOpaqueIntegration:
    """Integration tests for opaque placeholder flow."""
    
    def setup_method(self):
        clear_pii_context()
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_full_flow_ssn(self):
        """Complete flow: user input → masked → LLM → unmasked."""
        # 1. User sends SSN
        user_input = "Remember my SIN: 111-222-333"
        masked = mask_message_for_llm(user_input)
        
        # 2. Verify opaque masking
        assert "111-222-333" not in masked
        assert "[MASKED_1]" in masked
        assert "SIN" not in masked or "[SSN_" not in masked
        
        # 3. What LLM sees
        assert masked == "Remember my SIN: [MASKED_1]"
        
        # 4. Simulate LLM response
        llm_response = "I've noted [MASKED_1] for you."
        
        # 5. Unmask for user
        final = unmask_pii(llm_response)
        assert final == "I've noted 111-222-333 for you."
    
    def test_llm_cannot_infer_type(self):
        """Verify LLM sees only opaque placeholders, not types."""
        inputs = [
            ("SSN: 123-45-6789", "ssn"),
            ("Card: 4111-1111-1111-1111", "card"),
            ("Email: test@example.com", "email"),
            ("Phone: 555-123-4567", "phone"),
        ]
        
        for text, pii_type in inputs:
            clear_pii_context()
            set_pii_context(PIIContext())
            
            masked = mask_pii(text)
            
            # Verify no type information in placeholder
            assert f"[{pii_type.upper()}_" not in masked
            assert "[MASKED_" in masked
```

---

### Phase 3: Update Audit Logging

The audit log should continue to track PII types for compliance:

```python
# In pii_audit.py

def log_masking_event(user_id: UUID, request_id: str, stats: Dict[str, int]):
    """
    Log PII masking event with type breakdown.
    
    Even though placeholders are opaque, we track types internally.
    """
    entry = {
        "user_id": str(user_id),
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_masked": stats.get("total", 0),
        "breakdown": {
            "ssn": stats.get("ssn", 0),
            "card": stats.get("card", 0),
            "email": stats.get("email", 0),
            "phone": stats.get("phone", 0),
            "account": stats.get("account", 0),
            "address": stats.get("address", 0),
            "dob": stats.get("dob", 0),
        }
    }
    # ... write to audit log
```

---

### Phase 4: System Prompt Update (Optional)

Add context to help the LLM understand opaque placeholders:

```python
# In agent.py SYSTEM_PROMPT addition

PII_INSTRUCTION = """
## Handling User Information

When users share personal information like numbers, IDs, or codes, they may appear 
as [MASKED_N] placeholders (e.g., [MASKED_1], [MASKED_2]). These are the user's 
actual information that has been securely handled.

When referencing these in your responses:
- Use the same placeholder (e.g., "I've noted [MASKED_1]")
- The user will see their original information
- Do not ask for the information again if you already have a placeholder

Example:
- User: "My reference number is [MASKED_1]"
- You: "I've recorded your reference number [MASKED_1]."
"""
```

---

## Testing Plan

### Unit Tests

| Test ID | Description | Expected Result |
|---------|-------------|-----------------|
| OP-U01 | SSN masked as `[MASKED_N]` | No `[SSN_` in output |
| OP-U02 | Credit card masked as `[MASKED_N]` | No `[CARD_` in output |
| OP-U03 | Email masked as `[MASKED_N]` | No `[EMAIL_` in output |
| OP-U04 | Phone masked as `[MASKED_N]` | No `[PHONE_` in output |
| OP-U05 | Sequential IDs across types | `[MASKED_1]`, `[MASKED_2]`, etc. |
| OP-U06 | Same value = same placeholder | Deduplication works |
| OP-U07 | Stats still track types | `{ssn: 1, card: 1}` |
| OP-U08 | Unmask opaque placeholder | Original value restored |
| OP-U09 | Backwards compatibility | Old `[SSN_1]` still unmasks |

### Integration Tests

| Test ID | Description | Expected Result |
|---------|-------------|-----------------|
| OP-I01 | Full roundtrip (SSN) | User sees original SSN in response |
| OP-I02 | Full roundtrip (Card) | User sees original card in response |
| OP-I03 | Multiple PII items | All items correctly tracked |
| OP-I04 | Chat history masking | History uses opaque placeholders |
| OP-I05 | Tool call args masking | Args use opaque placeholders |

### Manual QA (Production)

| Test ID | Scenario | Steps | Expected |
|---------|----------|-------|----------|
| OP-QA01 | SIN storage | 1. Clear history<br>2. "Remember my SIN: 111-222-333"<br>3. Wait for response | LLM acknowledges (no refusal) |
| OP-QA02 | Credit card | 1. "My card is 4500 1111 1111 0911"<br>2. Wait for response | LLM acknowledges (no refusal) |
| OP-QA03 | Recall PII | 1. After OP-QA01<br>2. "What SIN did I tell you?" | LLM returns 111-222-333 |
| OP-QA04 | Email from tool | 1. "Read my latest email"<br>2. If email has SSN | SSN shown to user correctly |
| OP-QA05 | Server logs | After any test | `PII MASKING: N items masked` logged |

---

## Rollback Plan

If opaque placeholders cause issues:

1. **Feature flag**: Add `USE_OPAQUE_PLACEHOLDERS = True` in config
2. **Quick revert**: Set to `False` to use semantic placeholders
3. **Database**: No schema changes needed (audit log is append-only)

```python
# In pii.py
from .config import get_settings

def get_placeholder(original: str, pii_type: str, ctx: PIIContext) -> str:
    settings = get_settings()
    
    if settings.USE_OPAQUE_PLACEHOLDERS:
        return ctx.add_masked_item(original, pii_type)  # [MASKED_N]
    else:
        return ctx.add_typed_item(original, pii_type)   # [TYPE_N]
```

---

## Timeline

| Phase | Task | Duration |
|-------|------|----------|
| 1 | Update `pii.py` with opaque placeholders | 30 min |
| 2 | Update tests | 30 min |
| 3 | Run unit tests | 10 min |
| 4 | Deploy to production | 10 min |
| 5 | Manual QA | 20 min |
| **Total** | | **~1.5 hours** |

---

## Success Criteria

1. **No type leakage**: Placeholders are always `[MASKED_N]`, never `[SSN_N]`
2. **LLM accepts PII**: No more "I can't store sensitive information" refusals
3. **Unmasking works**: User sees original values in responses
4. **Audit intact**: Type statistics still tracked for compliance
5. **All tests pass**: Unit + integration tests green

---

## Files to Modify

| File | Changes |
|------|---------|
| `app/core/pii.py` | Opaque placeholder generation, updated unmask |
| `tests/test_pii_masking.py` | New opaque placeholder tests |
| `app/core/agent.py` | (Optional) System prompt update |
| `app/core/config.py` | (Optional) Feature flag |


