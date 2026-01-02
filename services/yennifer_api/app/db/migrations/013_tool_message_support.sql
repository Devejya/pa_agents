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

ALTER TABLE chat_messages 
ADD COLUMN IF NOT EXISTS tool_call_id VARCHAR(64) DEFAULT NULL;

COMMENT ON COLUMN chat_messages.tool_call_id IS 
'For role=tool messages: links back to the AIMessage tool_call that invoked this tool';

