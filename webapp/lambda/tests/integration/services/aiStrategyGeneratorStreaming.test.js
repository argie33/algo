/**
 * Integration Tests for AI Strategy Generator Streaming Service
 * Tests real-time streaming strategy generation functionality
 */

const AIStrategyGeneratorStreaming = require('../../../services/aiStrategyGeneratorStreaming');

// Extend setup timeout for streaming operations
jest.setTimeout(60000);

describe('AI Strategy Generator Streaming Integration Tests', () => {
  let streamingGenerator;
  let mockSymbols;
  let progressEvents;

  beforeEach(() => {
    streamingGenerator = new AIStrategyGeneratorStreaming();
    mockSymbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA'];
    progressEvents = [];
    
    // Mock the streaming API call since AWS Bedrock isn't available
    jest.spyOn(streamingGenerator, 'callClaudeStreaming').mockImplementation(async () => {
      // Simulate streaming response chunks
      const mockChunks = [
        { chunk: { bytes: new TextEncoder().encode(JSON.stringify({ type: 'content_block_delta', delta: { text: '{"name": "AI Momentum Strategy",' } })) } },
        { chunk: { bytes: new TextEncoder().encode(JSON.stringify({ type: 'content_block_delta', delta: { text: '"description": "Advanced momentum strategy using moving averages",' } })) } },
        { chunk: { bytes: new TextEncoder().encode(JSON.stringify({ type: 'content_block_delta', delta: { text: '"code": "import pandas as pd\\nimport numpy as np\\n' } })) } },
        { chunk: { bytes: new TextEncoder().encode(JSON.stringify({ type: 'content_block_delta', delta: { text: 'def generate_signals(data):\\n    signals = []\\n' } })) } },
        { chunk: { bytes: new TextEncoder().encode(JSON.stringify({ type: 'content_block_delta', delta: { text: '    for symbol in data:\\n        signals.append("buy")\\n' } })) } },
        { chunk: { bytes: new TextEncoder().encode(JSON.stringify({ type: 'content_block_delta', delta: { text: '    return signals"}' } })) } }
      ];
      
      return {
        async *[Symbol.asyncIterator]() {
          for (const chunk of mockChunks) {
            await new Promise(resolve => setTimeout(resolve, 100)); // Simulate streaming delay
            yield chunk;
          }
        }
      };
    });

    // Mock inherited methods from base AIStrategyGenerator
    jest.spyOn(streamingGenerator, 'buildSystemPrompt').mockReturnValue('Mock system prompt');
    jest.spyOn(streamingGenerator, 'buildUserPrompt').mockReturnValue('Mock user prompt');
    jest.spyOn(streamingGenerator, 'parseClaudeResponse').mockResolvedValue({
      name: 'AI Momentum Strategy',
      description: 'Advanced momentum strategy using moving averages',
      code: 'def generate_signals(data): return ["buy"]',
      parameters: { short_window: 10, long_window: 30 }
    });
    jest.spyOn(streamingGenerator, 'validateAndEnhanceStrategy').mockImplementation(async (strategy) => ({
      ...strategy,
      validated: true,
      insights: ['Strategy uses momentum indicators', 'Suitable for trending markets']
    }));
    jest.spyOn(streamingGenerator, 'generateAIMetadata').mockResolvedValue({
      complexity: 'medium',
      riskLevel: 'moderate',
      expectedReturns: '8-12% annually'
    });
    jest.spyOn(streamingGenerator, 'generateAIVisualConfig').mockResolvedValue({
      chartType: 'candlestick',
      indicators: ['SMA', 'EMA'],
      colors: { bullish: '#00ff00', bearish: '#ff0000' }
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Core Streaming Functionality', () => {
    test('should generate strategy with streaming progress updates', async () => {
      const onProgress = jest.fn((event) => {
        progressEvents.push(event);
      });

      const result = await streamingGenerator.generateWithStreaming(
        'Create a momentum strategy using moving averages',
        mockSymbols,
        { assetType: 'stock' },
        onProgress
      );

      // Verify result structure
      expect(result).toHaveProperty('success', true);
      expect(result).toHaveProperty('streamId');
      expect(result).toHaveProperty('strategy');
      expect(result).toHaveProperty('visualConfig');
      expect(result).toHaveProperty('aiInsights');

      // Verify strategy properties
      expect(result.strategy).toHaveProperty('name', 'AI Momentum Strategy');
      expect(result.strategy).toHaveProperty('aiGenerated', true);
      expect(result.strategy).toHaveProperty('streamGenerated', true);
      expect(result.strategy).toHaveProperty('timestamp');
      expect(result.strategy).toHaveProperty('correlationId');

      // Verify progress updates were called
      expect(onProgress).toHaveBeenCalled();
      expect(progressEvents.length).toBeGreaterThan(0);

      // Verify progress event structure
      const progressEvent = progressEvents.find(e => e.type === 'progress');
      expect(progressEvent).toBeDefined();
      expect(progressEvent).toHaveProperty('streamId');
      expect(progressEvent).toHaveProperty('chunk');
      expect(progressEvent).toHaveProperty('progress');
      expect(progressEvent).toHaveProperty('accumulated');

      // Verify completion event
      const completionEvent = progressEvents.find(e => e.type === 'complete');
      expect(completionEvent).toBeDefined();
      expect(completionEvent).toHaveProperty('result');
    });

    test('should handle streaming without progress callback', async () => {
      const result = await streamingGenerator.generateWithStreaming(
        'Create a simple trading strategy',
        mockSymbols
      );

      expect(result).toHaveProperty('success', true);
      expect(result).toHaveProperty('strategy');
    });

    test('should generate unique stream IDs', async () => {
      const streamId1 = streamingGenerator.generateStreamId();
      const streamId2 = streamingGenerator.generateStreamId();

      expect(streamId1).toMatch(/^stream-\d+-[a-z0-9]+$/);
      expect(streamId2).toMatch(/^stream-\d+-[a-z0-9]+$/);
      expect(streamId1).not.toBe(streamId2);
    });
  });

  describe('Stream Management', () => {
    test('should track active streams', async () => {
      const onProgress = jest.fn();
      const initialMetrics = streamingGenerator.getStreamingMetrics();
      expect(initialMetrics.activeStreams).toBe(0);

      // Start streaming (don't await to keep it active)
      const streamPromise = streamingGenerator.generateWithStreaming(
        'Create a strategy',
        mockSymbols,
        {},
        onProgress
      );

      // Check metrics during streaming (may be 0 or 1 depending on timing)
      const duringMetrics = streamingGenerator.getStreamingMetrics();
      expect(duringMetrics.maxConcurrentStreams).toBe(5);
      expect(duringMetrics.streamingEnabled).toBe(true);

      // Wait for completion
      await streamPromise;

      // Check final metrics
      const finalMetrics = streamingGenerator.getStreamingMetrics();
      expect(finalMetrics.activeStreams).toBe(0);
    });

    test('should enforce maximum concurrent streams', async () => {
      // Set low limit for testing
      streamingGenerator.streamingConfig.maxConcurrentStreams = 1;

      // Mock a long-running stream
      jest.spyOn(streamingGenerator, 'callClaudeStreaming').mockImplementation(async () => {
        return {
          async *[Symbol.asyncIterator]() {
            await new Promise(resolve => setTimeout(resolve, 1000));
            yield { chunk: { bytes: new TextEncoder().encode(JSON.stringify({ type: 'content_block_delta', delta: { text: '{"name": "Strategy"}' } })) } };
          }
        };
      });

      // Start first stream
      const stream1Promise = streamingGenerator.generateWithStreaming('Strategy 1', mockSymbols);

      // Try to start second stream immediately
      await expect(
        streamingGenerator.generateWithStreaming('Strategy 2', mockSymbols)
      ).rejects.toThrow('Maximum concurrent streams reached');

      // Wait for first stream to complete
      await stream1Promise;
    });

    test('should get stream status', async () => {
      const streamId = streamingGenerator.generateStreamId();
      
      // Non-existent stream
      const notFoundStatus = streamingGenerator.getStreamStatus(streamId);
      expect(notFoundStatus.status).toBe('not_found');

      // Active stream would be tested during actual streaming
      // For now, just verify the method exists and returns expected structure
      expect(typeof streamingGenerator.getStreamStatus).toBe('function');
    });

    test('should cancel streams', () => {
      const streamId = streamingGenerator.generateStreamId();
      
      // Cancel non-existent stream
      const result1 = streamingGenerator.cancelStream(streamId);
      expect(result1).toBe(false);

      // Add a mock active stream
      streamingGenerator.activeStreams.set(streamId, { status: 'active', startTime: Date.now() });
      
      // Cancel existing stream
      const result2 = streamingGenerator.cancelStream(streamId);
      expect(result2).toBe(true);
      expect(streamingGenerator.activeStreams.has(streamId)).toBe(false);
    });
  });

  describe('Progress Analysis', () => {
    test('should analyze streaming progress correctly', () => {
      const testCases = [
        {
          text: '',
          expectedStage: 'Initializing',
          minProgress: 0
        },
        {
          text: '{"name": "Test Strategy", "description": "A test strategy that uses advanced technical indicators to generate trading signals based on market momentum and trend analysis"}',
          expectedStage: 'Creating strategy metadata',
          minProgress: 20
        },
        {
          text: '{"name": "Test Strategy", "code": "# This is the beginning of the strategy code generation process", "description": "Strategy"}',
          expectedStage: 'Starting code generation',
          minProgress: 50
        },
        {
          text: 'import pandas as pd\nimport numpy as np\nimport talib\nfrom datetime import datetime\n# Setting up all required libraries for technical analysis',
          expectedStage: 'Setting up imports and parameters',
          minProgress: 50
        },
        {
          text: 'def generate_signals(data):\n    signals = []\n    for symbol in data:\n        # Process each symbol individually with technical indicators',
          expectedStage: 'Implementing strategy logic',
          minProgress: 5
        },
        {
          text: 'signals.append("buy")\nsignals.append("sell")\nreturn processed_signals # Final signal processing complete with all conditions met',
          expectedStage: 'Finalizing trade signals',
          minProgress: 85
        },
        {
          text: 'return signals}}\n# Strategy generation complete with all metadata and implementation ready for deployment and backtesting',
          expectedStage: 'Completing strategy',
          minProgress: 95
        }
      ];

      testCases.forEach(({ text, expectedStage, minProgress }) => {
        const progress = streamingGenerator.analyzeStreamingProgress(text);
        
        expect(progress).toHaveProperty('percentage');
        expect(progress).toHaveProperty('stage', expectedStage);
        expect(progress).toHaveProperty('estimatedTimeRemaining');
        expect(progress.percentage).toBeGreaterThanOrEqual(minProgress);
        expect(progress.estimatedTimeRemaining).toBeGreaterThanOrEqual(0);
      });
    });

    test('should determine generation stages correctly', () => {
      const stages = [
        { text: '', expected: 'Initializing' },
        { text: '{"name": "Strategy", "description": "A strategy that uses advanced technical indicators to generate trading signals based on market momentum and trend analysis"}', expected: 'Creating strategy metadata' },
        { text: '{"name": "Strategy", "code": "# This is the beginning of the strategy code generation process", "description": "Strategy"}', expected: 'Starting code generation' },
        { text: 'import pandas as pd\\nimport numpy as np\\nimport talib\\nfrom datetime import datetime\\n# Setting up all required libraries', expected: 'Setting up imports and parameters' },
        { text: 'def generate_signals(data):\\n    signals = []\\n    for symbol in symbols:\\n        # Process each symbol individually', expected: 'Implementing strategy logic' },
        { text: 'for symbol in symbols:\\n    if condition_met:\\n        signals.append("buy")\\n        portfolio.add_position(symbol)', expected: 'Implementing strategy logic' },
        { text: 'signals.append("buy")\\nsignals.append("sell")\\nreturn processed_signals # Final signal processing complete', expected: 'Finalizing trade signals' },
        { text: 'return signals}}\\n# Strategy generation complete with all metadata and implementation ready for deployment', expected: 'Completing strategy' },
        { text: 'random text with more than 100 characters to make sure it is not considered initializing phase because the logic checks for length', expected: 'Generating strategy' }
      ];

      stages.forEach(({ text, expected }) => {
        const stage = streamingGenerator.determineGenerationStage(text);
        expect(stage).toBe(expected);
      });
    });

    test('should estimate time remaining correctly', () => {
      const testCases = [
        { progress: 0, expectedMax: 10000 },
        { progress: 50, expectedMax: 5000 },
        { progress: 90, expectedMax: 1000 },
        { progress: 100, expectedMin: 0, expectedMax: 0 }
      ];

      testCases.forEach(({ progress, expectedMin = 0, expectedMax }) => {
        const timeRemaining = streamingGenerator.estimateTimeRemaining(progress);
        expect(timeRemaining).toBeGreaterThanOrEqual(expectedMin);
        expect(timeRemaining).toBeLessThanOrEqual(expectedMax);
      });
    });
  });

  describe('Error Handling', () => {
    test('should handle streaming errors gracefully', async () => {
      // Mock streaming error
      jest.spyOn(streamingGenerator, 'callClaudeStreaming').mockRejectedValue(
        new Error('Streaming connection failed')
      );

      const onProgress = jest.fn();

      await expect(
        streamingGenerator.generateWithStreaming(
          'Create a strategy',
          mockSymbols,
          {},
          onProgress
        )
      ).rejects.toThrow('Streaming connection failed');

      // Verify error was sent to progress callback
      expect(onProgress).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'error',
          error: 'Streaming connection failed'
        })
      );
    });

    test('should clean up streams on error', async () => {
      jest.spyOn(streamingGenerator, 'callClaudeStreaming').mockRejectedValue(
        new Error('Test error')
      );

      const initialCount = streamingGenerator.activeStreams.size;

      try {
        await streamingGenerator.generateWithStreaming('Create a strategy', mockSymbols);
      } catch (error) {
        // Expected to throw
      }

      // Verify stream was cleaned up
      expect(streamingGenerator.activeStreams.size).toBe(initialCount);
    });
  });

  describe('Configuration and Metrics', () => {
    test('should provide streaming metrics', () => {
      const metrics = streamingGenerator.getStreamingMetrics();

      expect(metrics).toHaveProperty('activeStreams');
      expect(metrics).toHaveProperty('maxConcurrentStreams', 5);
      expect(metrics).toHaveProperty('streamingEnabled', true);
      expect(metrics).toHaveProperty('averageStreamDuration');

      expect(typeof metrics.activeStreams).toBe('number');
      expect(typeof metrics.averageStreamDuration).toBe('number');
    });

    test('should calculate average stream duration', () => {
      // No active streams
      expect(streamingGenerator.calculateAverageStreamDuration()).toBe(0);

      // Add mock active streams
      const now = Date.now();
      streamingGenerator.activeStreams.set('stream1', { status: 'active', startTime: now - 5000 });
      streamingGenerator.activeStreams.set('stream2', { status: 'active', startTime: now - 3000 });

      const avgDuration = streamingGenerator.calculateAverageStreamDuration();
      expect(avgDuration).toBeGreaterThan(3000);
      expect(avgDuration).toBeLessThan(6000);

      // Clean up
      streamingGenerator.activeStreams.clear();
    });

    test('should have correct streaming configuration', () => {
      const config = streamingGenerator.streamingConfig;

      expect(config).toHaveProperty('enabled', true);
      expect(config).toHaveProperty('chunkSize', 1024);
      expect(config).toHaveProperty('timeout', 30000);
      expect(config).toHaveProperty('maxConcurrentStreams', 5);
    });
  });

  describe('Integration with Base Class', () => {
    test('should inherit from AIStrategyGenerator', () => {
      expect(streamingGenerator.constructor.name).toBe('AIStrategyGeneratorStreaming');
      expect(streamingGenerator).toHaveProperty('logger');
      expect(streamingGenerator).toHaveProperty('correlationId');
      expect(streamingGenerator).toHaveProperty('aiConfig');
    });

    test('should use inherited methods for strategy parsing', async () => {
      const onProgress = jest.fn();
      
      await streamingGenerator.generateWithStreaming(
        'Create a strategy',
        mockSymbols,
        {},
        onProgress
      );

      // Verify inherited methods were called
      expect(streamingGenerator.buildSystemPrompt).toHaveBeenCalled();
      expect(streamingGenerator.buildUserPrompt).toHaveBeenCalled();
      expect(streamingGenerator.parseClaudeResponse).toHaveBeenCalled();
      expect(streamingGenerator.validateAndEnhanceStrategy).toHaveBeenCalled();
      expect(streamingGenerator.generateAIMetadata).toHaveBeenCalled();
      expect(streamingGenerator.generateAIVisualConfig).toHaveBeenCalled();
    });
  });
});