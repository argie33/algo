/**
 * Enhanced AI Chat Component Unit Tests
 * 
 * Comprehensive testing for the AI chat interface and functionality
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock the AI service
vi.mock('../../../services/aiService', () => ({
  sendChatMessage: vi.fn(),
  getChatHistory: vi.fn(),
  getConversations: vi.fn(),
  getAIConfig: vi.fn(),
  healthCheck: vi.fn()
}));

// Mock WebSocket
const mockWebSocket = {
  send: vi.fn(),
  close: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  readyState: 1,
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3
};

global.WebSocket = vi.fn(() => mockWebSocket);

import EnhancedAIChat from '../../../components/EnhancedAIChat';
import * as aiService from '../../../services/aiService';

const theme = createTheme();

const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('EnhancedAIChat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock AI service responses
    aiService.getAIConfig.mockResolvedValue({
      features: {
        streamingEnabled: true,
        enhancedContext: true,
        portfolioIntegration: true
      },
      models: {
        'claude-3-haiku': { name: 'Claude 3 Haiku' },
        'claude-3-sonnet': { name: 'Claude 3 Sonnet' }
      },
      defaultModel: 'claude-3-haiku'
    });

    aiService.getChatHistory.mockResolvedValue([]);
    aiService.getConversations.mockResolvedValue([]);
    aiService.healthCheck.mockResolvedValue({ status: 'healthy' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Component Rendering', () => {
    test('should render AI chat interface', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      expect(screen.getByText('AI Financial Assistant')).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/ask me about your portfolio/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
    });

    test('should show loading state during initialization', async () => {
      aiService.getAIConfig.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)));

      renderWithTheme(<EnhancedAIChat />);

      expect(screen.getByTestId('ai-chat-loading')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.queryByTestId('ai-chat-loading')).not.toBeInTheDocument();
      });
    });

    test('should display AI configuration settings', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Open settings
      const settingsButton = screen.getByRole('button', { name: /settings/i });
      fireEvent.click(settingsButton);

      await waitFor(() => {
        expect(screen.getByText('AI Assistant Settings')).toBeInTheDocument();
        expect(screen.getByText('Streaming Enabled')).toBeInTheDocument();
        expect(screen.getByText('Portfolio Integration')).toBeInTheDocument();
      });
    });
  });

  describe('Message Handling', () => {
    test('should send message when form is submitted', async () => {
      const user = userEvent.setup();
      
      aiService.sendChatMessage.mockResolvedValue({
        response: 'Hello! How can I help you with your portfolio today?',
        messageId: 'msg-1',
        conversationId: 'conv-1'
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      const sendButton = screen.getByRole('button', { name: /send/i });

      await user.type(input, 'What is my portfolio performance?');
      await user.click(sendButton);

      await waitFor(() => {
        expect(aiService.sendChatMessage).toHaveBeenCalledWith({
          message: 'What is my portfolio performance?',
          conversationId: expect.any(String),
          context: {
            page: 'chat',
            timestamp: expect.any(Number)
          }
        });
      });
    });

    test('should display sent and received messages', async () => {
      const user = userEvent.setup();
      
      aiService.sendChatMessage.mockResolvedValue({
        response: 'Your portfolio is performing well with a 12% return this year.',
        messageId: 'msg-1',
        conversationId: 'conv-1'
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'How is my portfolio doing?');
      await user.click(screen.getByRole('button', { name: /send/i }));

      // Check user message appears
      await waitFor(() => {
        expect(screen.getByText('How is my portfolio doing?')).toBeInTheDocument();
      });

      // Check AI response appears
      await waitFor(() => {
        expect(screen.getByText(/Your portfolio is performing well/)).toBeInTheDocument();
      });
    });

    test('should handle message sending errors', async () => {
      const user = userEvent.setup();
      
      aiService.sendChatMessage.mockRejectedValue(new Error('Service unavailable'));

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText(/error sending message/i)).toBeInTheDocument();
      });
    });

    test('should prevent sending empty messages', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const sendButton = screen.getByRole('button', { name: /send/i });
      
      // Button should be disabled when input is empty
      expect(sendButton).toBeDisabled();

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, '   '); // Just spaces
      
      // Should still be disabled
      expect(sendButton).toBeDisabled();
    });
  });

  describe('WebSocket Streaming', () => {
    test('should establish WebSocket connection for streaming', async () => {
      // Mock WebSocket URL from environment
      process.env.VITE_AI_WEBSOCKET_URL = 'wss://test-websocket-url.com';

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      await waitFor(() => {
        expect(global.WebSocket).toHaveBeenCalledWith('wss://test-websocket-url.com');
      });
    });

    test('should handle streaming message chunks', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate WebSocket message event
      const messageEvent = new MessageEvent('message', {
        data: JSON.stringify({
          type: 'stream_chunk',
          data: {
            streamId: 'stream-1',
            chunk: {
              type: 'content',
              text: 'Your portfolio'
            }
          }
        })
      });

      act(() => {
        const onMessage = mockWebSocket.addEventListener.mock.calls
          .find(call => call[0] === 'message')?.[1];
        if (onMessage) onMessage(messageEvent);
      });

      await waitFor(() => {
        expect(screen.getByText('Your portfolio')).toBeInTheDocument();
      });
    });

    test('should handle streaming completion', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate stream completion
      const completeEvent = new MessageEvent('message', {
        data: JSON.stringify({
          type: 'stream_complete',
          data: {
            streamId: 'stream-1',
            metadata: {
              tokensUsed: 150,
              cost: 0.00075
            }
          }
        })
      });

      act(() => {
        const onMessage = mockWebSocket.addEventListener.mock.calls
          .find(call => call[0] === 'message')?.[1];
        if (onMessage) onMessage(completeEvent);
      });

      // Should show completion indicator
      await waitFor(() => {
        expect(screen.getByText(/150 tokens/)).toBeInTheDocument();
      });
    });

    test('should handle WebSocket connection errors', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate WebSocket error
      const errorEvent = new Event('error');

      act(() => {
        const onError = mockWebSocket.addEventListener.mock.calls
          .find(call => call[0] === 'error')?.[1];
        if (onError) onError(errorEvent);
      });

      await waitFor(() => {
        expect(screen.getByText(/connection error/i)).toBeInTheDocument();
      });
    });

    test('should implement WebSocket reconnection', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate WebSocket close
      const closeEvent = new CloseEvent('close', { code: 1006, wasClean: false });

      act(() => {
        const onClose = mockWebSocket.addEventListener.mock.calls
          .find(call => call[0] === 'close')?.[1];
        if (onClose) onClose(closeEvent);
      });

      // Should attempt reconnection
      await waitFor(() => {
        expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
      });
    });
  });

  describe('Conversation Management', () => {
    test('should load chat history on mount', async () => {
      const mockHistory = [
        {
          id: 'msg-1',
          type: 'user',
          content: 'Hello',
          timestamp: Date.now() - 10000
        },
        {
          id: 'msg-2',
          type: 'assistant',
          content: 'Hi there! How can I help you?',
          timestamp: Date.now() - 5000
        }
      ];

      aiService.getChatHistory.mockResolvedValue(mockHistory);

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      await waitFor(() => {
        expect(screen.getByText('Hello')).toBeInTheDocument();
        expect(screen.getByText('Hi there! How can I help you?')).toBeInTheDocument();
      });
    });

    test('should clear conversation history', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Add some messages first
      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      // Find and click clear button
      const clearButton = screen.getByRole('button', { name: /clear/i });
      await user.click(clearButton);

      // Messages should be cleared
      await waitFor(() => {
        expect(screen.queryByText('Test message')).not.toBeInTheDocument();
      });
    });

    test('should handle conversation switching', async () => {
      const user = userEvent.setup();
      
      const mockConversations = [
        { id: 'conv-1', title: 'Portfolio Analysis', lastMessage: Date.now() - 1000 },
        { id: 'conv-2', title: 'Investment Strategy', lastMessage: Date.now() - 5000 }
      ];

      aiService.getConversations.mockResolvedValue(mockConversations);

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Open conversation list
      const conversationsButton = screen.getByRole('button', { name: /conversations/i });
      await user.click(conversationsButton);

      await waitFor(() => {
        expect(screen.getByText('Portfolio Analysis')).toBeInTheDocument();
        expect(screen.getByText('Investment Strategy')).toBeInTheDocument();
      });
    });
  });

  describe('AI Model Selection', () => {
    test('should allow model switching', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Open model selection
      const modelButton = screen.getByRole('button', { name: /claude 3 haiku/i });
      await user.click(modelButton);

      await waitFor(() => {
        expect(screen.getByText('Claude 3 Sonnet')).toBeInTheDocument();
      });

      // Switch to Sonnet
      await user.click(screen.getByText('Claude 3 Sonnet'));

      expect(screen.getByRole('button', { name: /claude 3 sonnet/i })).toBeInTheDocument();
    });

    test('should show model-specific features', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Switch to Sonnet model
      const modelButton = screen.getByRole('button', { name: /claude 3 haiku/i });
      await user.click(modelButton);
      await user.click(screen.getByText('Claude 3 Sonnet'));

      // Should show advanced features for Sonnet
      await waitFor(() => {
        expect(screen.getByText(/advanced analysis/i)).toBeInTheDocument();
      });
    });
  });

  describe('Portfolio Integration', () => {
    test('should include portfolio context in messages', async () => {
      const user = userEvent.setup();
      
      // Mock portfolio data
      const mockPortfolioData = {
        totalValue: 50000,
        dayChange: 250,
        holdings: [
          { symbol: 'AAPL', shares: 100, value: 15000 },
          { symbol: 'MSFT', shares: 50, value: 12000 }
        ]
      };

      // Mock the portfolio prop
      await act(async () => {
        renderWithTheme(<EnhancedAIChat portfolioData={mockPortfolioData} />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Analyze my holdings');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(aiService.sendChatMessage).toHaveBeenCalledWith(
          expect.objectContaining({
            context: expect.objectContaining({
              portfolioData: mockPortfolioData
            })
          })
        );
      });
    });

    test('should show portfolio summary in context panel', async () => {
      const mockPortfolioData = {
        totalValue: 50000,
        dayChange: 250,
        holdings: [
          { symbol: 'AAPL', shares: 100, value: 15000 }
        ]
      };

      await act(async () => {
        renderWithTheme(<EnhancedAIChat portfolioData={mockPortfolioData} />);
      });

      expect(screen.getByText('$50,000')).toBeInTheDocument();
      expect(screen.getByText('+$250')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });
  });

  describe('Error Handling and Fallbacks', () => {
    test('should handle AI service unavailable', async () => {
      aiService.healthCheck.mockRejectedValue(new Error('Service unavailable'));

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      await waitFor(() => {
        expect(screen.getByText(/ai service unavailable/i)).toBeInTheDocument();
      });
    });

    test('should show fallback responses when streaming fails', async () => {
      const user = userEvent.setup();
      
      aiService.sendChatMessage.mockRejectedValue(new Error('Bedrock unavailable'));

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText(/fallback response/i)).toBeInTheDocument();
      });
    });

    test('should retry failed requests', async () => {
      const user = userEvent.setup();
      
      aiService.sendChatMessage
        .mockRejectedValueOnce(new Error('Temporary error'))
        .mockResolvedValueOnce({
          response: 'Success after retry',
          messageId: 'msg-1'
        });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      // Should show retry button
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });

      // Click retry
      await user.click(screen.getByRole('button', { name: /retry/i }));

      // Should eventually show success
      await waitFor(() => {
        expect(screen.getByText('Success after retry')).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    test('should be keyboard accessible', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      
      // Should be able to focus input with tab
      await user.tab();
      expect(input).toHaveFocus();

      // Should be able to submit with Enter
      await user.type(input, 'Test message');
      await user.keyboard('{Enter}');

      expect(aiService.sendChatMessage).toHaveBeenCalled();
    });

    test('should have proper ARIA labels', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      expect(screen.getByRole('textbox')).toHaveAccessibleName(/message input/i);
      expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
      expect(screen.getByRole('log')).toHaveAccessibleName(/chat messages/i);
    });

    test('should announce new messages to screen readers', async () => {
      const user = userEvent.setup();
      
      aiService.sendChatMessage.mockResolvedValue({
        response: 'New AI response',
        messageId: 'msg-1'
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        const announcement = screen.getByRole('status', { name: /new message/i });
        expect(announcement).toBeInTheDocument();
      });
    });
  });

  describe('Performance', () => {
    test('should virtualize long conversation history', async () => {
      const longHistory = Array.from({ length: 1000 }, (_, i) => ({
        id: `msg-${i}`,
        type: i % 2 === 0 ? 'user' : 'assistant',
        content: `Message ${i}`,
        timestamp: Date.now() - (1000 - i) * 1000
      }));

      aiService.getChatHistory.mockResolvedValue(longHistory);

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Should only render visible messages
      await waitFor(() => {
        const messages = screen.getAllByText(/Message \d+/);
        expect(messages.length).toBeLessThan(100); // Virtualized
      });
    });

    test('should debounce typing indicators', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);

      // Type rapidly
      await user.type(input, 'Quick typing test');

      // Should not send typing events for every keystroke
      await waitFor(() => {
        const typingCalls = mockWebSocket.send.mock.calls.filter(
          call => call[0].includes('typing')
        );
        expect(typingCalls.length).toBeLessThan(10); // Debounced
      });
    });
  });
});