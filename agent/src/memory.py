"""
User Memory Storage

Stores contextual facts and preferences about the user.
Facts are stored per-context and can be promoted to global when they appear
in multiple contexts.

All data is encrypted locally using the same key as style profiles.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .crypto import (
    AGENT_DIR,
    get_or_create_key,
    encrypt_data,
    decrypt_data,
)

# Memory storage path
MEMORY_PATH = AGENT_DIR / "user_memory.enc"

# Number of contexts a fact must appear in to be promoted to global
GLOBAL_PROMOTION_THRESHOLD = 3

# Predefined context categories
CONTEXT_CATEGORIES = [
    "medical_health",
    "professional_work",
    "recruiters_jobs",
    "financial_banking",
    "family_friends",
    "services_utilities",
    "shopping_retail",
    "travel",
    "education",
    "legal",
    "other",
]


def _get_empty_memory() -> dict:
    """Return empty memory structure."""
    return {
        "contextual_facts": {cat: {} for cat in CONTEXT_CATEGORIES},
        "global_facts": {},
        "fact_occurrences": {},  # Tracks which contexts a fact key appears in
        "_metadata": {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "version": "1.0",
        }
    }


def load_memory() -> dict:
    """
    Load user memory from encrypted storage.
    
    Returns:
        Memory dictionary, or empty structure if not found
    """
    if not MEMORY_PATH.exists():
        return _get_empty_memory()
    
    try:
        with open(MEMORY_PATH, "rb") as f:
            encrypted = f.read()
        return decrypt_data(encrypted)
    except Exception:
        return _get_empty_memory()


def save_memory(memory: dict) -> Path:
    """
    Save user memory to encrypted storage.
    
    Args:
        memory: Memory dictionary to save
        
    Returns:
        Path where memory was saved
    """
    memory["_metadata"]["last_updated"] = datetime.now().isoformat()
    
    AGENT_DIR.mkdir(mode=0o700, exist_ok=True)
    encrypted = encrypt_data(memory)
    
    with open(MEMORY_PATH, "wb") as f:
        f.write(encrypted)
    
    import os
    os.chmod(MEMORY_PATH, 0o600)
    
    return MEMORY_PATH


def add_contextual_fact(
    context: str,
    fact_key: str,
    fact_value: str,
    auto_promote: bool = True,
) -> dict:
    """
    Add a fact to a specific context.
    
    Args:
        context: Context category (e.g., "medical_health")
        fact_key: Key for the fact (e.g., "insurance_status")
        fact_value: Value of the fact (e.g., "No current dental insurance")
        auto_promote: If True, check if fact should be promoted to global
        
    Returns:
        Status dict with result
    """
    memory = load_memory()
    
    # Normalize context
    if context not in CONTEXT_CATEGORIES:
        # Try to find closest match or use "other"
        context = _categorize_context(context)
    
    # Initialize context if needed
    if context not in memory["contextual_facts"]:
        memory["contextual_facts"][context] = {}
    
    # Add fact
    memory["contextual_facts"][context][fact_key] = {
        "value": fact_value,
        "added_at": datetime.now().isoformat(),
    }
    
    # Track occurrence for global promotion
    if fact_key not in memory["fact_occurrences"]:
        memory["fact_occurrences"][fact_key] = []
    
    if context not in memory["fact_occurrences"][fact_key]:
        memory["fact_occurrences"][fact_key].append(context)
    
    # Check for global promotion
    promoted = False
    if auto_promote:
        occurrences = len(memory["fact_occurrences"].get(fact_key, []))
        if occurrences >= GLOBAL_PROMOTION_THRESHOLD:
            # Promote to global
            memory["global_facts"][fact_key] = {
                "value": fact_value,
                "promoted_at": datetime.now().isoformat(),
                "source_contexts": memory["fact_occurrences"][fact_key],
            }
            promoted = True
    
    save_memory(memory)
    
    return {
        "status": "success",
        "context": context,
        "fact_key": fact_key,
        "promoted_to_global": promoted,
    }


def get_facts_for_context(context: str, include_global: bool = True) -> dict:
    """
    Get all facts relevant to a specific context.
    
    Args:
        context: Context category
        include_global: Whether to include global facts
        
    Returns:
        Dict of relevant facts
    """
    memory = load_memory()
    
    # Normalize context
    if context not in CONTEXT_CATEGORIES:
        context = _categorize_context(context)
    
    facts = {}
    
    # Add context-specific facts
    context_facts = memory["contextual_facts"].get(context, {})
    for key, data in context_facts.items():
        facts[key] = data["value"]
    
    # Add global facts
    if include_global:
        for key, data in memory["global_facts"].items():
            if key not in facts:  # Context-specific takes precedence
                facts[key] = data["value"]
    
    return facts


def get_all_facts() -> dict:
    """
    Get all stored facts organized by context.
    
    Returns:
        Dict with all facts
    """
    memory = load_memory()
    
    result = {
        "global": {},
        "by_context": {},
    }
    
    # Global facts
    for key, data in memory["global_facts"].items():
        result["global"][key] = data["value"]
    
    # Context facts
    for context, facts in memory["contextual_facts"].items():
        if facts:  # Only include non-empty contexts
            result["by_context"][context] = {
                key: data["value"] for key, data in facts.items()
            }
    
    return result


def remove_fact(fact_key: str, context: Optional[str] = None) -> dict:
    """
    Remove a fact from memory.
    
    Args:
        fact_key: Key of the fact to remove
        context: If provided, only remove from this context.
                If None, remove from all contexts and global.
                
    Returns:
        Status dict
    """
    memory = load_memory()
    removed_from = []
    
    if context:
        # Remove from specific context
        if context in memory["contextual_facts"]:
            if fact_key in memory["contextual_facts"][context]:
                del memory["contextual_facts"][context][fact_key]
                removed_from.append(context)
    else:
        # Remove from all contexts
        for ctx in memory["contextual_facts"]:
            if fact_key in memory["contextual_facts"][ctx]:
                del memory["contextual_facts"][ctx][fact_key]
                removed_from.append(ctx)
        
        # Remove from global
        if fact_key in memory["global_facts"]:
            del memory["global_facts"][fact_key]
            removed_from.append("global")
        
        # Remove from occurrences tracking
        if fact_key in memory["fact_occurrences"]:
            del memory["fact_occurrences"][fact_key]
    
    save_memory(memory)
    
    return {
        "status": "success" if removed_from else "not_found",
        "removed_from": removed_from,
    }


def clear_all_memory() -> dict:
    """
    Clear all stored memory.
    
    Returns:
        Status dict
    """
    memory = _get_empty_memory()
    save_memory(memory)
    
    return {
        "status": "success",
        "message": "All memory cleared.",
    }


def _categorize_context(text: str) -> str:
    """
    Categorize a context string into one of the predefined categories.
    
    Args:
        text: Context description or category name
        
    Returns:
        Matching category from CONTEXT_CATEGORIES
    """
    text_lower = text.lower()
    
    # Simple keyword matching
    category_keywords = {
        "medical_health": ["medical", "health", "doctor", "hospital", "dental", "clinic", "pharmacy", "insurance"],
        "professional_work": ["work", "professional", "office", "colleague", "boss", "manager", "business"],
        "recruiters_jobs": ["recruit", "job", "career", "hiring", "interview", "resume", "linkedin"],
        "financial_banking": ["bank", "financial", "money", "payment", "loan", "credit", "investment"],
        "family_friends": ["family", "friend", "mom", "dad", "brother", "sister", "personal"],
        "services_utilities": ["service", "utility", "electric", "gas", "water", "internet", "phone"],
        "shopping_retail": ["shop", "retail", "order", "delivery", "purchase", "amazon", "store"],
        "travel": ["travel", "flight", "hotel", "booking", "vacation", "trip", "airline"],
        "education": ["school", "university", "college", "education", "course", "class", "student"],
        "legal": ["legal", "lawyer", "attorney", "court", "contract"],
    }
    
    for category, keywords in category_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return category
    
    return "other"


def detect_context_from_email(
    sender: str = "",
    subject: str = "",
    body: str = "",
) -> str:
    """
    Auto-detect context category from email content.
    
    Args:
        sender: Sender email/name
        subject: Email subject
        body: Email body
        
    Returns:
        Detected context category
    """
    combined = f"{sender} {subject} {body}".lower()
    return _categorize_context(combined)


def get_memory_stats() -> dict:
    """
    Get statistics about stored memory.
    
    Returns:
        Dict with memory statistics
    """
    memory = load_memory()
    
    total_contextual = sum(
        len(facts) for facts in memory["contextual_facts"].values()
    )
    
    contexts_with_facts = [
        ctx for ctx, facts in memory["contextual_facts"].items() if facts
    ]
    
    return {
        "global_facts_count": len(memory["global_facts"]),
        "contextual_facts_count": total_contextual,
        "contexts_with_facts": contexts_with_facts,
        "last_updated": memory["_metadata"].get("last_updated"),
    }



