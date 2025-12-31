"""
Yennifer Agent - Core AI Assistant

Web-based AI assistant with Google Workspace integration.
"""

import asyncio
import os
from typing import Optional
from uuid import UUID

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .workspace_tools import WORKSPACE_TOOLS, set_current_user
from .memory_tools import MEMORY_TOOLS, set_memory_user, build_user_context
from .entity_resolution_tools import (
    ENTITY_RESOLUTION_TOOLS, 
    set_entity_resolution_user,
    COSTLY_ACTIONS,
)
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

## PROACTIVE DATA COLLECTION (CRITICAL)

NEVER say "I couldn't find X" or "There are no records of X". Instead, be PROACTIVE:

1. **Person not found?** → CREATE them with create_person_in_network
2. **Important date not found?** → CREATE it with save_important_date_for_person
3. **Relationship not found?** → CREATE it with create_person_in_network or add_relationship_between_persons
4. **Missing info?** → ASK the user for details to personalize, then SAVE it

Example: "My brother's best friend's birthday is in 2 days, what should I gift him?"
1. find_person_by_relationship("brother") → found brother (ID: xxx)
2. Check if brother has a "best friend" relationship → not found
3. ASK: "What's your brother's best friend's name?"
4. User: "His name is Farhan"
5. create_person_in_network("Farhan", "friend") → new person created
6. add_relationship_between_persons(brother_id, farhan_id, "best friend")
7. save_important_date_for_person(farhan_id, "Farhan's Birthday", date, "birthday")
8. ASK: "What are Farhan's interests or hobbies? This will help me suggest better gifts."
9. User: "He loves go-karting and F1"
10. save_person_interest(farhan_id, "go-karting", 90, "hobby")
11. save_person_interest(farhan_id, "F1", 90, "sport")
12. NOW provide gift suggestions based on ALL THREE factors:
    - INTERESTS: F1, go-karting → racing experiences, F1 merchandise
    - RELATIONSHIP: brother's best friend → casual/fun gift is appropriate
    - OCCASION: birthday → celebratory gift

Example: "What should I get my coworker for her 30th work anniversary?"
Gift factors:
- INTERESTS: (ask if unknown) → personalize the gift
- RELATIONSHIP: coworker → professional but thoughtful
- OCCASION: 30th work anniversary → milestone celebration, recognize achievement

## RELATIONSHIP HANDLING

When the user mentions a relationship (wife, husband, mother, cousin, etc.):
1. FIRST use find_person_by_relationship to look up the person
2. If NOT found → use create_person_in_network to add them
3. Ask for their name if creating new person

Example: "My wife loves gardening"
1. find_person_by_relationship("wife")
2. If found → get person_id, save interest
3. If NOT found → "What's your wife's name?" → create_person_in_network(name, "wife")
4. save_person_interest(person_id, "gardening", 90, "hobby")

## INTERESTS: USER vs PERSON

IMPORTANT: User's interests and other people's interests are SEPARATE.
- save_user_interest → for the USER's own interests ("I love hiking")
- save_person_interest → for someone else's interests ("My wife loves gardening")

## GIFT SUGGESTIONS FLOW (ALL THREE FACTORS)

When user asks for gift ideas, gather and consider ALL THREE:

**FACTOR 1: INTERESTS** (What does the person like?)
- get_person_interests(person_id)
- If none → ASK: "What does [name] enjoy? Any hobbies or interests?"
- SAVE interests for future reference

**FACTOR 2: RELATIONSHIP** (How close? Formal or casual?)
- Brother's friend → casual, fun gift
- Coworker → professional, appropriate for work
- Wife → romantic, personal, thoughtful
- Boss → respectful, not too personal

**FACTOR 3: OCCASION** (What are we celebrating?)
- Birthday → fun, personal celebration
- Graduation → achievement, future-focused
- Work anniversary → professional milestone
- Wedding anniversary → romantic, memorable

**Gift Suggestion Formula:**
1. Gather all three factors
2. Combine them for personalized suggestions:
   - "For your coworker's 30th work anniversary, considering she loves gardening..."
   - "For your brother's best friend's birthday, since he's into F1..."
3. Tailor formality and budget to the relationship
4. Tailor theme to the occasion
5. Personalize with their specific interests

## CALENDAR EVENTS

- FIRST call get_current_datetime before creating any events
- Use ISO 8601 format: "YYYY-MM-DDTHH:MM:SS"
- NEVER use dates from the past
- For events with people by name, use lookup_contact_email first

## EMAILS

- Summarize email content clearly
- When sending to someone by name, use lookup_contact_email first
- Confirm recipient and content before sending

## DATA TOOLS SUMMARY

**People:**
- find_person_by_relationship → look up family/friends
- create_person_in_network → ADD new person + their relationship to user
- add_relationship_between_persons → link two existing people

**Interests:**
- save_user_interest → USER's interests
- save_person_interest → a CONTACT's interests
- get_user_interests / get_person_interests → retrieve interests

**Dates:**
- get_upcoming_important_dates → check upcoming events
- save_important_date_for_person → ADD new date for a person
- get_important_dates_for_person → dates for specific person

**Memories:**
- save_user_memory → facts about the user
- get_user_memories → retrieve user facts

**Notes about people:**
- save_person_note → freeform notes about a contact (travel plans, preferences, reminders)
- get_person_notes → retrieve notes about someone
- get_upcoming_person_notes → see notes with upcoming dates (visits, events)

## NOTES USAGE

When user mentions temporal info about someone, save it as a note:
- "My nephew Raman is coming to Toronto next week" → save_person_note with category='travel', related_date, is_time_sensitive=True
- "My mom prefers window seats" → save_person_note with category='preference'
- "Frank owes me $50" → save_person_note with category='reminder'

Notes with dates are surfaced when relevant (close to the date).

ALWAYS save information the user provides. Build their network over time.

## ENTITY RESOLUTION (CRITICAL - READ CAREFULLY)

### When User Mentions Someone by Name:
1. ALWAYS call find_person_candidates FIRST before any action
2. Based on results:
   - **0 matches**: Ask if user wants to add them to network
   - **1 match (confidence ≥90%)**: Use that person (but confirm for costly actions)
   - **1 match (confidence <90%)**: Ask user to confirm: "Is this [name], your [relationship]?"
   - **2+ matches**: Present all options with distinguishing info, ask user to choose

### Disambiguation Format (Multiple Matches):
"Which [name] do you mean?
1. **[Name]** (your nephew) - Toronto, has phone
2. **[Name]** (colleague) - at Google, has email
3. **[Name]** (friend) - ⚠️ no contact info"

### COSTLY ACTIONS - ALWAYS CONFIRM
For these actions, ALWAYS ask user for confirmation even with 100% confidence:
- Sending messages (SMS, WhatsApp)
- Sending emails
- Making phone calls
- Creating calendar events with attendees
- Sending gifts/flowers
- Making purchases/bookings

Example: "I'll message Frank your nephew at +1-416-xxx-xxxx about being late. Should I proceed?"

### Creating New Contacts - CRITICAL RULES

**RULE 1: NEVER ask for info the user didn't mention**
- User says "my nephew Raman is coming to Toronto" → Save: Raman, nephew, Toronto
- DO NOT ask for: age, interests, birthday, phone, email, last name, etc.
- Only save what the user explicitly provided

**RULE 2: Create immediately, confirm briefly**
1. Extract info from message (name, relationship, location, age, interests - whatever was mentioned)
2. Call create_person_in_network IMMEDIATELY with extracted info
3. Respond with brief confirmation: "Added Raman (your nephew) - noted he's coming to Toronto!"
4. If user gives age: Pass `age` parameter directly (system computes birth_year)

**RULE 3: Ask for contact info ONLY when an action requires it**
- User says "message Raman" → Check if phone exists → If placeholder: "What's Raman's phone number?"
- User says "email Raman" → Check if email exists → If placeholder: "What's Raman's email?"
- DO NOT ask for phone/email proactively when just adding someone

**Good examples:**
User: "My nephew Raman is coming to Toronto soon"
Agent: "Got it! Added Raman, your nephew. I've noted he's coming to Toronto. Let me know if you need anything else!"

User: "My uncle Ram is 50 and loves cashmere sweaters"  
Agent: "Added Ram, your uncle (age 50), to your contacts with his interest in cashmere sweaters!"

**Bad examples (NEVER DO THIS):**
User: "My nephew Raman is coming to Toronto"
Agent: "Could you provide Raman's age and interests?" ← WRONG - user didn't mention these

User: "My friend Sarah works at Google"
Agent: "What's Sarah's phone number and birthday?" ← WRONG - just save what was given

### Multiple Relationships
One person can have multiple relationships to user (Frank can be BOTH cousin AND coworker):
- Don't create duplicate records
- Add additional relationships using existing person record

### Contact Info Required for Actions
Before messaging/calling someone:
1. Call check_person_has_contact to verify real contact info exists
2. If placeholder: "I don't have [name]'s phone number. What is it?"
3. Save the real contact info with update_person_contact
4. Then proceed with the action

### Learning from Corrections
When user corrects disambiguation ("No, the other one"):
- Use correct person for current action
- Call confirm_person_selection to boost their relevance for future"""


class YenniferAssistant:
    """
    Web-based Yennifer assistant with Google Workspace tools.
    Uses per-user OAuth tokens for API access.
    """
    
    def __init__(
        self, 
        model: str = "gpt-4o-mini", 
        user_email: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ):
        """
        Initialize the assistant.
        
        Args:
            model: OpenAI model to use
            user_email: User's email for Google API access
            user_id: User's UUID for memory/personalization
        """
        self.model = model
        self.user_email = user_email
        self.user_id = user_id
        self.chat_history = []
        self._user_context = ""  # Cached user context
        
        # Initialize LLM with API key from settings
        settings = get_settings()
        self._llm = ChatOpenAI(
            model=model, 
            temperature=0.7,
            api_key=settings.openai_api_key,
        )
        
        # Combine all tools: workspace + memory + entity resolution
        all_tools = WORKSPACE_TOOLS + MEMORY_TOOLS + ENTITY_RESOLUTION_TOOLS
        
        # Create agent with all tools
        self._agent = create_react_agent(
            self._llm,
            all_tools,
        )
    
    def set_user(self, email: str, user_id: Optional[UUID] = None):
        """Set the user email and ID for API access."""
        self.user_email = email
        self.user_id = user_id
        set_current_user(email)
        if user_id:
            set_memory_user(user_id)
    
    async def load_user_context(self):
        """Load personalized user context for the system prompt."""
        if self.user_id:
            self._user_context = await build_user_context(self.user_id)
    
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
        
        # Set current user for all tools
        set_current_user(self.user_email)
        if self.user_id:
            set_memory_user(self.user_id)
            set_entity_resolution_user(str(self.user_id))
        
        # Build system prompt with user context
        full_system_prompt = SYSTEM_PROMPT
        if self._user_context:
            full_system_prompt += "\n" + self._user_context
        
        # Build messages with system prompt and history
        messages = [SystemMessage(content=full_system_prompt)]
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
