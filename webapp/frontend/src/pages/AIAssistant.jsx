import React, { useState, useRef, useEffect } from 'react';
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
  ListItemText,
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
  LinearProgress
} from '@mui/material';
import {
  Send as SendIcon,
  Psychology as PsychologyIcon,
  Person as PersonIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  VolumeUp as VolumeUpIcon,
  VolumeOff as VolumeOffIcon,
  Settings as SettingsIcon,
  Clear as ClearIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  TrendingUp as TrendingUpIcon,
  AccountBalance as AccountBalanceIcon,
  Assessment as AssessmentIcon,
  Lightbulb as LightbulbIcon,
  SmartToy as SmartToyIcon,
  MoreVert as MoreVertIcon,
  Videocam as VideocamIcon,
  VideocamOff as VideocamOffIcon
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { sendChatMessage, getChatHistory, clearChatHistory, getAIConfig, updateAIPreferences, requestDigitalHuman } from '../services/api';
import speechService from '../services/speechService';

const AIAssistant = () => {
  const { user } = useAuth();
  const [messages, setMessages] = useState([
    {
      id: 1,
      type: 'assistant',
      content: "Hello! I'm your AI investment assistant. I can help you with portfolio analysis, market insights, stock research, and investment strategies. What would you like to know?",
      timestamp: new Date(),
      suggestions: [
        "Analyze my portfolio performance",
        "What's trending in the market today?",
        "Help me find undervalued stocks",
        "Explain dividend investing"
      ]
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isVoiceEnabled, setIsVoiceEnabled] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [optionsMenuAnchor, setOptionsMenuAnchor] = useState(null);
  const [digitalHumanEnabled, setDigitalHumanEnabled] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [autoVoiceResponse, setAutoVoiceResponse] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(null);
  const [interimTranscript, setInterimTranscript] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Quick action suggestions
  const quickActions = [
    { icon: <TrendingUpIcon />, text: "Market Analysis", action: "Give me a market analysis for today" },
    { icon: <AccountBalanceIcon />, text: "Portfolio Review", action: "Review my portfolio performance" },
    { icon: <AssessmentIcon />, text: "Stock Research", action: "Help me research a specific stock" },
    { icon: <LightbulbIcon />, text: "Investment Ideas", action: "Suggest some investment ideas for me" }
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Initialize speech service
  useEffect(() => {
    const supportStatus = speechService.getSupportStatus();
    setSpeechSupported(supportStatus);

    // Set up speech service callbacks
    speechService.setCallbacks({
      onResult: (finalTranscript, interim) => {
        if (finalTranscript) {
          setInterimTranscript('');
          handleSendMessage(finalTranscript);
        } else {
          setInterimTranscript(interim);
        }
      },
      onError: (message, error) => {
        console.error('Speech error:', message, error);
        setIsListening(false);
        setInterimTranscript('');
        // Show error message to user
        const errorMessage = {
          id: Date.now(),
          type: 'assistant',
          content: `Voice input error: ${message}`,
          timestamp: new Date(),
          isError: true
        };
        setMessages(prev => [...prev, errorMessage]);
      },
      onStart: () => {
        setIsListening(true);
        setInterimTranscript('');
      },
      onEnd: () => {
        setIsListening(false);
        setInterimTranscript('');
      },
      onSpeechStart: () => {
        console.log('AI started speaking');
      },
      onSpeechEnd: () => {
        console.log('AI finished speaking');
      }
    });

    return () => {
      // Cleanup speech service
      speechService.stopListening();
      speechService.stopSpeaking();
    };
  }, []);

  const handleSendMessage = async (messageContent = null) => {
    const content = messageContent || inputMessage.trim();
    if (!content) return;

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      // Send message to AI backend
      const response = await sendChatMessage(content, { digitalHumanEnabled });
      
      if (response.success) {
        const assistantMessage = {
          id: response.message.id,
          type: 'assistant',
          content: response.message.content,
          timestamp: new Date(response.message.timestamp || new Date()),
          suggestions: response.message.suggestions || []
        };

        setMessages(prev => [...prev, assistantMessage]);

        // If voice is enabled and auto-response is on, speak the response
        if (voiceEnabled && autoVoiceResponse && speechService.isSynthesisSupported()) {
          try {
            speechService.speak(response.message.content);
          } catch (voiceError) {
            console.log('Voice response failed:', voiceError.message);
          }
        }

        // If digital human is enabled, request avatar response
        if (digitalHumanEnabled) {
          try {
            const digitalHumanResponse = await requestDigitalHuman(content);
            console.log('Digital human response:', digitalHumanResponse);
          } catch (dhError) {
            console.log('Digital human not available:', dhError.message);
          }
        }
      } else {
        throw new Error(response.error || 'Failed to send message');
      }
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        id: Date.now() + 1,
        type: 'assistant',
        content: "I'm sorry, I encountered an error. Please try again later.",
        timestamp: new Date(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const generateAIResponse = (input) => {
    const responses = {
      portfolio: "Based on your portfolio data, I can see you have a diversified mix of stocks and ETFs. Your current allocation shows 60% stocks and 40% bonds, which aligns well with a moderate risk profile. Would you like me to analyze any specific holdings or suggest rebalancing strategies?",
      market: "The market is showing mixed signals today. The S&P 500 is up 0.3% driven by strong tech earnings, while small-cap stocks are underperforming. Key sectors to watch include healthcare and renewable energy, which are showing unusual volume patterns.",
      stock: "I'd be happy to help you research stocks. Please tell me which ticker symbol you're interested in, and I'll provide a comprehensive analysis including technical indicators, fundamental metrics, analyst ratings, and recent news sentiment.",
      investment: "For investment ideas, I recommend looking at defensive sectors given current market conditions. Consider dividend aristocrats, REITs for income, or growth stocks in emerging technologies. What's your risk tolerance and investment timeline?",
      default: "I understand you're looking for investment guidance. I can help with portfolio analysis, market insights, stock research, risk assessment, and investment strategies. What specific area would you like to explore?"
    };

    const lowerInput = input.toLowerCase();
    if (lowerInput.includes('portfolio')) return responses.portfolio;
    if (lowerInput.includes('market') || lowerInput.includes('trending')) return responses.market;
    if (lowerInput.includes('stock') || lowerInput.includes('research')) return responses.stock;
    if (lowerInput.includes('investment') || lowerInput.includes('ideas')) return responses.investment;
    return responses.default;
  };

  const generateSuggestions = (input) => {
    const baseSuggestions = [
      "Tell me more about this",
      "What are the risks?",
      "Show me the data",
      "What's your recommendation?"
    ];

    const lowerInput = input.toLowerCase();
    if (lowerInput.includes('portfolio')) {
      return ["Analyze sector allocation", "Check risk metrics", "Suggest rebalancing", "Compare to benchmark"];
    }
    if (lowerInput.includes('market')) {
      return ["Sector performance", "Economic indicators", "Volatility analysis", "Weekly outlook"];
    }
    if (lowerInput.includes('stock')) {
      return ["Technical analysis", "Fundamental metrics", "Analyst ratings", "Price targets"];
    }
    
    return baseSuggestions;
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleVoiceToggle = async () => {
    if (!speechService.isRecognitionSupported()) {
      const errorMessage = {
        id: Date.now(),
        type: 'assistant',
        content: 'Voice input is not supported in this browser. Please try Chrome or Edge.',
        timestamp: new Date(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
      return;
    }

    if (!voiceEnabled) {
      const errorMessage = {
        id: Date.now(),
        type: 'assistant',
        content: 'Please enable voice chat in settings first.',
        timestamp: new Date(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
      return;
    }

    if (isListening) {
      speechService.stopListening();
    } else {
      try {
        speechService.startListening({
          continuous: false,
          interimResults: true
        });
      } catch (error) {
        console.error('Failed to start voice recognition:', error);
        const errorMessage = {
          id: Date.now(),
          type: 'assistant',
          content: 'Failed to start voice input. Please check microphone permissions.',
          timestamp: new Date(),
          isError: true
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    }
  };

  const handleClearChat = async () => {
    try {
      await clearChatHistory();
      setMessages([{
        id: 1,
        type: 'assistant',
        content: "Chat cleared. How can I help you today?",
        timestamp: new Date(),
        suggestions: [
          "Analyze my portfolio performance",
          "What's trending in the market today?",
          "Help me find undervalued stocks",
          "Explain dividend investing"
        ]
      }]);
    } catch (error) {
      console.error('Error clearing chat:', error);
    }
    setOptionsMenuAnchor(null);
  };

  const handleQuickAction = (action) => {
    handleSendMessage(action);
  };

  return (
    <div className="container mx-auto" maxWidth="lg">
      <div  sx={{ height: '100vh', display: 'flex', flexDirection: 'column', py: 2 }}>
        {/* Header */}
        <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <div  sx={{ display: 'flex', alignItems: 'center' }}>
            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: 'primary.main', mr: 2 }}>
              <SmartToyIcon />
            </div>
            <div>
              <div  variant="h5" fontWeight="bold">
                AI Investment Assistant
              </div>
              <div  variant="body2" color="text.secondary">
                Your personal finance advisor powered by AI
              </div>
            </div>
          </div>
          
          <div  sx={{ display: 'flex', gap: 1 }}>
            <div  title="Digital Human (Beta)">
              <button className="p-2 rounded-full hover:bg-gray-100" 
                color={digitalHumanEnabled ? 'primary' : 'default'}
                onClick={() => setDigitalHumanEnabled(!digitalHumanEnabled)}
              >
                {digitalHumanEnabled ? <VideocamIcon /> : <VideocamOffIcon />}
              </button>
            </div>
            <div  title={`Voice Chat ${speechService.isRecognitionSupported() ? '' : '(Not Supported)'}`}>
              <button className="p-2 rounded-full hover:bg-gray-100" 
                color={voiceEnabled ? 'primary' : 'default'}
                onClick={() => setVoiceEnabled(!voiceEnabled)}
                disabled={!speechService.isRecognitionSupported()}
              >
                {voiceEnabled ? <VolumeUpIcon /> : <VolumeOffIcon />}
              </button>
            </div>
            <div  title="Settings">
              <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => setSettingsOpen(true)}>
                <SettingsIcon />
              </button>
            </div>
            <div  title="Options">
              <button className="p-2 rounded-full hover:bg-gray-100" onClick={(e) => setOptionsMenuAnchor(e.currentTarget)}>
                <⋮  />
              </button>
            </div>
          </div>
        </div>

        {/* Digital Human Video Container */}
        {digitalHumanEnabled && (
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 2 }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  
                sx={{ 
                  height: 200, 
                  bgcolor: 'grey.100', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  borderRadius: 1
                }}
              >
                <div  sx={{ textAlign: 'center' }}>
                  <VideocamIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 1 }} />
                  <div  variant="body2" color="text.secondary">
                    Digital Human Avatar
                  </div>
                  <div  variant="caption" color="text.secondary">
                    NVIDIA Digital Human integration coming soon
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Quick Actions */}
        <div className="grid" container spacing={2} sx={{ mb: 2 }}>
          {quickActions.map((action, index) => (
            <div className="grid" item xs={12} sm={6} md={3} key={index}>
              <div className="bg-white shadow-md rounded-lg" 
                sx={{ 
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  '&:hover': { transform: 'translateY(-2px)', boxShadow: 3 }
                }}
                onClick={() => handleQuickAction(action.action)}
              >
                <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 2 }}>
                  <div  sx={{ color: 'primary.main', mb: 1 }}>
                    {action.icon}
                  </div>
                  <div  variant="body2" fontWeight="medium">
                    {action.text}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Messages Container */}
        <div className="bg-white shadow-md rounded-lg p-4" 
          elevation={2} 
          sx={{ 
            flex: 1, 
            display: 'flex', 
            flexDirection: 'column',
            overflow: 'hidden'
          }}
        >
          <div  sx={{ flex: 1, overflow: 'auto', p: 2 }}>
            <List>
              {messages.map((message) => (
                <ListItem 
                  key={message.id}
                  sx={{
                    flexDirection: message.type === 'user' ? 'row-reverse' : 'row',
                    alignItems: 'flex-start',
                    mb: 2
                  }}
                >
                  <ListItemAvatar>
                    <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" 
                      sx={{ 
                        bgcolor: message.type === 'user' ? 'secondary.main' : 'primary.main',
                        ml: message.type === 'user' ? 1 : 0,
                        mr: message.type === 'user' ? 0 : 1
                      }}
                    >
                      {message.type === 'user' ? <PersonIcon /> : <PsychologyIcon />}
                    </div>
                  </ListItemAvatar>
                  
                  <div  sx={{ flex: 1, maxWidth: '70%' }}>
                    <div className="bg-white shadow-md rounded-lg p-4"
                      elevation={1}
                      sx={{
                        p: 2,
                        bgcolor: message.type === 'user' ? 'primary.light' : 'grey.100',
                        color: message.type === 'user' ? 'primary.contrastText' : 'text.primary',
                        borderRadius: 2,
                        ...(message.isError && { bgcolor: 'error.light' })
                      }}
                    >
                      <div  variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                        {message.content}
                      </div>
                      <div  sx={{ 
                        display: 'flex', 
                        justifyContent: message.type === 'user' ? 'flex-end' : 'space-between',
                        alignItems: 'center',
                        mt: 1 
                      }}>
                        <div  
                          variant="caption" 
                          sx={{ opacity: 0.7 }}
                        >
                          {message.timestamp.toLocaleTimeString()}
                        </div>
                        {message.type === 'assistant' && voiceEnabled && speechService.isSynthesisSupported() && (
                          <div  title={speechService.isCurrentlySpeaking() ? "Stop speaking" : "Speak this message"}>
                            <button className="p-2 rounded-full hover:bg-gray-100" 
                              size="small"
                              onClick={() => {
                                if (speechService.isCurrentlySpeaking()) {
                                  speechService.stopSpeaking();
                                } else {
                                  speechService.speak(message.content);
                                }
                              }}
                              sx={{ opacity: 0.7, ml: 1 }}
                            >
                              {speechService.isCurrentlySpeaking() ? 
                                <StopIcon fontSize="small" /> : 
                                <PlayArrowIcon fontSize="small" />
                              }
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                    
                    {/* Suggestions */}
                    {message.suggestions && (
                      <div  sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {message.suggestions.map((suggestion, index) => (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            key={index}
                            label={suggestion}
                            size="small"
                            variant="outlined"
                            clickable
                            onClick={() => handleSendMessage(suggestion)}
                            sx={{ fontSize: '0.75rem' }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </ListItem>
              ))}
            </List>
            
            {isLoading && (
              <div  sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} />
                <div  variant="body2" sx={{ ml: 1 }}>
                  AI is thinking...
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>
          
          {/* Input Area */}
          <hr className="border-gray-200" />
          <div  sx={{ p: 2 }}>
            <div  sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                ref={inputRef}
                fullWidth
                multiline
                maxRows={3}
                variant="outlined"
                placeholder="Ask me anything about investments, markets, or your portfolio..."
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={isLoading}
                size="small"
                helperText={isListening && interimTranscript ? `Listening: ${interimTranscript}` : ''}
              />
              {voiceEnabled && (
                <div  title={isListening ? "Stop listening" : "Start voice input"}>
                  <button className="p-2 rounded-full hover:bg-gray-100" 
                    color={isListening ? 'error' : 'primary'}
                    onClick={handleVoiceToggle}
                    disabled={isLoading}
                  >
                    {isListening ? <MicOffIcon /> : <MicIcon />}
                  </button>
                </div>
              )}
              <div  title="Send message">
                <button className="p-2 rounded-full hover:bg-gray-100" 
                  color="primary" 
                  onClick={() => handleSendMessage()}
                  disabled={!inputMessage.trim() || isLoading}
                >
                  <SendIcon />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Options Menu */}
        <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg z-10"
          anchorEl={optionsMenuAnchor}
          open={Boolean(optionsMenuAnchor)}
          onClose={() => setOptionsMenuAnchor(null)}
        >
          <option  onClick={handleClearChat}>
            <ClearIcon sx={{ mr: 1 }} />
            Clear Chat
          </option>
        </div>

        {/* Settings Dialog */}
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={settingsOpen} onClose={() => setSettingsOpen(false)} maxWidth="sm" fullWidth>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>AI Assistant Settings</h2>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
            <div  sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={digitalHumanEnabled}
                    onChange={(e) => setDigitalHumanEnabled(e.target.checked)}
                  />
                }
                label="Enable Digital Human Avatar (Beta)"
              />
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={voiceEnabled}
                    onChange={(e) => setVoiceEnabled(e.target.checked)}
                  />
                }
                label="Enable Voice Chat"
              />
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={autoVoiceResponse}
                    onChange={(e) => setAutoVoiceResponse(e.target.checked)}
                    disabled={!voiceEnabled}
                  />
                }
                label="Auto-play Voice Responses"
              />
              
              {speechSupported && (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
                  severity={speechSupported.fullSupport ? 'success' : 'warning'} 
                  sx={{ mt: 2 }}
                >
                  <div  variant="body2">
                    <strong>Voice Support:</strong> 
                    {speechSupported.fullSupport 
                      ? ' Full voice chat supported in this browser!' 
                      : ` Limited support. ${speechSupported.recommendedBrowser}`
                    }
                  </div>
                </div>
              )}
              
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 1 }}>
                <div  variant="body2">
                  <strong>Digital Human Avatar:</strong> This feature uses NVIDIA's Digital Human technology 
                  to provide a more engaging experience. Currently in beta phase.
                </div>
              </div>
            </div>
          </div>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setSettingsOpen(false)}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIAssistant;