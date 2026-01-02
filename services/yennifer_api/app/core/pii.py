"""
PII (Personally Identifiable Information) Masking Module

Provides tool-level masking of sensitive data before it reaches the LLM.

Architecture:
- Masking happens at tool OUTPUT, not input
- Different masking modes for different tool purposes
- Per-request context tracks masked items for potential resolution
- Action tools resolve IDs internally, not masked placeholders

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
    """
    
    def __init__(self):
        self._mappings: Dict[str, MaskedItem] = {}
        self._counters: Dict[PIIType, int] = {}
        self._total_masked: int = 0
    
    def _next_placeholder(self, pii_type: PIIType) -> str:
        """Generate next placeholder for a PII type."""
        count = self._counters.get(pii_type, 0) + 1
        self._counters[pii_type] = count
        return f"[{pii_type.value}_{count}]"
    
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
                    
                    placeholder = self._next_placeholder(pii_type)
                    
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
                    
                    # Replace in text
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
    
    Args:
        text: Text with PII placeholders (e.g., "Your card is [CARD_1]")
        
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
    
    # Find all placeholders and replace with original values
    import re
    placeholder_pattern = re.compile(r'\[([A-Z_]+)_(\d+)\]')
    
    for match in placeholder_pattern.finditer(text):
        placeholder = match.group(0)  # e.g., "[CARD_1]"
        original = ctx.resolve(placeholder)
        if original:
            result = result.replace(placeholder, original)
            logger.debug(f"Unmasked {placeholder}")
    
    return result

