"""
Priority Email Detection Tools

Use AI to identify and classify high-priority emails.
"""

import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from .read_emails import read_emails


def get_priority_emails(
    max_emails: int = 20,
    days_back: int = 1,
) -> dict:
    """
    Identify priority emails using AI classification.
    
    Analyzes recent emails and classifies them by priority level
    based on sender, subject, content, and urgency indicators.
    
    Args:
        max_emails: Maximum emails to analyze
        days_back: Days to look back
        
    Returns:
        Dict with high, medium, low priority emails and reasoning
    """
    # Fetch recent emails
    emails = read_emails(max_results=max_emails, days_back=days_back)
    
    if not emails:
        return {
            "high_priority": [],
            "medium_priority": [],
            "low_priority": [],
            "analysis": "No emails found in the specified time period.",
        }
    
    # Prepare emails for analysis
    email_summaries = []
    for i, email in enumerate(emails):
        email_summaries.append({
            "index": i,
            "id": email["id"],
            "from": email["from"],
            "subject": email["subject"],
            "snippet": email["snippet"][:200],
            "is_unread": email["is_unread"],
            "date": email["date"],
        })
    
    # Create priority analysis prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an email priority classifier. Analyze emails and classify them by urgency.

Priority Criteria:
- HIGH: Urgent deadlines, important people (boss, clients), time-sensitive requests, emergencies
- MEDIUM: Work-related tasks, meeting requests, important but not urgent
- LOW: Newsletters, promotions, FYI emails, automated notifications

Return JSON in this exact format:
{{
    "high_priority": [list of email indices],
    "medium_priority": [list of email indices],
    "low_priority": [list of email indices],
    "reasoning": "Brief explanation of your classification logic"
}}"""),
        ("user", """Classify these emails by priority:

{emails}

Return ONLY valid JSON."""),
    ])
    
    # Initialize LLM with JSON mode
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
    )
    
    # Generate classification
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "emails": str(email_summaries),
        })
    except Exception as e:
        # Fallback if JSON parsing fails
        return {
            "high_priority": [],
            "medium_priority": [],
            "low_priority": emails,
            "analysis": f"Classification failed: {str(e)}",
            "error": True,
        }
    
    # Map indices back to email data
    def get_emails_by_indices(indices):
        return [
            {
                "id": emails[i]["id"],
                "from": emails[i]["from"],
                "subject": emails[i]["subject"],
                "date": emails[i]["date"],
                "is_unread": emails[i]["is_unread"],
            }
            for i in indices if i < len(emails)
        ]
    
    return {
        "high_priority": get_emails_by_indices(result.get("high_priority", [])),
        "medium_priority": get_emails_by_indices(result.get("medium_priority", [])),
        "low_priority": get_emails_by_indices(result.get("low_priority", [])),
        "analysis": result.get("reasoning", ""),
        "total_analyzed": len(emails),
    }



