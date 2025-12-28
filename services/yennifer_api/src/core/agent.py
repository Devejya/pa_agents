"""
Yennifer Agent - Core AI Assistant

Wrapper around the existing gmail_agent that provides a web-friendly interface.
"""

import os
import sys
import importlib.util

# Add agent src to Python path
agent_src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../agent/src"))

# We need to set up the package structure properly for relative imports to work
# First, add the parent of agent/src to the path so 'src' can be found as a package
agent_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../agent"))
if agent_base_path not in sys.path:
    sys.path.insert(0, agent_base_path)

# Now import through the package structure
from src.gmail_agent import GmailAssistant, GMAIL_TOOLS, SYSTEM_PROMPT


class YenniferAssistant:
    """
    Web-friendly wrapper around GmailAssistant.
    Provides conversation history management suitable for web sessions.
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        """Initialize the assistant with the underlying GmailAssistant."""
        self._assistant = GmailAssistant(model=model)
    
    def chat(self, message: str) -> str:
        """
        Send a message to the assistant and get a response.
        
        Args:
            message: User's message/request
            
        Returns:
            Assistant's response
        """
        return self._assistant.chat(message)
    
    def clear_history(self):
        """Clear conversation history."""
        self._assistant.clear_history()
    
    def get_history(self) -> list[dict]:
        """
        Get chat history as a list of dicts.
        
        Returns:
            List of messages with 'role' and 'content' keys
        """
        from langchain_core.messages import HumanMessage, AIMessage
        
        history = []
        for msg in self._assistant.chat_history:
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
        from langchain_core.messages import HumanMessage, AIMessage
        
        self._assistant.chat_history = []
        for msg in history:
            if msg["role"] == "user":
                self._assistant.chat_history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                self._assistant.chat_history.append(AIMessage(content=msg["content"]))
