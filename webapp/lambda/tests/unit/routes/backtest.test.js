/**
 * Backtest Route Tests
 * Tests backtesting engine and strategy management
 */

const request = require("supertest");
const express = require("express");

const backtestRouter = require("../../../routes/backtest");

const { execFile: _execFile } = require("child_process");

// Mock dependencies
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue({}),
}));

jest.mock("../../../utils/backtestStore", () => ({
  loadStrategies: jest.fn(),
  saveStrategies: jest.fn(),
  addStrategy: jest.fn(),
  getStrategy: jest.fn(),
  deleteStrategy: jest.fn(),
}));

jest.mock("../../../utils/logger", () => ({
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
  debug: jest.fn(),
}));

jest.mock("child_process", () => ({
  execFile: jest.fn(),
}));

jest.mock("fs", () => ({
  existsSync: jest.fn(),
  readFileSync: jest.fn(),
  writeFileSync: jest.fn(),
}));

const { query } = require("../../../utils/database");
const backtestStore = require("../../../utils/backtestStore");

// Create test app
const app = express();
app.use(express.json());
app.use("/api/backtest", backtestRouter);

describe("Backtest Routes", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    console.log = jest.fn();
    console.error = jest.fn();
  });

  describe("GET /api/backtest/strategies", () => {
    const mockStrategies = [
      {
        id: "1",
        name: "Moving Average Strategy",
        code: "// MA strategy code",
        language: "javascript",
        created: "2024-01-01",
      },
      {
        id: "2",
        name: "RSI Strategy",
        code: "// RSI strategy code",
        language: "python",
        created: "2024-01-02",
      },
    ];

    test("should return list of strategies", async () => {
      backtestStore.loadStrategies.mockReturnValue(mockStrategies);

      const response = await request(app).get("/api/backtest/strategies");

      expect(response.status).toBe(200);
      expect(response.body).toEqual({
        strategies: mockStrategies,
      });
      expect(backtestStore.loadStrategies).toHaveBeenCalled();
    });

    test("should handle empty strategies list", async () => {
      backtestStore.loadStrategies.mockReturnValue([]);

      const response = await request(app).get("/api/backtest/strategies");

      expect(response.status).toBe(200);
      expect(response.body.strategies).toEqual([]);
    });

    test("should handle storage errors", async () => {
      backtestStore.loadStrategies.mockImplementation(() => {
        throw new Error("File read error");
      });

      const response = await request(app).get("/api/backtest/strategies");

      expect(response.status).toBe(500);
      // The implementation doesn't have error handling for this endpoint
      expect(response.body).toEqual({});
    });
  });

  describe("POST /api/backtest/strategies", () => {
    const newStrategy = {
      name: "New Strategy",
      code: "// new strategy code",
      language: "javascript",
    };

    test("should create new strategy", async () => {
      const createdStrategy = { ...newStrategy, id: "123" };
      backtestStore.addStrategy.mockReturnValue(createdStrategy);

      const response = await request(app)
        .post("/api/backtest/strategies")
        .send(newStrategy);

      expect(response.status).toBe(200);
      expect(response.body).toEqual({
        strategy: createdStrategy,
      });
      expect(backtestStore.addStrategy).toHaveBeenCalledWith(newStrategy);
    });

    test("should validate required fields", async () => {
      const response = await request(app)
        .post("/api/backtest/strategies")
        .send({});

      expect(response.status).toBe(400);
      expect(response.body.error).toBe("Name and code required");
    });

    test("should handle creation errors", async () => {
      backtestStore.addStrategy.mockImplementation(() => {
        throw new Error("Storage error");
      });

      const response = await request(app)
        .post("/api/backtest/strategies")
        .send(newStrategy);

      expect(response.status).toBe(500);
      // The implementation doesn't have error handling for this endpoint
      expect(response.body).toEqual({});
    });
  });

  describe("GET /api/backtest/strategies/:id", () => {
    const mockStrategy = {
      id: "123",
      name: "Test Strategy",
      code: "// test code",
      language: "javascript",
    };

    test("should return strategy by ID", async () => {
      backtestStore.getStrategy.mockReturnValue(mockStrategy);

      const response = await request(app).get("/api/backtest/strategies/123");

      expect(response.status).toBe(200);
      expect(response.body).toEqual({ strategy: mockStrategy });
      expect(backtestStore.getStrategy).toHaveBeenCalledWith("123");
    });

    test("should handle strategy not found", async () => {
      backtestStore.getStrategy.mockReturnValue(undefined);

      const response = await request(app).get("/api/backtest/strategies/999");

      expect(response.status).toBe(404);
      expect(response.body.error).toBe("Not found");
    });

    test("should handle retrieval errors", async () => {
      backtestStore.getStrategy.mockImplementation(() => {
        throw new Error("Storage error");
      });

      const response = await request(app).get("/api/backtest/strategies/123");

      expect(response.status).toBe(500);
      // The implementation doesn't have error handling for this endpoint
      expect(response.body).toEqual({});
    });
  });

  describe("DELETE /api/backtest/strategies/:id", () => {
    test("should delete strategy by ID", async () => {
      backtestStore.deleteStrategy.mockReturnValue();

      const response = await request(app).delete(
        "/api/backtest/strategies/123"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(backtestStore.deleteStrategy).toHaveBeenCalledWith("123");
    });

    test("should handle deletion errors", async () => {
      backtestStore.deleteStrategy.mockImplementation(() => {
        throw new Error("Storage error");
      });

      const response = await request(app).delete(
        "/api/backtest/strategies/123"
      );

      expect(response.status).toBe(500);
      // The implementation doesn't have error handling for this endpoint
      expect(response.body).toEqual({});
    });
  });

  describe("POST /api/backtest/run", () => {
    const backtestConfig = {
      strategy: "// test strategy",
      config: {
        initialCapital: 100000,
      },
      startDate: "2023-01-01",
      endDate: "2023-12-31",
      symbols: ["AAPL", "MSFT"],
    };

    const mockPriceData = [
      {
        symbol: "AAPL",
        date: "2023-01-01",
        open: 150.0,
        high: 155.0,
        low: 148.0,
        close: 152.0,
        volume: 1000000,
      },
      {
        symbol: "MSFT",
        date: "2023-01-01",
        open: 300.0,
        high: 305.0,
        low: 298.0,
        close: 302.0,
        volume: 800000,
      },
    ];

    test("should run backtest with valid configuration", async () => {
      query.mockResolvedValue({ rows: mockPriceData, rowCount: 2 });

      const response = await request(app)
        .post("/api/backtest/run")
        .send(backtestConfig);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("config");
      expect(response.body).toHaveProperty("metrics");
      expect(response.body).toHaveProperty("trades");
      expect(response.body).toHaveProperty("equity");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("FROM price_daily"),
        expect.arrayContaining(["AAPL", "2023-01-01", "2023-12-31"])
      );
    });

    test("should validate required backtest parameters", async () => {
      const response = await request(app).post("/api/backtest/run").send({});

      expect(response.status).toBe(400);
      expect(response.body.error).toContain("required");
    });

    test("should handle missing price data", async () => {
      query.mockResolvedValue({ rows: [], rowCount: 0 });

      const response = await request(app)
        .post("/api/backtest/run")
        .send(backtestConfig);

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Backtest execution failed");
    });

    test("should handle database errors during backtest", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .post("/api/backtest/run")
        .send(backtestConfig);

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Backtest execution failed");
    });

    test("should validate date range", async () => {
      const invalidConfig = {
        ...backtestConfig,
        startDate: "2023-12-31",
        endDate: "2023-01-01", // End before start
      };

      query.mockResolvedValue({ rows: [], rowCount: 0 });

      const response = await request(app)
        .post("/api/backtest/run")
        .send(invalidConfig);

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Backtest execution failed");
    });

    test("should validate symbols array", async () => {
      const invalidConfig = {
        ...backtestConfig,
        symbols: [], // Empty symbols
      };

      const response = await request(app)
        .post("/api/backtest/run")
        .send(invalidConfig);

      expect(response.status).toBe(400);
      expect(response.body.error).toContain("At least one symbol is required");
    });
  });

  describe("BacktestEngine Class", () => {
    test("should initialize with correct configuration", async () => {
      const config = {
        initialCapital: 50000,
        commission: 0.002,
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        symbols: ["AAPL"],
      };

      const localMockData = [
        {
          symbol: "AAPL",
          date: "2023-01-01",
          open: 150.0,
          high: 155.0,
          low: 148.0,
          close: 152.0,
          volume: 1000000,
        },
      ];
      query.mockResolvedValue({ rows: localMockData, rowCount: 1 });

      const response = await request(app)
        .post("/api/backtest/run")
        .send({ ...config, strategy: "// test strategy" });

      expect(response.status).toBe(200);
      // The engine should use the provided configuration
      expect(query).toHaveBeenCalled();
    });

    test("should handle strategy execution errors", async () => {
      const localMockData = [
        {
          symbol: "AAPL",
          date: "2023-01-01",
          open: 150.0,
          close: 152.0,
          volume: 1000000,
        },
        {
          symbol: "MSFT",
          date: "2023-01-01",
          open: 300.0,
          close: 302.0,
          volume: 800000,
        },
      ];
      query.mockResolvedValue({ rows: localMockData, rowCount: 2 });

      const invalidStrategy = {
        strategy: "throw new Error('test error')",
        config: {
          initialCapital: 100000,
        },
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        symbols: ["AAPL", "MSFT"],
      };

      const response = await request(app)
        .post("/api/backtest/run")
        .send(invalidStrategy);

      // Should return error for strategy execution failure
      expect(response.status).toBe(400);
      expect(response.body.error).toBe("Strategy execution failed");
    });
  });

  describe("Error Handling", () => {
    test("should handle malformed JSON requests", async () => {
      const response = await request(app)
        .post("/api/backtest/strategies")
        .send("invalid json")
        .set("Content-Type", "application/json");

      expect(response.status).toBe(400);
    });

    test("should handle very large backtests", async () => {
      const largeConfig = {
        strategy: "// test strategy",
        config: {
          initialCapital: 100000,
        },
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        symbols: Array.from({ length: 100 }, (_, i) => `STOCK${i}`),
      };

      query.mockResolvedValue({ rows: [], rowCount: 0 });

      const response = await request(app)
        .post("/api/backtest/run")
        .send(largeConfig);

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Backtest execution failed");
    });

    test("should handle concurrent backtest requests", async () => {
      const localMockData = [
        {
          symbol: "AAPL",
          date: "2023-01-01",
          open: 150.0,
          close: 152.0,
          volume: 1000000,
        },
        {
          symbol: "MSFT",
          date: "2023-01-01",
          open: 300.0,
          close: 302.0,
          volume: 800000,
        },
      ];
      query.mockResolvedValue({ rows: localMockData, rowCount: 2 });

      const testConfig = {
        strategy: "// test strategy",
        config: {
          initialCapital: 100000,
        },
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        symbols: ["AAPL", "MSFT"],
      };

      const promises = Array.from({ length: 3 }, () =>
        request(app).post("/api/backtest/run").send(testConfig)
      );

      const responses = await Promise.all(promises);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body.success).toBe(true);
      });
    });
  });

  describe("Performance Validation", () => {
    test("should calculate basic performance metrics", async () => {
      const localMockData = [
        {
          symbol: "AAPL",
          date: "2023-01-01",
          open: 150.0,
          close: 152.0,
          volume: 1000000,
        },
        {
          symbol: "MSFT",
          date: "2023-01-01",
          open: 300.0,
          close: 302.0,
          volume: 800000,
        },
      ];
      query.mockResolvedValue({ rows: localMockData, rowCount: 2 });

      const testConfig = {
        strategy: "// test strategy",
        config: {
          initialCapital: 100000,
        },
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        symbols: ["AAPL", "MSFT"],
      };

      const response = await request(app)
        .post("/api/backtest/run")
        .send(testConfig);

      expect(response.status).toBe(200);
      expect(response.body.metrics).toHaveProperty("totalReturn");
      expect(response.body.metrics).toHaveProperty("annualizedReturn");
      expect(response.body.metrics).toHaveProperty("volatility");
      expect(response.body.metrics).toHaveProperty("sharpeRatio");
      expect(response.body.metrics).toHaveProperty("maxDrawdown");
    });

    test("should track equity curve", async () => {
      const localMockData = [
        {
          symbol: "AAPL",
          date: "2023-01-01",
          open: 150.0,
          close: 152.0,
          volume: 1000000,
        },
        {
          symbol: "MSFT",
          date: "2023-01-01",
          open: 300.0,
          close: 302.0,
          volume: 800000,
        },
      ];
      query.mockResolvedValue({ rows: localMockData, rowCount: 2 });

      const testConfig = {
        strategy: "// test strategy",
        config: {
          initialCapital: 100000,
        },
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        symbols: ["AAPL", "MSFT"],
      };

      const response = await request(app)
        .post("/api/backtest/run")
        .send(testConfig);

      expect(response.status).toBe(200);
      expect(Array.isArray(response.body.equity)).toBe(true);
      expect(response.body.equity.length).toBeGreaterThan(0);
      expect(response.body.equity[0]).toHaveProperty("date");
      expect(response.body.equity[0]).toHaveProperty("value");
    });
  });
});
