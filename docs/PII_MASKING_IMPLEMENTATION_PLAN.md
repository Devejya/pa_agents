# PII Masking Implementation Plan

## Executive Summary

Add a privacy-preserving layer that masks PII in tool outputs before they reach the LLM, while maintaining full functionality through ID-based references for action tools.

**Key Design Decision**: Use **two masking modes** to balance privacy with usability:
- **FULL mode**: Mask all PII (for reasoning about email/document content)
- **FINANCIAL_ONLY mode**: Only mask SSN/cards (for contact lookups where user expects to see emails/phones)

**Estimated Effort**: 3-4 days  
**Risk Level**: Low (additive changes, no breaking modifications)  
**Priority**: Critical

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         LLM (OpenAI)                            │
│                                                                 │
│  FULL mode:          "[EMAIL_1] sent message about [SSN]..."    │
│  FINANCIAL_ONLY:     "john@work.com mentioned [SSN]..."         │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Masked Output (mode-dependent)
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      PII Masking Layer                          │
│                                                                 │
│  FULL mode (for reasoning):                                     │
│    - Masks: emails, phones, SSN, cards, addresses, DOB          │
│    - Use for: email bodies, documents, spreadsheets             │
│                                                                 │
│  FINANCIAL_ONLY mode (for explicit queries):                    │
│    - Masks: SSN, credit cards, bank accounts                    │
│    - Preserves: emails, phones (user asked for contact info)    │
│    - Use for: contact lookups, notes, memories, relationships   │
│                                                                 │
│  Also: Tracks mappings for action tool resolution               │
│        Provides audit logging                                   │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Raw Data
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    Google Workspace APIs                        │
│  Gmail, Docs, Drive, Sheets, Calendar, Contacts                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why Two Modes?

| Scenario | User Expectation | Mode | Example |
|----------|------------------|------|---------|
| "Summarize my emails" | Privacy of email content | FULL | "Email from [EMAIL_1] mentions [SSN]" |
| "What's John's phone?" | See the contact info | FINANCIAL_ONLY | "John's phone is 555-123-4567" |
| "What notes do I have about Sarah?" | See context including contact | FINANCIAL_ONLY | "Sarah's email is sarah@work.com" |
| "Read my bank statement doc" | Privacy of financial data | FULL | "Balance: $[AMOUNT], Account: [ACCOUNT]" |

---

## Phase 1: Core PII Masking Module (Day 1)

### 1.1 Create the PII masking module

**File**: `services/yennifer_api/app/core/pii.py`

```python
"""
PII (Personally Identifiable Information) Masking Module

Masks sensitive data before sending to LLM APIs while tracking
references for action tools that need to resolve real values.

Categories of PII:
- TRACKABLE: Needs resolution for actions (emails, phones) → [EMAIL_1], [PHONE_2]
- REDACTED: Never needed, fully mask (SSN, credit cards) → [SSN], [CARD]
- CONTEXTUAL: Mask but keep format hint (addresses, DOB) → [ADDRESS], [DOB]

Masking Modes:
- FULL: Mask all PII (for content the LLM is reasoning about)
- FINANCIAL_ONLY: Only mask SSN, credit cards, bank accounts (for contact lookups, notes)
- NONE: No masking (internal use only)
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from contextvars import ContextVar
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class MaskingMode(Enum):
    """
    Masking modes for different tool purposes.
    
    FULL: Mask all PII - use for content the LLM is reasoning about
          (email bodies, documents, spreadsheets)
    
    FINANCIAL_ONLY: Only mask sensitive financial/medical data (SSN, cards, accounts)
                    Keep emails, phones visible - use for contact lookups, notes, memories
                    where the user expects to see contact info
    
    NONE: No masking - internal use only, never for LLM-facing tools
    """
    FULL = "full"
    FINANCIAL_ONLY = "financial_only"
    NONE = "none"


class PIIType(Enum):
    """Categories of PII with their handling strategy."""
    # Trackable - may need resolution for actions
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    
    # Redacted - never needed, fully mask (ALWAYS masked in all modes except NONE)
    SSN = "SSN"
    CREDIT_CARD = "CARD"
    BANK_ACCOUNT = "ACCOUNT"
    
    # Contextual - mask but might need for context
    ADDRESS = "ADDRESS"
    DOB = "DOB"
    IP_ADDRESS = "IP"


# Define which PII types are masked in each mode
ALWAYS_MASK = {PIIType.SSN, PIIType.CREDIT_CARD, PIIType.BANK_ACCOUNT}  # Financial/sensitive
FULL_MODE_ONLY = {PIIType.EMAIL, PIIType.PHONE, PIIType.ADDRESS, PIIType.DOB}  # Contact info


@dataclass
class MaskedItem:
    """Record of a masked PII item."""
    pii_type: PIIType
    placeholder: str
    original_value: str
    masked_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PIIMaskingResult:
    """Result of masking operation with audit info."""
    masked_text: str
    items_masked: List[MaskedItem]
    
    @property
    def mask_count(self) -> int:
        return len(self.items_masked)
    
    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return audit-safe log (no original values)."""
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
    Per-request context for PII masking operations.
    
    Tracks masked values so action tools can resolve references
    back to real values when needed (e.g., sending email).
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
        mode: MaskingMode = MaskingMode.FULL
    ) -> PIIMaskingResult:
        """
        Mask PII in text based on the specified mode.
        
        Args:
            text: Raw text potentially containing PII
            mode: Masking mode - FULL, FINANCIAL_ONLY, or NONE
            
        Returns:
            PIIMaskingResult with masked text and audit info
            
        Modes:
            FULL: Mask all PII (emails, phones, SSN, cards, addresses, DOB)
                  Use for: email bodies, documents, spreadsheets
                  
            FINANCIAL_ONLY: Only mask sensitive financial/medical (SSN, cards, accounts)
                           Keep emails and phones visible
                           Use for: contact lookups, notes, memories, relationships
                           
            NONE: No masking (internal use only)
        """
        if not text:
            return PIIMaskingResult(masked_text="", items_masked=[])
        
        if mode == MaskingMode.NONE:
            return PIIMaskingResult(masked_text=text, items_masked=[])
        
        items_masked = []
        
        # =========================================================
        # ALWAYS MASKED (both FULL and FINANCIAL_ONLY modes)
        # These are sensitive financial/medical data - never show to LLM
        # =========================================================
        
        # SSN
        def replace_ssn(match):
            item = MaskedItem(PIIType.SSN, "[SSN]", match.group(0))
            items_masked.append(item)
            return "[SSN]"
        
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', replace_ssn, text)
        
        # Credit card numbers
        def replace_card(match):
            item = MaskedItem(PIIType.CREDIT_CARD, "[CARD]", match.group(0))
            items_masked.append(item)
            return "[CARD]"
        
        text = re.sub(
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            replace_card,
            text
        )
        
        # Bank account numbers
        def replace_account(match):
            item = MaskedItem(PIIType.BANK_ACCOUNT, "[ACCOUNT]", match.group(0))
            items_masked.append(item)
            return "[ACCOUNT]"
        
        text = re.sub(
            r'(?:account|acct|routing)[#:\s]*\d{8,17}',
            replace_account,
            text,
            flags=re.IGNORECASE
        )
        
        # =========================================================
        # FULL MODE ONLY - Contact info (masked for reasoning, not lookups)
        # These are needed when user explicitly asks for contact info
        # =========================================================
        
        if mode == MaskingMode.FULL:
            # Email addresses
            def replace_email(match):
                email = match.group(0)
                placeholder = self._next_placeholder(PIIType.EMAIL)
                item = MaskedItem(PIIType.EMAIL, placeholder, email)
                self._mappings[placeholder] = item
                items_masked.append(item)
                return placeholder
            
            text = re.sub(
                r'[\w\.\-\+]+@[\w\.\-]+\.\w{2,}',
                replace_email,
                text
            )
            
            # Phone numbers (various formats)
            def replace_phone(match):
                phone = match.group(0)
                placeholder = self._next_placeholder(PIIType.PHONE)
                item = MaskedItem(PIIType.PHONE, placeholder, phone)
                self._mappings[placeholder] = item
                items_masked.append(item)
                return placeholder
            
            phone_patterns = [
                r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # 123-456-7890
                r'\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b',   # (123) 456-7890
                r'\b\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # +1-123-456-7890
                r'\b\+\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b',  # International
            ]
            for pattern in phone_patterns:
                text = re.sub(pattern, replace_phone, text)
            
            # Street addresses
            def replace_address(match):
                item = MaskedItem(PIIType.ADDRESS, "[ADDRESS]", match.group(0))
                items_masked.append(item)
                return "[ADDRESS]"
            
            text = re.sub(
                r'\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct)\.?(?:[\w\s,]*\d{5}(?:-\d{4})?)?',
                replace_address,
                text,
                flags=re.IGNORECASE
            )
            
            # Date of Birth (contextual)
            def replace_dob(match):
                item = MaskedItem(PIIType.DOB, "[DOB]", match.group(0))
                items_masked.append(item)
                return "[DOB]"
            
            text = re.sub(
                r'(?:born|birthday|dob|date of birth)[:\s]*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',
                replace_dob,
                text,
                flags=re.IGNORECASE
            )
        
        self._total_masked += len(items_masked)
        
        return PIIMaskingResult(
            masked_text=text,
            items_masked=items_masked
        )
    
    def resolve(self, placeholder: str) -> Optional[str]:
        """
        Resolve a placeholder back to its original value.
        
        Only works for TRACKABLE PII types (EMAIL, PHONE).
        Returns None for REDACTED types or unknown placeholders.
        
        Args:
            placeholder: The placeholder string (e.g., "[EMAIL_1]")
            
        Returns:
            Original value or None
        """
        item = self._mappings.get(placeholder)
        if item and item.pii_type in (PIIType.EMAIL, PIIType.PHONE):
            return item.original_value
        return None
    
    def resolve_all_trackable(self) -> Dict[str, str]:
        """Get all trackable PII mappings (for action tools)."""
        return {
            placeholder: item.original_value
            for placeholder, item in self._mappings.items()
            if item.pii_type in (PIIType.EMAIL, PIIType.PHONE)
        }
    
    def get_stats(self) -> Dict[str, int]:
        """Get masking statistics for this context."""
        stats = {"total": self._total_masked}
        for pii_type in PIIType:
            stats[pii_type.value.lower()] = self._counters.get(pii_type, 0)
        return stats
    
    def get_full_audit_log(self) -> List[Dict[str, Any]]:
        """Get full audit log of all masked items (no original values)."""
        return [
            {
                "type": item.pii_type.value,
                "placeholder": item.placeholder,
                "masked_at": item.masked_at.isoformat(),
            }
            for item in self._mappings.values()
        ]


# --- Context Variable for Per-Request State ---

_pii_context: ContextVar[Optional[PIIContext]] = ContextVar('pii_context', default=None)


def get_pii_context() -> PIIContext:
    """
    Get or create PII context for current request.
    
    Should be called within a request context. Creates a new context
    if one doesn't exist (useful for testing).
    """
    ctx = _pii_context.get()
    if ctx is None:
        ctx = PIIContext()
        _pii_context.set(ctx)
    return ctx


def set_pii_context(ctx: PIIContext) -> None:
    """Set the PII context (used by middleware)."""
    _pii_context.set(ctx)


def clear_pii_context() -> None:
    """Clear the PII context at end of request."""
    _pii_context.set(None)


# --- Convenience Functions ---

def mask_pii(text: str, mode: MaskingMode = MaskingMode.FULL) -> str:
    """
    Mask PII in text using current request context.
    
    Convenience function for simple masking.
    
    Args:
        text: Raw text to mask
        mode: Masking mode (FULL, FINANCIAL_ONLY, NONE)
              - FULL: Mask all PII (default, for email bodies, documents)
              - FINANCIAL_ONLY: Only mask SSN/cards (for contact lookups, notes)
        
    Returns:
        Masked text
    """
    ctx = get_pii_context()
    result = ctx.mask_and_track(text, mode=mode)
    return result.masked_text


def mask_financial_only(text: str) -> str:
    """
    Mask only sensitive financial data, keeping contact info visible.
    
    Use this for tools where users expect to see emails/phones:
    - Contact lookups
    - Notes and memories
    - Relationship queries
    
    Args:
        text: Raw text to mask
        
    Returns:
        Text with only SSN/cards/accounts masked
    """
    return mask_pii(text, mode=MaskingMode.FINANCIAL_ONLY)


def mask_pii_in_dict(
    data: Dict[str, Any],
    keys_to_mask: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Mask PII in dictionary values.
    
    Args:
        data: Dictionary with potential PII
        keys_to_mask: Specific keys to mask (None = all string values)
        
    Returns:
        Dictionary with masked values
    """
    result = {}
    ctx = get_pii_context()
    
    for key, value in data.items():
        if isinstance(value, str):
            if keys_to_mask is None or key in keys_to_mask:
                result[key] = ctx.mask_and_track(value).masked_text
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = mask_pii_in_dict(value, keys_to_mask)
        elif isinstance(value, list):
            result[key] = [
                ctx.mask_and_track(v).masked_text if isinstance(v, str) else v
                for v in value
            ]
        else:
            result[key] = value
    
    return result


def resolve_pii_reference(placeholder: str) -> Optional[str]:
    """
    Resolve a PII placeholder to its original value.
    
    Args:
        placeholder: The placeholder (e.g., "[EMAIL_1]")
        
    Returns:
        Original value or None
    """
    ctx = get_pii_context()
    return ctx.resolve(placeholder)
```

### 1.2 Create middleware for per-request context

**File**: `services/yennifer_api/app/middleware/pii_context.py`

```python
"""
PII Context Middleware

Ensures each request has its own PII context for tracking masked values.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import logging

from ..core.pii import PIIContext, set_pii_context, clear_pii_context, get_pii_context

logger = logging.getLogger(__name__)


class PIIContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that creates a fresh PII context for each request.
    
    This ensures:
    1. Each request has isolated PII tracking
    2. Masked values from one request don't leak to another
    3. Context is cleaned up after request completes
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Create fresh context for this request
        ctx = PIIContext()
        set_pii_context(ctx)
        
        try:
            response = await call_next(request)
            
            # Log masking stats for monitoring (optional)
            stats = ctx.get_stats()
            if stats["total"] > 0:
                logger.debug(
                    f"PII masked in request: {stats['total']} items "
                    f"(emails: {stats.get('email', 0)}, "
                    f"phones: {stats.get('phone', 0)}, "
                    f"ssn: {stats.get('ssn', 0)})"
                )
            
            return response
            
        finally:
            # Always clean up context
            clear_pii_context()
```

### 1.3 Register middleware in main.py

**File**: `services/yennifer_api/app/main.py` (modification)

```python
# Add import
from .middleware.pii_context import PIIContextMiddleware

# Add middleware (after CORS, before other middleware)
app.add_middleware(PIIContextMiddleware)
```

---

## Phase 2: Add Masking to Workspace Tools (Day 1-2)

### Masking Mode Reference

| Tool Category | Mode | Rationale |
|---------------|------|-----------|
| **Email reading** (read_emails, get_email_details) | `FULL` | LLM is reasoning about content, doesn't need raw contact info |
| **Document reading** (read_google_doc, get_file_content) | `FULL` | Documents may contain sensitive data |
| **Spreadsheet reading** (read_spreadsheet_data) | `FULL` | May contain PII, financial data |
| **Contact lookup** (list_my_contacts, search_my_contacts) | `FINANCIAL_ONLY` | User explicitly asked for contact info - show emails/phones |
| **Memory/Notes** (get_user_memories, get_person_notes) | `FINANCIAL_ONLY` | Keep context, mask sensitive financial data |
| **Relationship queries** (find_person_by_relationship) | `FINANCIAL_ONLY` | Keep contact info for context |

### 2.1 Gmail Tools (Mode: FULL)

**File**: `services/yennifer_api/app/tools/gmail_tools.py`

No changes needed - raw data layer.

**File**: `services/yennifer_api/app/core/workspace_tools.py` (Gmail section)

```python
from ..core.pii import mask_pii, mask_financial_only, MaskingMode

@tool
def read_recent_emails(max_results: int = 10, days_back: int = 7) -> str:
    """Read recent emails from inbox."""
    emails = _read_emails(
        user_email=get_current_user(),
        max_results=max_results,
        days_back=days_back,
    )
    if not emails:
        return "No emails found."
    
    result = f"Found {len(emails)} emails:\n"
    for email in emails:
        result += f"\n- **{email['subject']}**\n"
        result += f"  From: {email['from']}\n"
        result += f"  Date: {email['date']}\n"
        result += f"  {email['snippet'][:100]}...\n"
        result += f"  ID: {email['id']}\n"  # Keep ID for actions
    
    # FULL masking - LLM is reasoning about email content
    return mask_pii(result)  # mode=FULL is default


@tool
def get_email_details(email_id: str) -> str:
    """Get full details of a specific email by ID."""
    email = _get_email_by_id(user_email=get_current_user(), email_id=email_id)
    
    result = f"**{email['subject']}**\n"
    result += f"From: {email['from']}\n"
    result += f"To: {email['to']}\n"
    result += f"Date: {email['date']}\n\n"
    result += f"{email['body']}"
    
    # FULL masking - email bodies may contain SSN, financial info, etc.
    return mask_pii(result)


@tool
def search_emails(query: str, max_results: int = 10) -> str:
    """Search emails using Gmail search query."""
    emails = _search_emails(
        user_email=get_current_user(),
        query=query,
        max_results=max_results,
    )
    if not emails:
        return f"No emails found matching: {query}"
    
    result = f"Found {len(emails)} emails matching '{query}':\n"
    for email in emails:
        result += f"\n- **{email['subject']}**\n"
        result += f"  From: {email['from']}\n"
        result += f"  Date: {email['date']}\n"
        result += f"  ID: {email['id']}\n"
    
    # FULL masking for email search results
    return mask_pii(result)
```

### 2.2 Docs Tools (Mode: FULL)

**File**: `services/yennifer_api/app/core/workspace_tools.py` (Docs section)

```python
@tool
def read_google_doc(document_id: str) -> str:
    """Read content from a Google Doc."""
    doc = _read_document(
        user_email=get_current_user(),
        document_id=document_id,
    )
    result = f"**{doc['title']}**\n\n{doc['content']}"
    
    # FULL masking - documents may contain contracts, PII, financial info
    return mask_pii(result)
```

### 2.3 Drive Tools (Mode: FULL)

```python
@tool
def get_file_content(file_id: str) -> str:
    """Get file content from Drive."""
    file_data = _get_file_content(
        user_email=get_current_user(),
        file_id=file_id,
    )
    
    result = f"**{file_data['name']}**\n"
    result += f"Type: {file_data['mime_type']}\n"
    if file_data.get('content'):
        result += f"\nContent:\n{file_data['content']}"
    
    # FULL masking - file content could be anything
    return mask_pii(result)
```

### 2.4 Sheets Tools (Mode: FULL)

```python
@tool
def read_spreadsheet_data(spreadsheet_id: str, range_name: str = "Sheet1") -> str:
    """Read data from a Google Sheets spreadsheet."""
    data = _read_spreadsheet(
        user_email=get_current_user(),
        spreadsheet_id=spreadsheet_id,
        range_name=range_name,
    )
    
    result = f"**{data['title']}** - {data['range']}\n\n"
    for row in data['values'][:20]:
        result += " | ".join(str(cell) for cell in row) + "\n"
    
    if data['row_count'] > 20:
        result += f"\n... ({data['row_count'] - 20} more rows)"
    
    # FULL masking - spreadsheets often contain financial data, contact lists
    return mask_pii(result)
```

### 2.5 Contacts Tools (Mode: FINANCIAL_ONLY)

**These tools show contact info to the user - only mask financial data.**

```python
@tool
def list_my_contacts(max_results: int = 20) -> str:
    """List contacts from Google Contacts."""
    contacts = _list_contacts(
        user_email=get_current_user(),
        max_results=max_results,
    )
    if not contacts:
        return "No contacts found."
    
    result = f"Found {len(contacts)} contacts:\n"
    for contact in contacts:
        result += f"\n- **{contact['name']}**"
        if contact['emails']:
            result += f" - {contact['emails'][0]}"
        if contact['organization']:
            result += f" ({contact['organization']})"
        result += "\n"
    
    # FINANCIAL_ONLY - user asked for contacts, show emails/phones
    # Only mask if contact info happens to contain SSN/card numbers
    return mask_financial_only(result)


@tool
def search_my_contacts(query: str) -> str:
    """Search contacts by name or email."""
    contacts = _search_contacts(
        user_email=get_current_user(),
        query=query,
    )
    if not contacts:
        return f"No contacts found matching: {query}"
    
    result = f"Contacts matching '{query}':\n"
    for contact in contacts:
        result += f"\n- **{contact['name']}**"
        if contact['emails']:
            result += f"\n  Email: {contact['emails'][0]}"
        if contact['phones']:
            result += f"\n  Phone: {contact['phones'][0]}"
        result += "\n"
    
    # FINANCIAL_ONLY - user explicitly asked for contact info
    return mask_financial_only(result)


@tool
def lookup_contact_email(name: str) -> str:
    """Look up a contact's email address by name."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - user is asking for email specifically
    return mask_financial_only(result)
```

---

## Phase 3: Update Action Tools for ID-Based Resolution (Day 2)

### 3.1 Create Draft Reply Tool (Updated)

The key insight: Action tools should accept **IDs** not raw email addresses:

```python
@tool
def create_draft_reply(
    email_id: str,
    body: str,
    include_original: bool = False,
) -> str:
    """
    Create a draft reply to an email.
    
    IMPORTANT: Use the email_id from read_recent_emails or get_email_details,
    NOT a raw email address. The recipient is determined from the original email.
    
    Args:
        email_id: Gmail message ID of the email to reply to
        body: The reply message body
        include_original: Whether to include quoted original message
        
    Returns:
        Confirmation with draft ID
    """
    user_email = get_current_user()
    
    # Resolve recipient from original email (internally, never from LLM)
    original = _get_email_by_id(user_email=user_email, email_id=email_id)
    
    # Extract recipient email from "From" header
    from_header = original['from']
    # Parse "Name <email@domain.com>" format
    import re
    email_match = re.search(r'<([^>]+)>', from_header)
    recipient = email_match.group(1) if email_match else from_header
    
    # Create the draft
    draft = _create_draft_reply(
        user_email=user_email,
        to=recipient,
        subject=f"Re: {original['subject']}",
        body=body,
        thread_id=original['thread_id'],
    )
    
    # Return confirmation (mask the recipient in output)
    return mask_pii(f"✅ Draft reply created to {recipient}\nDraft ID: {draft['id']}")
```

### 3.2 Send Email Tool (Updated)

```python
@tool
def send_email_to_contact(
    contact_name: str,
    subject: str,
    body: str,
) -> str:
    """
    Send an email to a contact by name.
    
    IMPORTANT: Use this instead of send_email when you know the contact's name.
    The email address is looked up internally.
    
    Args:
        contact_name: Name of the contact (looked up in User Network)
        subject: Email subject
        body: Email body
        
    Returns:
        Confirmation message
    """
    user_email = get_current_user()
    
    # Look up contact email internally
    recipient = _lookup_contact_email_internal(contact_name)
    if not recipient:
        return f"Could not find email for contact: {contact_name}"
    
    result = _send_email(
        user_email=user_email,
        to=recipient,
        subject=subject,
        body=body,
    )
    
    return mask_pii(f"✅ Email sent to {contact_name} ({recipient})")


@tool
def send_email_by_address(
    to_email: str,
    subject: str,
    body: str,
) -> str:
    """
    Send an email to a specific email address.
    
    Use this when you have a specific email address (e.g., from user input).
    For contacts in the user's network, prefer send_email_to_contact.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body
        
    Returns:
        Confirmation message
    """
    # This tool accepts raw email - for cases where user explicitly provides it
    result = _send_email(
        user_email=get_current_user(),
        to=to_email,
        subject=subject,
        body=body,
    )
    
    return f"✅ Email sent to {mask_pii(to_email)}"
```

### 3.3 Calendar Tools (Updated)

```python
@tool
def create_calendar_event_with_contact(
    summary: str,
    start_time: str,
    end_time: str,
    contact_name: str,
    description: str = "",
    location: str = "",
) -> str:
    """
    Create a calendar event and invite a contact by name.
    
    Args:
        summary: Event title
        start_time: Start time in ISO format
        end_time: End time in ISO format
        contact_name: Name of the contact to invite
        description: Event description
        location: Event location
        
    Returns:
        Confirmation with event details
    """
    user_email = get_current_user()
    
    # Look up contact email internally
    attendee_email = _lookup_contact_email_internal(contact_name)
    if not attendee_email:
        return f"Could not find email for contact: {contact_name}"
    
    result = _create_calendar_event(
        user_email=user_email,
        summary=summary,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
        attendees=[attendee_email],
    )
    
    return mask_pii(
        f"✅ Event created: **{result['summary']}**\n"
        f"Invited: {contact_name}\n"
        f"Event ID: {result['id']}"
    )
```

---

## Phase 4: Add Masking to Memory/Entity Tools (Day 2-3)

### Mode Selection for Memory/Entity Tools

Memory and entity tools need context to work well. The LLM needs to know:
- Who someone is (relationship)
- Their email/phone (for follow-up actions)
- Personal details (interests, notes)

Use **FINANCIAL_ONLY** mode to preserve context while protecting truly sensitive data.

### 4.1 Memory Tools (Mode: FINANCIAL_ONLY)

**File**: `services/yennifer_api/app/core/memory_tools.py`

```python
from ..core.pii import mask_financial_only

@tool
def get_user_memories(context: Optional[str] = None, category: Optional[str] = None) -> str:
    """Get memories/facts about the user."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - memories may contain contact info that provides context
    # but should mask any SSN/financial info that got stored
    return mask_financial_only(result)


@tool
def get_user_interests(category: Optional[str] = None, min_level: int = 50) -> str:
    """Get the user's interests and hobbies."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - interests are generally not sensitive
    return mask_financial_only(result)


@tool
def get_person_notes(person_id: str, include_expired: bool = False) -> str:
    """Get notes about a specific person."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - notes may contain "John's email is X" which is useful context
    # but should mask "John's SSN is X" if someone stored that
    return mask_financial_only(result)


@tool
def get_person_interests(person_id: str) -> str:
    """Get interests of a person in the user's network."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - interests are not sensitive
    return mask_financial_only(result)


@tool
def get_upcoming_important_dates(days_ahead: int = 30) -> str:
    """Get upcoming important dates."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - dates include contact info for context
    return mask_financial_only(result)


@tool
def get_important_dates_for_person(person_id: str) -> str:
    """Get important dates for a specific person."""
    # ... existing implementation ...
    
    return mask_financial_only(result)
```

### 4.2 Entity Resolution Tools (Mode: FINANCIAL_ONLY)

**File**: `services/yennifer_api/app/core/entity_resolution_tools.py`

```python
from ..core.pii import mask_financial_only

@tool
def find_person_candidates(name: str) -> str:
    """Find person candidates matching a name."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - need to show contact info for disambiguation
    # "Which John? John Smith (john@work.com) or John Doe (john@personal.com)"
    return mask_financial_only(result)


@tool
def find_person_by_relationship(relationship_type: str) -> str:
    """Find a person by their relationship to the user."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - relationship queries need contact context
    return mask_financial_only(result)


@tool
def check_person_has_contact(person_id: str, contact_type: str = "phone") -> str:
    """Check if a person has valid contact info."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - this is explicitly checking for contact info
    return mask_financial_only(result)
```

### 4.3 Person Management Tools (Mode: FINANCIAL_ONLY)

```python
@tool
def create_person_in_network(
    first_name: str,
    relationship_to_user: str,
    # ... other params
) -> str:
    """Create a new person in the user's network."""
    # ... existing implementation ...
    
    # FINANCIAL_ONLY - confirmation may include contact info
    return mask_financial_only(result)
```

---

## Phase 5: Testing and Validation (Day 3)

### 5.1 Unit Tests for PII Module

**File**: `services/yennifer_api/tests/test_pii.py`

```python
"""
Tests for PII masking module.
"""

import pytest
from app.core.pii import (
    PIIContext,
    MaskingMode,
    mask_pii,
    mask_financial_only,
    resolve_pii_reference,
    set_pii_context,
    clear_pii_context,
    PIIType,
)


class TestMaskingModes:
    """Test different masking modes."""
    
    def test_full_mode_masks_everything(self):
        """FULL mode should mask emails, phones, SSN, cards."""
        ctx = PIIContext()
        text = "Email john@example.com, phone 555-123-4567, SSN 123-45-6789"
        
        result = ctx.mask_and_track(text, mode=MaskingMode.FULL)
        
        # All PII should be masked
        assert "john@example.com" not in result.masked_text
        assert "555-123-4567" not in result.masked_text
        assert "123-45-6789" not in result.masked_text
        assert "[EMAIL_1]" in result.masked_text
        assert "[PHONE_1]" in result.masked_text
        assert "[SSN]" in result.masked_text
    
    def test_financial_only_preserves_contact_info(self):
        """FINANCIAL_ONLY mode should keep emails/phones, mask SSN/cards."""
        ctx = PIIContext()
        text = "Email john@example.com, phone 555-123-4567, SSN 123-45-6789"
        
        result = ctx.mask_and_track(text, mode=MaskingMode.FINANCIAL_ONLY)
        
        # Contact info should be preserved
        assert "john@example.com" in result.masked_text
        assert "555-123-4567" in result.masked_text
        
        # Financial data should still be masked
        assert "123-45-6789" not in result.masked_text
        assert "[SSN]" in result.masked_text
    
    def test_financial_only_masks_credit_cards(self):
        """FINANCIAL_ONLY should mask credit card numbers."""
        ctx = PIIContext()
        text = "Card: 4111-1111-1111-1111, email: support@bank.com"
        
        result = ctx.mask_and_track(text, mode=MaskingMode.FINANCIAL_ONLY)
        
        # Card masked, email preserved
        assert "4111-1111-1111-1111" not in result.masked_text
        assert "[CARD]" in result.masked_text
        assert "support@bank.com" in result.masked_text
    
    def test_none_mode_masks_nothing(self):
        """NONE mode should not mask anything (internal use only)."""
        ctx = PIIContext()
        text = "SSN 123-45-6789, email john@example.com"
        
        result = ctx.mask_and_track(text, mode=MaskingMode.NONE)
        
        # Nothing should be masked
        assert result.masked_text == text
        assert len(result.items_masked) == 0


class TestConvenienceFunctions:
    """Test convenience functions use correct modes."""
    
    def setup_method(self):
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_mask_pii_uses_full_mode(self):
        """mask_pii() should use FULL mode by default."""
        result = mask_pii("Email john@example.com, SSN 123-45-6789")
        
        # Both should be masked in FULL mode
        assert "john@example.com" not in result
        assert "123-45-6789" not in result
    
    def test_mask_financial_only_preserves_contact(self):
        """mask_financial_only() should preserve contact info."""
        result = mask_financial_only("Email john@example.com, SSN 123-45-6789")
        
        # Email preserved, SSN masked
        assert "john@example.com" in result
        assert "123-45-6789" not in result


class TestPIIContext:
    """Test PIIContext class."""
    
    def test_mask_email_full_mode(self):
        ctx = PIIContext()
        result = ctx.mask_and_track(
            "Contact john@example.com for details",
            mode=MaskingMode.FULL
        )
        
        assert "[EMAIL_1]" in result.masked_text
        assert "john@example.com" not in result.masked_text
        assert len(result.items_masked) == 1
        assert result.items_masked[0].pii_type == PIIType.EMAIL
    
    def test_mask_multiple_emails(self):
        ctx = PIIContext()
        result = ctx.mask_and_track(
            "Email john@example.com or jane@example.com",
            mode=MaskingMode.FULL
        )
        
        assert "[EMAIL_1]" in result.masked_text
        assert "[EMAIL_2]" in result.masked_text
        assert len(result.items_masked) == 2
    
    def test_mask_ssn_always(self):
        """SSN should be masked in ALL modes (except NONE)."""
        ctx = PIIContext()
        
        # Test FULL mode
        result_full = ctx.mask_and_track("SSN: 123-45-6789", mode=MaskingMode.FULL)
        assert "[SSN]" in result_full.masked_text
        
        # Test FINANCIAL_ONLY mode
        ctx2 = PIIContext()
        result_fin = ctx2.mask_and_track("SSN: 123-45-6789", mode=MaskingMode.FINANCIAL_ONLY)
        assert "[SSN]" in result_fin.masked_text
    
    def test_resolve_trackable(self):
        ctx = PIIContext()
        ctx.mask_and_track("Email john@example.com", mode=MaskingMode.FULL)
        
        # Should be able to resolve email
        resolved = ctx.resolve("[EMAIL_1]")
        assert resolved == "john@example.com"
    
    def test_cannot_resolve_ssn(self):
        ctx = PIIContext()
        ctx.mask_and_track("SSN: 123-45-6789", mode=MaskingMode.FULL)
        
        # SSN should not be resolvable (redacted type)
        resolved = ctx.resolve("[SSN]")
        assert resolved is None
    
    def test_audit_log_no_original_values(self):
        ctx = PIIContext()
        ctx.mask_and_track(
            "Email john@example.com, SSN 123-45-6789",
            mode=MaskingMode.FULL
        )
        
        audit = ctx.get_full_audit_log()
        
        # Audit log should NOT contain original values
        for entry in audit:
            assert "john@example.com" not in str(entry)
            assert "123-45-6789" not in str(entry)


class TestRealWorldExamples:
    """Test with realistic content for each mode."""
    
    def test_email_body_full_mode(self):
        """Email bodies should use FULL mode."""
        ctx = PIIContext()
        email_body = """
        Hi,
        
        My SSN is 123-45-6789 for the insurance form.
        You can reach me at john@example.com or 555-123-4567.
        
        Best,
        John
        """
        
        result = ctx.mask_and_track(email_body, mode=MaskingMode.FULL)
        
        # ALL PII should be masked
        assert "123-45-6789" not in result.masked_text
        assert "john@example.com" not in result.masked_text
        assert "555-123-4567" not in result.masked_text
    
    def test_contact_lookup_financial_only(self):
        """Contact lookup should use FINANCIAL_ONLY to show contact info."""
        ctx = PIIContext()
        contact_result = """
        Found contact: John Smith
        Email: john@example.com
        Phone: 555-123-4567
        Note: SSN on file is 123-45-6789
        """
        
        result = ctx.mask_and_track(contact_result, mode=MaskingMode.FINANCIAL_ONLY)
        
        # Contact info preserved
        assert "john@example.com" in result.masked_text
        assert "555-123-4567" in result.masked_text
        
        # SSN still masked
        assert "123-45-6789" not in result.masked_text
        assert "[SSN]" in result.masked_text
    
    def test_person_notes_financial_only(self):
        """Person notes should preserve emails but mask financial."""
        ctx = PIIContext()
        notes = """
        - John's work email is john@work.com
        - His credit card ends in 4111-1111-1111-1111
        - Meeting next Tuesday
        """
        
        result = ctx.mask_and_track(notes, mode=MaskingMode.FINANCIAL_ONLY)
        
        # Email preserved (useful context)
        assert "john@work.com" in result.masked_text
        
        # Credit card masked
        assert "4111-1111-1111-1111" not in result.masked_text
```

### 5.2 Integration Tests

**File**: `services/yennifer_api/tests/test_workspace_tools_pii.py`

```python
"""
Integration tests for PII masking in workspace tools.
"""

import pytest
from unittest.mock import patch, MagicMock
from app.core.workspace_tools import (
    read_recent_emails,
    get_email_details,
    read_google_doc,
)
from app.core.pii import set_pii_context, clear_pii_context, PIIContext


class TestWorkspaceToolsPII:
    """Test that workspace tools properly mask PII."""
    
    def setup_method(self):
        set_pii_context(PIIContext())
    
    def teardown_method(self):
        clear_pii_context()
    
    @patch('app.core.workspace_tools._read_emails')
    @patch('app.core.workspace_tools.get_current_user')
    def test_read_emails_masks_sender(self, mock_user, mock_read):
        mock_user.return_value = "test@example.com"
        mock_read.return_value = [{
            'subject': 'Test Email',
            'from': 'sender@company.com',
            'date': '2024-01-01',
            'snippet': 'Call me at 555-123-4567',
            'id': 'msg123',
        }]
        
        result = read_recent_emails.invoke({"max_results": 10, "days_back": 7})
        
        # Should mask email and phone
        assert "sender@company.com" not in result
        assert "555-123-4567" not in result
        # But keep the ID for actions
        assert "msg123" in result
```

---

## Phase 6: Audit Logging for Compliance (Day 3-4)

### 6.1 Add PII Audit Logger

**File**: `services/yennifer_api/app/core/pii_audit.py`

```python
"""
PII Audit Logging

Logs PII masking operations for compliance and monitoring.
Never logs actual PII values.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from .pii import PIIContext

logger = logging.getLogger("pii_audit")


class PIIAuditLogger:
    """Audit logger for PII masking operations."""
    
    def __init__(self, user_id: Optional[UUID] = None, request_id: Optional[str] = None):
        self.user_id = user_id
        self.request_id = request_id
    
    def log_masking_summary(self, ctx: PIIContext, tool_name: str):
        """Log summary of masking operations for a tool call."""
        stats = ctx.get_stats()
        
        if stats["total"] == 0:
            return  # Nothing masked, nothing to log
        
        log_entry = {
            "event": "pii_masked",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": str(self.user_id) if self.user_id else None,
            "request_id": self.request_id,
            "tool": tool_name,
            "stats": stats,
        }
        
        logger.info(f"PII masked: {log_entry}")
    
    def log_resolution_attempt(self, placeholder: str, resolved: bool, tool_name: str):
        """Log when a PII reference is resolved (for action tools)."""
        log_entry = {
            "event": "pii_resolved" if resolved else "pii_resolution_failed",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": str(self.user_id) if self.user_id else None,
            "request_id": self.request_id,
            "tool": tool_name,
            "placeholder": placeholder,
        }
        
        logger.info(f"PII resolution: {log_entry}")
```

### 6.2 Database Table for PII Audit (Optional)

**File**: `services/yennifer_api/app/db/migrations/012_pii_audit_log.sql`

```sql
-- PII masking audit log for compliance
CREATE TABLE IF NOT EXISTS pii_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    request_id VARCHAR(100),
    tool_name VARCHAR(100) NOT NULL,
    
    -- Masking stats (no actual PII values)
    total_masked INTEGER NOT NULL DEFAULT 0,
    emails_masked INTEGER NOT NULL DEFAULT 0,
    phones_masked INTEGER NOT NULL DEFAULT 0,
    ssn_masked INTEGER NOT NULL DEFAULT 0,
    cards_masked INTEGER NOT NULL DEFAULT 0,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pii_audit_user ON pii_audit_log(user_id);
CREATE INDEX idx_pii_audit_time ON pii_audit_log(created_at);
```

---

## Summary: Files to Create/Modify

### Masking Mode Quick Reference

| Tool Type | Mode | What's Masked | What's Visible |
|-----------|------|---------------|----------------|
| **Email reading** | `FULL` | All PII | Subject, names, dates, IDs |
| **Documents/Sheets** | `FULL` | All PII | Document structure |
| **Contact lookup** | `FINANCIAL_ONLY` | SSN, cards | Emails, phones, names |
| **Memory/Notes** | `FINANCIAL_ONLY` | SSN, cards | Emails, phones, context |
| **Relationships** | `FINANCIAL_ONLY` | SSN, cards | Contact info, names |

### New Files

| File | Purpose |
|------|---------|
| `app/core/pii.py` | Core PII masking module with `MaskingMode` enum |
| `app/middleware/pii_context.py` | Per-request context middleware |
| `app/core/pii_audit.py` | Audit logging |
| `tests/test_pii.py` | Unit tests (including mode tests) |
| `tests/test_workspace_tools_pii.py` | Integration tests |
| `app/db/migrations/012_pii_audit_log.sql` | Audit table (optional) |

### Modified Files

| File | Changes |
|------|---------|
| `app/main.py` | Add PIIContextMiddleware |
| `app/core/workspace_tools.py` | Add `mask_pii()` (FULL) to email/doc/drive/sheet tools, `mask_financial_only()` to contact tools |
| `app/core/memory_tools.py` | Add `mask_financial_only()` to all memory/note/interest tools |
| `app/core/entity_resolution_tools.py` | Add `mask_financial_only()` to all entity tools |

---

## Rollout Plan

1. **Day 1**: Core module + middleware + Gmail tools
2. **Day 2**: Remaining workspace tools + action tools update
3. **Day 3**: Memory tools + testing + bug fixes
4. **Day 4**: Audit logging + documentation + deploy to staging

---

## Configuration

Add to `.env`:

```env
# PII Masking Configuration
PII_MASKING_ENABLED=true
PII_AUDIT_LOGGING=true
PII_AUDIT_TO_DATABASE=false  # Set to true for compliance requirements
```

