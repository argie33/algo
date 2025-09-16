/**
 * Enhanced Chat Interface - ChatGPT-like Experience
 *
 * Features:
 * - Real-time streaming responses
 * - Rich message formatting (Markdown, code blocks, tables)
 * - Message actions (copy, regenerate, feedback)
 * - Typing indicators and response metadata
 * - Code execution and interactive elements
 * - Conversation export and management
 */

import {
  Send,
  ContentCopy as Copy,
  Refresh as RotateCcw,
  ThumbUp as ThumbsUp,
  ThumbDown as ThumbsDown,
  Download,
  PlayArrow as Play,
} from "@mui/icons-material";
import { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

const CHAT_CONSTANTS = {
  DATA_PREFIX_LENGTH: 6, // 'data: '.length
  MAX_RETRIES: 3,
  RETRY_DELAY: 1000,
  STREAMING_TIMEOUT: 30000,
  MESSAGE_MAX_LENGTH: 4000,
  DEFAULT_USER_AVATAR: "U",
  DEFAULT_ASSISTANT_AVATAR: "A",
};

const EnhancedChatInterface = ({
  conversationId = "default",
  onConversationChange: _onConversationChange,
  className = "",
}) => {
  // State management
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [_currentStreamId, setCurrentStreamId] = useState(null);
  const [typingIndicator, setTypingIndicator] = useState(false);
  const [suggestions, _setSuggestions] = useState([]);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [connectionStatus, setConnectionStatus] = useState("connected");

  // Refs
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const eventSourceRef = useRef(null);
  const abortControllerRef = useRef(null);

  /**
   * Load conversation history
   */
  const loadConversationHistory = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(
        `/api/ai-assistant/conversations/${conversationId}/history`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        if (data.success && data.messages) {
          setMessages(
            (data.messages || []).map((msg) => ({
              ...msg,
              id: msg.id || `${msg.role}_${Date.now()}_${Math.random()}`,
              timestamp: new Date(msg.timestamp),
              isStreaming: false,
            }))
          );
        }
      }
    } catch (error) {
      console.error(error);
    }
  }, [conversationId]);

  /**
   * Process streaming chunk
   */
  const processStreamChunk = useCallback((chunk, messageId) => {
    switch (chunk.type) {
      case "init":
        setCurrentStreamId(chunk.streamId);
        setConnectionStatus("streaming");
        break;

      case "typing":
        setTypingIndicator(true);
        break;

      case "content":
      case "text":
        setTypingIndicator(false);
        setMessages((prev) =>
          (prev || []).map((msg) =>
            msg.id === messageId
              ? {
                  ...msg,
                  content: msg.content + chunk.content,
                  metadata: { ...msg.metadata, ...chunk.metadata },
                }
              : msg
          )
        );
        break;

      case "code":
        setMessages((prev) =>
          (prev || []).map((msg) =>
            msg.id === messageId
              ? {
                  ...msg,
                  content: msg.content + chunk.content,
                  metadata: {
                    ...msg.metadata,
                    ...chunk.metadata,
                    hasCode: true,
                  },
                }
              : msg
          )
        );
        break;

      case "tool-executing":
        setMessages((prev) =>
          (prev || []).map((msg) =>
            msg.id === messageId
              ? {
                  ...msg,
                  content: `${msg.content}\n\n*${chunk.content}*`,
                  metadata: {
                    ...msg.metadata,
                    toolsUsed: [
                      ...(msg.metadata?.toolsUsed || []),
                      chunk.metadata.tool,
                    ],
                  },
                }
              : msg
          )
        );
        break;

      case "tool-_result":
        setMessages((prev) =>
          (prev || []).map((msg) =>
            msg.id === messageId
              ? {
                  ...msg,
                  content: `${msg.content}\n\n${chunk.content}`,
                  metadata: {
                    ...msg.metadata,
                    toolResults: [
                      ...(msg.metadata?.toolResults || []),
                      chunk.metadata._result,
                    ],
                  },
                }
              : msg
          )
        );
        break;

      case "complete":
        setMessages((prev) =>
          (prev || []).map((msg) =>
            msg.id === messageId
              ? {
                  ...msg,
                  isStreaming: false,
                  metadata: { ...msg.metadata, ...chunk.metadata },
                }
              : msg
          )
        );
        setIsStreaming(false);
        setTypingIndicator(false);
        break;

      case "error":
        setMessages((prev) =>
          (prev || []).map((msg) =>
            msg.id === messageId
              ? {
                  ...msg,
                  content: chunk.content || `Error: ${chunk.error}`,
                  isStreaming: false,
                  hasError: true,
                }
              : msg
          )
        );
        setIsStreaming(false);
        setTypingIndicator(false);
        setConnectionStatus("error");
        break;

      case "stream-complete":
        setConnectionStatus("connected");
        break;

      default:
        console.warn("Unknown stream chunk type:", chunk.type);
        break;
    }
  }, []);

  /**
   * Execute code from chat message
   */
  const executeCode = useCallback(
    async (code, language) => {
      try {
        const token = localStorage.getItem("token");
        const response = await fetch("/api/ai-assistant/code/execute", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            code: code.trim(),
            language,
            conversationId,
            messageId: `exec_${Date.now()}`,
          }),
        });

        const _result = await response.json();

        if (_result.success) {
          // Add execution _result as a new assistant message
          const executionMessage = {
            id: `exec_result_${Date.now()}`,
            role: "assistant",
            content: `**Code Execution Result:**\n\n${_result.output ? `**Output:**\n\`\`\`\n${_result.output}\n\`\`\`\n\n` : ""}${_result.error ? `**Warnings:**\n\`\`\`\n${_result.error}\n\`\`\`\n\n` : ""}*Execution time: ${_result.executionTime}ms*`,
            timestamp: new Date(),
            isStreaming: false,
            metadata: {
              isCodeExecution: true,
              language,
              executionTime: _result.executionTime,
            },
          };

          setMessages((prev) => [...prev, executionMessage]);
        } else {
          // Add error message
          const errorMessage = {
            id: `execerror_${Date.now()}`,
            role: "assistant",
            content: `**Code Execution Failed:**\n\n**Error:** ${_result.error}${_result.securityViolation ? "\n\n⚠️ *Security policy violation detected*" : ""}`,
            timestamp: new Date(),
            isStreaming: false,
            hasError: true,
            metadata: {
              isCodeExecution: true,
              language,
              securityViolation: _result.securityViolation,
            },
          };

          setMessages((prev) => [...prev, errorMessage]);
        }
      } catch (error) {
        console.error(error);

        // Add error message
        const errorMessage = {
          id: `execerror_${Date.now()}`,
          role: "assistant",
          content: `**Code Execution Error:** Failed to execute code - ${error.message}`,
          timestamp: new Date(),
          isStreaming: false,
          hasError: true,
          metadata: {
            isCodeExecution: true,
            language,
          },
        };

        setMessages((prev) => [...prev, errorMessage]);
      }
    },
    [conversationId]
  );

  /**
   * Provide feedback on AI response
   */
  const provideFeedback = useCallback(
    async (messageId, type) => {
      try {
        const token = localStorage.getItem("token");
        const response = await fetch("/api/ai-assistant/feedback", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            messageId,
            conversationId,
            feedbackType: "rating",
            rating: type === "positive" ? 5 : 1,
            feedbackText:
              type === "positive" ? "Helpful response" : "Not helpful",
          }),
        });

        if (response.ok) {
          // Update message with feedback indicator
          setMessages((prev) =>
            (prev || []).map((msg) =>
              msg.id === messageId
                ? { ...msg, metadata: { ...msg.metadata, userFeedback: type } }
                : msg
            )
          );
        }
      } catch (error) {
        console.error(error);
      }
    },
    [conversationId]
  );

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessage]);

  // Load conversation history on mount
  useEffect(() => {
    loadConversationHistory();

    // Capture current ref values to avoid stale references in cleanup
    const eventSource = eventSourceRef.current;
    const abortController = abortControllerRef.current;

    return () => {
      // Cleanup event source on unmount using captured values
      if (eventSource) {
        eventSource.close();
      }
      if (abortController) {
        abortController.abort();
      }
    };
  }, [conversationId, loadConversationHistory]);

  /**
   * Send message with enhanced streaming
   */
  const sendMessage = useCallback(
    async (messageText = inputValue.trim()) => {
      if (!messageText || isStreaming) return;

      const userMessage = {
        id: `user_${Date.now()}`,
        role: "user",
        content: messageText,
        timestamp: new Date(),
        isStreaming: false,
      };

      // Add user message immediately
      setMessages((prev) => [...prev, userMessage]);
      setInputValue("");
      setIsStreaming(true);
      setTypingIndicator(true);
      setStreamingMessage("");

      // Create assistant message placeholder
      const assistantMessageId = `assistant_${Date.now()}`;
      const assistantMessage = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isStreaming: true,
        metadata: {},
      };

      setMessages((prev) => [...prev, assistantMessage]);

      try {
        const token = localStorage.getItem("token");

        // Create abort controller for this request
        abortControllerRef.current = new AbortController();

        // Start streaming request
        const response = await fetch("/api/ai-assistant/chat/stream", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            message: messageText,
            conversationId,
            options: {
              enableTypingIndicator: true,
              enableTools: true,
              personalizeResponse: true,
              includeMetadata: true,
            },
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        // Process Server-Sent Events
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(CHAT_CONSTANTS.DATA_PREFIX_LENGTH);

              if (data === "[DONE]") {
                setIsStreaming(false);
                setTypingIndicator(false);
                setCurrentStreamId(null);
                break;
              }

              try {
                const chunk = JSON.parse(data);
                processStreamChunk(chunk, assistantMessageId);
              } catch (parseError) {
                console.warn("Failed to parse stream chunk:", parseError);
              }
            }
          }
        }
      } catch (error) {
        console.error(error);

        // Update assistant message with error
        setMessages((prev) =>
          (prev || []).map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content: `I encountered an error: ${error.message}. Please try again.`,
                  isStreaming: false,
                  hasError: true,
                }
              : msg
          )
        );

        setIsStreaming(false);
        setTypingIndicator(false);
        setConnectionStatus("error");
      }
    },
    [inputValue, isStreaming, conversationId, processStreamChunk]
  );

  /**
   * Regenerate last response
   */
  const regenerateResponse = async (messageId) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch("/api/ai-assistant/chat/regenerate", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversationId,
          messageId,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          // Remove the old response and generate new one
          setMessages((prev) => prev.filter((msg) => msg.id !== messageId));
          // The streaming will be handled by the backend
        }
      }
    } catch (error) {
      console.error(error);
    }
  };

  /**
   * Copy message to clipboard
   */
  const copyMessage = async (content) => {
    try {
      await navigator.clipboard.writeText(content);
      // Could show a toast notification here
    } catch (error) {
      console.error(error);
    }
  };

  /**
   * Export conversation
   */
  const exportConversation = async (format = "json") => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(
        `/api/ai-assistant/conversations/${conversationId}/export?format=${format}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (response.ok) {
        if (format === "json") {
          const data = await response.json();
          const blob = new Blob([JSON.stringify(data, null, 2)], {
            type: "application/json",
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `conversation-${conversationId}.json`;
          a.click();
          URL.revokeObjectURL(url);
        } else {
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `conversation-${conversationId}.${format}`;
          a.click();
          URL.revokeObjectURL(url);
        }
      }
    } catch (error) {
      console.error(error);
    }
  };

  /**
   * Handle input key press
   */
  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  /**
   * Message Component
   */
  const MessageComponent = ({ message }) => {
    const isUser = message.role === "user";

    return (
      <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
        <div
          className={`max-w-[80%] ${isUser ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-900"} rounded-lg px-4 py-2 relative group`}
        >
          {/* Message Content */}
          <div className="message-content">
            {isUser ? (
              <div className="whitespace-pre-wrap">{message.content}</div>
            ) : (
              <div>
                {message.isStreaming && typingIndicator && !message.content && (
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    <div
                      className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: "0.1s" }}
                    />
                    <div
                      className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: "0.2s" }}
                    />
                  </div>
                )}

                {message.content && (
                  <ReactMarkdown
                    components={{
                      code({
                        node: _node,
                        inline,
                        className: codeClassName,
                        children,
                        ...props
                      }) {
                        const match = /language-(\w+)/.exec(
                          codeClassName || ""
                        );
                        return !inline && match ? (
                          <div className="relative">
                            <SyntaxHighlighter
                              style={vscDarkPlus}
                              language={match[1]}
                              PreTag="div"
                              {...props}
                            >
                              {String(children).replace(/\n$/, "")}
                            </SyntaxHighlighter>
                            {message.metadata?.executable && (
                              <button
                                onClick={() =>
                                  executeCode(String(children), match[1])
                                }
                                className="absolute top-2 right-2 bg-green-600 text-white px-2 py-1 rounded text-xs hover:bg-green-700"
                              >
                                <Play className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        ) : (
                          <code
                            className={`${codeClassName} bg-gray-200 px-1 py-0.5 rounded text-sm`}
                            {...props}
                          >
                            {children}
                          </code>
                        );
                      },
                    }}
                  >
                    {message.content}
                  </ReactMarkdown>
                )}
              </div>
            )}
          </div>

          {/* Message Actions */}
          {!isUser && !message.isStreaming && (
            <div className="flex items-center space-x-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => copyMessage(message.content)}
                className="p-1 hover:bg-gray-200 rounded"
                title="Copy message"
              >
                <Copy className="w-4 h-4" />
              </button>
              <button
                onClick={() => regenerateResponse(message.id)}
                className="p-1 hover:bg-gray-200 rounded"
                title="Regenerate response"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                onClick={() => provideFeedback(message.id, "positive")}
                className="p-1 hover:bg-gray-200 rounded"
                title="Good response"
              >
                <ThumbsUp className="w-4 h-4" />
              </button>
              <button
                onClick={() => provideFeedback(message.id, "negative")}
                className="p-1 hover:bg-gray-200 rounded"
                title="Bad response"
              >
                <ThumbsDown className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Streaming indicator */}
          {message.isStreaming && (
            <div className="flex items-center space-x-2 mt-2 text-xs text-gray-500">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span>AI is typing...</span>
            </div>
          )}

          {/* Message metadata */}
          {message.metadata && Object.keys(message.metadata).length > 0 && (
            <div className="text-xs text-gray-500 mt-2">
              {message.metadata.toolsUsed && (
                <div>Tools used: {message.metadata.toolsUsed.join(", ")}</div>
              )}
              {message.metadata.processingTime && (
                <div>Response time: {message.metadata.processingTime}ms</div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className={`flex flex-col h-full bg-white ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-gray-50">
        <div className="flex items-center space-x-2">
          <h2 className="text-lg font-semibold">AI Assistant</h2>
          <div
            className={`w-2 h-2 rounded-full ${
              connectionStatus === "connected"
                ? "bg-green-500"
                : connectionStatus === "streaming"
                  ? "bg-yellow-500"
                  : "bg-red-500"
            }`}
          />
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => exportConversation("json")}
            className="p-2 hover:bg-gray-200 rounded"
            title="Export conversation"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {(messages?.length || 0) === 0 && (
          <div className="text-center text-gray-500 mt-8">
            <p className="text-lg mb-2">How can I help you today?</p>
            <p className="text-sm">
              Ask me about your portfolio, market analysis, or trading
              strategies.
            </p>
          </div>
        )}

        {(messages || []).map((message) => (
          <MessageComponent key={message.id} message={message} />
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t p-4">
        <div className="flex items-end space-x-2">
          <div className="flex-1">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask about your trading strategies, market analysis, or code..."
              className="w-full resize-none border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={1}
              style={{ minHeight: "40px", maxHeight: "120px" }}
              disabled={isStreaming}
            />
          </div>
          <button
            onClick={() => sendMessage()}
            disabled={!inputValue.trim() || isStreaming}
            className="bg-blue-600 text-white p-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>

        {/* Suggestions */}
        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {(suggestions || []).map((suggestion, _index) => (
              <button
                key={`suggestion-${suggestion.slice(0, 30).replace(/[^a-zA-Z0-9]/g, "-")}`}
                onClick={() => setInputValue(suggestion)}
                className="text-xs bg-gray-100 hover:bg-gray-200 px-2 py-1 rounded"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default EnhancedChatInterface;
