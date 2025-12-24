"""
Email Summarization Tools

Generate AI-powered summaries of emails.
"""

import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from .read_emails import read_emails


def summarize_daily_emails(days_back: int = 1) -> dict:
    """
    Generate a summary of emails from the past day(s).
    
    Args:
        days_back: Number of days to look back (default 1)
        
    Returns:
        Dict with summary, email count, and key highlights
    """
    # Fetch recent emails
    emails = read_emails(max_results=50, days_back=days_back)
    
    if not emails:
        return {
            "summary": "No emails found in the specified time period.",
            "email_count": 0,
            "highlights": [],
        }
    
    # Prepare email content for summarization
    email_texts = []
    for i, email in enumerate(emails, 1):
        email_texts.append(
            f"Email {i}:\n"
            f"From: {email['from']}\n"
            f"Subject: {email['subject']}\n"
            f"Date: {email['date']}\n"
            f"Preview: {email['snippet']}\n"
        )
    
    all_emails_text = "\n---\n".join(email_texts)
    
    # Create summarization prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an executive assistant summarizing emails. 
Your task is to provide a concise, actionable summary of the user's recent emails.

Focus on:
1. Key messages that need attention or response
2. Important updates or information
3. Action items or deadlines mentioned
4. Group related emails by topic/sender if helpful

Be concise but don't miss important details."""),
        ("user", """Please summarize the following {count} emails from the past {days} day(s):

{emails}

Provide:
1. A brief executive summary (2-3 sentences)
2. Key highlights (bullet points)
3. Suggested action items if any"""),
    ])
    
    # Initialize LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
    )
    
    # Generate summary
    chain = prompt | llm
    response = chain.invoke({
        "count": len(emails),
        "days": days_back,
        "emails": all_emails_text,
    })
    
    return {
        "summary": response.content,
        "email_count": len(emails),
        "time_period": f"Last {days_back} day(s)",
        "emails_included": [
            {"from": e["from"], "subject": e["subject"]} 
            for e in emails
        ],
    }

