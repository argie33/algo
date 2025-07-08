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

  const handleVoiceToggle = () => {
    setIsListening(!isListening);
    // Implement voice recognition here
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
    <Container maxWidth="lg">
      <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', py: 2 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Avatar sx={{ bgcolor: 'primary.main', mr: 2 }}>
              <SmartToyIcon />
            </Avatar>
            <Box>
              <Typography variant="h5" fontWeight="bold">
                AI Investment Assistant
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Your personal finance advisor powered by AI
              </Typography>
            </Box>
          </Box>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Tooltip title="Digital Human (Beta)">
              <IconButton 
                color={digitalHumanEnabled ? 'primary' : 'default'}
                onClick={() => setDigitalHumanEnabled(!digitalHumanEnabled)}
              >
                {digitalHumanEnabled ? <VideocamIcon /> : <VideocamOffIcon />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Voice Chat">
              <IconButton 
                color={voiceEnabled ? 'primary' : 'default'}
                onClick={() => setVoiceEnabled(!voiceEnabled)}
              >
                {voiceEnabled ? <VolumeUpIcon /> : <VolumeOffIcon />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Settings">
              <IconButton onClick={() => setSettingsOpen(true)}>
                <SettingsIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title="Options">
              <IconButton onClick={(e) => setOptionsMenuAnchor(e.currentTarget)}>
                <MoreVertIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {/* Digital Human Video Container */}
        {digitalHumanEnabled && (
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Box 
                sx={{ 
                  height: 200, 
                  bgcolor: 'grey.100', 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  borderRadius: 1
                }}
              >
                <Box sx={{ textAlign: 'center' }}>
                  <VideocamIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 1 }} />
                  <Typography variant="body2" color="text.secondary">
                    Digital Human Avatar
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    NVIDIA Digital Human integration coming soon
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        )}

        {/* Quick Actions */}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          {quickActions.map((action, index) => (
            <Grid item xs={12} sm={6} md={3} key={index}>
              <Card 
                sx={{ 
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  '&:hover': { transform: 'translateY(-2px)', boxShadow: 3 }
                }}
                onClick={() => handleQuickAction(action.action)}
              >
                <CardContent sx={{ textAlign: 'center', py: 2 }}>
                  <Box sx={{ color: 'primary.main', mb: 1 }}>
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

        {/* Messages Container */}
        <Paper 
          elevation={2} 
          sx={{ 
            flex: 1, 
            display: 'flex', 
            flexDirection: 'column',
            overflow: 'hidden'
          }}
        >
          <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
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
                    <Avatar 
                      sx={{ 
                        bgcolor: message.type === 'user' ? 'secondary.main' : 'primary.main',
                        ml: message.type === 'user' ? 1 : 0,
                        mr: message.type === 'user' ? 0 : 1
                      }}
                    >
                      {message.type === 'user' ? <PersonIcon /> : <PsychologyIcon />}
                    </Avatar>
                  </ListItemAvatar>
                  
                  <Box sx={{ flex: 1, maxWidth: '70%' }}>
                    <Paper
                      elevation={1}
                      sx={{
                        p: 2,
                        bgcolor: message.type === 'user' ? 'primary.light' : 'grey.100',
                        color: message.type === 'user' ? 'primary.contrastText' : 'text.primary',
                        borderRadius: 2,
                        ...(message.isError && { bgcolor: 'error.light' })
                      }}
                    >
                      <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                        {message.content}
                      </Typography>
                      <Typography 
                        variant="caption" 
                        sx={{ 
                          display: 'block', 
                          mt: 1, 
                          opacity: 0.7,
                          textAlign: message.type === 'user' ? 'right' : 'left'
                        }}
                      >
                        {message.timestamp.toLocaleTimeString()}
                      </Typography>
                    </Paper>
                    
                    {/* Suggestions */}
                    {message.suggestions && (
                      <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {message.suggestions.map((suggestion, index) => (
                          <Chip
                            key={index}
                            label={suggestion}
                            size="small"
                            variant="outlined"
                            clickable
                            onClick={() => handleSendMessage(suggestion)}
                            sx={{ fontSize: '0.75rem' }}
                          />
                        ))}
                      </Box>
                    )}
                  </Box>
                </ListItem>
              ))}
            </List>
            
            {isLoading && (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                <CircularProgress size={24} />
                <Typography variant="body2" sx={{ ml: 1 }}>
                  AI is thinking...
                </Typography>
              </Box>
            )}
            
            <div ref={messagesEndRef} />
          </Box>
          
          {/* Input Area */}
          <Divider />
          <Box sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
              <TextField
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
              />
              {voiceEnabled && (
                <Tooltip title={isListening ? "Stop listening" : "Start voice input"}>
                  <IconButton 
                    color={isListening ? 'error' : 'primary'}
                    onClick={handleVoiceToggle}
                    disabled={isLoading}
                  >
                    {isListening ? <MicOffIcon /> : <MicIcon />}
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title="Send message">
                <IconButton 
                  color="primary" 
                  onClick={() => handleSendMessage()}
                  disabled={!inputMessage.trim() || isLoading}
                >
                  <SendIcon />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
        </Paper>

        {/* Options Menu */}
        <Menu
          anchorEl={optionsMenuAnchor}
          open={Boolean(optionsMenuAnchor)}
          onClose={() => setOptionsMenuAnchor(null)}
        >
          <MenuItem onClick={handleClearChat}>
            <ClearIcon sx={{ mr: 1 }} />
            Clear Chat
          </MenuItem>
        </Menu>

        {/* Settings Dialog */}
        <Dialog open={settingsOpen} onClose={() => setSettingsOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle>AI Assistant Settings</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={digitalHumanEnabled}
                    onChange={(e) => setDigitalHumanEnabled(e.target.checked)}
                  />
                }
                label="Enable Digital Human Avatar (Beta)"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={voiceEnabled}
                    onChange={(e) => setVoiceEnabled(e.target.checked)}
                  />
                }
                label="Enable Voice Chat"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={isVoiceEnabled}
                    onChange={(e) => setIsVoiceEnabled(e.target.checked)}
                  />
                }
                label="Auto-play Voice Responses"
              />
              
              <Alert severity="info" sx={{ mt: 2 }}>
                <Typography variant="body2">
                  <strong>Digital Human Avatar:</strong> This feature uses NVIDIA's Digital Human technology 
                  to provide a more engaging experience. Currently in beta phase.
                </Typography>
              </Alert>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSettingsOpen(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Box>
    </Container>
  );
};

export default AIAssistant;