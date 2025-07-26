/**
 * Enhanced Bedrock Service Unit Tests
 * 
 * Comprehensive testing for AWS Bedrock AI integration with streaming support
 */

// Mock AWS SDK
jest.mock('@aws-sdk/client-bedrock-runtime', () => ({
  BedrockRuntimeClient: jest.fn().mockImplementation(() => ({
    send: jest.fn()
  })),
  InvokeModelCommand: jest.fn(),
  InvokeModelWithResponseStreamCommand: jest.fn()
}));

const EnhancedBedrockService = require('../../../services/EnhancedBedrockService');

describe('EnhancedBedrockService', () => {
  let service;
  let mockClient;

  beforeEach(() => {
    jest.clearAllMocks();
    service = new EnhancedBedrockService();
    mockClient = service.client;
  });

  describe('Service Initialization', () => {
    test('should initialize with correct default configuration', () => {
      expect(service.defaultModel).toBe('claude-3-haiku');
      expect(service.modelConfigs).toHaveProperty('claude-3-haiku');
      expect(service.modelConfigs).toHaveProperty('claude-3-sonnet');
    });

    test('should initialize usage statistics', () => {
      expect(service.usageStats).toEqual({
        totalRequests: 0,
        streamingRequests: 0,
        inputTokens: 0,
        outputTokens: 0,
        totalCost: 0,
        errorCount: 0,
        averageResponseTime: 0
      });
    });

    test('should configure models with correct properties', () => {
      const haikuConfig = service.modelConfigs['claude-3-haiku'];
      expect(haikuConfig).toHaveProperty('modelId');
      expect(haikuConfig).toHaveProperty('maxTokens');
      expect(haikuConfig).toHaveProperty('temperature');
      expect(haikuConfig).toHaveProperty('costPerInputToken');
      expect(haikuConfig).toHaveProperty('costPerOutputToken');
      expect(haikuConfig.streamingSupported).toBe(true);
    });
  });

  describe('Model Selection', () => {
    test('should select correct model based on request complexity', async () => {
      const simpleRequest = {
        message: 'Hello',
        context: 'greeting'
      };

      const complexRequest = {
        message: 'Analyze my portfolio performance with detailed risk metrics and provide strategic recommendations',
        context: 'portfolio_analysis'
      };

      // Test model selection logic
      const simpleModel = service._selectOptimalModel(simpleRequest);
      const complexModel = service._selectOptimalModel(complexRequest);

      expect(simpleModel).toBe('claude-3-haiku');
      expect(complexModel).toBe('claude-3-sonnet');
    });

    test('should handle model fallback when preferred model unavailable', async () => {
      // Mock unavailable model
      service.modelConfigs['claude-3-sonnet'].available = false;

      const complexRequest = {
        message: 'Complex analysis request',
        context: 'analysis'
      };

      const selectedModel = service._selectOptimalModel(complexRequest);
      expect(selectedModel).toBe('claude-3-haiku'); // Fallback to available model
    });
  });

  describe('Non-streaming Responses', () => {
    test('should generate standard response successfully', async () => {
      const mockResponse = {
        body: new TextEncoder().encode(JSON.stringify({
          content: [{ text: 'Test response' }],
          usage: { input_tokens: 10, output_tokens: 20 }
        }))
      };

      mockClient.send.mockResolvedValue(mockResponse);

      const result = await service.generateResponse({
        message: 'Test message',
        userId: 'test-user',
        conversationId: 'test-conversation'
      });

      expect(result).toHaveProperty('response', 'Test response');
      expect(result).toHaveProperty('metadata');
      expect(result.metadata).toHaveProperty('tokensUsed', 20);
      expect(result.metadata).toHaveProperty('model');
    });

    test('should handle Bedrock API errors gracefully', async () => {
      mockClient.send.mockRejectedValue(new Error('Bedrock API Error'));

      const result = await service.generateResponse({
        message: 'Test message',
        userId: 'test-user',
        conversationId: 'test-conversation'
      });

      expect(result).toHaveProperty('error');
      expect(result.error).toContain('Error generating response');
      expect(service.usageStats.errorCount).toBe(1);
    });

    test('should update usage statistics after successful request', async () => {
      const mockResponse = {
        body: new TextEncoder().encode(JSON.stringify({
          content: [{ text: 'Test response' }],
          usage: { input_tokens: 10, output_tokens: 20 }
        }))
      };

      mockClient.send.mockResolvedValue(mockResponse);

      await service.generateResponse({
        message: 'Test message',
        userId: 'test-user',
        conversationId: 'test-conversation'
      });

      expect(service.usageStats.totalRequests).toBe(1);
      expect(service.usageStats.inputTokens).toBe(10);
      expect(service.usageStats.outputTokens).toBe(20);
    });
  });

  describe('Streaming Responses', () => {
    test('should handle streaming response setup', async () => {
      const mockStream = {
        [Symbol.asyncIterator]: jest.fn().mockReturnValue({
          async *[Symbol.asyncIterator]() {
            yield {
              chunk: {
                bytes: new TextEncoder().encode(JSON.stringify({
                  type: 'content_block_delta',
                  delta: { text: 'Streaming ' }
                }))
              }
            };
            yield {
              chunk: {
                bytes: new TextEncoder().encode(JSON.stringify({
                  type: 'content_block_delta',
                  delta: { text: 'response' }
                }))
              }
            };
          }
        })
      };

      mockClient.send.mockResolvedValue({ body: mockStream });

      const streamHandler = jest.fn();
      
      await service.generateStreamingResponse({
        message: 'Test streaming message',
        userId: 'test-user',
        conversationId: 'test-conversation',
        onChunk: streamHandler
      });

      expect(mockClient.send).toHaveBeenCalled();
      expect(service.usageStats.streamingRequests).toBe(1);
    });

    test('should handle streaming errors gracefully', async () => {
      mockClient.send.mockRejectedValue(new Error('Streaming Error'));

      const streamHandler = jest.fn();
      const errorHandler = jest.fn();

      await service.generateStreamingResponse({
        message: 'Test message',
        userId: 'test-user',
        conversationId: 'test-conversation',
        onChunk: streamHandler,
        onError: errorHandler
      });

      expect(errorHandler).toHaveBeenCalled();
      expect(service.usageStats.errorCount).toBe(1);
    });
  });

  describe('Context Enhancement', () => {
    test('should enhance context with portfolio information', async () => {
      const portfolioContext = {
        holdings: [
          { symbol: 'AAPL', shares: 100, value: 15000 },
          { symbol: 'MSFT', shares: 50, value: 12000 }
        ],
        totalValue: 27000,
        dayChange: 350
      };

      const enhancedContext = service._enhanceContext({
        message: 'How is my portfolio performing?',
        context: 'portfolio',
        portfolioData: portfolioContext
      });

      expect(enhancedContext).toContain('portfolio holdings');
      expect(enhancedContext).toContain('AAPL');
      expect(enhancedContext).toContain('MSFT');
      expect(enhancedContext).toContain('$27,000');
    });

    test('should enhance context with market data', async () => {
      const marketContext = {
        marketStatus: 'open',
        majorIndices: {
          SPY: { price: 420.50, change: 2.15 },
          QQQ: { price: 350.25, change: -1.85 }
        }
      };

      const enhancedContext = service._enhanceContext({
        message: 'What is the market doing today?',
        context: 'market',
        marketData: marketContext
      });

      expect(enhancedContext).toContain('market is open');
      expect(enhancedContext).toContain('SPY');
      expect(enhancedContext).toContain('420.50');
    });
  });

  describe('Cost Optimization', () => {
    test('should calculate costs accurately', () => {
      const haikuCost = service._calculateCost('claude-3-haiku', 1000, 500);
      const sonnetCost = service._calculateCost('claude-3-sonnet', 1000, 500);

      expect(haikuCost).toBeCloseTo(0.000875); // (1000 * 0.25 + 500 * 1.25) / 1000000
      expect(sonnetCost).toBeCloseTo(0.01050);  // (1000 * 3.0 + 500 * 15.0) / 1000000
    });

    test('should track total costs', async () => {
      const mockResponse = {
        body: new TextEncoder().encode(JSON.stringify({
          content: [{ text: 'Test response' }],
          usage: { input_tokens: 1000, output_tokens: 500 }
        }))
      };

      mockClient.send.mockResolvedValue(mockResponse);

      await service.generateResponse({
        message: 'Test message',
        userId: 'test-user',
        conversationId: 'test-conversation'
      });

      expect(service.usageStats.totalCost).toBeGreaterThan(0);
    });

    test('should provide cost estimates', () => {
      const estimate = service.estimateCost('Test message', 'claude-3-haiku');
      
      expect(estimate).toHaveProperty('estimatedInputTokens');
      expect(estimate).toHaveProperty('estimatedOutputTokens');
      expect(estimate).toHaveProperty('estimatedCost');
      expect(estimate.estimatedCost).toBeGreaterThan(0);
    });
  });

  describe('Error Handling and Resilience', () => {
    test('should implement circuit breaker pattern', async () => {
      // Mock repeated failures
      mockClient.send.mockRejectedValue(new Error('Service Unavailable'));

      // Trigger multiple failures
      for (let i = 0; i < 5; i++) {
        await service.generateResponse({
          message: 'Test message',
          userId: 'test-user',
          conversationId: 'test-conversation'
        });
      }

      expect(service.usageStats.errorCount).toBe(5);
      
      // Circuit breaker should be open now
      const result = await service.generateResponse({
        message: 'Test message',
        userId: 'test-user',
        conversationId: 'test-conversation'
      });

      expect(result).toHaveProperty('fallbackResponse');
    });

    test('should provide fallback responses', () => {
      const fallback = service._getFallbackResponse('portfolio');
      
      expect(fallback).toBeDefined();
      expect(fallback).toContain('temporarily unavailable');
    });

    test('should validate input parameters', async () => {
      const invalidRequests = [
        { message: '', userId: 'test' },
        { message: 'test', userId: '' },
        { message: null, userId: 'test' },
        {}
      ];

      for (const request of invalidRequests) {
        const result = await service.generateResponse(request);
        expect(result).toHaveProperty('error');
      }
    });
  });

  describe('Performance Monitoring', () => {
    test('should track response times', async () => {
      const mockResponse = {
        body: new TextEncoder().encode(JSON.stringify({
          content: [{ text: 'Test response' }],
          usage: { input_tokens: 10, output_tokens: 20 }
        }))
      };

      mockClient.send.mockResolvedValue(mockResponse);

      const startTime = Date.now();
      await service.generateResponse({
        message: 'Test message',
        userId: 'test-user',
        conversationId: 'test-conversation'
      });

      expect(service.usageStats.averageResponseTime).toBeGreaterThan(0);
    });

    test('should provide performance metrics', () => {
      const metrics = service.getPerformanceMetrics();
      
      expect(metrics).toHaveProperty('totalRequests');
      expect(metrics).toHaveProperty('successRate');
      expect(metrics).toHaveProperty('averageResponseTime');
      expect(metrics).toHaveProperty('totalCost');
      expect(metrics).toHaveProperty('costPerRequest');
    });
  });

  describe('Configuration Management', () => {
    test('should update model configurations', () => {
      const newConfig = {
        'claude-3-haiku': {
          ...service.modelConfigs['claude-3-haiku'],
          maxTokens: 3000
        }
      };

      service.updateModelConfig(newConfig);
      
      expect(service.modelConfigs['claude-3-haiku'].maxTokens).toBe(3000);
    });

    test('should validate model configurations', () => {
      const validConfig = {
        'claude-3-haiku': {
          modelId: 'anthropic.claude-3-haiku-20240307-v1:0',
          maxTokens: 2000,
          temperature: 0.1,
          costPerInputToken: 0.25 / 1000000,
          costPerOutputToken: 1.25 / 1000000
        }
      };

      const invalidConfig = {
        'invalid-model': {
          maxTokens: 'invalid'
        }
      };

      expect(service._validateModelConfig(validConfig)).toBe(true);
      expect(service._validateModelConfig(invalidConfig)).toBe(false);
    });
  });

  describe('Health Checks', () => {
    test('should report service health', async () => {
      const health = await service.healthCheck();
      
      expect(health).toHaveProperty('status');
      expect(health).toHaveProperty('bedrock');
      expect(health).toHaveProperty('models');
      expect(health).toHaveProperty('metrics');
    });

    test('should detect unhealthy service state', async () => {
      // Simulate high error rate
      service.usageStats.errorCount = 50;
      service.usageStats.totalRequests = 100;

      const health = await service.healthCheck();
      
      expect(health.status).not.toBe('healthy');
    });
  });
});