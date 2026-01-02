# PII Masking V2: Complete LLM Boundary Coverage

## Executive Summary

**Problem**: The current PII masking implementation only covers tool outputs. PII can enter the LLM through 4 additional channels that are currently unprotected:

| PII Source | Currently Masked? | Risk Level |
|------------|-------------------|------------|
| Tool outputs (current turn) | ✅ Yes | - |
| **User input (HumanMessage)** | ❌ **NO** | 🔴 Critical |
| **AIMessage from chat history** | ❌ **NO** | 🔴 Critical |
| **ToolMessage from chat history** | ❌ **NO** | 🔴 Critical |
| **Tool call args in chat history** | ❌ **NO** | 🟡 Medium |

**Impact**: 
- OpenAI's safety filters reject PII in user input (current Issue #1)
- PII from previous conversations is sent unmasked to OpenAI
- Cross-session PII leakage when history is restored from database

**Solution**: Implement comprehensive PII masking at the **LLM boundary** - mask all content BEFORE it enters the LLM, unmask the response BEFORE returning to user.

**Estimated Effort**: 2-3 days
**Risk Level**: Medium (modifies message flow, requires careful testing)
**Priority**: Critical

---

## Architecture: LLM Boundary Masking

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER SPACE                                     │
│                        (sees real PII values)                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM BOUNDARY                                       │
│                    ┌──────────────────────────┐                             │
│                    │      mask_for_llm()      │ ◄─── Entry Point            │
│                    └──────────────────────────┘                             │
│                                    │                                         │
│    ┌───────────────────────────────┼───────────────────────────────┐        │
│    │                               │                               │        │
│    ▼                               ▼                               ▼        │
│ ┌─────────────┐           ┌─────────────────┐            ┌──────────────┐   │
│ │ User Input  │           │  Chat History   │            │ Tool Results │   │
│ │ (current)   │           │  (from DB)      │            │ (current)    │   │
│ └─────────────┘           └─────────────────┘            └──────────────┘   │
│       │                           │                             │           │
│       │ mask_pii()                │ mask_pii()                  │ already   │
│       ▼                           ▼                             │ masked    │
│ ┌─────────────┐           ┌─────────────────┐                   │           │
│ │[SSN_1] sent │           │Previous msgs    │                   │           │
│ │ to LLM      │           │with [EMAIL_1]   │                   │           │
│ └─────────────┘           └─────────────────┘                   │           │
│                                    │                             │           │
│                    ┌───────────────┴───────────────┬─────────────┘           │
│                    ▼                               ▼                         │
│           ┌─────────────────────────────────────────────┐                   │
│           │                   LLM (OpenAI)              │                   │
│           │   Sees only masked PII: [SSN_1], [EMAIL_1]  │                   │
│           └─────────────────────────────────────────────┘                   │
│                                    │                                         │
│                                    ▼                                         │
│                    ┌──────────────────────────┐                             │
│                    │     unmask_for_user()    │ ◄─── Exit Point             │
│                    └──────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER SPACE                                     │
│              Response with real PII: "Your SIN 111-222-234..."             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Single Entry Point**: All messages pass through `mask_for_llm()` before LLM
2. **Single Exit Point**: All responses pass through `unmask_for_user()` before returning
3. **Context Preservation**: PIIContext tracks mappings for the entire request lifecycle
4. **Storage Agnostic**: Database stores UNMASKED content (encrypted at rest)
5. **LLM Never Sees Raw PII**: All PII is replaced with placeholders before LLM call

---

## Design: Message Flow Changes

### Current Flow (Problematic)

```python
# chat.py - Current implementation
async def send_message(request: ChatRequest, ...):
    # 1. User message goes to agent UNMASKED
    response = session.chat(request.message)  # ❌ PII in user input
    
    # 2. Unmask response (but mappings may be incomplete)
    response = unmask_pii(response)
    
    # 3. Persist messages
    await persist_message(content=request.message)  # Raw user input
```

```python
# agent.py - Current implementation
def chat(self, message: str) -> str:
    # 1. Build messages - NO MASKING
    messages = [SystemMessage(content=full_system_prompt)]
    messages.extend(self.chat_history)  # ❌ History may contain PII
    messages.append(HumanMessage(content=message))  # ❌ User input unmasked
    
    # 2. Trim and invoke LLM
    trimmed_messages = self._trimmer.invoke(messages)
    result = self._agent.invoke({"messages": trimmed_messages})  # ❌ PII sent to OpenAI
```

### Proposed Flow

```python
# chat.py - New implementation
async def send_message(request: ChatRequest, ...):
    # 1. Restore history (if needed)
    if not session.get_history() and db_session_id:
        await restore_agent_context_from_db(session, user_id, db_session_id)
    
    # 2. Agent chat with masking handled internally
    response = session.chat(request.message)  # Masking happens inside
    
    # 3. Unmask response for user
    response = copied_ctx.run(unmask_pii, response)
    
    # 4. Persist UNMASKED messages (encrypted at rest)
    await persist_message(content=request.message)  # Store original
```

```python
# agent.py - New implementation
def chat(self, message: str) -> str:
    # 1. Mask user input BEFORE adding to messages
    masked_message = mask_pii(message)
    
    # 2. Build messages with masking
    messages = [SystemMessage(content=full_system_prompt)]
    messages.extend(self._mask_chat_history())  # ✅ Mask history
    messages.append(HumanMessage(content=masked_message))  # ✅ Masked input
    
    # 3. Trim and invoke LLM
    trimmed_messages = self._trimmer.invoke(messages)
    result = self._agent.invoke({"messages": trimmed_messages})  # ✅ Only masked PII
```

---

## Implementation Plan

### Phase 1: Core Masking Functions (Day 1 Morning)

#### 1.1 Add `mask_message_for_llm()` function

**File**: `services/yennifer_api/app/core/pii.py`

```python
def mask_message_for_llm(content: str, role: str = "user") -> str:
    """
    Mask PII in a message before sending to LLM.
    
    This is the primary entry point for LLM-bound content.
    
    Args:
        content: Message content to mask
        role: Message role ('user', 'assistant', 'tool')
              - 'user': Use FULL masking (user input may contain any PII)
              - 'assistant': Use FULL masking (previous responses may echo PII)
              - 'tool': Use FULL masking (tool results already masked, but re-check)
        
    Returns:
        Masked content safe for LLM
        
    Example:
        >>> mask_message_for_llm("My SSN is 123-45-6789")
        "My SSN is [SSN_1]"
    """
    if not content:
        return content
    
    # All roles use FULL masking at LLM boundary
    # Tool-specific FINANCIAL_ONLY masking happens at tool output level
    return mask_pii(content, mode=MaskingMode.FULL)


def mask_tool_call_args(tool_calls: List[Dict]) -> List[Dict]:
    """
    Mask PII in tool call arguments.
    
    Tool calls may contain PII that the LLM decided to use
    (e.g., "send_email(to='user@example.com')").
    
    We mask these so that:
    1. The LLM sees consistent masked values
    2. Tool implementations can resolve placeholders if needed
    
    Args:
        tool_calls: List of tool call dicts with 'name', 'args', 'id'
        
    Returns:
        Tool calls with masked arguments
    """
    if not tool_calls:
        return tool_calls
    
    masked_calls = []
    for tc in tool_calls:
        masked_tc = {
            "name": tc.get("name"),
            "id": tc.get("id"),
            "args": {},
        }
        
        # Mask string arguments
        args = tc.get("args", {})
        for key, value in args.items():
            if isinstance(value, str):
                masked_tc["args"][key] = mask_pii(value, mode=MaskingMode.FULL)
            else:
                masked_tc["args"][key] = value
        
        masked_calls.append(masked_tc)
    
    return masked_calls
```

#### 1.2 Add `mask_chat_history()` method to agent

**File**: `services/yennifer_api/app/core/agent.py`

```python
from .pii import mask_message_for_llm, mask_tool_call_args

class YenniferAssistant:
    # ... existing code ...
    
    def _mask_chat_history(self) -> List:
        """
        Mask PII in chat history before sending to LLM.
        
        This ensures that previous messages (which may contain PII
        from user input or tool results) are masked before the LLM sees them.
        
        Returns:
            List of LangChain message objects with masked content
        """
        masked_messages = []
        
        for msg in self.chat_history:
            if isinstance(msg, HumanMessage):
                # Mask user messages
                masked_content = mask_message_for_llm(msg.content, role="user")
                masked_messages.append(HumanMessage(content=masked_content))
                
            elif isinstance(msg, AIMessage):
                # Mask assistant messages (may echo PII back)
                masked_content = mask_message_for_llm(msg.content, role="assistant")
                masked_msg = AIMessage(content=masked_content)
                
                # Also mask tool_calls arguments if present
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    masked_msg.tool_calls = mask_tool_call_args(msg.tool_calls)
                
                masked_messages.append(masked_msg)
                
            elif isinstance(msg, ToolMessage):
                # Mask tool results (should already be masked, but re-check)
                masked_content = mask_message_for_llm(msg.content, role="tool")
                masked_messages.append(ToolMessage(
                    content=masked_content,
                    tool_call_id=msg.tool_call_id,
                ))
            
            else:
                # SystemMessage or unknown - pass through
                masked_messages.append(msg)
        
        return masked_messages
```

### Phase 2: Update Agent Chat Method (Day 1 Afternoon)

#### 2.1 Modify `chat()` to mask all inputs

**File**: `services/yennifer_api/app/core/agent.py`

```python
def chat(self, message: str) -> str:
    """
    Send a message to the assistant and get a response.
    
    PII Masking:
    - User input is masked before sending to LLM
    - Chat history is masked before sending to LLM
    - Tool results are masked at tool level (already implemented)
    - Response is returned with placeholders (unmasked by caller)
    
    Args:
        message: User's message/request (may contain PII)
        
    Returns:
        Assistant's response (may contain placeholders like [SSN_1])
    """
    if not self.user_email:
        return "I need to know who you are first. Please log in."
    
    # Set current user for all tools
    set_current_user(self.user_email)
    if self.user_id:
        set_memory_user(self.user_id)
        set_entity_resolution_user(str(self.user_id))
    
    # =========================================================
    # NEW: Mask user input BEFORE building messages
    # This prevents PII from reaching the LLM
    # =========================================================
    from .pii import mask_message_for_llm
    masked_message = mask_message_for_llm(message, role="user")
    
    # Build system prompt with user context
    full_system_prompt = SYSTEM_PROMPT
    if self._user_context:
        full_system_prompt += "\n" + self._user_context
    
    # Build messages with system prompt and MASKED history
    messages = [SystemMessage(content=full_system_prompt)]
    
    # =========================================================
    # NEW: Mask chat history before sending to LLM
    # =========================================================
    messages.extend(self._mask_chat_history())
    
    # Add the MASKED user message
    messages.append(HumanMessage(content=masked_message))
    
    # Trim messages to fit within token budget
    trimmed_messages = self._trimmer.invoke(messages)
    
    try:
        # Run the agent with masked messages
        result = self._agent.invoke({"messages": trimmed_messages})
        
        # Extract assistant response (contains placeholders)
        response_messages = result.get("messages", [])
        
        # Find the final response
        assistant_response = ""
        fallback_response = ""
        for msg in reversed(response_messages):
            if isinstance(msg, AIMessage) and msg.content:
                if not getattr(msg, 'tool_calls', None):
                    assistant_response = msg.content
                    break
                elif not fallback_response:
                    fallback_response = msg.content
        
        if not assistant_response:
            assistant_response = fallback_response or "I apologize, I couldn't process that request."
        
        # =========================================================
        # IMPORTANT: Store ORIGINAL (unmasked) message in history
        # The history is for context when restored from DB
        # It will be re-masked when sent to LLM next time
        # =========================================================
        self.chat_history.append(HumanMessage(content=message))  # Original, not masked
        
        # Add new messages from agent (these have masked tool results)
        new_messages = response_messages[len(trimmed_messages):]
        self.chat_history.extend(new_messages)
        
        self._last_new_messages = new_messages
        
        return assistant_response
        
    except Exception as e:
        error_msg = str(e)
        if "No Google credentials" in error_msg or "re-authenticate" in error_msg:
            return "I don't have access to your Google account."
        return f"I encountered an error: {error_msg}"
```

### Phase 3: Update Chat History Restoration (Day 1 Evening)

#### 3.1 History from DB doesn't need masking at load time

The key insight: **We don't mask when loading from DB**. Instead, we mask when sending to LLM.

This is because:
1. DB stores original content (encrypted at rest)
2. Masking at load time would lose the original values
3. Each LLM call gets fresh masking with its own PIIContext

**File**: `services/yennifer_api/app/routes/chat.py`

```python
# NO CHANGES NEEDED to restore_agent_context_from_db()
# History is loaded with original content
# Masking happens in agent._mask_chat_history() when building LLM messages
```

### Phase 4: Handle Storage Decisions (Day 2 Morning)

#### 4.1 Storage Strategy

**Decision**: Store **UNMASKED** content in database (encrypted at rest)

**Rationale**:
1. Original content is needed for audit/compliance
2. Re-masking on each LLM call ensures consistent placeholders
3. Encryption at rest protects stored data
4. Users expect to see their original messages in chat history UI

**File**: `services/yennifer_api/app/routes/chat.py`

```python
# In send_message():
# Persist ORIGINAL (unmasked) user message
await persist_message(
    user_id=user_id,
    session_id=db_session_id,
    role="user",
    content=request.message,  # Original, not masked
)

# Persist agent messages (tool results may have placeholders from tools)
# But AIMessage content should be stored as-is from LLM
for msg in new_messages:
    if isinstance(msg, AIMessage):
        await persist_message(
            user_id=user_id,
            session_id=db_session_id,
            role="assistant",
            content=msg.content,  # LLM's response (may have placeholders)
            tool_calls=...,
        )
    elif isinstance(msg, ToolMessage):
        await persist_message(
            user_id=user_id,
            session_id=db_session_id,
            role="tool",
            content=msg.content,  # Tool result (masked by tool)
            tool_call_id=msg.tool_call_id,
        )
```

### Phase 5: Update Unmask Flow (Day 2 Afternoon)

#### 5.1 Ensure response unmasking works correctly

The response from the LLM may contain placeholders like `[SSN_1]` that were in the user's input or tool results. We need to unmask these before returning to the user.

**File**: `services/yennifer_api/app/routes/chat.py`

```python
# In send_message():

# Get response from agent (contains placeholders)
response = session.chat(request.message)

# Unmask PII in response before returning to user
# Run unmask in the same context to access the mappings
response = copied_ctx.run(unmask_pii, response)

return ChatResponse(response=response, ...)
```

**Important**: The `unmask_pii()` function relies on `PIIContext` mappings. These mappings are populated during:
1. `mask_message_for_llm(user_input)` - masks user input, tracks mappings
2. `_mask_chat_history()` - masks history, tracks mappings
3. `mask_pii()` in tools - masks tool results, tracks mappings

All these happen within the same request context, so `unmask_pii()` can find all placeholders.

---

## Testing Plan

### Unit Tests

**File**: `services/yennifer_api/tests/test_pii_llm_boundary.py`

```python
"""
Tests for PII masking at LLM boundary.
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.core.pii import (
    PIIContext,
    set_pii_context,
    clear_pii_context,
    mask_pii,
    unmask_pii,
)
from app.core.agent import YenniferAssistant


class TestUserInputMasking:
    """Test that user input is masked before LLM."""
    
    def setup_method(self):
        self.ctx = PIIContext()
        set_pii_context(self.ctx)
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_ssn_in_user_input_is_masked(self):
        """SSN in user input should be masked."""
        user_input = "My SSN is 123-45-6789"
        masked = mask_pii(user_input)
        
        assert "123-45-6789" not in masked
        assert "[SSN_1]" in masked
    
    def test_sin_in_user_input_is_masked(self):
        """Canadian SIN should be masked."""
        user_input = "My SIN is 111-222-234"
        masked = mask_pii(user_input)
        
        assert "111-222-234" not in masked
        assert "[SSN_1]" in masked
    
    def test_credit_card_in_user_input_is_masked(self):
        """Credit card number should be masked."""
        user_input = "My card is 4500 1111 1111 0911"
        masked = mask_pii(user_input)
        
        assert "4500 1111 1111 0911" not in masked
        assert "[CARD_1]" in masked
    
    def test_email_in_user_input_is_masked(self):
        """Email in user input should be masked in FULL mode."""
        user_input = "Contact me at user@example.com"
        masked = mask_pii(user_input)
        
        assert "user@example.com" not in masked
        assert "[EMAIL_1]" in masked
    
    def test_multiple_pii_items_tracked(self):
        """Multiple PII items should be independently tracked."""
        user_input = "SSN: 123-45-6789, Card: 4111-1111-1111-1111"
        masked = mask_pii(user_input)
        
        assert "[SSN_1]" in masked
        assert "[CARD_1]" in masked
        
        # Context should track both
        stats = self.ctx.get_stats()
        assert stats["ssn"] == 1
        assert stats["card"] == 1


class TestUnmaskingForUser:
    """Test that response is unmasked before returning to user."""
    
    def setup_method(self):
        self.ctx = PIIContext()
        set_pii_context(self.ctx)
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_unmask_restores_email(self):
        """Unmasking should restore original email."""
        # First mask the email
        original = "Contact john@example.com"
        masked = mask_pii(original)
        
        assert "[EMAIL_1]" in masked
        
        # Now unmask
        unmasked = unmask_pii(masked)
        
        assert "john@example.com" in unmasked
    
    def test_unmask_restores_phone(self):
        """Unmasking should restore original phone."""
        original = "Call me at 555-123-4567"
        masked = mask_pii(original)
        
        unmasked = unmask_pii(masked)
        
        assert "555-123-4567" in unmasked
    
    def test_unmask_preserves_non_pii(self):
        """Non-PII content should be preserved."""
        original = "Hello, how are you?"
        masked = mask_pii(original)
        unmasked = unmask_pii(masked)
        
        assert unmasked == original
    
    def test_unmask_works_with_llm_response(self):
        """Test realistic LLM response with placeholders."""
        # Simulate: user sent SSN, LLM echoes it back
        user_input = "My SSN is 123-45-6789, please save it"
        mask_pii(user_input)  # This populates the context
        
        # LLM response references the placeholder
        llm_response = "I've noted your SSN [SSN_1]. It's stored securely."
        
        # Unmask for user
        user_response = unmask_pii(llm_response)
        
        # User should see their actual SSN in the response
        assert "123-45-6789" in user_response


class TestChatHistoryMasking:
    """Test that chat history is masked before LLM."""
    
    def setup_method(self):
        self.ctx = PIIContext()
        set_pii_context(self.ctx)
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_human_message_in_history_masked(self):
        """HumanMessage from history should be masked."""
        history = [HumanMessage(content="My SSN is 123-45-6789")]
        
        # Simulate agent._mask_chat_history()
        masked_history = []
        for msg in history:
            if isinstance(msg, HumanMessage):
                masked_content = mask_pii(msg.content)
                masked_history.append(HumanMessage(content=masked_content))
        
        assert "[SSN_1]" in masked_history[0].content
        assert "123-45-6789" not in masked_history[0].content
    
    def test_ai_message_in_history_masked(self):
        """AIMessage from history should be masked."""
        history = [AIMessage(content="Your email is john@example.com")]
        
        masked_history = []
        for msg in history:
            if isinstance(msg, AIMessage):
                masked_content = mask_pii(msg.content)
                masked_history.append(AIMessage(content=masked_content))
        
        assert "[EMAIL_1]" in masked_history[0].content
    
    def test_tool_message_in_history_masked(self):
        """ToolMessage from history should be masked."""
        history = [ToolMessage(
            content="Found email: john@example.com",
            tool_call_id="call_123"
        )]
        
        masked_history = []
        for msg in history:
            if isinstance(msg, ToolMessage):
                masked_content = mask_pii(msg.content)
                masked_history.append(ToolMessage(
                    content=masked_content,
                    tool_call_id=msg.tool_call_id
                ))
        
        assert "[EMAIL_1]" in masked_history[0].content


class TestToolCallArgsMasking:
    """Test that tool call arguments are masked."""
    
    def setup_method(self):
        self.ctx = PIIContext()
        set_pii_context(self.ctx)
    
    def teardown_method(self):
        clear_pii_context()
    
    def test_email_in_tool_args_masked(self):
        """Email in tool call args should be masked."""
        from app.core.pii import mask_tool_call_args
        
        tool_calls = [{
            "name": "send_email",
            "id": "call_123",
            "args": {
                "to": "john@example.com",
                "subject": "Test",
                "body": "Hello"
            }
        }]
        
        masked = mask_tool_call_args(tool_calls)
        
        assert "john@example.com" not in str(masked)
        assert "[EMAIL_1]" in masked[0]["args"]["to"]
    
    def test_non_string_args_preserved(self):
        """Non-string arguments should be preserved."""
        from app.core.pii import mask_tool_call_args
        
        tool_calls = [{
            "name": "read_emails",
            "id": "call_123",
            "args": {
                "max_results": 10,
                "include_spam": False
            }
        }]
        
        masked = mask_tool_call_args(tool_calls)
        
        assert masked[0]["args"]["max_results"] == 10
        assert masked[0]["args"]["include_spam"] == False
```

### Integration Tests

**File**: `services/yennifer_api/tests/test_chat_pii_integration.py`

```python
"""
Integration tests for PII masking in chat flow.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from app.core.agent import YenniferAssistant
from app.core.pii import PIIContext, set_pii_context, clear_pii_context
from app.routes.chat import send_message, ChatRequest


class TestChatPIIIntegration:
    """Integration tests for complete PII flow."""
    
    @pytest.fixture
    def agent(self):
        """Create a test agent."""
        agent = YenniferAssistant(
            model="gpt-4o-mini",
            user_email="test@example.com",
            user_id=uuid4()
        )
        return agent
    
    @pytest.fixture
    def pii_context(self):
        """Set up PII context for test."""
        ctx = PIIContext()
        set_pii_context(ctx)
        yield ctx
        clear_pii_context()
    
    @patch('app.core.agent.create_react_agent')
    def test_user_ssn_masked_before_llm(self, mock_agent, agent, pii_context):
        """SSN in user input should be masked before reaching LLM."""
        # Track what messages are sent to agent
        captured_messages = []
        
        def capture_invoke(inputs):
            captured_messages.extend(inputs.get("messages", []))
            return {"messages": [AIMessage(content="Stored your information.")]}
        
        mock_agent.return_value.invoke = capture_invoke
        
        # User sends SSN
        response = agent.chat("Store my SSN: 123-45-6789")
        
        # Find the HumanMessage that was sent to LLM
        human_msgs = [m for m in captured_messages if isinstance(m, HumanMessage)]
        
        # SSN should be masked
        assert "123-45-6789" not in human_msgs[-1].content
        assert "[SSN_1]" in human_msgs[-1].content
    
    @patch('app.core.agent.create_react_agent')
    def test_history_ssn_masked_before_llm(self, mock_agent, agent, pii_context):
        """SSN in chat history should be masked before LLM."""
        # Set up history with SSN
        agent.chat_history = [
            HumanMessage(content="My SSN is 123-45-6789"),
            AIMessage(content="Got it, stored."),
        ]
        
        captured_messages = []
        
        def capture_invoke(inputs):
            captured_messages.extend(inputs.get("messages", []))
            return {"messages": [AIMessage(content="Hello!")]}
        
        mock_agent.return_value.invoke = capture_invoke
        
        # New message
        response = agent.chat("What did I tell you?")
        
        # Find history HumanMessage
        human_msgs = [m for m in captured_messages if isinstance(m, HumanMessage)]
        
        # Historical SSN should be masked
        assert "123-45-6789" not in human_msgs[0].content
        assert "[SSN_1]" in human_msgs[0].content


class TestStorageDecisions:
    """Test that correct content is stored in database."""
    
    @pytest.mark.asyncio
    async def test_original_message_stored(self):
        """Original (unmasked) user message should be stored."""
        from app.routes.chat import persist_message
        
        with patch('app.routes.chat.get_db_pool') as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.fetchrow.return_value = {
                "id": 1,
                "session_id": uuid4(),
                "user_id": uuid4(),
                "role": "user",
                "created_at": "2024-01-01T00:00:00",
            }
            
            # Store message with PII
            await persist_message(
                user_id=uuid4(),
                session_id=uuid4(),
                role="user",
                content="My SSN is 123-45-6789",  # Original, not masked
            )
            
            # Verify original content was passed (not masked)
            # The repository will encrypt it
            call_args = mock_conn.fetchrow.call_args
            assert "123-45-6789" in str(call_args)
```

---

## QA Plan

### Manual Test Cases

#### TC-1: User Provides SSN - Should Store Securely
**Steps**:
1. Start new chat session
2. Send: "My SIN is 111-222-333"
3. Observe response

**Expected**:
- Agent responds with confirmation (NOT rejection)
- Response mentions storing securely
- No raw SSN appears in network requests (check DevTools)

**Pass Criteria**:
- [ ] Agent processes request (no "I can't process sensitive information")
- [ ] Response acknowledges storage
- [ ] SSN not visible in browser network tab

#### TC-2: User Provides Credit Card - Should Store Securely
**Steps**:
1. Start new chat session  
2. Send: "My card is 4500 1111 1111 0911"
3. Observe response

**Expected**:
- Agent processes request
- Credit card stored securely
- No rejection message

**Pass Criteria**:
- [ ] No content moderation rejection
- [ ] Card not visible in network requests

#### TC-3: Cross-Session PII - Should Be Masked in History
**Steps**:
1. Session A: Send "My email is test@secret.com"
2. Refresh page (new session, same user)
3. Session B: Send "What's my email?"
4. Observe response

**Expected**:
- Agent recalls the email correctly
- Email not sent to OpenAI in plaintext (check logs)

**Pass Criteria**:
- [ ] Email correctly returned to user
- [ ] Server logs show [EMAIL_1] sent to LLM, not raw email

#### TC-4: Tool Results with PII - Should Be Masked
**Steps**:
1. Send: "Read my latest email"
2. Observe tool call and response

**Expected**:
- Email content shown to user
- PII in email masked before LLM sees it
- User sees actual PII in response

**Pass Criteria**:
- [ ] Email content visible to user
- [ ] Server logs show masked version sent to LLM

#### TC-5: PII in Follow-up Questions
**Steps**:
1. Send: "My SSN is 123-45-6789"
2. Send: "What SSN did I tell you?"

**Expected**:
- Agent recalls SSN correctly
- SSN not sent to LLM in plaintext on second message

**Pass Criteria**:
- [ ] Correct SSN returned
- [ ] History masked in second request

### Automated Regression Tests

```bash
# Run all PII tests
pytest services/yennifer_api/tests/test_pii*.py -v

# Run with coverage
pytest services/yennifer_api/tests/test_pii*.py --cov=app.core.pii --cov-report=term-missing
```

### Load Testing

```python
# Test PII masking performance impact
import time

def test_pii_masking_performance():
    """Masking should add <10ms per message."""
    text = "Email: test@example.com, SSN: 123-45-6789, Card: 4111-1111-1111-1111"
    
    start = time.time()
    for _ in range(1000):
        mask_pii(text)
    elapsed = (time.time() - start) * 1000  # ms
    
    avg_ms = elapsed / 1000
    assert avg_ms < 10, f"Masking took {avg_ms}ms per call, expected <10ms"
```

### Log Verification

Check server logs to verify PII is masked:

```bash
# Look for PII stats in logs
grep "PII stats" /var/log/yennifer/app.log

# Should see lines like:
# PII stats after agent run: total=2, emails=1, phones=0, ssn=1, cards=0

# Should NOT see raw PII in logs
grep -E "\d{3}-\d{2}-\d{4}" /var/log/yennifer/app.log  # SSN pattern
grep -E "\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}" /var/log/yennifer/app.log  # Card pattern
```

---

## Rollout Plan

### Day 1
- [ ] Implement `mask_message_for_llm()` in `pii.py`
- [ ] Implement `mask_tool_call_args()` in `pii.py`
- [ ] Add `_mask_chat_history()` method to agent
- [ ] Update `chat()` method to mask user input
- [ ] Write unit tests for new functions

### Day 2
- [ ] Integration testing with real OpenAI calls
- [ ] Verify storage decisions (unmasked in DB)
- [ ] Add logging for debugging
- [ ] Performance testing

### Day 3
- [ ] QA manual testing (all test cases)
- [ ] Fix any issues found
- [ ] Documentation update
- [ ] Deploy to staging

### Day 4
- [ ] Staging verification
- [ ] Production deployment
- [ ] Monitor logs for issues

---

## Configuration

No new configuration needed. Uses existing `PII_MASKING_ENABLED` setting.

---

## Rollback Plan

If issues are found:

1. **Immediate**: Disable PII masking via feature flag
   ```python
   # In pii.py
   def mask_pii(text, mode=MaskingMode.FULL):
       if not settings.pii_masking_enabled:
           return text  # Bypass masking
       # ... rest of function
   ```

2. **Revert**: Git revert the PR and redeploy

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| User PII rejection rate | 0% | Count "can't process sensitive" responses |
| PII masked per request | >0 when PII present | Log analysis |
| Latency impact | <50ms | P99 latency monitoring |
| User complaints | 0 | Support tickets |

