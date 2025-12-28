import { useState, useEffect, useRef } from 'react';
import ChatMessage from '../components/ChatMessage';
import { sendMessage, type ChatMessage as ChatMessageType } from '../services/api';
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load chat history from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setMessages(parsed);
      } catch (e) {
        console.error('Failed to parse chat history:', e);
      }
    }
  }, [storageKey]);

  // Save chat history to localStorage when it changes
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem(storageKey, JSON.stringify(messages));
    }
  }, [messages, storageKey]);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;

    const userMessage = input.trim();
    setInput('');
    
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

  const handleClearHistory = () => {
    if (confirm('Are you sure you want to clear the chat history?')) {
      setMessages([]);
      localStorage.removeItem(storageKey);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-gray-900">Chat with Yennifer</h1>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={handleClearHistory}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Clear history
          </button>
          <div className="w-9 h-9 bg-yennifer-600 rounded-full flex items-center justify-center">
            <span className="text-white text-sm font-bold">U</span>
          </div>
        </div>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-6">
          {/* Assistant header */}
          <div className="flex items-center gap-3 mb-6 pb-4 border-b border-gray-100">
            <div className="w-10 h-10 bg-yennifer-700 rounded-full flex items-center justify-center">
              <span className="text-white font-bold">Y</span>
            </div>
            <div>
              <h2 className="font-semibold text-gray-900">Yennifer</h2>
              <p className="text-sm text-gray-500">Your AI Executive Assistant</p>
            </div>
          </div>

          {/* Messages */}
          <div className="space-y-6">
            {messages.length === 0 ? (
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
      <div className="bg-white border-t border-gray-200 p-4">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask Yennifer anything..."
              disabled={isThinking}
              className="flex-1 px-4 py-3 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-yennifer-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
            />
            <button
              type="submit"
              disabled={!input.trim() || isThinking}
              className="px-6 py-3 bg-yennifer-700 text-white rounded-full font-medium hover:bg-yennifer-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Send
            </button>
          </form>
        </div>
      </div>

      {/* Help button (floating) */}
      <button className="fixed bottom-24 right-6 w-10 h-10 bg-gray-800 text-white rounded-full flex items-center justify-center shadow-lg hover:bg-gray-700 transition-colors">
        ?
      </button>
    </div>
  );
}

