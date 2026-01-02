import { useState, useEffect, useRef } from 'react';
import ChatMessage from '../components/ChatMessage';
import { sendMessage, getChatHistory, setChatHistory, clearChatHistory, type ChatMessage as ChatMessageType } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const STORAGE_KEY = 'yennifer_chat_history';

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

export default function ChatPage() {
  const { user } = useAuth();
  const storageKey = `${STORAGE_KEY}_${user?.email || 'default'}`;
  
  const [messages, setMessages] = useState<(ChatMessageType & { timestamp?: string })[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load chat history - server first, then localStorage fallback
  // This enables cross-device persistence
  useEffect(() => {
    async function loadHistory() {
      setIsLoadingHistory(true);
      
      try {
        // Try to fetch from server (database-backed, cross-device)
        const serverHistory = await getChatHistory();
        
        if (serverHistory && serverHistory.length > 0) {
          // Server has history - use it (add timestamps for display)
          const messagesWithTimestamps = serverHistory.map(msg => ({
            ...msg,
            timestamp: undefined, // Server messages don't have timestamps stored
          }));
          setMessages(messagesWithTimestamps);
          
          // Clear localStorage since server is now source of truth
          localStorage.removeItem(storageKey);
          console.log(`Loaded ${serverHistory.length} messages from server`);
        } else {
          // Server has no history - check localStorage for migration
          const saved = localStorage.getItem(storageKey);
          if (saved) {
            try {
              const localHistory = JSON.parse(saved);
              if (localHistory.length > 0) {
                setMessages(localHistory);
                
                // Migrate localStorage to server
                const toMigrate: ChatMessageType[] = localHistory.map((m: ChatMessageType & { timestamp?: string }) => ({
                  role: m.role,
                  content: m.content,
                }));
                await setChatHistory(toMigrate);
                console.log(`Migrated ${localHistory.length} messages from localStorage to server`);
                
                // Clear localStorage after successful migration
                localStorage.removeItem(storageKey);
              }
            } catch (e) {
              console.error('Failed to parse/migrate local chat history:', e);
            }
          }
        }
      } catch (error) {
        console.error('Failed to fetch chat history from server:', error);
        
        // Fallback to localStorage on server error
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          try {
            setMessages(JSON.parse(saved));
          } catch (e) {
            console.error('Failed to parse local chat history:', e);
          }
        }
      } finally {
        setIsLoadingHistory(false);
      }
    }
    
    loadHistory();
  }, [storageKey]);

  // Note: We no longer save to localStorage - server is the source of truth
  // Messages are persisted to the server in real-time via sendMessage API

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;

    const userMessage = input.trim();
    setInput('');
    
    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
    
    // Add user message
    const newUserMessage: ChatMessageType & { timestamp: string } = {
      role: 'user',
      content: userMessage,
      timestamp: formatTime(new Date()),
    };
    setMessages((prev) => [...prev, newUserMessage]);
    
    // Show thinking indicator
    setIsThinking(true);

    try {
      // Send to API
      const response = await sendMessage(userMessage);
      
      // Add assistant response
      const assistantMessage: ChatMessageType & { timestamp: string } = {
        role: 'assistant',
        content: response,
        timestamp: formatTime(new Date()),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      // Add error message
      const errorMessage: ChatMessageType & { timestamp: string } = {
        role: 'assistant',
        content: `I'm sorry, I encountered an error: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.`,
        timestamp: formatTime(new Date()),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsThinking(false);
      inputRef.current?.focus();
    }
  };

  const handleClearHistory = async () => {
    if (confirm('Are you sure you want to clear the chat history?')) {
      setMessages([]);
      localStorage.removeItem(storageKey);
      
      // Clear from server as well
      try {
        await clearChatHistory();
        console.log('Chat history cleared from server');
      } catch (error) {
        console.error('Failed to clear chat history from server:', error);
      }
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header - hidden on mobile since Layout shows a header */}
      <header className="hidden md:flex bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 px-4 lg:px-6 py-3 lg:py-4 items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-lg lg:text-xl font-semibold text-gray-900 dark:text-gray-100">Chat with Yennifer</h1>
        </div>
        <div className="flex items-center gap-3 lg:gap-4">
          <button
            onClick={handleClearHistory}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 whitespace-nowrap"
          >
            Clear history
          </button>
          <div className="w-8 h-8 lg:w-9 lg:h-9 bg-yennifer-600 rounded-full flex items-center justify-center shrink-0">
            <span className="text-white text-sm font-bold">U</span>
          </div>
        </div>
      </header>

      {/* Mobile sub-header */}
      <div className="md:hidden bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100">Chat</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={handleClearHistory}
            className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          >
            Clear
          </button>
          <div className="w-7 h-7 bg-yennifer-600 rounded-full flex items-center justify-center">
            <span className="text-white text-xs font-bold">U</span>
          </div>
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="max-w-4xl mx-auto px-3 py-4 sm:px-4 sm:py-5 md:p-6">
          {/* Assistant header - compact on mobile */}
          <div className="flex items-center gap-2 sm:gap-3 mb-4 sm:mb-6 pb-3 sm:pb-4 border-b border-gray-100 dark:border-zinc-800">
            <div className="w-8 h-8 sm:w-10 sm:h-10 bg-yennifer-700 rounded-full flex items-center justify-center shrink-0">
              <span className="text-white font-bold text-sm sm:text-base">Y</span>
            </div>
            <div className="min-w-0">
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm sm:text-base">Yennifer</h2>
              <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 truncate">Your AI Executive Assistant</p>
            </div>
          </div>

          {/* Messages */}
          <div className="space-y-4 sm:space-y-6">
            {isLoadingHistory ? (
              <div className="flex items-center justify-center py-8">
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                  <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span className="text-sm">Loading conversation...</span>
                </div>
              </div>
            ) : messages.length === 0 ? (
              <ChatMessage
                role="assistant"
                content="Hello! I'm Yennifer, your personal assistant. How can I help you today?"
                timestamp={formatTime(new Date())}
              />
            ) : (
              messages.map((message, index) => (
                <ChatMessage
                  key={index}
                  role={message.role}
                  content={message.content}
                  timestamp={message.timestamp}
                />
              ))
            )}
            
            {/* Thinking indicator */}
            {isThinking && (
              <ChatMessage role="assistant" content="" isThinking />
            )}
            
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      {/* Input area */}
      <div className="bg-white dark:bg-zinc-900 border-t border-gray-200 dark:border-zinc-800 p-3 sm:p-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:pb-[max(1rem,env(safe-area-inset-bottom))] shrink-0">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={handleSubmit} className="flex items-end gap-2 sm:gap-3">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                // Auto-resize textarea
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
              }}
              onKeyDown={(e) => {
                // Submit on Enter (without Shift)
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (input.trim() && !isThinking) {
                    handleSubmit(e);
                  }
                }
              }}
              placeholder="Ask Yennifer anything..."
              disabled={isThinking}
              rows={1}
              className="flex-1 min-w-0 px-3 sm:px-4 py-2.5 sm:py-3 text-sm sm:text-base border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 rounded-2xl focus:outline-none focus:ring-2 focus:ring-yennifer-500 focus:border-transparent disabled:bg-gray-50 dark:disabled:bg-zinc-900 disabled:text-gray-500 dark:disabled:text-gray-500 resize-none overflow-y-auto"
              style={{ maxHeight: '200px' }}
            />
            <button
              type="submit"
              disabled={!input.trim() || isThinking}
              className="px-4 sm:px-6 py-2.5 sm:py-3 bg-yennifer-700 text-white rounded-full font-medium text-sm sm:text-base hover:bg-yennifer-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0 self-end"
            >
              Send
            </button>
          </form>
        </div>
      </div>

      {/* Help button (floating) - adjusted position for mobile */}
      <button className="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] sm:bottom-24 right-4 sm:right-6 w-9 h-9 sm:w-10 sm:h-10 bg-gray-800 dark:bg-zinc-700 text-white rounded-full flex items-center justify-center shadow-lg hover:bg-gray-700 dark:hover:bg-zinc-600 transition-colors z-30 text-sm sm:text-base">
        ?
      </button>
    </div>
  );
}
