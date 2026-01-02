-- Migration: 013_tool_message_support.sql
-- Support for persisting tool call results (ToolMessage)
--
-- This enables cross-device session continuity by storing:
-- - AIMessage tool_calls (already supported via tool_calls_encrypted)
-- - ToolMessage results linked back via tool_call_id
--
-- The tool_call_id links a ToolMessage (role='tool') back to the 
-- AIMessage that invoked it, enabling proper reconstruction of
-- the conversation flow when restoring from database.

-- Step 1: Add tool_call_id column
ALTER TABLE chat_messages 
ADD COLUMN IF NOT EXISTS tool_call_id VARCHAR(64) DEFAULT NULL;

COMMENT ON COLUMN chat_messages.tool_call_id IS 
'For role=tool messages: links back to the AIMessage tool_call that invoked this tool';

-- Step 2: Update role check constraint to allow 'tool' role
-- Drop existing constraint and recreate with 'tool' included
ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS chat_messages_role_check;

ALTER TABLE chat_messages 
ADD CONSTRAINT chat_messages_role_check 
CHECK (role IN ('user', 'assistant', 'system', 'tool'));

COMMENT ON COLUMN chat_messages.role IS 'Message role: user, assistant, system, or tool (for tool results)';

