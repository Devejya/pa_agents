"""
Yennifer Agent - Core AI Assistant

Web-based AI assistant with Google Workspace integration.
"""

import os
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .workspace_tools import WORKSPACE_TOOLS, set_current_user
from .config import get_settings


SYSTEM_PROMPT = """You are Yennifer, an AI executive assistant. You help users manage their:

- **Calendar**: View, create, update, and delete events
- **Email**: Read, search, and send emails
- **Contacts**: Find and look up contact information
- **Drive**: Browse, search, create folders, and manage files
- **Sheets**: Read, write, and create spreadsheets
- **Docs**: Read, create, and modify documents
- **Slides**: View, create, and modify presentations

Be helpful, concise, and professional. When showing lists, use markdown formatting.
If a user asks about their schedule, emails, contacts, or files, use the appropriate tools.

IMPORTANT - For calendar events:
- FIRST call get_current_datetime to know today's date before creating any events
- Use ISO 8601 format for times (e.g., "YYYY-MM-DDTHH:MM:SS")
- NEVER use dates from the past - always use current or future dates
- If an event creation returns an error about past dates, call get_current_datetime and try again

For multi-step operations:
- When creating and then modifying something (event, doc, sheet, slides, folder):
  1. First create it and note the returned ID
  2. Then use that exact ID for the update/modification

For emails:
- Summarize email content clearly
- When sending emails, confirm the recipient and content before sending

Always be proactive in offering help and suggesting next steps."""


class YenniferAssistant:
    """
    Web-based Yennifer assistant with Google Workspace tools.
    Uses per-user OAuth tokens for API access.
    """
    
    def __init__(self, model: str = "gpt-4o-mini", user_email: Optional[str] = None):
        """
        Initialize the assistant.
        
        Args:
            model: OpenAI model to use
            user_email: User's email for Google API access
        """
        self.model = model
        self.user_email = user_email
        self.chat_history = []
        
        # Initialize LLM with API key from settings
        settings = get_settings()
        self._llm = ChatOpenAI(
            model=model, 
            temperature=0.7,
            api_key=settings.openai_api_key,
        )
        
        # Create agent with workspace tools
        self._agent = create_react_agent(
            self._llm,
            WORKSPACE_TOOLS,
        )
    
    def set_user(self, email: str):
        """Set the user email for API access."""
        self.user_email = email
        set_current_user(email)
    
    def chat(self, message: str) -> str:
        """
        Send a message to the assistant and get a response.
        
        Args:
            message: User's message/request
            
        Returns:
            Assistant's response
        """
        if not self.user_email:
            return "I need to know who you are first. Please log in."
        
        # Set current user for tools
        set_current_user(self.user_email)
        
        # Build messages with system prompt and history
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        messages.extend(self.chat_history)
        messages.append(HumanMessage(content=message))
        
        try:
            # Run the agent
            result = self._agent.invoke({"messages": messages})
            
            # Extract assistant response
            response_messages = result.get("messages", [])
            
            # Find the last AI message
            assistant_response = ""
            for msg in reversed(response_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    assistant_response = msg.content
                    break
            
            if not assistant_response:
                assistant_response = "I apologize, I couldn't process that request. Could you try again?"
            
            # Update chat history
            self.chat_history.append(HumanMessage(content=message))
            self.chat_history.append(AIMessage(content=assistant_response))
            
            return assistant_response
            
        except Exception as e:
            error_msg = str(e)
            if "No Google credentials" in error_msg or "re-authenticate" in error_msg:
                return "I don't have access to your Google account. Please log out and log back in to grant the necessary permissions."
            return f"I encountered an error: {error_msg}"
    
    def clear_history(self):
        """Clear conversation history."""
        self.chat_history = []
    
    def get_history(self) -> list[dict]:
        """
        Get chat history as a list of dicts.
        
        Returns:
            List of messages with 'role' and 'content' keys
        """
        history = []
        for msg in self.chat_history:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": msg.content})
        return history
    
    def set_history(self, history: list[dict]):
        """
        Set chat history from a list of dicts.
        
        Args:
            history: List of messages with 'role' and 'content' keys
        """
        self.chat_history = []
        for msg in history:
            if msg["role"] == "user":
                self.chat_history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                self.chat_history.append(AIMessage(content=msg["content"]))
