"""
Memory Management Tools

Tools for extracting, storing, and retrieving user facts and preferences.
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ..memory import (
    add_contextual_fact,
    get_facts_for_context,
    get_all_facts,
    remove_fact,
    clear_all_memory,
    detect_context_from_email,
    get_memory_stats,
    CONTEXT_CATEGORIES,
)
from ..pii import mask_pii


def extract_facts_from_conversation(
    user_message: str,
    email_context: str = "",
    auto_save: bool = False,
) -> dict:
    """
    Extract potential facts/preferences from user's message.
    
    This analyzes what the user said and identifies information that
    might be worth remembering for future interactions.
    
    Args:
        user_message: What the user said
        email_context: Context of the email being discussed
        auto_save: If True, automatically save extracted facts
        
    Returns:
        Dict with extracted facts and whether to save them
    """
    # Mask PII before sending to LLM
    masked_message = mask_pii(user_message)
    masked_context = mask_pii(email_context)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a memory extraction assistant. Analyze the user's message and identify 
facts or preferences that would be useful to remember for future similar situations.

Look for:
- Preferences (e.g., "I prefer afternoon appointments")
- Status information (e.g., "I don't have insurance")
- Constraints (e.g., "That's too expensive for me")
- Decisions (e.g., "I want to reschedule")
- Personal circumstances (e.g., "I'm actively job hunting")

DO NOT extract:
- One-time decisions that won't repeat
- Sensitive PII (SSN, credit cards, etc.)
- Information that's too specific to be useful later

For each fact, determine the appropriate context category from:
{categories}

Return JSON:
{{
    "facts": [
        {{
            "key": "short_key_name",
            "value": "the fact/preference to remember",
            "context": "category from list above",
            "reasoning": "why this is worth remembering"
        }}
    ],
    "has_useful_facts": true/false
}}

If nothing worth remembering, return empty facts array."""),
        ("user", """Analyze this user message for facts to remember:

User said: {message}

Email context: {context}

Return ONLY valid JSON."""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "categories": ", ".join(CONTEXT_CATEGORIES),
            "message": masked_message,
            "context": masked_context or "Not specified",
        })
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "facts": [],
        }
    
    facts = result.get("facts", [])
    
    if auto_save and facts:
        for fact in facts:
            add_contextual_fact(
                context=fact["context"],
                fact_key=fact["key"],
                fact_value=fact["value"],
            )
    
    return {
        "status": "success",
        "facts": facts,
        "has_useful_facts": result.get("has_useful_facts", bool(facts)),
        "auto_saved": auto_save and bool(facts),
    }


def store_user_fact(
    fact_key: str,
    fact_value: str,
    context: str,
) -> dict:
    """
    Store a fact about the user.
    
    Args:
        fact_key: Short key for the fact
        fact_value: The fact/preference to store
        context: Context category
        
    Returns:
        Status dict
    """
    result = add_contextual_fact(
        context=context,
        fact_key=fact_key,
        fact_value=fact_value,
    )
    
    return result


def retrieve_relevant_facts(
    context: str = "",
    sender: str = "",
    subject: str = "",
    body: str = "",
) -> dict:
    """
    Retrieve facts relevant to the current email/context.
    
    Args:
        context: Explicit context category (optional)
        sender: Email sender (for auto-detection)
        subject: Email subject (for auto-detection)
        body: Email body (for auto-detection)
        
    Returns:
        Dict with relevant facts
    """
    # Auto-detect context if not provided
    if not context:
        context = detect_context_from_email(
            sender=sender,
            subject=subject,
            body=body,
        )
    
    facts = get_facts_for_context(context, include_global=True)
    
    return {
        "status": "success",
        "detected_context": context,
        "facts": facts,
        "fact_count": len(facts),
    }


def list_all_memories() -> dict:
    """
    Get all stored facts organized by context.
    
    Returns:
        All stored facts
    """
    facts = get_all_facts()
    stats = get_memory_stats()
    
    return {
        "status": "success",
        "facts": facts,
        "stats": stats,
    }


def forget_fact(fact_key: str, context: str = None) -> dict:
    """
    Remove a stored fact.
    
    Args:
        fact_key: Key of fact to remove
        context: If specified, only remove from this context
        
    Returns:
        Status dict
    """
    return remove_fact(fact_key, context)


def forget_all_memories() -> dict:
    """
    Clear all stored memories.
    
    Returns:
        Status dict
    """
    return clear_all_memory()


def should_remember_this(
    user_message: str,
    assistant_response: str = "",
) -> dict:
    """
    Determine if there's something from this exchange worth remembering.
    
    This is called after a user provides answers to questions.
    
    Args:
        user_message: What the user said
        assistant_response: What the assistant said (for context)
        
    Returns:
        Dict with facts to potentially remember
    """
    # Mask PII
    masked_message = mask_pii(user_message)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Analyze if the user's response contains information worth remembering 
for future similar situations.

Criteria for remembering:
1. It's a preference that would apply to similar future situations
2. It's a status/circumstance that's ongoing (not a one-time thing)
3. It would help give better responses in the future

DO NOT remember:
- One-time specific answers
- Sensitive information
- Things that are likely to change frequently

Categories: {categories}

Return JSON:
{{
    "should_remember": true/false,
    "facts": [
        {{
            "key": "short_key",
            "value": "what to remember",
            "context": "category",
            "reason": "why worth remembering"
        }}
    ],
    "ask_user": true/false,
    "suggestion_message": "Message to ask user if they want this remembered"
}}"""),
        ("user", """User said: {message}

Should any of this be remembered for future interactions?"""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "categories": ", ".join(CONTEXT_CATEGORIES),
            "message": masked_message,
        })
        return {
            "status": "success",
            **result,
        }
    except Exception as e:
        return {
            "status": "error",
            "should_remember": False,
            "facts": [],
            "ask_user": False,
        }


def auto_extract_and_save_facts(
    user_message: str,
    email_context: str = "",
) -> dict:
    """
    Automatically extract facts from user's message and save them.
    
    This combines extraction and saving in one step for automatic memory.
    Called after user provides information that might be worth remembering.
    
    Args:
        user_message: What the user said
        email_context: Context of the email being discussed (for better categorization)
        
    Returns:
        Dict with what was saved
    """
    # Mask PII
    masked_message = mask_pii(user_message)
    masked_context = mask_pii(email_context) if email_context else ""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a memory extraction assistant. Analyze the user's message and identify 
facts or preferences worth remembering for future similar situations.

EXTRACT facts that are:
- Ongoing status (e.g., "no insurance", "job hunting")
- Reusable preferences (e.g., "prefer afternoon meetings", "don't share time preferences")
- Cost/budget constraints (e.g., "$X is too expensive for [category]")
- Communication preferences (e.g., "don't mention X to others")
- Behavioral patterns (e.g., "reschedule when cost is high")

DO NOT extract:
- One-time specific decisions
- Sensitive PII (SSN, credit cards, passwords)
- Temporary/changing information

Categories: {categories}

Return JSON:
{{
    "facts": [
        {{
            "key": "short_snake_case_key",
            "value": "concise fact to remember",
            "context": "category from list"
        }}
    ]
}}

If nothing worth remembering, return empty facts array."""),
        ("user", """User said: {message}

Email context: {context}

Extract facts worth remembering. Return ONLY valid JSON."""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "categories": ", ".join(CONTEXT_CATEGORIES),
            "message": masked_message,
            "context": masked_context or "General conversation",
        })
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "saved": [],
        }
    
    facts = result.get("facts", [])
    saved = []
    
    # Auto-save each fact
    for fact in facts:
        try:
            add_result = add_contextual_fact(
                context=fact["context"],
                fact_key=fact["key"],
                fact_value=fact["value"],
            )
            saved.append({
                "key": fact["key"],
                "value": fact["value"],
                "context": fact["context"],
                "promoted_to_global": add_result.get("promoted_to_global", False),
            })
        except Exception:
            continue
    
    return {
        "status": "success" if saved else "no_facts",
        "saved": saved,
        "count": len(saved),
    }

