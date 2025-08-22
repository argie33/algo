/**
 * WebSocket API Routes Tests
 * Tests for real-time market data streaming with API key authentication
 * Focus on critical API key dependencies
 */

const request = require("supertest");
const express = require("express");

// Set test environment
process.env.NODE_ENV = "test";

// Mock crypto module
jest.mock("crypto", () => ({
  randomUUID: jest.fn(() => "test-uuid-1234"),
}));

// Mock dependencies before requiring the route
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

jest.mock("../../../utils/responseFormatter", () => ({
  success: jest.fn((data) => ({ success: true, ...data })),
  error: jest.fn((message, code, details) => ({
    response: { success: false, error: message, code, ...details }
  })),
}));

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-id" };
    req.token = "test-jwt-token";
    next();
  },
}));

// Mock API key service with comprehensive functionality
const mockApiKeyService = {
  getDecryptedApiKey: jest.fn(),
  isEnabled: true,
  isLocalMode: false,
};
jest.mock("../../../utils/apiKeyService", () => mockApiKeyService);

// Mock AlpacaService 
const mockAlpacaInstance = {
  getLatestQuote: jest.fn(),
  getLatestTrade: jest.fn(),
  getBars: jest.fn(),
};

const mockAlpacaService = jest.fn(() => mockAlpacaInstance);
jest.mock("../../../utils/alpacaService", () => mockAlpacaService);

jest.mock("../../../middleware/validation", () => ({
  createValidationMiddleware: jest.fn(),
}));

// Set up timer mocks
jest.useFakeTimers();

const websocketRoutes = require("../../../routes/websocket");
const app = express();
app.use(express.json());
app.use("/api/websocket", websocketRoutes);

describe("WebSocket API Routes - API Key Dependencies", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAlpacaInstance.getLatestQuote.mockReset();
    mockAlpacaInstance.getLatestTrade.mockReset();
    mockAlpacaInstance.getBars.mockReset();
  });

  afterAll(() => {
    jest.useRealTimers();
  });

  describe("Basic Endpoints", () => {
    it("should return test endpoint status", async () => {
      const response = await request(app)
        .get("/api/websocket/test")
        .expect(200);

      expect(response.body.status).toBe("websocket route is working");
      expect(response.body.timestamp).toBeDefined();
    });

    it("should return health status with dependencies", async () => {
      const response = await request(app)
        .get("/api/websocket/health")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.service).toBe("websocket");
      expect(response.body.dependencies).toEqual({
        responseFormatter: true,
        apiKeyService: true,
        alpacaService: true,
        validationMiddleware: true,
      });
    });
  });

  describe("Stream Endpoint - Critical API Key Dependency", () => {
    it("should stream market data with valid API credentials", async () => {
      // Mock successful API key retrieval
      mockApiKeyService.getDecryptedApiKey.mockResolvedValue({
        apiKey: "test-alpaca-key",
        apiSecret: "test-alpaca-secret",
        isSandbox: true,
      });

      // Mock successful quote data
      mockAlpacaInstance.getLatestQuote.mockResolvedValue({
        bidPrice: 150.25,
        askPrice: 150.27,
        bidSize: 100,
        askSize: 200,
        timestamp: Date.now(),
      });

      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.symbols).toEqual(["AAPL"]);
      expect(response.body.data.AAPL).toMatchObject({
        symbol: "AAPL",
        bidPrice: 150.25,
        askPrice: 150.27,
        bidSize: 100,
        askSize: 200,
        cached: false,
      });

      expect(mockApiKeyService.getDecryptedApiKey).toHaveBeenCalledWith("test-user-id", "alpaca");
      expect(mockAlpacaInstance.getLatestQuote).toHaveBeenCalledWith("AAPL");
    });

    it("should return 400 when API credentials are missing", async () => {
      mockApiKeyService.getDecryptedApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "API credentials not configured",
        error_code: "API_CREDENTIALS_MISSING",
        provider: "alpaca",
      });

      expect(mockApiKeyService.getDecryptedApiKey).toHaveBeenCalledWith("test-user-id", "alpaca");
    });

    it("should handle API key retrieval errors", async () => {
      mockApiKeyService.getDecryptedApiKey.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to retrieve API credentials",
        error_code: "API_CREDENTIALS_ERROR",
      });
    });

    it("should handle Alpaca service initialization errors", async () => {
      mockApiKeyService.getDecryptedApiKey.mockResolvedValue({
        apiKey: "invalid-key",
        apiSecret: "invalid-secret",
        isSandbox: true,
      });

      // Mock constructor to throw error
      mockAlpacaService.mockImplementation(() => {
        throw new Error("Invalid API credentials");
      });

      const response = await request(app)
        .get("/api/websocket/stream/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to initialize live data service",
        error_code: "LIVE_DATA_SERVICE_INIT_ERROR",
        provider: "alpaca",
        environment: "sandbox",
      });
    });

    it("should handle invalid symbol validation", async () => {
      const response = await request(app)
        .get("/api/websocket/stream/INVALID!@#")
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "No valid symbols provided",
      });
    });
  });

  describe("Trades Endpoint - API Key Dependent", () => {
    it("should fetch trade data with valid credentials", async () => {
      mockApiKeyService.getDecryptedApiKey.mockResolvedValue({
        apiKey: "test-alpaca-key",
        apiSecret: "test-alpaca-secret",
        isSandbox: true,
      });

      mockAlpacaInstance.getLatestTrade.mockResolvedValue({
        price: 150.30,
        size: 100,
        timestamp: Date.now(),
        conditions: ["@"],
      });

      const response = await request(app)
        .get("/api/websocket/trades/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.AAPL).toMatchObject({
        symbol: "AAPL",
        price: 150.30,
        size: 100,
      });

      expect(mockApiKeyService.getDecryptedApiKey).toHaveBeenCalledWith("test-user-id", "alpaca");
      expect(mockAlpacaInstance.getLatestTrade).toHaveBeenCalledWith("AAPL");
    });

    it("should return 403 when API credentials are missing", async () => {
      mockApiKeyService.getDecryptedApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get("/api/websocket/trades/AAPL")
        .expect(403);

      expect(response.body).toMatchObject({
        success: false,
        error: "No Alpaca API key configured",
      });
    });
  });

  describe("Bars Endpoint - API Key Dependent", () => {
    it("should fetch bars data with valid credentials", async () => {
      mockApiKeyService.getDecryptedApiKey.mockResolvedValue({
        apiKey: "test-alpaca-key",
        apiSecret: "test-alpaca-secret",
        isSandbox: true,
      });

      const mockBarsData = [
        {
          timestamp: Date.now(),
          open: 150.00,
          high: 150.50,
          low: 149.80,
          close: 150.30,
          volume: 1000000,
        },
      ];

      mockAlpacaInstance.getBars.mockResolvedValue(mockBarsData);

      const response = await request(app)
        .get("/api/websocket/bars/AAPL?timeframe=1Min")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.AAPL).toEqual(mockBarsData);

      expect(mockApiKeyService.getDecryptedApiKey).toHaveBeenCalledWith("test-user-id", "alpaca");
      expect(mockAlpacaInstance.getBars).toHaveBeenCalledWith("AAPL", {
        timeframe: "1Min",
        start: expect.any(String),
        limit: 100,
      });
    });

    it("should return 403 when API credentials are missing", async () => {
      mockApiKeyService.getDecryptedApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get("/api/websocket/bars/AAPL")
        .expect(403);

      expect(response.body).toMatchObject({
        success: false,
        error: "No Alpaca API key configured",
      });
    });
  });

  describe("Subscription Management", () => {
    it("should subscribe to symbols successfully", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .send({
          symbols: ["AAPL", "TSLA"],
          dataTypes: ["quotes", "trades"],
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        subscribed: ["AAPL", "TSLA"],
        dataTypes: ["quotes", "trades"],
        message: "Subscribed to 2 symbols",
      });
    });

    it("should handle invalid symbols array", async () => {
      const response = await request(app)
        .post("/api/websocket/subscribe")
        .send({
          symbols: "invalid",
        })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "Invalid symbols array",
      });
    });

    it("should return current subscriptions", async () => {
      // First subscribe
      await request(app)
        .post("/api/websocket/subscribe")
        .send({ symbols: ["AAPL", "TSLA"] });

      // Then get subscriptions
      const response = await request(app)
        .get("/api/websocket/subscriptions")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        symbols: ["AAPL", "TSLA"],
        count: 2,
      });
    });

    it("should unsubscribe from symbols", async () => {
      // First subscribe
      await request(app)
        .post("/api/websocket/subscribe")
        .send({ symbols: ["AAPL", "TSLA", "MSFT"] });

      // Then unsubscribe from specific symbols
      const response = await request(app)
        .delete("/api/websocket/subscribe")
        .send({ symbols: ["AAPL", "TSLA"] })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Unsubscribed successfully",
        remainingSubscriptions: ["MSFT"],
      });
    });
  });
});