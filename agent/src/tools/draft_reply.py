"""
Draft Reply Creation Tools

Generate AI-powered draft replies to emails.
Uses learned style profile when available for personalized replies.
Supports context-specific styles (professional, personal, recruiters, etc.)
Uses stored memory/facts for context-aware responses.
"""

import base64
from email.mime.text import MIMEText
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..auth import get_gmail_service
from ..memory import get_facts_for_context, detect_context_from_email
from ..pii import mask_pii
from .read_emails import get_email_by_id
from .learn_style import get_style_for_context


def _get_memory_context(sender: str = "", subject: str = "", body: str = "") -> tuple[str, str]:
    """
    Get relevant stored facts for the email context.
    
    Returns:
        Tuple of (memory_context_string, detected_context)
    """
    # Detect context from email
    context = detect_context_from_email(sender, subject, body)
    
    # Get relevant facts
    facts = get_facts_for_context(context, include_global=True)
    
    if not facts:
        return "", context
    
    facts_text = "\n".join(f"- {key}: {value}" for key, value in facts.items())
    
    memory_str = f"\n\nRelevant facts about the user for this context ({context}):\n{facts_text}"
    return memory_str, context


def _get_style_instructions(context: str = "default") -> tuple[str, str]:
    """
    Load style profile for a specific context and format as instructions.
    
    Args:
        context: Context category (e.g., "professional_work", "family_friends")
                 Use "default" for general style.
    
    Returns:
        Tuple of (style_instructions_string, style_context_used)
    """
    profile = get_style_for_context(context)
    style_context_used = context
    
    # If no context-specific style found, try default
    if not profile and context != "default":
        profile = get_style_for_context("default")
        style_context_used = "default"
    
    if not profile:
        return "", ""
    
    instructions = []
    
    if profile.get("tone"):
        instructions.append(f"- Match this tone: {profile['tone']}")
    
    if profile.get("greeting_patterns"):
        greetings = ", ".join(profile["greeting_patterns"][:3])
        instructions.append(f"- Use greeting style like: {greetings}")
    
    if profile.get("signoff_patterns"):
        signoffs = ", ".join(profile["signoff_patterns"][:3])
        instructions.append(f"- Use sign-off style like: {signoffs}")
    
    if profile.get("common_phrases"):
        phrases = ", ".join(f'"{p}"' for p in profile["common_phrases"][:5])
        instructions.append(f"- Naturally incorporate phrases like: {phrases}")
    
    if profile.get("formality_level"):
        level = profile["formality_level"]
        if level <= 3:
            instructions.append("- Keep it very casual and informal")
        elif level <= 5:
            instructions.append("- Keep it conversational but respectful")
        elif level <= 7:
            instructions.append("- Maintain a professional but approachable tone")
        else:
            instructions.append("- Keep it formal and professional")
    
    if profile.get("typical_length"):
        instructions.append(f"- Email length should be: {profile['typical_length']}")
    
    if profile.get("uses_emojis"):
        instructions.append("- Feel free to use emojis where appropriate")
    
    if profile.get("overall_personality"):
        instructions.append(f"- Writing personality: {profile['overall_personality']}")
    
    if instructions:
        return "\n\nIMPORTANT - Match the user's personal writing style:\n" + "\n".join(instructions), style_context_used
    
    return "", ""


def create_draft_reply(
    email_id: str,
    instructions: str = "",
    tone: str = "professional",
) -> dict:
    """
    Create a draft reply to an email.
    
    Generates an AI-powered reply and saves it as a Gmail draft.
    Human-in-the-loop: Draft is NOT sent automatically.
    Uses context-specific style when available.
    
    Args:
        email_id: ID of the email to reply to
        instructions: Optional specific instructions for the reply
        tone: Tone of reply - "professional", "friendly", "formal", "brief"
        
    Returns:
        Dict with draft_id, generated reply content, and status
    """
    # Fetch the original email
    original = get_email_by_id(email_id)
    
    if not original:
        return {
            "status": "error",
            "error": "Email not found",
        }
    
    # Detect email context and get memory
    memory_context, detected_context = _get_memory_context(
        sender=original["from"],
        subject=original["subject"],
        body=original["body"],
    )
    using_memory = bool(memory_context)
    
    # Get personalized style instructions for this context
    style_instructions, style_context = _get_style_instructions(detected_context)
    using_style = bool(style_instructions)
    
    # Create reply generation prompt
    tone_instructions = {
        "professional": "professional and courteous",
        "friendly": "warm and friendly while remaining professional",
        "formal": "formal and business-like",
        "brief": "concise and to the point, minimal pleasantries",
    }
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an email assistant helping draft replies.

Guidelines:
- Write a {tone} reply
- Address the key points from the original email
- Be helpful and clear
- Keep it appropriately concise
- Do NOT include subject line - just the email body
- Do NOT include placeholder text like [Your Name] - end naturally
- Do NOT make assumptions - only use information explicitly provided or from stored facts{style_instructions}{memory_context}"""),
        ("user", """Draft a reply to this email:

From: {sender}
Subject: {subject}
Content:
{body}

{extra_instructions}

Write ONLY the reply body text."""),
    ])
    
    # Initialize LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
    )
    
    # Generate reply
    chain = prompt | llm
    response = chain.invoke({
        "tone": tone_instructions.get(tone, tone_instructions["professional"]),
        "style_instructions": style_instructions,
        "memory_context": memory_context,
        "sender": original["from"],
        "subject": original["subject"],
        "body": original["body"][:3000],  # Limit context
        "extra_instructions": f"Additional instructions: {instructions}" if instructions else "",
    })
    
    reply_text = response.content
    
    # Create the draft in Gmail
    service = get_gmail_service()
    
    # Build email message
    message = MIMEText(reply_text)
    
    # Extract reply-to address
    sender_email = original["from"]
    if "<" in sender_email:
        sender_email = sender_email.split("<")[1].split(">")[0]
    
    message["to"] = sender_email
    message["subject"] = f"Re: {original['subject']}"
    
    # Encode message
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    # Create draft with thread reference
    draft_body = {
        "message": {
            "raw": raw,
            "threadId": original["thread_id"],
        }
    }
    
    draft = service.users().drafts().create(
        userId="me",
        body=draft_body
    ).execute()
    
    return {
        "status": "success",
        "draft_id": draft["id"],
        "reply_to": original["from"],
        "subject": f"Re: {original['subject']}",
        "generated_reply": reply_text,
        "used_style_profile": using_style,
        "style_context": style_context if using_style else None,
        "used_memory": using_memory,
        "detected_context": detected_context,
        "message": "Draft created successfully. Review in Gmail before sending.",
    }


def generate_reply_preview(
    email_id: str,
    instructions: str = "",
    tone: str = "professional",
) -> dict:
    """
    Generate a reply preview WITHOUT creating a draft.
    
    Use this to preview/iterate on replies before saving as draft.
    Uses context-specific style profile when available.
    
    Args:
        email_id: ID of the email to reply to
        instructions: Optional specific instructions
        tone: Tone of reply
        
    Returns:
        Dict with generated reply for review
    """
    original = get_email_by_id(email_id)
    
    if not original:
        return {
            "status": "error",
            "error": "Email not found",
        }
    
    # Detect email context and get memory
    memory_context, detected_context = _get_memory_context(
        sender=original["from"],
        subject=original["subject"],
        body=original["body"],
    )
    using_memory = bool(memory_context)
    
    # Get personalized style instructions for this context
    style_instructions, style_context = _get_style_instructions(detected_context)
    using_style = bool(style_instructions)
    
    tone_instructions = {
        "professional": "professional and courteous",
        "friendly": "warm and friendly while remaining professional",
        "formal": "formal and business-like",
        "brief": "concise and to the point, minimal pleasantries",
    }
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an email assistant helping draft replies.
Write a {tone} reply that addresses the key points.
Be helpful, clear, and appropriately concise.
Do NOT include subject line or placeholders.
Do NOT make assumptions - only use information explicitly provided or from stored facts.{style_instructions}{memory_context}"""),
        ("user", """Draft a reply to:

From: {sender}
Subject: {subject}
Content:
{body}

{extra_instructions}"""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    chain = prompt | llm
    
    response = chain.invoke({
        "tone": tone_instructions.get(tone, tone_instructions["professional"]),
        "style_instructions": style_instructions,
        "memory_context": memory_context,
        "sender": original["from"],
        "subject": original["subject"],
        "body": original["body"][:3000],
        "extra_instructions": f"Instructions: {instructions}" if instructions else "",
    })
    
    return {
        "status": "preview",
        "original_from": original["from"],
        "original_subject": original["subject"],
        "generated_reply": response.content,
        "tone": tone,
        "used_style_profile": using_style,
        "style_context": style_context if using_style else None,
        "used_memory": using_memory,
        "detected_context": detected_context,
        "note": "This is a preview. Use create_draft_reply() to save as draft.",
    }


def analyze_email_for_questions(email_content: str) -> dict:
    """
    Analyze an email to identify questions or decisions the user needs to make
    before a reply can be drafted.
    
    Args:
        email_content: The email text to analyze
        
    Returns:
        Dict with questions that need user input
    """
    from langchain_core.output_parsers import JsonOutputParser
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an email analyst. Analyze the email and identify any questions or decisions 
the recipient needs to make before responding.

Look for:
- Direct questions asked by the sender
- Requests for confirmation or decisions
- Options presented that require choosing
- Information requests
- Anything that requires the recipient's input/opinion/decision

Return a JSON object:
{{
    "has_questions": true/false,
    "questions": [
        {{
            "question": "The question or decision needed",
            "context": "Brief context from the email"
        }}
    ],
    "can_auto_reply": true/false,
    "reason": "Why questions need answering OR why auto-reply is fine"
}}

If the email is purely informational with no questions, set has_questions to false and can_auto_reply to true."""),
        ("user", """Analyze this email for questions that need the recipient's input:

{email}

Return ONLY valid JSON."""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({"email": email_content})
        return result
    except Exception:
        return {
            "has_questions": False,
            "questions": [],
            "can_auto_reply": True,
            "reason": "Could not analyze email",
        }


def compose_reply_to_text(
    email_content: str,
    sender_name: str = "Someone",
    instructions: str = "",
    tone: str = "professional",
    user_answers: dict = None,
) -> dict:
    """
    Generate a reply to arbitrary email text provided by the user.
    
    This does NOT require an email to exist in Gmail - useful for:
    - Hypothetical "how would I respond to this?" questions
    - Drafting replies to emails the user pastes directly
    - Practice/example responses
    
    IMPORTANT: First analyzes for questions that need user input.
    Uses learned style profile and stored memory when available.
    
    Args:
        email_content: The email text to respond to (provided by user)
        sender_name: Name of the sender (optional, for greeting)
        instructions: Specific instructions for the reply
        tone: Tone - "professional", "friendly", "formal", or "brief"
        user_answers: Dict of answers to questions (if previously identified)
        
    Returns:
        Dict with either questions to ask OR generated reply
    """
    # Mask PII before processing
    masked_content = mask_pii(email_content)
    
    # First, analyze for questions if no answers provided
    if not user_answers and not instructions:
        analysis = analyze_email_for_questions(masked_content)
        
        if analysis.get("has_questions") and analysis.get("questions"):
            return {
                "status": "needs_input",
                "questions": analysis["questions"],
                "message": "Before I can draft a reply, I need your input on these questions:",
                "reason": analysis.get("reason", ""),
            }
    
    # Build context from user answers if provided
    answer_context = ""
    if user_answers:
        answer_parts = [f"- {k}: {v}" for k, v in user_answers.items()]
        answer_context = "\n\nUser's answers to include in reply:\n" + "\n".join(answer_parts)
    
    # Get memory context (stored facts relevant to this email)
    memory_context, detected_context = _get_memory_context(
        sender=sender_name,
        subject="",
        body=email_content,
    )
    using_memory = bool(memory_context)
    
    # Get personalized style instructions for this context
    style_instructions, style_context = _get_style_instructions(detected_context)
    using_style = bool(style_instructions)
    
    tone_instructions = {
        "professional": "professional and courteous",
        "friendly": "warm and friendly while remaining professional",
        "formal": "formal and business-like",
        "brief": "concise and to the point, minimal pleasantries",
    }
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an email assistant helping draft replies.
Write a {tone} reply that addresses the key points.
Be helpful, clear, and appropriately concise.
Do NOT include subject line or placeholders like [Your Name].
Do NOT make assumptions - only use information explicitly provided or from stored facts.{style_instructions}{memory_context}"""),
        ("user", """Draft a reply to this email:

From: {sender}
Content:
{body}

{extra_instructions}{answer_context}

Write ONLY the reply body text."""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    chain = prompt | llm
    
    extra = f"Instructions: {instructions}" if instructions else ""
    
    response = chain.invoke({
        "tone": tone_instructions.get(tone, tone_instructions["professional"]),
        "style_instructions": style_instructions,
        "memory_context": memory_context,
        "sender": sender_name,
        "body": masked_content[:3000],
        "extra_instructions": extra,
        "answer_context": answer_context,
    })
    
    return {
        "status": "success",
        "generated_reply": response.content,
        "tone": tone,
        "used_style_profile": using_style,
        "style_context": style_context if using_style else None,
        "used_memory": using_memory,
        "detected_context": detected_context,
        "note": "This is a sample reply. Copy/paste or modify as needed.",
    }


def compose_new_email(
    to_email: str,
    subject: str,
    context: str,
    tone: str = "friendly",
) -> dict:
    """
    Compose a NEW email (not a reply) to someone.
    
    Use this when user wants to write to someone without an existing email thread.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        context: What the email should say / the situation
        tone: Tone - "professional", "friendly", "formal", or "brief"
        
    Returns:
        Dict with generated email content
    """
    # Get memory context and detected context
    memory_context, detected_context = _get_memory_context(
        sender=to_email,  # Recipient for context detection
        subject=subject,
        body=context,
    )
    using_memory = bool(memory_context)
    
    # Get style instructions for this context
    style_instructions, style_context = _get_style_instructions(detected_context)
    using_style = bool(style_instructions)
    
    tone_instructions = {
        "professional": "professional and courteous",
        "friendly": "warm and friendly",
        "formal": "formal and business-like",
        "brief": "concise and to the point",
    }
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an email assistant helping compose emails.
Write a {tone} email based on the context provided.
Be helpful, clear, and appropriately concise.
Do NOT include the To/From/Subject headers - just the email body.
Do NOT include placeholders like [Your Name] - end naturally.{style_instructions}{memory_context}"""),
        ("user", """Compose an email with:

To: {to_email}
Subject: {subject}
Context/Purpose: {context}

Write ONLY the email body text."""),
    ])
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    chain = prompt | llm
    
    response = chain.invoke({
        "tone": tone_instructions.get(tone, tone_instructions["friendly"]),
        "style_instructions": style_instructions,
        "memory_context": memory_context,
        "to_email": to_email,
        "subject": subject,
        "context": context,
    })
    
    return {
        "status": "success",
        "to": to_email,
        "subject": subject,
        "body": response.content,
        "used_style_profile": using_style,
        "style_context": style_context if using_style else None,
        "used_memory": using_memory,
        "detected_context": detected_context,
    }


def create_new_draft(
    to_email: str,
    subject: str,
    body: str,
) -> dict:
    """
    Create a draft of a NEW email (not a reply) in Gmail.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body content
        
    Returns:
        Dict with draft_id and status
    """
    service = get_gmail_service()
    
    # Build email message
    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = subject
    
    # Encode message
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    # Create draft
    draft_body = {
        "message": {
            "raw": raw,
        }
    }
    
    draft = service.users().drafts().create(
        userId="me",
        body=draft_body
    ).execute()
    
    return {
        "status": "success",
        "draft_id": draft["id"],
        "to": to_email,
        "subject": subject,
        "message": "Draft created successfully. Review in Gmail before sending.",
    }

