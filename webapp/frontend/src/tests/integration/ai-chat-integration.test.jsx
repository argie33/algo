/**
 * AI Chat Frontend Integration Tests
 * 
 * Tests the complete AI chat functionality in the frontend including:
 * - API integration with backend
 * - WebSocket streaming
 * - Real portfolio data integration
 * - Error handling and resilience
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock fetch for API calls
global.fetch = vi.fn();

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

import EnhancedAIChat from '../../components/EnhancedAIChat';

const theme = createTheme();

const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('AI Chat Frontend Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup default fetch responses
    global.fetch.mockImplementation((url) => {
      if (url.includes('/api/ai/config')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            features: {
              streamingEnabled: true,
              enhancedContext: true,
              portfolioIntegration: true
            },
            models: {
              'claude-3-haiku': { name: 'Claude 3 Haiku', costEfficient: true },
              'claude-3-sonnet': { name: 'Claude 3 Sonnet', advanced: true }
            },
            defaultModel: 'claude-3-haiku'
          })
        });
      }
      
      if (url.includes('/api/ai/health')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'healthy',
            bedrock: { available: true },
            features: { portfolioAnalysis: true }
          })
        });
      }
      
      if (url.includes('/api/ai/history')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      
      if (url.includes('/api/ai/conversations')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([])
        });
      }
      
      return Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ error: 'Not found' })
      });
    });

    // Setup WebSocket environment
    process.env.VITE_AI_WEBSOCKET_URL = 'wss://test-websocket.com';
    process.env.VITE_AI_HTTP_URL = 'https://test-api.com';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Backend API Integration', () => {
    test('should load AI configuration from backend', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/ai/config'),
          expect.any(Object)
        );
      });

      // Should display configuration-based features
      expect(screen.getByText(/streaming enabled/i)).toBeInTheDocument();
    });

    test('should send chat messages to backend API', async () => {
      const user = userEvent.setup();
      
      // Mock successful chat response
      global.fetch.mockImplementation((url, options) => {
        if (url.includes('/api/ai/chat') && options.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              response: 'This is a test AI response from the backend',
              messageId: 'msg-12345',
              conversationId: 'conv-67890',
              metadata: {
                model: 'claude-3-haiku',
                tokensUsed: 45,
                cost: 0.00011
              }
            })
          });
        }
        
        // Fall back to default mock
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({})
        });
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'What is my portfolio performance?');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/ai/chat'),
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Content-Type': 'application/json'
            }),
            body: expect.stringContaining('What is my portfolio performance?')
          })
        );
      });

      // Should display the backend response
      await waitFor(() => {
        expect(screen.getByText('This is a test AI response from the backend')).toBeInTheDocument();
      });
    });

    test('should handle API authentication', async () => {
      const user = userEvent.setup();
      
      // Mock authentication required response
      global.fetch.mockImplementation((url, options) => {
        if (url.includes('/api/ai/chat')) {
          return Promise.resolve({
            ok: false,
            status: 401,
            json: () => Promise.resolve({ error: 'Authentication required' })
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText(/authentication required/i)).toBeInTheDocument();
      });
    });

    test('should load conversation history from backend', async () => {
      // Mock conversation history
      global.fetch.mockImplementation((url) => {
        if (url.includes('/api/ai/history')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([
              {
                id: 'msg-1',
                message_type: 'user',
                content: 'Previous user message',
                timestamp: new Date(Date.now() - 60000).toISOString()
              },
              {
                id: 'msg-2',
                message_type: 'assistant',
                content: 'Previous AI response',
                timestamp: new Date(Date.now() - 59000).toISOString()
              }
            ])
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      await waitFor(() => {
        expect(screen.getByText('Previous user message')).toBeInTheDocument();
        expect(screen.getByText('Previous AI response')).toBeInTheDocument();
      });
    });
  });

  describe('WebSocket Streaming Integration', () => {
    test('should establish WebSocket connection', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      await waitFor(() => {
        expect(global.WebSocket).toHaveBeenCalledWith('wss://test-websocket.com');
      });

      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('open', expect.any(Function));
      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('message', expect.any(Function));
      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('error', expect.any(Function));
      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('close', expect.any(Function));
    });

    test('should handle streaming message chunks', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate WebSocket messages
      const onMessage = mockWebSocket.addEventListener.mock.calls
        .find(call => call[0] === 'message')[1];

      // Simulate stream start
      act(() => {
        onMessage(new MessageEvent('message', {
          data: JSON.stringify({
            type: 'stream_started',
            data: { streamId: 'stream-123' }
          })
        }));
      });

      // Simulate streaming chunks
      act(() => {
        onMessage(new MessageEvent('message', {
          data: JSON.stringify({
            type: 'stream_chunk',
            data: {
              streamId: 'stream-123',
              chunk: { type: 'content', text: 'Your portfolio ' }
            }
          })
        }));
      });

      act(() => {
        onMessage(new MessageEvent('message', {
          data: JSON.stringify({
            type: 'stream_chunk',
            data: {
              streamId: 'stream-123',
              chunk: { type: 'content', text: 'is performing well' }
            }
          })
        }));
      });

      // Simulate stream completion
      act(() => {
        onMessage(new MessageEvent('message', {
          data: JSON.stringify({
            type: 'stream_complete',
            data: {
              streamId: 'stream-123',
              metadata: { tokensUsed: 25, cost: 0.00006 }
            }
          })
        }));
      });

      await waitFor(() => {
        expect(screen.getByText(/Your portfolio is performing well/)).toBeInTheDocument();
      });
    });

    test('should handle WebSocket reconnection', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate connection close
      const onClose = mockWebSocket.addEventListener.mock.calls
        .find(call => call[0] === 'close')[1];

      act(() => {
        onClose(new CloseEvent('close', { code: 1006, wasClean: false }));
      });

      await waitFor(() => {
        expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
      });

      // Should attempt to reconnect
      await waitFor(() => {
        expect(global.WebSocket).toHaveBeenCalledTimes(2);
      }, { timeout: 3000 });
    });

    test('should send WebSocket chat requests', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate successful WebSocket connection
      const onOpen = mockWebSocket.addEventListener.mock.calls
        .find(call => call[0] === 'open')[1];
      
      act(() => {
        onOpen(new Event('open'));
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'WebSocket test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(mockWebSocket.send).toHaveBeenCalledWith(
          expect.stringContaining('ai_chat_request')
        );
      });

      const sentData = JSON.parse(mockWebSocket.send.mock.calls[0][0]);
      expect(sentData.type).toBe('ai_chat_request');
      expect(sentData.data.message).toBe('WebSocket test message');
    });
  });

  describe('Portfolio Data Integration', () => {
    test('should integrate portfolio data in chat context', async () => {
      const user = userEvent.setup();
      
      const mockPortfolioData = {
        totalValue: 75000,
        dayChange: 1250,
        dayChangePercent: 1.69,
        holdings: [
          { symbol: 'AAPL', shares: 150, value: 22500, change: 450 },
          { symbol: 'MSFT', shares: 75, value: 18750, change: 300 },
          { symbol: 'GOOGL', shares: 25, value: 15000, change: 200 }
        ]
      };

      // Mock chat API to verify portfolio data is sent
      global.fetch.mockImplementation((url, options) => {
        if (url.includes('/api/ai/chat') && options.method === 'POST') {
          const requestBody = JSON.parse(options.body);
          
          // Verify portfolio data is included in context
          expect(requestBody.context).toHaveProperty('portfolioData');
          expect(requestBody.context.portfolioData.totalValue).toBe(75000);
          expect(requestBody.context.portfolioData.holdings).toHaveLength(3);
          
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              response: 'Based on your portfolio worth $75,000, you have strong positions in AAPL, MSFT, and GOOGL.',
              messageId: 'msg-portfolio-test'
            })
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat portfolioData={mockPortfolioData} />);
      });

      // Should display portfolio summary
      expect(screen.getByText('$75,000')).toBeInTheDocument();
      expect(screen.getByText('+$1,250')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'How is my portfolio doing today?');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText(/Based on your portfolio worth \$75,000/)).toBeInTheDocument();
      });
    });

    test('should handle missing portfolio data gracefully', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat portfolioData={null} />);
      });

      // Should not show portfolio summary
      expect(screen.queryByText(/\$\d+/)).not.toBeInTheDocument();

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'What can you help me with?');
      await user.click(screen.getByRole('button', { name: /send/i }));

      // Should still send message without portfolio context
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/ai/chat'),
          expect.objectContaining({
            method: 'POST'
          })
        );
      });
    });
  });

  describe('Error Handling and Resilience', () => {
    test('should handle backend API failures gracefully', async () => {
      const user = userEvent.setup();
      
      // Mock API failure
      global.fetch.mockImplementation((url) => {
        if (url.includes('/api/ai/chat')) {
          return Promise.reject(new Error('Network error'));
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test message');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText(/error sending message/i)).toBeInTheDocument();
      });

      // Should show retry option
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    test('should retry failed requests', async () => {
      const user = userEvent.setup();
      
      let callCount = 0;
      global.fetch.mockImplementation((url) => {
        if (url.includes('/api/ai/chat')) {
          callCount++;
          if (callCount === 1) {
            return Promise.reject(new Error('Temporary error'));
          }
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              response: 'Success after retry',
              messageId: 'msg-retry-success'
            })
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Test retry');
      await user.click(screen.getByRole('button', { name: /send/i }));

      // Wait for error and retry button
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });

      // Click retry
      await user.click(screen.getByRole('button', { name: /retry/i }));

      // Should eventually succeed
      await waitFor(() => {
        expect(screen.getByText('Success after retry')).toBeInTheDocument();
      });
    });

    test('should handle WebSocket connection failures', async () => {
      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Simulate WebSocket error
      const onError = mockWebSocket.addEventListener.mock.calls
        .find(call => call[0] === 'error')[1];

      act(() => {
        onError(new Event('error'));
      });

      await waitFor(() => {
        expect(screen.getByText(/connection error/i)).toBeInTheDocument();
      });
    });

    test('should fallback to HTTP when WebSocket unavailable', async () => {
      const user = userEvent.setup();
      
      // Mock WebSocket constructor to throw error
      global.WebSocket = vi.fn(() => {
        throw new Error('WebSocket not supported');
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Should still allow sending messages via HTTP
      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'HTTP fallback test');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/ai/chat'),
          expect.objectContaining({ method: 'POST' })
        );
      });
    });
  });

  describe('Performance and Optimization', () => {
    test('should debounce typing indicators', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);

      // Type rapidly
      await user.type(input, 'Quick typing test message', { delay: 10 });

      // Should not send typing indicator for every keystroke
      await waitFor(() => {
        const typingMessages = mockWebSocket.send.mock.calls.filter(
          call => call[0].includes('typing_start')
        );
        expect(typingMessages.length).toBeLessThan(10);
      });
    });

    test('should virtualize long conversation history', async () => {
      // Mock long conversation history
      const longHistory = Array.from({ length: 500 }, (_, i) => ({
        id: `msg-${i}`,
        message_type: i % 2 === 0 ? 'user' : 'assistant',
        content: `Message number ${i}`,
        timestamp: new Date(Date.now() - (500 - i) * 1000).toISOString()
      }));

      global.fetch.mockImplementation((url) => {
        if (url.includes('/api/ai/history')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(longHistory)
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      await waitFor(() => {
        // Should not render all 500 messages at once (virtualized)
        const messages = screen.getAllByText(/Message number \d+/);
        expect(messages.length).toBeLessThan(100);
      });
    });

    test('should handle rapid consecutive messages', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);

      // Send multiple rapid messages
      for (let i = 0; i < 5; i++) {
        await user.clear(input);
        await user.type(input, `Message ${i}`);
        await user.click(screen.getByRole('button', { name: /send/i }));
      }

      // Should handle all messages without crashes
      await waitFor(() => {
        const fetchCalls = global.fetch.mock.calls.filter(
          call => call[0].includes('/api/ai/chat') && call[1].method === 'POST'
        );
        expect(fetchCalls.length).toBe(5);
      });
    });
  });

  describe('Accessibility', () => {
    test('should announce new messages to screen readers', async () => {
      global.fetch.mockImplementation((url, options) => {
        if (url.includes('/api/ai/chat') && options.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              response: 'Accessible AI response',
              messageId: 'msg-a11y'
            })
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      });

      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      const input = screen.getByPlaceholderText(/ask me about your portfolio/i);
      await user.type(input, 'Accessibility test');
      await user.click(screen.getByRole('button', { name: /send/i }));

      await waitFor(() => {
        const announcement = screen.getByRole('status');
        expect(announcement).toBeInTheDocument();
      });
    });

    test('should support keyboard navigation', async () => {
      const user = userEvent.setup();

      await act(async () => {
        renderWithTheme(<EnhancedAIChat />);
      });

      // Should be able to navigate with keyboard
      await user.tab();
      expect(screen.getByPlaceholderText(/ask me about your portfolio/i)).toHaveFocus();

      await user.type(screen.getByPlaceholderText(/ask me about your portfolio/i), 'Keyboard test');
      await user.keyboard('{Enter}');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/ai/chat'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });
});