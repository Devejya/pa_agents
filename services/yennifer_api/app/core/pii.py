"""
PII (Personally Identifiable Information) Masking Module

Provides comprehensive PII masking at the LLM boundary.

Architecture:
- Masking happens at ALL LLM entry points:
  1. User input (HumanMessage)
  2. Chat history (from DB or in-memory)
  3. Tool outputs (already implemented)
- Per-request context tracks masked items for unmasking responses
- Unmasking happens before returning response to user

Masking Modes:
- FULL: Mask all PII (emails, phones, SSN, cards, accounts, addresses)
- FINANCIAL_ONLY: Only mask financial/medical PII, keep contact info visible
- NONE: No masking (for write/action tools that need raw data)
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextvars import ContextVar
from enum import Enum
from datetime import datetime


logger = logging.getLogger(__name__)


class PIIType(Enum):
    """Types of PII we detect and mask."""
    # Contact info - may be shown in FINANCIAL_ONLY mode
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    
    # Highly sensitive - always masked
    SSN = "SSN"
    CREDIT_CARD = "CARD"
    BANK_ACCOUNT = "ACCOUNT"
    
    # Contextual
    ADDRESS = "ADDRESS"
    DOB = "DOB"
    IP_ADDRESS = "IP"


class MaskingMode(Enum):
    """
    Different masking modes for different tool purposes.
    
    FULL: Mask everything - for reading emails, documents, etc.
    FINANCIAL_ONLY: Only mask SSN, cards, bank accounts - for contact lookup tools
    NONE: No masking - for action tools that need raw data internally
    """
    FULL = "full"
    FINANCIAL_ONLY = "financial_only"
    NONE = "none"


# PII patterns - ordered from most to least specific
PII_PATTERNS: Dict[PIIType, List[re.Pattern]] = {
    # SSN/SIN - US and Canadian formats
    PIIType.SSN: [
        re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),      # US SSN: XXX-XX-XXXX
        re.compile(r'\b\d{3}-\d{3}-\d{3}\b'),      # Canadian SIN: XXX-XXX-XXX
        re.compile(r'\b\d{3}\s\d{3}\s\d{3}\b'),    # Canadian SIN with spaces
    ],
    
    # Credit cards - 16 digits with separators
    PIIType.CREDIT_CARD: [
        re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
        re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b'),
    ],
    
    # Bank/Account numbers
    PIIType.BANK_ACCOUNT: [
        re.compile(r'(?:account|acct|routing)[#:\s]*\d{8,16}', re.IGNORECASE),
        re.compile(r'(?:bank\s*account)[#:\s]*\d{6,17}', re.IGNORECASE),
    ],
    
    # Emails
    PIIType.EMAIL: [
        re.compile(r'[\w\.\-\+]+@[\w\.-]+\.[a-zA-Z]{2,}'),
    ],
    
    # Phone numbers - various formats
    PIIType.PHONE: [
        re.compile(r'\+\d{1,3}[-.\s]?\(?\d{2,3}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b'),  # +1 (123) 456-7890
        re.compile(r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}'),   # (123) 456-7890
        re.compile(r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b'),      # 123-456-7890
    ],
    
    # Street addresses - specific patterns to avoid false positives like "Google Drive"
    # Pattern 1: Full street names (123 Main Street) - common suffixes except Drive
    PIIType.ADDRESS: [
        re.compile(
            r'\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+(?:Street|Avenue|Road|Boulevard|Lane|Way|Court|Circle|Place|Highway|Parkway)\b',
            re.IGNORECASE
        ),
        # Pattern 2: "Drive" only with trailing comma/city/state/zip (to avoid "Google Drive")
        re.compile(
            r'\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+Drive\s*,',
            re.IGNORECASE
        ),
        # Pattern 3: Abbreviated forms with period (123 Main St.)
        re.compile(
            r'\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+(?:St|Ave|Rd|Blvd|Dr|Ln|Ct|Pl)\.',
            re.IGNORECASE
        ),
        # Pattern 4: Full address with city, state, zip
        re.compile(
            r'\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Circle|Cir|Place|Pl)[.,]?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,?\s+[A-Z]{2}\s+\d{5}',
            re.IGNORECASE
        ),
    ],
    
    # Dates of birth - contextual
    PIIType.DOB: [
        re.compile(
            r'(?:born|birthday|dob|date\s+of\s+birth)[:\s]*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',
            re.IGNORECASE
        ),
    ],
    
    # IP addresses
    PIIType.IP_ADDRESS: [
        re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    ],
}

# Which PII types to mask in each mode
MASKING_RULES: Dict[MaskingMode, set] = {
    MaskingMode.FULL: {
        PIIType.EMAIL,
        PIIType.PHONE,
        PIIType.SSN,
        PIIType.CREDIT_CARD,
        PIIType.BANK_ACCOUNT,
        PIIType.ADDRESS,
        PIIType.DOB,
        PIIType.IP_ADDRESS,
    },
    MaskingMode.FINANCIAL_ONLY: {
        PIIType.SSN,
        PIIType.CREDIT_CARD,
        PIIType.BANK_ACCOUNT,
        # Email, Phone, Address visible in this mode
    },
    MaskingMode.NONE: set(),  # Nothing masked
}


@dataclass
class MaskedItem:
    """Record of a single masked PII item."""
    pii_type: PIIType
    placeholder: str
    original_value: str
    masked_at: datetime = field(default_factory=lambda: datetime.now(tz=None))


@dataclass
class PIIMaskingResult:
    """Result of a masking operation."""
    masked_text: str
    items_masked: List[MaskedItem]
    
    @property
    def mask_count(self) -> int:
        return len(self.items_masked)
    
    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get audit log entries (without original values)."""
        return [
            {
                "type": item.pii_type.value,
                "placeholder": item.placeholder,
                "masked_at": item.masked_at.isoformat(),
            }
            for item in self.items_masked
        ]


class PIIContext:
    """
    Per-request context for PII masking.
    
    Tracks all masked items within a single request lifecycle.
    Allows resolution of tracked items for action tools.
    
    Uses OPAQUE placeholders ([MASKED_N]) to avoid triggering LLM safety filters.
    The PII type is tracked internally for audit/statistics but NOT exposed in placeholders.
    """
    
    def __init__(self):
        self._mappings: Dict[str, MaskedItem] = {}
        self._counters: Dict[PIIType, int] = {}  # Type counts for statistics
        self._total_masked: int = 0
        self._opaque_counter: int = 0  # Global counter for [MASKED_N]
        self._value_to_placeholder: Dict[str, str] = {}  # Dedup: same value = same placeholder
    
    def _next_placeholder(self, pii_type: PIIType, original_value: str) -> str:
        """
        Generate next OPAQUE placeholder.
        
        Uses [MASKED_N] format to avoid revealing PII type to LLM.
        Same original value always gets the same placeholder (deduplication).
        
        Args:
            pii_type: The type of PII (for internal tracking only)
            original_value: The original PII value
            
        Returns:
            Opaque placeholder like [MASKED_1], [MASKED_2], etc.
        """
        # Check if this value was already masked (deduplication)
        if original_value in self._value_to_placeholder:
            return self._value_to_placeholder[original_value]
        
        # Generate new opaque placeholder
        self._opaque_counter += 1
        placeholder = f"[MASKED_{self._opaque_counter}]"
        
        # Track for deduplication
        self._value_to_placeholder[original_value] = placeholder
        
        # Update type counter for statistics
        count = self._counters.get(pii_type, 0) + 1
        self._counters[pii_type] = count
        
        return placeholder
    
    def mask_and_track(
        self,
        text: str,
        mode: MaskingMode = MaskingMode.FULL,
    ) -> PIIMaskingResult:
        """
        Mask PII in text and track masked items.
        
        Args:
            text: Text to mask
            mode: Masking mode determining which PII types to mask
            
        Returns:
            PIIMaskingResult with masked text and list of masked items
        """
        if not text or mode == MaskingMode.NONE:
            return PIIMaskingResult(masked_text=text, items_masked=[])
        
        items_masked: List[MaskedItem] = []
        result_text = text
        
        # Get which types to mask in this mode
        types_to_mask = MASKING_RULES.get(mode, set())
        
        # Apply patterns in order (most specific first)
        for pii_type in [
            PIIType.SSN,
            PIIType.CREDIT_CARD,
            PIIType.BANK_ACCOUNT,
            PIIType.EMAIL,
            PIIType.PHONE,
            PIIType.ADDRESS,
            PIIType.DOB,
            PIIType.IP_ADDRESS,
        ]:
            if pii_type not in types_to_mask:
                continue
                
            patterns = PII_PATTERNS.get(pii_type, [])
            for pattern in patterns:
                # Find all matches
                for match in pattern.finditer(result_text):
                    original = match.group()
                    
                    # Skip if already masked (contains brackets)
                    if original.startswith('[') and original.endswith(']'):
                        continue
                    
                    # Get opaque placeholder (handles deduplication)
                    placeholder = self._next_placeholder(pii_type, original)
                    
                    # Only create new record if this is a new placeholder
                    if placeholder not in self._mappings:
                        # Create masked item record
                        item = MaskedItem(
                            pii_type=pii_type,
                            placeholder=placeholder,
                            original_value=original,
                        )
                        items_masked.append(item)
                        
                        # Store mapping for potential resolution
                        self._mappings[placeholder] = item
                        self._total_masked += 1
                    
                    # Replace in text (always replace, even for deduped values)
                    result_text = result_text.replace(original, placeholder, 1)
        
        return PIIMaskingResult(masked_text=result_text, items_masked=items_masked)
    
    def resolve(self, placeholder: str) -> Optional[str]:
        """
        Resolve a placeholder back to original value.
        
        Use sparingly - only for action tools that need the real value.
        
        Args:
            placeholder: The placeholder to resolve (e.g., "[EMAIL_1]")
            
        Returns:
            Original value if found, None otherwise
        """
        item = self._mappings.get(placeholder)
        if item:
            logger.debug(f"Resolved {placeholder} to {item.pii_type.value}")
            return item.original_value
        return None
    
    def get_stats(self) -> Dict[str, int]:
        """Get masking statistics for this context."""
        stats = {"total": self._total_masked}
        for pii_type, count in self._counters.items():
            stats[pii_type.value.lower()] = count
        return stats
    
    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get full audit log for this context (no original values)."""
        return [
            {
                "type": item.pii_type.value,
                "placeholder": item.placeholder,
                "masked_at": item.masked_at.isoformat(),
            }
            for item in self._mappings.values()
        ]


# Context variable for per-request PII context
_pii_context: ContextVar[Optional[PIIContext]] = ContextVar('pii_context', default=None)


def get_pii_context() -> PIIContext:
    """
    Get the current PII context.
    
    Creates a new context if none exists (for non-HTTP contexts like testing).
    """
    ctx = _pii_context.get()
    if ctx is None:
        ctx = PIIContext()
        _pii_context.set(ctx)
    return ctx


def set_pii_context(ctx: PIIContext) -> None:
    """Set the PII context (called by middleware)."""
    _pii_context.set(ctx)


def clear_pii_context() -> None:
    """Clear the PII context (called by middleware on request end)."""
    _pii_context.set(None)


# =============================================================================
# Convenience functions for tool authors
# =============================================================================

def mask_pii(
    text: str,
    mode: MaskingMode = MaskingMode.FULL,
) -> str:
    """
    Mask PII in text using current context.
    
    This is the main function tools should use.
    
    Args:
        text: Text to mask
        mode: Masking mode (default: FULL)
        
    Returns:
        Text with PII masked
        
    Example:
        @tool
        def read_email(email_id: str) -> str:
            email = fetch_email(email_id)
            return mask_pii(format_email(email))
    """
    if not text:
        return text
    
    ctx = get_pii_context()
    result = ctx.mask_and_track(text, mode)
    
    # Log when masking actually happens (use WARNING for visibility in prod logs)
    if result.mask_count > 0:
        logger.warning(
            f"PII MASKING: {result.mask_count} items masked "
            f"(mode={mode.value}, total_in_context={ctx.get_stats()['total']})"
        )
    
    return result.masked_text


def mask_pii_financial_only(text: str) -> str:
    """
    Mask only financial PII (SSN, cards, bank accounts).
    
    Use for tools that answer contact queries where user expects
    to see email addresses and phone numbers.
    
    Args:
        text: Text to mask
        
    Returns:
        Text with financial PII masked, contact info visible
    """
    return mask_pii(text, mode=MaskingMode.FINANCIAL_ONLY)


def mask_pii_in_dict(
    data: Dict[str, Any],
    keys_to_mask: Optional[List[str]] = None,
    mode: MaskingMode = MaskingMode.FULL,
) -> Dict[str, Any]:
    """
    Mask PII in dictionary values.
    
    Args:
        data: Dictionary with potential PII
        keys_to_mask: Specific keys to mask (None = all string values)
        mode: Masking mode
        
    Returns:
        Dictionary with PII masked in values
    """
    result = {}
    
    for key, value in data.items():
        if isinstance(value, str):
            if keys_to_mask is None or key in keys_to_mask:
                result[key] = mask_pii(value, mode)
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = mask_pii_in_dict(value, keys_to_mask, mode)
        elif isinstance(value, list):
            result[key] = [
                mask_pii(v, mode) if isinstance(v, str) else v
                for v in value
            ]
        else:
            result[key] = value
    
    return result


def resolve_pii_reference(placeholder: str) -> Optional[str]:
    """
    Resolve a PII placeholder back to its original value.
    
    USE WITH CAUTION: Only for action tools that absolutely need
    the real value (e.g., send_email needs actual email address).
    
    Args:
        placeholder: The placeholder (e.g., "[EMAIL_1]")
        
    Returns:
        Original value or None if not found
    """
    ctx = get_pii_context()
    return ctx.resolve(placeholder)


def unmask_pii(text: str) -> str:
    """
    Unmask all PII placeholders in text back to original values.
    
    Call this on the final response before returning to user.
    The user should see the real PII - only the LLM should be masked.
    
    Handles both:
    - New opaque format: [MASKED_1], [MASKED_2], etc.
    - Legacy typed format: [SSN_1], [CARD_1], etc. (for backwards compatibility)
    
    Args:
        text: Text with PII placeholders (e.g., "Your info is [MASKED_1]")
        
    Returns:
        Text with original PII values restored
        
    Example:
        response = agent.chat(message)
        return unmask_pii(response)  # User sees real values
    """
    if not text:
        return text
    
    ctx = get_pii_context()
    result = text
    
    # Pattern 1: New opaque format [MASKED_N]
    opaque_pattern = re.compile(r'\[MASKED_(\d+)\]')
    for match in opaque_pattern.finditer(text):
        placeholder = match.group(0)  # e.g., "[MASKED_1]"
        original = ctx.resolve(placeholder)
        if original:
            result = result.replace(placeholder, original)
            logger.debug(f"Unmasked opaque {placeholder}")
    
    # Pattern 2: Legacy typed format [TYPE_N] (backwards compatibility)
    legacy_pattern = re.compile(r'\[([A-Z_]+)_(\d+)\]')
    for match in legacy_pattern.finditer(result):  # Note: use 'result' to avoid re-matching opaque
        placeholder = match.group(0)
        # Skip if it's an opaque placeholder (already handled)
        if placeholder.startswith("[MASKED_"):
            continue
        original = ctx.resolve(placeholder)
        if original:
            result = result.replace(placeholder, original)
            logger.debug(f"Unmasked legacy {placeholder}")
    
    return result


# =============================================================================
# LLM Boundary Functions - Mask all content before it reaches the LLM
# =============================================================================

# Sensitive keywords that trigger LLM safety filters
# These are replaced with neutral terms to avoid refusals
# Format: (pattern, replacement, restore_term)
SENSITIVE_KEYWORDS = [
    # Social Insurance Number (Canadian)
    (re.compile(r'\bSIN\b', re.IGNORECASE), 'reference number', 'SIN'),
    (re.compile(r'\bSocial Insurance Number\b', re.IGNORECASE), 'reference number', 'Social Insurance Number'),
    (re.compile(r'\bSocial Insurance\b', re.IGNORECASE), 'reference', 'Social Insurance'),
    
    # Social Security Number (US)
    (re.compile(r'\bSSN\b', re.IGNORECASE), 'reference number', 'SSN'),
    (re.compile(r'\bSocial Security Number\b', re.IGNORECASE), 'reference number', 'Social Security Number'),
    (re.compile(r'\bSocial Security\b', re.IGNORECASE), 'reference', 'Social Security'),
    
    # Credit card terminology
    (re.compile(r'\bcredit card number\b', re.IGNORECASE), 'payment reference', 'credit card number'),
    (re.compile(r'\bcard number\b', re.IGNORECASE), 'payment reference', 'card number'),
    (re.compile(r'\bdebit card number\b', re.IGNORECASE), 'payment reference', 'debit card number'),
    
    # Bank account
    (re.compile(r'\bbank account number\b', re.IGNORECASE), 'account reference', 'bank account number'),
    (re.compile(r'\baccount number\b', re.IGNORECASE), 'account reference', 'account number'),
    (re.compile(r'\brouting number\b', re.IGNORECASE), 'routing reference', 'routing number'),
]


def _mask_sensitive_keywords(text: str) -> tuple[str, Dict[str, str]]:
    """
    Replace sensitive keywords with neutral terms.
    
    This prevents LLM safety filters from triggering on semantic context
    even when the actual PII data is already masked.
    
    Returns:
        Tuple of (masked_text, keyword_mappings) where keyword_mappings
        tracks what was replaced for potential restoration.
    """
    result = text
    keyword_mappings = {}
    
    for pattern, replacement, original_term in SENSITIVE_KEYWORDS:
        matches = list(pattern.finditer(result))
        for match in matches:
            matched_text = match.group(0)
            # Track for potential restoration (case-preserved)
            keyword_mappings[replacement] = matched_text
            result = result[:match.start()] + replacement + result[match.end():]
            # Re-find matches since positions changed
            break  # Process one at a time to handle position shifts
    
    # Multiple passes to catch all instances
    changed = True
    while changed:
        changed = False
        for pattern, replacement, original_term in SENSITIVE_KEYWORDS:
            if pattern.search(result):
                result = pattern.sub(replacement, result, count=1)
                changed = True
                break
    
    return result, keyword_mappings


def mask_message_for_llm(content: str, role: str = "user") -> str:
    """
    Mask PII in a message before sending to LLM.
    
    This is the primary entry point for LLM-bound content.
    Use this to mask user input, chat history messages, etc.
    
    Two-stage masking:
    1. Mask PII data (SSN, cards, etc.) → [MASKED_N] placeholders
    2. Mask sensitive keywords (SIN, SSN, etc.) → neutral terms
    
    This prevents LLM safety filters from triggering on BOTH:
    - The actual sensitive data
    - The semantic context/terminology
    
    Args:
        content: Message content to mask
        role: Message role ('user', 'assistant', 'tool') - currently all use FULL mode
              but role is preserved for potential future mode differentiation
        
    Returns:
        Masked content safe for LLM (uses opaque [MASKED_N] placeholders
        and neutral terminology)
        
    Example:
        >>> mask_message_for_llm("My SIN is 123-45-6789")
        "My reference number is [MASKED_1]"
    """
    if not content:
        return content
    
    # Stage 1: Mask PII data with opaque placeholders
    result = mask_pii(content, mode=MaskingMode.FULL)
    
    # Stage 2: Mask sensitive keywords to avoid semantic triggers
    result, _ = _mask_sensitive_keywords(result)
    
    return result


def mask_tool_call_args(tool_calls: Optional[List[Dict]]) -> Optional[List[Dict]]:
    """
    Mask PII in tool call arguments.
    
    Tool calls from chat history may contain PII that the LLM decided to use
    (e.g., "send_email(to='user@example.com')").
    
    We mask these so that:
    1. The LLM sees consistent masked values across the conversation
    2. Tool implementations can resolve placeholders if needed
    
    Args:
        tool_calls: List of tool call dicts with 'name', 'args', 'id'
        
    Returns:
        Tool calls with masked arguments, or None if input was None
    """
    if not tool_calls:
        return tool_calls
    
    masked_calls = []
    for tc in tool_calls:
        masked_tc = {
            "name": tc.get("name"),
            "id": tc.get("id"),
            "args": {},
        }
        
        # Mask string arguments
        args = tc.get("args", {})
        if args:
            for key, value in args.items():
                if isinstance(value, str):
                    masked_tc["args"][key] = mask_pii(value, mode=MaskingMode.FULL)
                else:
                    masked_tc["args"][key] = value
        
        masked_calls.append(masked_tc)
    
    return masked_calls

