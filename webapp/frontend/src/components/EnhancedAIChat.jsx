import {
  Send as SendIcon,
  Psychology as PsychologyIcon,
  Person as PersonIcon,
  Settings as SettingsIcon,
  Clear as ClearIcon,
  TrendingUp as TrendingUpIcon,
  AccountBalance as AccountBalanceIcon,
  Assessment as AssessmentIcon,
  Lightbulb as LightbulbIcon,
  SmartToy as SmartToyIcon,
  MoreVert as MoreVertIcon,
  Stop as StopIcon,
  Refresh as RefreshIcon,
  Download as DownloadIcon,
  Search as SearchIcon,
  BookmarkBorder as BookmarkIcon,
  Share as ShareIcon,
  ThumbUp as ThumbUpIcon,
  ThumbDown as ThumbDownIcon,
  ContentCopy as CopyIcon,
  Edit as EditIcon,
  Reply as ReplyIcon,
} from "@mui/icons-material";
import {
  Box,
  Container,
  Typography,
  Paper,
  TextField,
  IconButton,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Switch,
  FormControlLabel,
  Grid,
  Divider,
  Tooltip,
  Menu,
  MenuItem,
  Badge,
  Stack,
  ButtonGroup,
} from "@mui/material";
import { useState, useRef, useEffect } from "react";

import { useAuth } from "../contexts/AuthContext.jsx";
import { useWebSocket } from "../hooks/useWebSocket.js";
import {
  sendChatMessage,
  clearChatHistory,
  // streamChatMessage // Temporarily disabled
} from "../services/api.js";

// Constants
const RANDOM_STRING_CONFIG = {
  BASE: 36, // Base-36 for alphanumeric string generation
  START_INDEX: 2, // Skip first 2 characters from random string
  END_INDEX: 9, // Take substring up to index 9
};

const EnhancedAIChat = () => {
  const { _user } = useAuth();

  // Core state
  const [messages, setMessages] = useState([
    {
      id: 1,
      type: "assistant",
      content:
        "Hello! I'm your enhanced AI investment assistant. I can provide real-time market analysis, personalized portfolio insights, and comprehensive investment guidance. What would you like to explore today?",
      timestamp: new Date(),
      suggestions: [
        "Analyze my portfolio performance",
        "Current market opportunities",
        "Risk assessment and optimization",
        "Investment strategy review",
      ],
      enhanced: true,
    },
  ]);

  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [currentStreamId, setCurrentStreamId] = useState(null);

  // UI state
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [optionsMenuAnchor, setOptionsMenuAnchor] = useState(null);
  const [selectedMessageId, setSelectedMessageId] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [bookmarkedMessages, setBookmarkedMessages] = useState(new Set());
  const [feedback, setFeedback] = useState({}); // { messageId: 'thumbup' | 'thumbdown' }

  // Enhanced features state
  const [streamingEnabled, setStreamingEnabled] = useState(true);
  const [autoSuggestions, setAutoSuggestions] = useState(true);
  const [conversationId, _setConversationId] = useState("default");
  const [aiModel, setAiModel] = useState("claude-3-haiku");
  const [responseStyle, setResponseStyle] = useState("balanced");

  // Refs
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const messageRefs = useRef({});

  // WebSocket connection for real-time streaming
  const {
    isConnected,
    sendMessage: sendWSMessage,
    _lastMessage,
    _connectionId,
  } = useWebSocket("/ws/ai", {
    enabled: streamingEnabled,
    onMessage: handleWebSocketMessage,
  });

  // Enhanced quick actions with more sophisticated options
  const quickActions = [
    {
      icon: <TrendingUpIcon />,
      text: "Market Pulse",
      action:
        "Give me a comprehensive market analysis with current trends, sector performance, and key opportunities to watch today",
      color: "primary",
    },
    {
      icon: <AccountBalanceIcon />,
      text: "Portfolio Deep Dive",
      action:
        "Perform a detailed analysis of my portfolio including risk assessment, sector allocation, performance metrics, and optimization recommendations",
      color: "secondary",
    },
    {
      icon: <AssessmentIcon />,
      text: "Investment Research",
      action:
        "Help me research and analyze potential investment opportunities based on my current portfolio and risk profile",
      color: "success",
    },
    {
      icon: <LightbulbIcon />,
      text: "Strategy Advisor",
      action:
        "Review my investment strategy and provide recommendations for optimization, rebalancing, and future planning",
      color: "warning",
    },
  ];

  // Scroll to bottom when messages change
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingMessage]);

  // Handle WebSocket messages for real-time streaming
  function handleWebSocketMessage(event) {
    try {
      const data = JSON.parse(event?.data);

      switch (data.type) {
        case "connection_established":
          console.log("✅ WebSocket connected:", data._connectionId);
          break;

        case "ai_response_chunk":
          if (data.streamId === currentStreamId) {
            setStreamingMessage((prev) => prev + (data.content || ""));
          }
          break;

        case "ai_response_complete":
          if (data.streamId === currentStreamId) {
            const assistantMessage = {
              id: data.messageId || Date.now(),
              type: "assistant",
              content: data.fullResponse || streamingMessage,
              suggestions: data.suggestions || [],
              metadata: data.metadata || {},
              timestamp: new Date(),
              enhanced: true,
              streamId: data.streamId,
            };

            setMessages((prev) => [...prev, assistantMessage]);
            setStreamingMessage("");
            setCurrentStreamId(null);
            setIsStreaming(false);
          }
          break;

        case "ai_streamerror": {
          console.error("Streaming error:", data.error);
          setIsStreaming(false);
          setStreamingMessage("");
          setCurrentStreamId(null);

          const errorMessage = {
            id: Date.now(),
            type: "assistant",
            content: `I encountered an error while processing your request: ${data.error}. Please try again.`,
            timestamp: new Date(),
            isError: true,
          };
          setMessages((prev) => [...prev, errorMessage]);
          break;
        }

        case "error":
          console.error("WebSocket error:", data.error);
          break;

        default:
          console.warn("Unknown WebSocket message type:", data.type);
          break;
      }
    } catch (error) {
      console.error(error);
    }
  }

  // Enhanced message sending with streaming support
  const handleSendMessage = async (messageContent = null) => {
    const content = messageContent || inputMessage.trim();
    if (!content || isLoading || isStreaming) return;

    const userMessage = {
      id: Date.now(),
      type: "user",
      content,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage("");

    if (streamingEnabled && isConnected) {
      // Use WebSocket streaming
      setIsStreaming(true);
      setStreamingMessage("");

      const streamId = `stream_${Date.now()}_${Math.random().toString(RANDOM_STRING_CONFIG.BASE).substring(RANDOM_STRING_CONFIG.START_INDEX, RANDOM_STRING_CONFIG.END_INDEX)}`;
      setCurrentStreamId(streamId);

      sendWSMessage({
        type: "ai_chat_request",
        content,
        conversationId,
        context: {
          streamingEnabled: true,
          model: aiModel,
          responseStyle,
        },
        options: {
          model: aiModel,
        },
      });
    } else {
      // Fallback to HTTP request
      setIsLoading(true);

      try {
        const response = await sendChatMessage(content, {
          conversationId,
          model: aiModel,
          responseStyle,
        });

        if (response.success) {
          const assistantMessage = {
            id: response.message.id || Date.now(),
            type: "assistant",
            content: response.message.content,
            suggestions: response.message.suggestions || [],
            metadata: response.message.metadata || {},
            timestamp: new Date(response.message.timestamp || new Date()),
            enhanced: response.enhanced || false,
          };

          setMessages((prev) => [...prev, assistantMessage]);
        } else {
          throw new Error(response.error || "Failed to send message");
        }
      } catch (error) {
        console.error(error);
        const errorMessage = {
          id: Date.now() + 1,
          type: "assistant",
          content: "I'm sorry, I encountered an error. Please try again later.",
          timestamp: new Date(),
          isError: true,
        };
        setMessages((prev) => [...prev, errorMessage]);
      } finally {
        setIsLoading(false);
      }
    }
  };

  // Stop streaming
  const handleStopStreaming = () => {
    if (currentStreamId && isConnected) {
      sendWSMessage({
        type: "stream_stop",
        streamId: currentStreamId,
      });
    }
    setIsStreaming(false);
    setStreamingMessage("");
    setCurrentStreamId(null);
  };

  // Enhanced message actions
  const handleMessageAction = (action, message) => {
    switch (action) {
      case "copy":
        navigator.clipboard.writeText(message.content);
        break;
      case "bookmark":
        setBookmarkedMessages((prev) => {
          const newSet = new Set(prev);
          if (newSet.has(message.id)) {
            newSet.delete(message.id);
          } else {
            newSet.add(message.id);
          }
          return newSet;
        });
        break;
      case "share":
        if (navigator.share) {
          navigator
            .share({
              title: "AI Chat Message",
              text: message.content,
              url: window.location.href,
            })
            .catch((err) => console.error("Error sharing:", err));
        } else {
          // Fallback to clipboard
          navigator.clipboard.writeText(`AI Chat Message: ${message.content}`);
          alert("Message copied to clipboard!");
        }
        break;
      case "thumbup":
        setFeedback((prev) => ({
          ...prev,
          [message.id]: prev[message.id] === "thumbup" ? null : "thumbup",
        }));
        break;
      case "thumbdown":
        setFeedback((prev) => ({
          ...prev,
          [message.id]: prev[message.id] === "thumbdown" ? null : "thumbdown",
        }));
        break;
      case "edit":
        if (message.type === "user") {
          setInputMessage(message.content);
          inputRef.current?.focus();
          // Remove the message being edited
          setMessages((prev) => prev.filter((m) => m.id !== message.id));
        }
        break;
      case "reply":
        setInputMessage(`Regarding "${message.content.substring(0, 50)}...": `);
        inputRef.current?.focus();
        break;
      default:
        console.warn("Unexpected message action:", action);
        break;
    }
    setSelectedMessageId(null);
  };

  // Search functionality
  const handleSearch = (query) => {
    setSearchQuery(query);

    if (!query.trim()) {
      return; // No search if empty query
    }

    // Filter messages based on search query
    const filteredMessages = messages.filter((message) => {
      const searchTerm = query.toLowerCase();
      return (
        message.content.toLowerCase().includes(searchTerm) ||
        (message.type === "user" &&
          message.content.toLowerCase().includes(searchTerm)) ||
        (message.suggestions &&
          message.suggestions.some((suggestion) =>
            suggestion.toLowerCase().includes(searchTerm)
          ))
      );
    });

    // Scroll to first matching message if found
    if (filteredMessages.length > 0) {
      const firstMatch = filteredMessages[0];
      const messageElement = messageRefs.current[firstMatch.id];
      if (messageElement) {
        messageElement.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });

        // Highlight the message temporarily
        messageElement.style.backgroundColor = "#fff3cd";
        setTimeout(() => {
          messageElement.style.backgroundColor = "";
        }, 2000);
      }
    }
  };

  // Clear chat with confirmation
  const handleClearChat = async () => {
    try {
      await clearChatHistory();
      setMessages([
        {
          id: 1,
          type: "assistant",
          content: "Chat cleared. How can I help you today?",
          timestamp: new Date(),
          suggestions: [
            "Analyze my portfolio performance",
            "Current market opportunities",
            "Risk assessment and optimization",
            "Investment strategy review",
          ],
        },
      ]);
    } catch (error) {
      console.error(error);
    }
    setOptionsMenuAnchor(null);
  };

  // Export conversation
  const handleExportConversation = () => {
    const conversationData = {
      conversationId,
      timestamp: new Date().toISOString(),
      messages: (messages || []).map((msg) => ({
        type: msg.type,
        content: msg.content,
        timestamp: msg.timestamp,
        suggestions: msg.suggestions,
      })),
    };

    const blob = new Blob([JSON.stringify(conversationData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ai-conversation-${conversationId}-${new Date().toISOString().split("T")[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setOptionsMenuAnchor(null);
  };

  // Handle keyboard shortcuts
  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    } else if (e.key === "Escape" && isStreaming) {
      handleStopStreaming();
    }
  };

  // Render streaming message
  const renderStreamingMessage = () => {
    if (!isStreaming || !streamingMessage) return null;

    return (
      <ListItem sx={{ flexDirection: "row", alignItems: "flex-start", mb: 2 }}>
        <ListItemAvatar>
          <Avatar sx={{ bgcolor: "primary.main", mr: 1 }}>
            <PsychologyIcon />
          </Avatar>
        </ListItemAvatar>

        <Box sx={{ flex: 1, maxWidth: "70%" }}>
          <Paper
            elevation={1}
            sx={{
              p: 2,
              bgcolor: "grey.100",
              borderRadius: 2,
              position: "relative",
            }}
          >
            <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
              {streamingMessage}
              <Box
                component="span"
                sx={{
                  display: "inline-block",
                  width: "8px",
                  height: "16px",
                  bgcolor: "primary.main",
                  ml: 0.5,
                  animation: "blink 1s infinite",
                }}
              />
            </Typography>

            <Box
              sx={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                mt: 1,
              }}
            >
              <Typography variant="caption" sx={{ opacity: 0.7 }}>
                Streaming...
              </Typography>
              <Tooltip title="Stop streaming">
                <IconButton
                  size="small"
                  onClick={handleStopStreaming}
                  sx={{ opacity: 0.7 }}
                >
                  <StopIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
          </Paper>
        </Box>
      </ListItem>
    );
  };

  // Render enhanced message with actions
  const renderMessage = (message) => {
    const isUser = message.type === "user";
    const isBookmarked = bookmarkedMessages.has(message.id);
    const messageFeedback = feedback[message.id];

    return (
      <ListItem
        key={message.id}
        ref={(el) => {
          messageRefs.current[message.id] = el;
        }}
        sx={{
          flexDirection: isUser ? "row-reverse" : "row",
          alignItems: "flex-start",
          mb: 2,
        }}
      >
        <ListItemAvatar>
          <Avatar
            sx={{
              bgcolor: isUser ? "secondary.main" : "primary.main",
              ml: isUser ? 1 : 0,
              mr: isUser ? 0 : 1,
            }}
          >
            {isUser ? <PersonIcon /> : <PsychologyIcon />}
          </Avatar>
        </ListItemAvatar>

        <Box sx={{ flex: 1, maxWidth: "70%" }}>
          <Paper
            elevation={1}
            sx={{
              p: 2,
              bgcolor: isUser ? "primary.light" : "grey.100",
              color: isUser ? "primary.contrastText" : "text.primary",
              borderRadius: 2,
              position: "relative",
              ...(message.isError && { bgcolor: "error.light" }),
              ...(isBookmarked && {
                border: "2px solid",
                borderColor: "primary.main",
                bgcolor: isUser ? "primary.light" : "primary.50",
              }),
            }}
          >
            <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
              <Typography
                variant="body1"
                sx={{ whiteSpace: "pre-wrap", flex: 1 }}
              >
                {message.content}
              </Typography>

              {/* Status indicators */}
              <Box
                sx={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 0.5,
                  mt: 0.5,
                }}
              >
                {isBookmarked && (
                  <BookmarkIcon sx={{ fontSize: 16, color: "primary.main" }} />
                )}
                {messageFeedback === "thumbup" && (
                  <ThumbUpIcon sx={{ fontSize: 16, color: "success.main" }} />
                )}
                {messageFeedback === "thumbdown" && (
                  <ThumbDownIcon sx={{ fontSize: 16, color: "error.main" }} />
                )}
              </Box>
            </Box>

            {/* Enhanced metadata display */}
            {message.enhanced && message.metadata && (
              <Box
                sx={{ mt: 1, pt: 1, borderTop: "1px solid rgba(0,0,0,0.1)" }}
              >
                <Typography variant="caption" sx={{ opacity: 0.7 }}>
                  Enhanced • {message.metadata.model} •{" "}
                  {message.metadata.tokensUsed} tokens
                  {message.metadata.cost &&
                    ` • $${message.metadata.cost.toFixed(4)}`}
                </Typography>
              </Box>
            )}

            <Box
              sx={{
                display: "flex",
                justifyContent: isUser ? "flex-end" : "space-between",
                alignItems: "center",
                mt: 1,
              }}
            >
              <Typography variant="caption" sx={{ opacity: 0.7 }}>
                {message.timestamp.toLocaleTimeString()}
              </Typography>

              {!isUser && (
                <Stack direction="row" spacing={0.5}>
                  <Tooltip title="Copy message">
                    <IconButton
                      size="small"
                      onClick={() => handleMessageAction("copy", message)}
                      sx={{ opacity: 0.7 }}
                    >
                      <CopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="More actions">
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        setSelectedMessageId(message.id);
                        setOptionsMenuAnchor(e.currentTarget);
                      }}
                      sx={{ opacity: 0.7 }}
                    >
                      <MoreVertIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              )}
            </Box>
          </Paper>

          {/* Enhanced suggestions */}
          {message.suggestions && message.suggestions.length > 0 && (
            <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {(message.suggestions || []).map((suggestion) => (
                <Chip
                  key={`suggestion-${message.id}-${suggestion.replace(/[^a-zA-Z0-9]/g, "").slice(0, 20)}`}
                  label={suggestion}
                  size="small"
                  variant="outlined"
                  clickable
                  onClick={() => handleSendMessage(suggestion)}
                  sx={{
                    fontSize: "0.75rem",
                    "&:hover": {
                      bgcolor: "primary.light",
                      color: "primary.contrastText",
                    },
                  }}
                />
              ))}
            </Box>
          )}
        </Box>
      </ListItem>
    );
  };

  return (
    <Container maxWidth="lg">
      <Box
        sx={{
          height: "100vh",
          display: "flex",
          flexDirection: "column",
          py: 2,
        }}
      >
        {/* Enhanced Header */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 2,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center" }}>
            <Badge
              color={isConnected ? "success" : "error"}
              variant="dot"
              sx={{ mr: 2 }}
            >
              <Avatar sx={{ bgcolor: "primary.main" }}>
                <SmartToyIcon />
              </Avatar>
            </Badge>
            <Box>
              <Typography variant="h5" fontWeight="bold">
                Enhanced AI Assistant
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Real-time financial advisor with streaming responses
                {streamingEnabled && isConnected && " • Connected"}
                {streamingEnabled && !isConnected && " • Connecting..."}
              </Typography>
            </Box>
          </Box>

          <Stack direction="row" spacing={1}>
            <Tooltip title="Search conversation">
              <IconButton onClick={() => setShowSearch(!showSearch)}>
                <SearchIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title="Settings">
              <IconButton onClick={() => setSettingsOpen(true)}>
                <SettingsIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title="More options">
              <IconButton
                onClick={(e) => setOptionsMenuAnchor(e.currentTarget)}
              >
                <MoreVertIcon />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        {/* Search Bar */}
        {showSearch && (
          <Paper sx={{ p: 2, mb: 2 }}>
            <TextField
              fullWidth
              size="small"
              placeholder="Search conversation..."
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              InputProps={{
                startAdornment: <SearchIcon sx={{ mr: 1, opacity: 0.6 }} />,
              }}
            />
          </Paper>
        )}

        {/* Enhanced Quick Actions */}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          {(quickActions || []).map((action) => (
            <Grid
              item
              xs={12}
              sm={6}
              md={3}
              key={`quickaction-${action.color || "unknown"}-${(action.text || "untitled").replace(/\s+/g, "")}`}
            >
              <Card
                sx={{
                  cursor: "pointer",
                  transition: "all 0.3s ease",
                  "&:hover": {
                    transform: "translateY(-4px)",
                    boxShadow: 6,
                    bgcolor: `${action.color}.50`,
                  },
                }}
                onClick={() => handleSendMessage(action.action)}
              >
                <CardContent sx={{ textAlign: "center", py: 2 }}>
                  <Box sx={{ color: `${action.color}.main`, mb: 1 }}>
                    {action.icon}
                  </Box>
                  <Typography variant="body2" fontWeight="medium">
                    {action.text}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* Enhanced Messages Container */}
        <Paper
          elevation={2}
          sx={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
            <List>
              {(messages || []).map(renderMessage)}
              {renderStreamingMessage()}
            </List>

            {(isLoading || isStreaming) && (
              <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
                <Stack direction="row" spacing={2} alignItems="center">
                  <CircularProgress size={24} />
                  <Typography variant="body2">
                    {isStreaming
                      ? "AI is streaming response..."
                      : "AI is thinking..."}
                  </Typography>
                  {isStreaming && (
                    <Button
                      size="small"
                      onClick={handleStopStreaming}
                      startIcon={<StopIcon />}
                    >
                      Stop
                    </Button>
                  )}
                </Stack>
              </Box>
            )}

            <div ref={messagesEndRef} />
          </Box>

          {/* Enhanced Input Area */}
          <Divider />
          <Box sx={{ p: 2 }}>
            <Box sx={{ display: "flex", gap: 1, alignItems: "flex-end" }}>
              <TextField
                ref={inputRef}
                fullWidth
                multiline
                maxRows={4}
                variant="outlined"
                placeholder="Ask me about investments, portfolio analysis, market trends, or any financial topic..."
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={isLoading || isStreaming}
                size="small"
                sx={{
                  "& .MuiOutlinedInput-root": {
                    borderRadius: 3,
                  },
                }}
              />

              <Tooltip title={isStreaming ? "Stop streaming" : "Send message"}>
                <span>
                  <IconButton
                    color="primary"
                    onClick={
                      isStreaming
                        ? handleStopStreaming
                        : () => handleSendMessage()
                    }
                    disabled={
                      (!inputMessage.trim() && !isStreaming) || isLoading
                    }
                    aria-label={isStreaming ? "Stop streaming" : "Send message"}
                    sx={{
                      bgcolor: "primary.main",
                      color: "white",
                      "&:hover": { bgcolor: "primary.dark" },
                      "&:disabled": { bgcolor: "grey.300" },
                    }}
                  >
                    {isStreaming ? <StopIcon /> : <SendIcon />}
                  </IconButton>
                </span>
              </Tooltip>
            </Box>

            {/* Connection Status */}
            <Box
              sx={{
                mt: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <Typography variant="caption" color="text.secondary">
                Model: {aiModel} • Style: {responseStyle}
                {streamingEnabled &&
                  ` • Streaming: ${isConnected ? "Connected" : "Disconnected"}`}
              </Typography>

              {streamingEnabled && !isConnected && (
                <Chip
                  size="small"
                  label="Reconnecting..."
                  color="warning"
                  variant="outlined"
                />
              )}
            </Box>
          </Box>
        </Paper>

        {/* Options Menu */}
        <Menu
          anchorEl={optionsMenuAnchor}
          open={Boolean(optionsMenuAnchor)}
          onClose={() => setOptionsMenuAnchor(null)}
        >
          {selectedMessageId
            ? (() => {
                const message = messages.find(
                  (m) => m.id === selectedMessageId
                );
                const isBookmarked = bookmarkedMessages.has(selectedMessageId);
                const currentFeedback = feedback[selectedMessageId];

                return [
                  <MenuItem
                    key="bookmark"
                    onClick={() => handleMessageAction("bookmark", message)}
                  >
                    <BookmarkIcon
                      sx={{
                        mr: 1,
                        color: isBookmarked ? "primary.main" : "inherit",
                      }}
                    />
                    {isBookmarked ? "Remove Bookmark" : "Bookmark"}
                  </MenuItem>,
                  <MenuItem
                    key="share"
                    onClick={() => handleMessageAction("share", message)}
                  >
                    <ShareIcon sx={{ mr: 1 }} />
                    Share
                  </MenuItem>,
                  <MenuItem
                    key="thumbup"
                    onClick={() => handleMessageAction("thumbup", message)}
                  >
                    <ThumbUpIcon
                      sx={{
                        mr: 1,
                        color:
                          currentFeedback === "thumbup"
                            ? "success.main"
                            : "inherit",
                      }}
                    />
                    Helpful
                  </MenuItem>,
                  <MenuItem
                    key="thumbdown"
                    onClick={() => handleMessageAction("thumbdown", message)}
                  >
                    <ThumbDownIcon
                      sx={{
                        mr: 1,
                        color:
                          currentFeedback === "thumbdown"
                            ? "error.main"
                            : "inherit",
                      }}
                    />
                    Not Helpful
                  </MenuItem>,
                  ...(message?.type === "user"
                    ? [
                        <MenuItem
                          key="edit"
                          onClick={() => handleMessageAction("edit", message)}
                        >
                          <EditIcon sx={{ mr: 1 }} />
                          Edit Message
                        </MenuItem>,
                      ]
                    : []),
                  <MenuItem
                    key="reply"
                    onClick={() => handleMessageAction("reply", message)}
                  >
                    <ReplyIcon sx={{ mr: 1 }} />
                    Reply
                  </MenuItem>,
                ];
              })()
            : // General actions
              [
                <MenuItem key="export" onClick={handleExportConversation}>
                  <DownloadIcon sx={{ mr: 1 }} />
                  Export Conversation
                </MenuItem>,
                <MenuItem key="clear" onClick={handleClearChat}>
                  <ClearIcon sx={{ mr: 1 }} />
                  Clear Chat
                </MenuItem>,
                <MenuItem
                  key="refresh"
                  onClick={() => window.location.reload()}
                >
                  <RefreshIcon sx={{ mr: 1 }} />
                  Refresh
                </MenuItem>,
              ]}
        </Menu>

        {/* Enhanced Settings Dialog */}
        <Dialog
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          maxWidth="md"
          fullWidth
        >
          <DialogTitle>Enhanced AI Assistant Settings</DialogTitle>
          <DialogContent>
            <Box
              sx={{ display: "flex", flexDirection: "column", gap: 3, mt: 1 }}
            >
              {/* Streaming Settings */}
              <Box>
                <Typography variant="h6" gutterBottom>
                  Streaming & Performance
                </Typography>
                <FormControlLabel
                  control={
                    <Switch
                      checked={streamingEnabled}
                      onChange={(e) => setStreamingEnabled(e.target.checked)}
                    />
                  }
                  label="Enable Real-time Streaming"
                />
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ ml: 4 }}
                >
                  Get responses as they&apos;re generated for faster interaction
                </Typography>
              </Box>

              {/* AI Model Selection */}
              <Box>
                <Typography variant="h6" gutterBottom>
                  AI Model
                </Typography>
                <ButtonGroup variant="outlined" size="small">
                  <Button
                    variant={
                      aiModel === "claude-3-haiku" ? "contained" : "outlined"
                    }
                    onClick={() => setAiModel("claude-3-haiku")}
                  >
                    Claude 3 Haiku (Fast)
                  </Button>
                  <Button
                    variant={
                      aiModel === "claude-3-sonnet" ? "contained" : "outlined"
                    }
                    onClick={() => setAiModel("claude-3-sonnet")}
                  >
                    Claude 3 Sonnet (Advanced)
                  </Button>
                </ButtonGroup>
              </Box>

              {/* Response Style */}
              <Box>
                <Typography variant="h6" gutterBottom>
                  Response Style
                </Typography>
                <ButtonGroup variant="outlined" size="small">
                  <Button
                    variant={
                      responseStyle === "concise" ? "contained" : "outlined"
                    }
                    onClick={() => setResponseStyle("concise")}
                  >
                    Concise
                  </Button>
                  <Button
                    variant={
                      responseStyle === "balanced" ? "contained" : "outlined"
                    }
                    onClick={() => setResponseStyle("balanced")}
                  >
                    Balanced
                  </Button>
                  <Button
                    variant={
                      responseStyle === "detailed" ? "contained" : "outlined"
                    }
                    onClick={() => setResponseStyle("detailed")}
                  >
                    Detailed
                  </Button>
                </ButtonGroup>
              </Box>

              {/* Auto Suggestions */}
              <Box>
                <Typography variant="h6" gutterBottom>
                  Interface
                </Typography>
                <FormControlLabel
                  control={
                    <Switch
                      checked={autoSuggestions}
                      onChange={(e) => setAutoSuggestions(e.target.checked)}
                    />
                  }
                  label="Auto-generate Suggestions"
                />
              </Box>

              {/* Connection Status */}
              <Alert severity={isConnected ? "success" : "warning"}>
                WebSocket Status: {isConnected ? "Connected" : "Disconnected"}
                {!isConnected && " - Using HTTP fallback"}
              </Alert>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSettingsOpen(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Box>

      {/* CSS for blinking cursor */}
      <style>{`
        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </Container>
  );
};

export default EnhancedAIChat;
