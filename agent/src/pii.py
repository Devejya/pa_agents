"""
PII (Personally Identifiable Information) Masking

Masks sensitive information before sending to LLM APIs.
This protects user privacy while still allowing email analysis.
"""

import re
from typing import Callable


def mask_email_addresses(text: str) -> str:
    """Mask email addresses."""
    return re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL]', text)


def mask_phone_numbers(text: str) -> str:
    """Mask phone numbers (various formats)."""
    patterns = [
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # 123-456-7890
        r'\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b',   # (123) 456-7890
        r'\b\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # +1-123-456-7890
    ]
    for pattern in patterns:
        text = re.sub(pattern, '[PHONE]', text)
    return text


def mask_ssn(text: str) -> str:
    """Mask Social Security Numbers."""
    return re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)


def mask_credit_cards(text: str) -> str:
    """Mask credit card numbers."""
    return re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD]', text)


def mask_addresses(text: str) -> str:
    """Mask street addresses (basic patterns)."""
    # Street addresses with zip codes
    text = re.sub(
        r'\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct)\.?(?:[\w\s,]*\d{5}(?:-\d{4})?)?',
        '[ADDRESS]',
        text,
        flags=re.IGNORECASE
    )
    return text


def mask_dates_of_birth(text: str) -> str:
    """Mask dates that might be DOB (context: born, birthday, DOB)."""
    # Look for dates near DOB-related words
    text = re.sub(
        r'(?:born|birthday|dob|date of birth)[:\s]*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',
        '[DOB]',
        text,
        flags=re.IGNORECASE
    )
    return text


def mask_account_numbers(text: str) -> str:
    """Mask account numbers (generic long numbers)."""
    # Account numbers typically 8-16 digits
    text = re.sub(
        r'(?:account|acct|routing)[#:\s]*\d{8,16}',
        '[ACCOUNT]',
        text,
        flags=re.IGNORECASE
    )
    return text


def mask_pii(text: str, preserve_names: bool = False) -> str:
    """
    Apply all PII masking to text.
    
    Args:
        text: Text to mask
        preserve_names: If True, don't mask names (useful for greetings analysis)
        
    Returns:
        Text with PII masked
    """
    if not text:
        return text
    
    # Apply all masking functions
    text = mask_email_addresses(text)
    text = mask_phone_numbers(text)
    text = mask_ssn(text)
    text = mask_credit_cards(text)
    text = mask_addresses(text)
    text = mask_dates_of_birth(text)
    text = mask_account_numbers(text)
    
    return text


def mask_pii_in_dict(data: dict, keys_to_mask: list[str] = None) -> dict:
    """
    Mask PII in specific dictionary values.
    
    Args:
        data: Dictionary with potential PII
        keys_to_mask: List of keys whose values should be masked
                     If None, masks all string values
    
    Returns:
        Dictionary with PII masked
    """
    result = {}
    
    for key, value in data.items():
        if isinstance(value, str):
            if keys_to_mask is None or key in keys_to_mask:
                result[key] = mask_pii(value)
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = mask_pii_in_dict(value, keys_to_mask)
        elif isinstance(value, list):
            result[key] = [
                mask_pii(v) if isinstance(v, str) else v 
                for v in value
            ]
        else:
            result[key] = value
    
    return result



