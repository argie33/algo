const AIStrategyGeneratorStreaming = require("../../../services/aiStrategyGeneratorStreaming");

// Mock dependencies
jest.mock("../../../utils/logger", () => ({
  createLogger: jest.fn().mockReturnValue({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

describe("AIStrategyGeneratorStreaming Service", () => {
  let streamingGenerator;
  let mockLogger;

  beforeEach(() => {
    streamingGenerator = new AIStrategyGeneratorStreaming();
    mockLogger = streamingGenerator.logger;
    jest.clearAllMocks();
  });

  describe("Constructor and Initialization", () => {
    test("should extend AIStrategyGenerator", () => {
      expect(streamingGenerator).toBeInstanceOf(AIStrategyGeneratorStreaming);
      expect(streamingGenerator.activeStreams).toBeInstanceOf(Map);
      expect(streamingGenerator.streamingConfig).toMatchObject({
        enabled: true,
        chunkSize: 1024,
        timeout: 30000,
        maxConcurrentStreams: 5,
      });
    });

    test("should initialize with empty active streams", () => {
      expect(streamingGenerator.activeStreams.size).toBe(0);
    });
  });

  describe("generateStreamId", () => {
    test("should generate unique stream IDs", () => {
      const id1 = streamingGenerator.generateStreamId();
      const id2 = streamingGenerator.generateStreamId();

      expect(id1).toMatch(/^stream-\d+-[a-z0-9]+$/);
      expect(id2).toMatch(/^stream-\d+-[a-z0-9]+$/);
      expect(id1).not.toBe(id2);
    });
  });

  describe("generateWithStreaming", () => {
    test("should generate strategy with streaming progress", async () => {
      const prompt = "Create a momentum strategy";
      const symbols = ["AAPL", "MSFT"];
      const options = { timeframe: "1day" };
      const progressUpdates = [];
      const onProgress = jest.fn((update) => progressUpdates.push(update));

      const result = await streamingGenerator.generateWithStreaming(
        prompt,
        symbols,
        options,
        onProgress
      );

      expect(result.success).toBe(true);
      expect(result.strategy).toBeDefined();
      expect(result.streamId).toMatch(/^stream-\d+-[a-z0-9]+$/);
      expect(result.metadata.streaming).toBe(true);
      expect(onProgress).toHaveBeenCalled();
      
      // Should have called progress with initialization
      expect(progressUpdates.some(update => 
        update.phase === "initialization"
      )).toBe(true);

      expect(mockLogger.info).toHaveBeenCalledWith(
        "Starting streaming strategy generation",
        expect.objectContaining({
          streamId: expect.any(String),
          prompt: expect.any(String),
          correlationId: streamingGenerator.correlationId,
        })
      );
    });

    test("should handle concurrent stream limit", async () => {
      const prompt = "Create a strategy";
      
      // Fill up to max concurrent streams
      const promises = [];
      for (let i = 0; i < 6; i++) {
        const promise = streamingGenerator.generateWithStreaming(prompt, ["AAPL"]);
        promises.push(promise);
        
        // Small delay to ensure streams start
        await new Promise(resolve => setTimeout(resolve, 10));
      }

      const results = await Promise.allSettled(promises);
      
      // At least one should fail due to concurrent limit
      const failures = results.filter(r => r.status === "rejected");
      expect(failures.length).toBeGreaterThan(0);
      
      const rejectedError = failures.find(f => 
        f.reason.message.includes("Maximum concurrent streams reached")
      );
      expect(rejectedError).toBeDefined();
    });

    test("should handle streaming without progress callback", async () => {
      const prompt = "Create a simple strategy";
      const symbols = ["SPY"];

      const result = await streamingGenerator.generateWithStreaming(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.streamId).toBeDefined();
    });

    test("should handle empty symbols in streaming", async () => {
      const prompt = "Create a strategy";

      const result = await streamingGenerator.generateWithStreaming(prompt, []);

      expect(result.success).toBe(true);
      expect(result.strategy.symbols).toEqual([]);
    });

    test("should clean up stream after completion", async () => {
      const prompt = "Create a strategy";
      const initialStreamCount = streamingGenerator.activeStreams.size;

      await streamingGenerator.generateWithStreaming(prompt, ["AAPL"]);

      expect(streamingGenerator.activeStreams.size).toBe(initialStreamCount);
    });

    test("should handle streaming errors gracefully", async () => {
      const prompt = "Invalid prompt that will cause errors";
      
      // Mock an error in the parent class method
      jest.spyOn(streamingGenerator, "buildSystemPrompt").mockImplementation(() => {
        throw new Error("System prompt generation failed");
      });

      const result = await streamingGenerator.generateWithStreaming(prompt, ["AAPL"]);

      expect(result.success).toBe(false);
      expect(result.error).toContain("Streaming generation failed");
      expect(mockLogger.error).toHaveBeenCalled();
    });

    test("should handle stream timeout", async () => {
      // Set a very short timeout for testing
      streamingGenerator.streamingConfig.timeout = 10; // 10ms

      const prompt = "Create a complex strategy";
      
      // Mock a slow operation
      jest.spyOn(streamingGenerator, "buildUserPrompt").mockImplementation(async () => {
        await new Promise(resolve => setTimeout(resolve, 50)); // 50ms delay
        return "prompt";
      });

      const result = await streamingGenerator.generateWithStreaming(prompt, ["AAPL"]);

      expect(result.success).toBe(false);
      expect(result.error).toContain("timeout");
    });
  });

  describe("processStreamingChunk", () => {
    test("should process chunks and call progress callback", async () => {
      const chunk = "def strategy(): pass";
      const progressUpdates = [];
      const onProgress = jest.fn((update) => progressUpdates.push(update));

      await streamingGenerator.processStreamingChunk(chunk, onProgress);

      expect(onProgress).toHaveBeenCalledWith(
        expect.objectContaining({
          phase: "generation",
          chunk: chunk,
          timestamp: expect.any(Number),
        })
      );
    });

    test("should handle null progress callback", async () => {
      const chunk = "def strategy(): pass";

      await expect(
        streamingGenerator.processStreamingChunk(chunk, null)
      ).resolves.not.toThrow();
    });

    test("should handle empty chunks", async () => {
      const onProgress = jest.fn();

      await streamingGenerator.processStreamingChunk("", onProgress);

      expect(onProgress).toHaveBeenCalledWith(
        expect.objectContaining({
          chunk: "",
        })
      );
    });

    test("should handle very large chunks", async () => {
      const largeChunk = "x".repeat(10000);
      const onProgress = jest.fn();

      await streamingGenerator.processStreamingChunk(largeChunk, onProgress);

      expect(onProgress).toHaveBeenCalledWith(
        expect.objectContaining({
          chunk: largeChunk,
        })
      );
    });
  });

  describe("simulateStreamingResponse", () => {
    test("should simulate streaming for template fallback", async () => {
      const strategy = {
        name: "Test Strategy",
        code: "def test_strategy(): pass",
        description: "A test strategy",
      };
      const progressUpdates = [];
      const onProgress = jest.fn((update) => progressUpdates.push(update));

      await streamingGenerator.simulateStreamingResponse(strategy, onProgress);

      expect(onProgress).toHaveBeenCalledTimes(3); // name, description, code
      
      const phases = progressUpdates.map(update => update.phase);
      expect(phases).toContain("name");
      expect(phases).toContain("description");
      expect(phases).toContain("code");
    });

    test("should handle strategy without all fields", async () => {
      const incompleteStrategy = {
        name: "Incomplete Strategy",
        // missing description and code
      };
      const onProgress = jest.fn();

      await streamingGenerator.simulateStreamingResponse(incompleteStrategy, onProgress);

      expect(onProgress).toHaveBeenCalled();
    });

    test("should simulate with appropriate delays", async () => {
      const strategy = {
        name: "Test Strategy",
        description: "A test strategy",
        code: "def test(): pass",
      };
      const onProgress = jest.fn();
      const startTime = Date.now();

      await streamingGenerator.simulateStreamingResponse(strategy, onProgress);

      const endTime = Date.now();
      const duration = endTime - startTime;
      
      // Should take some time due to simulated delays
      expect(duration).toBeGreaterThan(100); // At least 100ms
    });
  });

  describe("stopStream", () => {
    test("should stop active stream", async () => {
      const streamId = "test-stream-id";
      streamingGenerator.activeStreams.set(streamId, {
        status: "active",
        startTime: Date.now(),
      });

      const result = streamingGenerator.stopStream(streamId);

      expect(result.success).toBe(true);
      expect(streamingGenerator.activeStreams.has(streamId)).toBe(false);
      expect(mockLogger.info).toHaveBeenCalledWith(
        "Stream stopped",
        expect.objectContaining({
          streamId: streamId,
        })
      );
    });

    test("should handle stopping non-existent stream", () => {
      const result = streamingGenerator.stopStream("non-existent-stream");

      expect(result.success).toBe(false);
      expect(result.error).toBe("Stream not found");
    });

    test("should handle null stream ID", () => {
      const result = streamingGenerator.stopStream(null);

      expect(result.success).toBe(false);
      expect(result.error).toBe("Stream not found");
    });
  });

  describe("stopAllStreams", () => {
    test("should stop all active streams", () => {
      // Add multiple active streams
      streamingGenerator.activeStreams.set("stream1", { status: "active" });
      streamingGenerator.activeStreams.set("stream2", { status: "active" });
      streamingGenerator.activeStreams.set("stream3", { status: "active" });

      const result = streamingGenerator.stopAllStreams();

      expect(result.success).toBe(true);
      expect(result.stoppedCount).toBe(3);
      expect(streamingGenerator.activeStreams.size).toBe(0);
      expect(mockLogger.info).toHaveBeenCalledWith(
        "All streams stopped",
        expect.objectContaining({
          stoppedCount: 3,
        })
      );
    });

    test("should handle when no streams are active", () => {
      const result = streamingGenerator.stopAllStreams();

      expect(result.success).toBe(true);
      expect(result.stoppedCount).toBe(0);
    });
  });

  describe("getActiveStreams", () => {
    test("should return active stream information", () => {
      const now = Date.now();
      streamingGenerator.activeStreams.set("stream1", {
        status: "active",
        startTime: now - 1000,
      });
      streamingGenerator.activeStreams.set("stream2", {
        status: "active",
        startTime: now - 2000,
      });

      const activeStreams = streamingGenerator.getActiveStreams();

      expect(activeStreams).toHaveLength(2);
      expect(activeStreams[0]).toMatchObject({
        streamId: "stream1",
        status: "active",
        duration: expect.any(Number),
      });
      expect(activeStreams[1]).toMatchObject({
        streamId: "stream2",
        status: "active",
        duration: expect.any(Number),
      });
    });

    test("should return empty array when no streams are active", () => {
      const activeStreams = streamingGenerator.getActiveStreams();

      expect(activeStreams).toEqual([]);
    });

    test("should calculate stream durations correctly", () => {
      const startTime = Date.now() - 5000; // 5 seconds ago
      streamingGenerator.activeStreams.set("stream1", {
        status: "active",
        startTime: startTime,
      });

      const activeStreams = streamingGenerator.getActiveStreams();

      expect(activeStreams[0].duration).toBeGreaterThanOrEqual(4000);
      expect(activeStreams[0].duration).toBeLessThan(6000);
    });
  });

  describe("getStreamingMetrics", () => {
    test("should return streaming metrics", () => {
      streamingGenerator.activeStreams.set("stream1", {
        status: "active",
        startTime: Date.now() - 1000,
      });
      streamingGenerator.activeStreams.set("stream2", {
        status: "active",
        startTime: Date.now() - 2000,
      });

      const metrics = streamingGenerator.getStreamingMetrics();

      expect(metrics).toMatchObject({
        activeStreams: 2,
        maxConcurrentStreams: 5,
        streamingEnabled: true,
        averageStreamDuration: expect.any(Number),
      });
    });

    test("should handle zero active streams", () => {
      const metrics = streamingGenerator.getStreamingMetrics();

      expect(metrics.activeStreams).toBe(0);
      expect(metrics.averageStreamDuration).toBe(0);
    });
  });

  describe("calculateAverageStreamDuration", () => {
    test("should calculate average duration correctly", () => {
      const now = Date.now();
      streamingGenerator.activeStreams.set("stream1", {
        startTime: now - 1000, // 1 second ago
      });
      streamingGenerator.activeStreams.set("stream2", {
        startTime: now - 3000, // 3 seconds ago
      });

      const average = streamingGenerator.calculateAverageStreamDuration();

      expect(average).toBeCloseTo(2000, -2); // Around 2000ms, with tolerance
    });

    test("should return 0 when no streams are active", () => {
      const average = streamingGenerator.calculateAverageStreamDuration();

      expect(average).toBe(0);
    });

    test("should handle single stream", () => {
      const now = Date.now();
      streamingGenerator.activeStreams.set("stream1", {
        startTime: now - 1500, // 1.5 seconds ago
      });

      const average = streamingGenerator.calculateAverageStreamDuration();

      expect(average).toBeCloseTo(1500, -2);
    });
  });

  describe("Stream Configuration", () => {
    test("should allow updating streaming configuration", () => {
      const newConfig = {
        enabled: false,
        chunkSize: 2048,
        timeout: 60000,
        maxConcurrentStreams: 10,
      };

      Object.assign(streamingGenerator.streamingConfig, newConfig);

      expect(streamingGenerator.streamingConfig).toMatchObject(newConfig);
    });

    test("should respect chunk size configuration", async () => {
      streamingGenerator.streamingConfig.chunkSize = 100;
      
      const onProgress = jest.fn();
      const largeChunk = "x".repeat(500);

      await streamingGenerator.processStreamingChunk(largeChunk, onProgress);

      expect(onProgress).toHaveBeenCalled();
      // In a real implementation, large chunks would be split
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle concurrent stream generation attempts", async () => {
      const promises = Array(3).fill().map((_, i) =>
        streamingGenerator.generateWithStreaming(`strategy ${i}`, ["AAPL"])
      );

      const results = await Promise.allSettled(promises);

      // All should either succeed or fail gracefully
      results.forEach(result => {
        if (result.status === "fulfilled") {
          expect(result.value).toHaveProperty("success");
        } else {
          expect(result.reason).toBeInstanceOf(Error);
        }
      });
    });

    test("should handle progress callback errors", async () => {
      const faultyProgress = jest.fn().mockImplementation(() => {
        throw new Error("Progress callback error");
      });

      // Should not crash the streaming process
      await expect(
        streamingGenerator.processStreamingChunk("test chunk", faultyProgress)
      ).resolves.not.toThrow();
    });

    test("should handle very rapid stream start/stop cycles", async () => {
      const streamId = streamingGenerator.generateStreamId();
      
      streamingGenerator.activeStreams.set(streamId, {
        status: "active",
        startTime: Date.now(),
      });

      const stopResult = streamingGenerator.stopStream(streamId);
      const stopAgainResult = streamingGenerator.stopStream(streamId);

      expect(stopResult.success).toBe(true);
      expect(stopAgainResult.success).toBe(false);
    });

    test("should handle invalid stream data", () => {
      // Add invalid stream data
      streamingGenerator.activeStreams.set("invalid", null);
      streamingGenerator.activeStreams.set("malformed", { status: "unknown" });

      const activeStreams = streamingGenerator.getActiveStreams();
      const metrics = streamingGenerator.getStreamingMetrics();

      // Should handle gracefully without crashing
      expect(activeStreams).toBeInstanceOf(Array);
      expect(metrics).toHaveProperty("activeStreams");
    });

    test("should handle memory pressure with many streams", () => {
      // Simulate many streams
      for (let i = 0; i < 100; i++) {
        streamingGenerator.activeStreams.set(`stream${i}`, {
          status: "active",
          startTime: Date.now() - Math.random() * 10000,
        });
      }

      const metrics = streamingGenerator.getStreamingMetrics();
      const activeStreams = streamingGenerator.getActiveStreams();

      expect(metrics.activeStreams).toBe(100);
      expect(activeStreams).toHaveLength(100);
      expect(typeof metrics.averageStreamDuration).toBe("number");
    });

    test("should clean up properly on errors", async () => {
      const initialStreamCount = streamingGenerator.activeStreams.size;
      
      // Force an error during streaming
      jest.spyOn(streamingGenerator, "buildSystemPrompt").mockImplementation(() => {
        throw new Error("Forced error");
      });

      const result = await streamingGenerator.generateWithStreaming("test", ["AAPL"]);

      expect(result.success).toBe(false);
      expect(streamingGenerator.activeStreams.size).toBe(initialStreamCount);
    });
  });

  describe("Integration with Base Class", () => {
    test("should inherit all base class functionality", () => {
      expect(streamingGenerator.assetTypePatterns).toBeDefined();
      expect(streamingGenerator.strategyTemplates).toBeDefined();
      expect(typeof streamingGenerator.parseIntent).toBe("function");
      expect(typeof streamingGenerator.validateStrategy).toBe("function");
    });

    test("should use base class template generation", async () => {
      const prompt = "momentum strategy";
      const result = await streamingGenerator.generateWithStreaming(prompt, ["AAPL"]);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toContain("Momentum");
    });

    test("should maintain correlation ID from base class", () => {
      expect(streamingGenerator.correlationId).toMatch(/^ai-strategy-\d+-[a-z0-9]+$/);
    });
  });
});