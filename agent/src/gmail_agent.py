"""
Gmail LangChain Agent

Main agent that combines all Gmail tools with LLM reasoning.
"""

import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from .tools.read_emails import read_emails, get_email_by_id
from .tools.summarize import summarize_daily_emails
from .tools.priority import get_priority_emails
from .tools.draft_reply import (
    create_draft_reply,
    generate_reply_preview,
    compose_reply_to_text,
    compose_new_email,
    create_new_draft,
)
from .tools.learn_style import (
    analyze_writing_style,
    analyze_contextual_styles,
    get_style_status,
    get_contextual_style_status,
    clear_style_profile,
    auto_refresh_styles_if_needed,
    STYLE_CATEGORIES,
)
from .tools.memory_tools import (
    store_user_fact,
    retrieve_relevant_facts,
    list_all_memories,
    forget_fact,
    forget_all_memories,
    should_remember_this,
    auto_extract_and_save_facts,
)
from .tools.user_network import USER_NETWORK_TOOLS
from .tools.profile_discovery import PROFILE_DISCOVERY_TOOLS


# Define tools for the agent
@tool
def fetch_emails(
    max_results: int = 10,
    days_back: int = 7,
    unread_only: bool = False,
    query: str = "",
) -> str:
    """
    Fetch emails from Gmail (both inbox AND sent).
    
    Args:
        max_results: Maximum number of emails to fetch (default 10)
        days_back: Only fetch emails from last N days (default 7)
        unread_only: Only fetch unread emails (default False)
        query: Gmail search query for filtering. Examples:
               - "to:someone@gmail.com" for emails sent TO someone
               - "from:someone@gmail.com" for emails FROM someone  
               - "subject:meeting" for emails with subject containing "meeting"
               - "in:sent" for only sent emails
               - "in:inbox" for only inbox emails
               - Combine: "to:friend@gmail.com in:sent" for sent emails to a friend
    
    Returns:
        List of emails with id, subject, from, to, date, and snippet
    """
    emails = read_emails(
        max_results=max_results,
        days_back=days_back,
        unread_only=unread_only,
        query=query,
    )
    
    if not emails:
        return "No emails found matching the criteria."
    
    result = []
    for e in emails:
        status = "📬 UNREAD" if e["is_unread"] else "📭 Read"
        # Show To field for sent emails, From for received
        is_sent = "SENT" in e.get("labels", [])
        contact_info = f"To: {e['to']}" if is_sent else f"From: {e['from']}"
        
        result.append(
            f"ID: {e['id']}\n"
            f"Status: {status}{' (SENT)' if is_sent else ''}\n"
            f"{contact_info}\n"
            f"Subject: {e['subject']}\n"
            f"Date: {e['date']}\n"
            f"Preview: {e['snippet'][:100]}...\n"
        )
    
    return f"Found {len(emails)} emails:\n\n" + "\n---\n".join(result)


@tool
def get_email_details(email_id: str) -> str:
    """
    Get full details of a specific email by ID.
    
    Args:
        email_id: The Gmail message ID
        
    Returns:
        Full email content including body
    """
    email = get_email_by_id(email_id)
    
    if not email:
        return f"Email with ID {email_id} not found."
    
    return (
        f"From: {email['from']}\n"
        f"To: {email['to']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email['date']}\n"
        f"Labels: {', '.join(email['labels'])}\n\n"
        f"Body:\n{email['body']}"
    )


@tool
def summarize_emails(days_back: int = 1) -> str:
    """
    Generate an AI summary of recent emails.
    
    Args:
        days_back: Number of days to look back (default 1)
        
    Returns:
        Executive summary with highlights and action items
    """
    result = summarize_daily_emails(days_back=days_back)
    
    output = f"📧 Email Summary ({result['time_period']})\n"
    output += f"Total emails analyzed: {result['email_count']}\n\n"
    output += result['summary']
    
    return output


@tool
def find_priority_emails(days_back: int = 1) -> str:
    """
    Find and classify priority emails using AI.
    
    Args:
        days_back: Days to look back (default 1)
        
    Returns:
        Emails classified by priority (high/medium/low) with reasoning
    """
    result = get_priority_emails(days_back=days_back)
    
    output = f"📊 Priority Analysis ({result['total_analyzed']} emails analyzed)\n\n"
    
    if result.get("high_priority"):
        output += "🔴 HIGH PRIORITY:\n"
        for e in result["high_priority"]:
            output += f"  • {e['subject']} (from: {e['from']})\n"
        output += "\n"
    
    if result.get("medium_priority"):
        output += "🟡 MEDIUM PRIORITY:\n"
        for e in result["medium_priority"]:
            output += f"  • {e['subject']} (from: {e['from']})\n"
        output += "\n"
    
    if result.get("low_priority"):
        output += "🟢 LOW PRIORITY:\n"
        for e in result["low_priority"]:
            output += f"  • {e['subject']} (from: {e['from']})\n"
        output += "\n"
    
    output += f"Analysis: {result.get('analysis', 'N/A')}"
    
    return output


@tool
def draft_reply(email_id: str, instructions: str = "", tone: str = "professional") -> str:
    """
    Create a draft reply to an email. The draft is saved in Gmail for review.
    Uses CONTEXT-SPECIFIC writing style if available (auto-detected from email).
    
    Args:
        email_id: ID of the email to reply to
        instructions: Specific instructions for what to include in the reply
        tone: Tone of reply - "professional", "friendly", "formal", or "brief"
        
    Returns:
        Generated reply content and draft status
    """
    result = create_draft_reply(
        email_id=email_id,
        instructions=instructions,
        tone=tone,
    )
    
    if result["status"] == "error":
        return f"Error: {result['error']}"
    
    # Build context notes
    context_notes = []
    if result.get("used_style_profile"):
        style_ctx = result.get("style_context", "default")
        context_notes.append(f"style: {style_ctx} ✨")
    if result.get("used_memory"):
        context_notes.append("memory 🧠")
    
    context_str = f" (using {', '.join(context_notes)})" if context_notes else ""
    detected = result.get("detected_context", "unknown")
    
    return (
        f"✅ Draft Created{context_str}!\n\n"
        f"Context detected: {detected}\n"
        f"Reply to: {result['reply_to']}\n"
        f"Subject: {result['subject']}\n\n"
        f"Generated Reply:\n{result['generated_reply']}\n\n"
        f"📝 {result['message']}"
    )


@tool
def preview_reply(email_id: str, instructions: str = "", tone: str = "professional") -> str:
    """
    Preview a reply without saving as draft. Use this to iterate before creating the actual draft.
    Uses CONTEXT-SPECIFIC writing style if available.
    
    Args:
        email_id: ID of the email to reply to
        instructions: Specific instructions for the reply
        tone: Tone - "professional", "friendly", "formal", or "brief"
        
    Returns:
        Preview of the generated reply
    """
    result = generate_reply_preview(
        email_id=email_id,
        instructions=instructions,
        tone=tone,
    )
    
    if result["status"] == "error":
        return f"Error: {result['error']}"
    
    # Build context notes
    context_notes = []
    if result.get("used_style_profile"):
        style_ctx = result.get("style_context", "default")
        context_notes.append(f"style: {style_ctx} ✨")
    if result.get("used_memory"):
        context_notes.append("memory 🧠")
    
    context_str = f" (using {', '.join(context_notes)})" if context_notes else ""
    detected = result.get("detected_context", "unknown")
    
    return (
        f"📝 Reply Preview{context_str} (NOT saved as draft)\n\n"
        f"Context detected: {detected}\n"
        f"To: {result['original_from']}\n"
        f"Re: {result['original_subject']}\n"
        f"Tone: {result['tone']}\n\n"
        f"--- Generated Reply ---\n{result['generated_reply']}\n"
        f"--- End ---\n\n"
        f"💡 {result['note']}"
    )


@tool
def respond_to_email_text(email_content: str, sender_name: str = "Someone", instructions: str = "", tone: str = "professional") -> str:
    """
    Generate a reply to email text provided directly by the user.
    Use this when the user pastes an email or asks "how would I respond to this?".
    Does NOT require the email to exist in Gmail.
    
    IMPORTANT: This tool will first analyze the email for questions that need user input.
    If questions are found, it returns them instead of generating a reply.
    Once the user provides answers, call again with their answers in 'instructions'.
    
    Args:
        email_content: The email text to respond to (provided by user in the conversation)
        sender_name: Name of the sender if known (for greeting)
        instructions: User's answers/preferences for drafting the reply (e.g., "cost is ok, no new insurance")
        tone: Tone - "professional", "friendly", "formal", or "brief"
        
    Returns:
        Either questions needing user input OR generated reply
    """
    result = compose_reply_to_text(
        email_content=email_content,
        sender_name=sender_name,
        instructions=instructions,
        tone=tone,
    )
    
    # If questions need to be answered first
    if result.get("status") == "needs_input":
        questions_list = []
        for i, q in enumerate(result.get("questions", []), 1):
            questions_list.append(f"{i}. {q['question']}\n   Context: {q['context']}")
        
        return (
            f"❓ Before I can draft a reply, I need your input:\n\n"
            f"{chr(10).join(questions_list)}\n\n"
            f"Please answer these questions, then I'll draft a reply matching your style."
        )
    
    # Build context notes
    context_notes = []
    if result.get("used_style_profile"):
        style_ctx = result.get("style_context", "default")
        context_notes.append(f"style: {style_ctx} ✨")
    if result.get("used_memory"):
        context_notes.append("memory 🧠")
    
    context_str = f" (using {', '.join(context_notes)})" if context_notes else ""
    detected = result.get("detected_context", "unknown")
    
    return (
        f"📝 Here's how you could respond{context_str}:\n\n"
        f"Context detected: {detected}\n\n"
        f"--- Suggested Reply ---\n{result['generated_reply']}\n"
        f"--- End ---\n\n"
        f"💡 {result['note']}"
    )


@tool
def write_new_email(to_email: str, subject: str, context: str, tone: str = "friendly") -> str:
    """
    Compose a NEW email (not a reply) to someone.
    Use this when user wants to email someone without an existing thread.
    
    Args:
        to_email: Recipient's email address
        subject: Email subject line
        context: What the email should say / purpose / situation
        tone: Tone - "professional", "friendly", "formal", or "brief"
        
    Returns:
        Generated email content
    """
    result = compose_new_email(
        to_email=to_email,
        subject=subject,
        context=context,
        tone=tone,
    )
    
    # Build context notes
    context_notes = []
    if result.get("used_style_profile"):
        style_ctx = result.get("style_context", "default")
        context_notes.append(f"style: {style_ctx} ✨")
    if result.get("used_memory"):
        context_notes.append("memory 🧠")
    
    context_str = f" (using {', '.join(context_notes)})" if context_notes else ""
    detected = result.get("detected_context", "unknown")
    
    return (
        f"📧 Here's your email{context_str}:\n\n"
        f"Context detected: {detected}\n"
        f"**To:** {result['to']}\n"
        f"**Subject:** {result['subject']}\n\n"
        f"--- Email Body ---\n{result['body']}\n"
        f"--- End ---\n\n"
        f"💡 Would you like me to save this as a draft in Gmail?"
    )


@tool
def save_new_email_as_draft(to_email: str, subject: str, body: str) -> str:
    """
    Save a NEW email as a draft in Gmail.
    Use after write_new_email when user approves the content.
    
    Args:
        to_email: Recipient's email address
        subject: Email subject line
        body: Email body content (from write_new_email)
        
    Returns:
        Confirmation with draft ID
    """
    result = create_new_draft(
        to_email=to_email,
        subject=subject,
        body=body,
    )
    
    if result["status"] == "error":
        return f"❌ Error: {result.get('error', 'Unknown error')}"
    
    return (
        f"✅ Draft saved!\n\n"
        f"**To:** {result['to']}\n"
        f"**Subject:** {result['subject']}\n"
        f"**Draft ID:** {result['draft_id']}\n\n"
        f"📝 {result['message']}"
    )


@tool
def learn_my_style(num_emails: int = 50) -> str:
    """
    Analyze sent emails to learn the user's writing style.
    Creates CONTEXT-SPECIFIC style profiles (professional, personal, recruiters, etc.)
    Encrypted and stored locally.
    Future drafts will automatically use the appropriate style for each context.
    
    Args:
        num_emails: Number of sent emails to analyze (default 50 for better categorization)
        
    Returns:
        Status and summary of learned styles per context
    """
    result = analyze_contextual_styles(num_emails=num_emails)
    
    if result["status"] == "error":
        return f"❌ {result['error']}"
    
    if result["status"] == "warning":
        return f"⚠️ {result['message']}\n\n📊 Email distribution: {result.get('email_distribution', {})}"
    
    # Format categories learned
    categories = result.get("categories_learned", [])
    categories_str = "\n".join(f"  • {cat}" for cat in categories)
    
    # Format email distribution
    dist = result.get("email_distribution", {})
    dist_str = ", ".join(f"{k}: {v}" for k, v in dist.items() if v > 0)
    
    return (
        f"✅ {result['message']}\n\n"
        f"📊 **Context-Specific Styles Learned:**\n{categories_str}\n\n"
        f"📬 **Email Distribution:**\n  {dist_str}\n\n"
        f"🔐 Encrypted and stored locally at ~/.gmail_agent/\n\n"
        f"🎯 Future drafts will automatically use the right style for each context!"
    )


@tool
def check_style_status() -> str:
    """
    Check if a writing style profile exists and show its detailed characteristics.
    Shows context-specific styles if available (professional, personal, recruiters, etc.)
    
    Returns:
        Detailed status of the style profile including all learned patterns per context
    """
    result = get_contextual_style_status()
    
    if not result["has_profile"]:
        return f"📭 No Style Profile Found\n\n{result['message']}"
    
    version = result.get("version", "unknown")
    
    # Check if contextual styles (v2.0)
    if "2.0" in version:
        output = (
            f"✅ **Context-Specific Style Profile Active**\n\n"
            f"📊 **Metadata:**\n"
            f"  • Version: {version}\n"
            f"  • Total emails analyzed: {result.get('total_emails_analyzed', 'N/A')}\n"
            f"  • Created: {result.get('created_at', 'N/A')}\n"
            f"  • Contexts learned: {', '.join(result.get('contexts_learned', []))}\n\n"
        )
        
        # Show each context style
        styles = result.get("styles", {})
        
        if "default" in styles:
            default = styles["default"]
            output += (
                f"🌐 **Default Style:**\n"
                f"  • Tone: {default.get('tone', 'N/A')}\n"
                f"  • Formality: {default.get('formality_level', 'N/A')}/10\n"
                f"  • Based on: {default.get('email_count', 'N/A')} emails\n\n"
            )
        
        # Context-specific styles
        for context, style in styles.items():
            if context == "default":
                continue
            
            greetings = ", ".join(style.get("greeting_patterns", [])) or "—"
            signoffs = ", ".join(style.get("signoff_patterns", [])) or "—"
            
            output += (
                f"📁 **{context.replace('_', ' ').title()}:**\n"
                f"  • Tone: {style.get('tone', 'N/A')}\n"
                f"  • Formality: {style.get('formality_level', 'N/A')}/10\n"
                f"  • Greetings: {greetings}\n"
                f"  • Sign-offs: {signoffs}\n"
                f"  • Based on: {style.get('email_count', 'N/A')} emails\n\n"
            )
        
        output += (
            f"---\n"
            f"🎯 Drafts will automatically use the appropriate style based on email context.\n"
            f"Use 'forget my style' to reset."
        )
        return output
    
    # Old v1.0 single style format
    greetings = ", ".join(result.get("greeting_patterns", [])) or "Not detected"
    signoffs = ", ".join(result.get("signoff_patterns", [])) or "Not detected"
    
    return (
        f"⚠️ **Single Style Profile (v1.0)**\n\n"
        f"📊 **Metadata:**\n"
        f"  • Emails analyzed: {result.get('emails_analyzed', 'N/A')}\n"
        f"  • Created: {result.get('created_at', 'N/A')}\n\n"
        f"🎭 **Style:**\n"
        f"  • Tone: {result.get('tone', 'N/A')}\n"
        f"  • Formality: {result.get('formality_level', 'N/A')}/10\n\n"
        f"💡 {result.get('note', 'Run learn my style again to upgrade to contextual styles.')}"
    )


@tool
def forget_my_style() -> str:
    """
    Delete the learned writing style profile.
    Future drafts will use default style instead.
    
    Returns:
        Confirmation of deletion
    """
    result = clear_style_profile()
    
    if result["status"] == "success":
        return f"🗑️ {result['message']}"
    
    return f"ℹ️ {result['message']}"


# ============== MEMORY TOOLS ==============

@tool
def remember_this(fact_key: str, fact_value: str, context: str) -> str:
    """
    Store a fact or preference about the user for future reference.
    Use this when the user shares information worth remembering.
    
    Args:
        fact_key: Short identifier (e.g., "insurance_status", "cost_preference")
        fact_value: The fact to remember (e.g., "No dental insurance")
        context: Category - one of: medical_health, professional_work, recruiters_jobs,
                 financial_banking, family_friends, services_utilities, shopping_retail,
                 travel, education, legal, other
    
    Returns:
        Confirmation of storage
    """
    result = store_user_fact(fact_key, fact_value, context)
    
    promoted_note = ""
    if result.get("promoted_to_global"):
        promoted_note = "\n🌟 This fact now applies globally (seen in 3+ contexts)!"
    
    return (
        f"✅ Remembered for {result['context']}:\n"
        f"  {fact_key}: {fact_value}{promoted_note}"
    )


@tool
def recall_facts(context: str = "", sender: str = "", subject: str = "") -> str:
    """
    Retrieve stored facts relevant to the current context.
    Can auto-detect context from email details.
    
    Args:
        context: Explicit context category (optional)
        sender: Email sender for auto-detection (optional)
        subject: Email subject for auto-detection (optional)
        
    Returns:
        Relevant facts for the context
    """
    result = retrieve_relevant_facts(
        context=context,
        sender=sender,
        subject=subject,
    )
    
    if not result["facts"]:
        return f"📭 No facts stored for context: {result['detected_context']}"
    
    facts_list = "\n".join(
        f"  • {key}: {value}" 
        for key, value in result["facts"].items()
    )
    
    return (
        f"📋 Facts for {result['detected_context']}:\n{facts_list}\n\n"
        f"({result['fact_count']} facts found)"
    )


@tool
def show_all_memories() -> str:
    """
    Show all stored facts and preferences organized by context.
    
    Returns:
        All stored memories
    """
    result = list_all_memories()
    
    output = "🧠 **Your Stored Memories**\n\n"
    
    # Global facts
    if result["facts"]["global"]:
        output += "🌍 **Global (apply everywhere):**\n"
        for key, value in result["facts"]["global"].items():
            output += f"  • {key}: {value}\n"
        output += "\n"
    
    # Context-specific facts
    if result["facts"]["by_context"]:
        output += "📁 **By Context:**\n"
        for context, facts in result["facts"]["by_context"].items():
            output += f"\n  **{context}:**\n"
            for key, value in facts.items():
                output += f"    • {key}: {value}\n"
    
    # Stats
    stats = result["stats"]
    output += (
        f"\n---\n"
        f"📊 Total: {stats['global_facts_count']} global, "
        f"{stats['contextual_facts_count']} contextual facts"
    )
    
    return output


@tool
def forget_memory(fact_key: str, context: str = "") -> str:
    """
    Remove a stored fact from memory.
    
    Args:
        fact_key: Key of the fact to forget
        context: If specified, only forget from this context.
                 If empty, forget from all contexts.
    
    Returns:
        Confirmation
    """
    result = forget_fact(fact_key, context if context else None)
    
    if result["status"] == "not_found":
        return f"❓ No fact found with key: {fact_key}"
    
    locations = ", ".join(result["removed_from"])
    return f"🗑️ Forgot '{fact_key}' from: {locations}"


@tool
def clear_all_memories() -> str:
    """
    Delete ALL stored memories. Use with caution!
    
    Returns:
        Confirmation
    """
    result = forget_all_memories()
    return f"🗑️ {result['message']}"


@tool
def check_if_should_remember(user_message: str) -> str:
    """
    Analyze user's message to see if anything should be remembered.
    Call this after user provides answers to questions.
    
    Args:
        user_message: What the user said
        
    Returns:
        Suggestions for what to remember, if anything
    """
    result = should_remember_this(user_message)
    
    if not result.get("should_remember") or not result.get("facts"):
        return "📝 Nothing particularly worth remembering from this."
    
    output = "💡 **I noticed some things worth remembering:**\n\n"
    for fact in result["facts"]:
        output += (
            f"• **{fact['key']}**: {fact['value']}\n"
            f"  Context: {fact['context']}\n"
            f"  Reason: {fact['reason']}\n\n"
        )
    
    if result.get("ask_user"):
        output += f"\n{result.get('suggestion_message', 'Would you like me to remember these?')}"
    
    return output


@tool
def auto_remember(user_message: str, email_context: str = "") -> str:
    """
    AUTOMATICALLY extract and save facts from user's message.
    Call this IMMEDIATELY after user shares ANY information that could be useful for future emails.
    
    This is the PRIMARY tool for building memory - use it proactively!
    
    Args:
        user_message: What the user just said (their answer, preference, status, etc.)
        email_context: Brief context about the email being discussed
        
    Returns:
        Confirmation of what was saved
    """
    result = auto_extract_and_save_facts(user_message, email_context)
    
    if result["status"] == "error":
        return f"⚠️ Could not process: {result.get('error', 'Unknown error')}"
    
    if result["status"] == "no_facts" or not result.get("saved"):
        return ""  # Return empty string - nothing worth noting
    
    # Build confirmation message
    saved_items = []
    for fact in result["saved"]:
        promoted = " (now global! 🌍)" if fact.get("promoted_to_global") else ""
        saved_items.append(f"  • {fact['key']}: {fact['value']} [{fact['context']}]{promoted}")
    
    return (
        f"✅ Noted for future reference:\n"
        f"{chr(10).join(saved_items)}"
    )


# All available tools
GMAIL_TOOLS = [
    fetch_emails,
    get_email_details,
    summarize_emails,
    find_priority_emails,
    draft_reply,
    preview_reply,
    respond_to_email_text,
    write_new_email,
    save_new_email_as_draft,
    learn_my_style,
    check_style_status,
    forget_my_style,
    # Memory tools
    remember_this,
    recall_facts,
    show_all_memories,
    forget_memory,
    clear_all_memories,
    check_if_should_remember,
    auto_remember,
    # User Network tools (contact management)
    *USER_NETWORK_TOOLS,
    # Profile Discovery tools
    *PROFILE_DISCOVERY_TOOLS,
]


SYSTEM_PROMPT = """You are a helpful email assistant with access to the user's Gmail account, persistent memory, and a User Network database.

You can help with:
1. Reading and searching emails
2. Summarizing recent emails
3. Identifying priority/urgent emails
4. Drafting replies to emails in Gmail
5. Responding to email text the user pastes/provides directly
6. Learning CONTEXT-SPECIFIC writing styles (professional, personal, recruiters, etc.)
7. Automatically remembering facts and preferences about the user
8. Managing a User Network - storing contacts, relationships, and interests
9. Discovering user profile and contacts from emails

Guidelines for Email:
- Always confirm before creating drafts in Gmail
- When showing emails, include the ID so the user can reference them
- Be concise but informative
- Draft replies are saved as drafts, NOT sent automatically
- When user asks "how would I respond to [email text]", use respond_to_email_text (NOT draft_reply)
- Before drafting replies to emails with questions, identify unknowns and ask user first
- To find emails BY RECIPIENT (sent emails): use fetch_emails with query="to:email@example.com"
- To find emails BY SENDER (received emails): use fetch_emails with query="from:email@example.com"
- To find ONLY SENT emails: use fetch_emails with query="in:sent"
- Combine queries like: query="to:friend@gmail.com in:sent" for sent emails to a specific person

Guidelines for Writing Style:
- Style profiles are CONTEXT-SPECIFIC: the agent learns different styles for different types of emails
- Contexts: professional_work, recruiters_jobs, family_friends, medical_health, services_utilities, etc.
- When drafting, the system auto-detects the email context and uses the appropriate style
- Encourage users to run 'learn my style' to enable personalized context-specific drafts
- Style is learned from sent emails - categorized automatically by analyzing recipients and content

Guidelines for Memory - AUTOMATIC FACT STORAGE:
- AUTOMATICALLY identify and store important facts when user shares them - DO NOT wait to be asked
- After user provides ANY information (answers, preferences, constraints, status), IMMEDIATELY:
  1. Identify facts worth remembering for similar future situations
  2. Call auto_remember to store them with the appropriate context
  3. Briefly mention what you remembered (e.g., "✅ Noted for future medical emails")
- Use recall_facts BEFORE drafting replies to get relevant stored context
- Facts are stored BY CONTEXT (medical, professional, family, etc.)
- A fact becomes global after appearing in 3+ different contexts

What to AUTOMATICALLY remember:
- Status information: "I don't have insurance", "I'm job hunting"
- Preferences: "I prefer afternoon meetings", "Don't share my time preferences"
- Constraints: "$230 is too expensive", "I prefer to reschedule"
- Patterns: How user wants certain types of emails handled

What NOT to remember:
- One-time specific details (specific dates, one-off decisions)
- Information that changes frequently
- Sensitive PII (SSN, credit cards, etc.)

Context Categories: medical_health, professional_work, recruiters_jobs, financial_banking, family_friends, services_utilities, shopping_retail, travel, education, legal, other

Guidelines for User Network:
- The User Network stores contacts (people), relationships between them, and their interests
- Use profile discovery tools to set up the user's profile from their emails
- When user mentions a person (family, colleague, friend), check if they're in the network
- When user shares info about someone, add/update them in the network
- Interests help with gift suggestions, conversation topics, etc.

Available tools: 
- Email Reading: fetch_emails, get_email_details, summarize_emails, find_priority_emails
- Replying to EXISTING emails: draft_reply (needs email_id), preview_reply, respond_to_email_text (for pasted email text)
- Writing NEW emails: write_new_email (compose to an email address), save_new_email_as_draft
- Style: learn_my_style (learns context-specific styles!), check_style_status, forget_my_style  
- Memory: auto_remember (USE THIS PROACTIVELY!), remember_this, recall_facts, show_all_memories, forget_memory, clear_all_memories
- Profile Discovery: analyze_emails_for_profile (extract user profile from emails), update_discovered_profile (apply user corrections), save_discovered_profile (save after review)
- User Network READ: get_contact_by_relationship, get_contact_by_name, get_interests_by_relationship, get_interests_by_name, find_related_person, search_contacts
- User Network WRITE: add_new_contact, update_contact_info, add_relationship, add_interest_to_contact, deactivate_contact

Style Command Variations (all map to the same tools):
- "learn my style", "learn my styles", "analyze my style", "update my style" → learn_my_style
- "show my style", "check style", "what's my style", "show styles" → check_style_status
- "forget my style", "reset style", "clear style" → forget_my_style

Profile Discovery Command Variations:
- "set up my profile", "create my profile", "set up my profile from emails", "who am I" → analyze_emails_for_profile
- User provides corrections ("my name is X", "Y is my friend", "Z is a recruiter") → update_discovered_profile FIRST
- "save my profile", "confirm profile" → save_discovered_profile (AFTER update_discovered_profile if corrections were given)

IMPORTANT Profile Discovery Flow:
1. analyze_emails_for_profile → shows discovered info
2. User provides corrections/additions about themselves or contacts
3. update_discovered_profile → apply ALL corrections before saving
4. save_discovered_profile → save everything at once (DO NOT call add_relationship separately!)

User Network Command Variations:
- "who is my [sister/brother/etc]", "what's my [mom's] phone number" → get_contact_by_relationship
- "what does [name] like", "[name]'s interests" → get_interests_by_name
- "add [name] as my [relationship]", "remember [name]" → add_new_contact

CRITICAL RULES:
1. After user provides information, ALWAYS call auto_remember to save relevant facts automatically
2. When user wants to EMAIL SOMEONE (gives an email address), use write_new_email - NOT draft_reply
3. draft_reply is ONLY for replying to emails that exist in the inbox (requires email_id, NOT email address)
4. An EMAIL ADDRESS is NOT an email_id - never pass an email address to draft_reply
5. When drafting replies, mention which style context was used (e.g., "using professional_work style")
6. Style profiles are auto-refreshed on startup if stale (>7 days old or too few emails)
7. USER NETWORK: When user mentions a NEW person (family, friend, colleague), AUTOMATICALLY add them using add_new_contact
8. USER NETWORK: When user shares INFO about someone (phone, email, job, interests), AUTOMATICALLY update using update_contact_info or add_interest_to_contact
9. USER NETWORK: When discovering relationships between people, add them using add_relationship
10. USER NETWORK: Before asking "who is X?", first check the User Network using get_contact_by_name or get_contact_by_relationship"""


def create_gmail_agent(model: str = "gpt-4o-mini"):
    """
    Create the Gmail agent with all tools.
    
    Args:
        model: OpenAI model to use (default gpt-4o-mini)
        
    Returns:
        Configured LangGraph agent
    """
    # Initialize LLM
    llm = ChatOpenAI(model=model, temperature=0)
    
    # Create agent using LangGraph
    agent = create_react_agent(
        model=llm,
        tools=GMAIL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )
    
    return agent


class GmailAssistant:
    """
    High-level Gmail assistant with conversation memory.
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.agent = create_gmail_agent(model=model)
        self.chat_history: list = []
    
    def chat(self, message: str) -> str:
        """
        Send a message to the assistant.
        
        Args:
            message: User's message/request
            
        Returns:
            Assistant's response
        """
        # Build messages list with history
        messages = self.chat_history + [HumanMessage(content=message)]
        
        # Invoke agent
        response = self.agent.invoke({"messages": messages})
        
        # Extract the final response
        response_messages = response.get("messages", [])
        final_response = ""
        for msg in reversed(response_messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_response = msg.content
                break
        
        # Update history
        self.chat_history.append(HumanMessage(content=message))
        self.chat_history.append(AIMessage(content=final_response))
        
        return final_response
    
    def clear_history(self):
        """Clear conversation history."""
        self.chat_history = []

