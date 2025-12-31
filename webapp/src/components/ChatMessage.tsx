import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ThinkingIndicator from './ThinkingIndicator';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  isThinking?: boolean;
  timestamp?: string;
}

export default function ChatMessage({ role, content, isThinking, timestamp }: ChatMessageProps) {
  const isUser = role === 'user';

  return (
    <div className={`flex gap-2 sm:gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar - smaller on mobile */}
      <div
        className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser ? 'bg-yennifer-100' : 'bg-yennifer-700'
        }`}
      >
        <span className={`text-xs sm:text-sm font-bold ${isUser ? 'text-yennifer-700' : 'text-white'}`}>
          {isUser ? 'U' : 'Y'}
        </span>
      </div>

      {/* Message bubble - wider on mobile to use more space */}
      <div className={`max-w-[85%] sm:max-w-[75%] md:max-w-[70%] ${isUser ? 'text-right' : ''}`}>
        <div
          className={`inline-block px-3 py-2 sm:px-4 sm:py-3 rounded-2xl ${
            isUser
              ? 'bg-gray-100 text-gray-900 rounded-tr-md'
              : 'bg-yennifer-50 border border-yennifer-200 text-yennifer-900 rounded-tl-md'
          }`}
        >
          {isThinking ? (
            <ThinkingIndicator />
          ) : isUser ? (
            <div className="whitespace-pre-wrap text-sm leading-relaxed break-words">{content}</div>
          ) : (
            <div className="prose prose-sm max-w-none prose-yennifer break-words">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Style links
                  a: ({ ...props }) => (
                    <a
                      {...props}
                      className="text-yennifer-600 hover:text-yennifer-800 underline break-all"
                      target="_blank"
                      rel="noopener noreferrer"
                    />
                  ),
                  // Style code blocks
                  code: ({ className, children, ...props }) => {
                    const isInline = !className;
                    return isInline ? (
                      <code
                        className="bg-yennifer-100 text-yennifer-800 px-1 py-0.5 rounded text-xs font-mono break-all"
                        {...props}
                      >
                        {children}
                      </code>
                    ) : (
                      <code
                        className={`block bg-gray-800 text-gray-100 p-2 sm:p-3 rounded-lg text-xs font-mono overflow-x-auto ${className || ''}`}
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  },
                  // Style pre blocks
                  pre: ({ children, ...props }) => (
                    <pre className="bg-gray-800 rounded-lg overflow-hidden my-2 text-xs sm:text-sm" {...props}>
                      {children}
                    </pre>
                  ),
                  // Style lists
                  ul: ({ children, ...props }) => (
                    <ul className="list-disc list-inside space-y-1 my-2 text-sm" {...props}>
                      {children}
                    </ul>
                  ),
                  ol: ({ children, ...props }) => (
                    <ol className="list-decimal list-inside space-y-1 my-2 text-sm" {...props}>
                      {children}
                    </ol>
                  ),
                  // Style paragraphs
                  p: ({ children, ...props }) => (
                    <p className="my-1 leading-relaxed text-sm" {...props}>
                      {children}
                    </p>
                  ),
                  // Style headings
                  h1: ({ children, ...props }) => (
                    <h1 className="text-base sm:text-lg font-bold mt-3 mb-1" {...props}>{children}</h1>
                  ),
                  h2: ({ children, ...props }) => (
                    <h2 className="text-sm sm:text-base font-bold mt-2 mb-1" {...props}>{children}</h2>
                  ),
                  h3: ({ children, ...props }) => (
                    <h3 className="text-sm font-bold mt-2 mb-1" {...props}>{children}</h3>
                  ),
                  // Style strong/bold
                  strong: ({ children, ...props }) => (
                    <strong className="font-semibold text-yennifer-800" {...props}>{children}</strong>
                  ),
                  // Style blockquotes
                  blockquote: ({ children, ...props }) => (
                    <blockquote 
                      className="border-l-4 border-yennifer-300 pl-2 sm:pl-3 my-2 italic text-gray-600 text-sm"
                      {...props}
                    >
                      {children}
                    </blockquote>
                  ),
                  // Style horizontal rules
                  hr: ({ ...props }) => (
                    <hr className="my-3 border-yennifer-200" {...props} />
                  ),
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          )}
        </div>
        {timestamp && (
          <p className={`text-[10px] sm:text-xs text-gray-400 mt-1 ${isUser ? 'text-right' : ''}`}>
            {timestamp}
          </p>
        )}
      </div>
    </div>
  );
}
