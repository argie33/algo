/**
 * Response Formatter Integration Tests
 * Tests response formatting with real API responses and edge cases
 */

const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");
const responseFormatter = require("../../../utils/responseFormatter");

describe("Response Formatter Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Success Response Formatting", () => {
    test("should format successful API responses", () => {
      const testData = {
        symbol: "AAPL",
        price: 150.25,
        change: 2.5,
        changePercent: 1.68,
      };

      const formatted = responseFormatter.success(
        testData,
        "Stock data retrieved successfully"
      );

      expect(formatted).toBeDefined();
      expect(formatted.success).toBe(true);
      expect(formatted.data).toEqual(testData);
      expect(formatted.message).toBe("Stock data retrieved successfully");
      expect(formatted.timestamp).toBeDefined();
      expect(formatted.requestId).toBeDefined();
    });

    test("should handle array data in responses", () => {
      const testArray = [
        { symbol: "AAPL", price: 150.25 },
        { symbol: "GOOGL", price: 2800.5 },
        { symbol: "MSFT", price: 310.75 },
      ];

      const formatted = responseFormatter.success(
        testArray,
        "Portfolio data retrieved"
      );

      expect(formatted.success).toBe(true);
      expect(Array.isArray(formatted.data)).toBe(true);
      expect(formatted.data.length).toBe(3);
      expect(formatted.count).toBe(3);
      expect(formatted.message).toBe("Portfolio data retrieved");
    });

    test("should include pagination metadata", () => {
      const testData = Array.from({ length: 10 }, (_, i) => ({
        id: i,
        value: `item_${i}`,
      }));
      const paginationMeta = {
        page: 2,
        limit: 10,
        total: 50,
        totalPages: 5,
      };

      const formatted = responseFormatter.success(
        testData,
        "Paginated data retrieved",
        paginationMeta
      );

      expect(formatted.success).toBe(true);
      expect(formatted.data.length).toBe(10);
      expect(formatted.pagination).toEqual(paginationMeta);
      expect(formatted.pagination.hasNext).toBe(true);
      expect(formatted.pagination.hasPrevious).toBe(true);
    });
  });

  describe("Error Response Formatting", () => {
    test("should format client errors (4xx)", () => {
      const error = new Error("Invalid symbol provided");
      error.statusCode = 400;
      error.code = "INVALID_SYMBOL";

      const formatted = responseFormatter.error(error, "Bad Request");

      expect(formatted.success).toBe(false);
      expect(formatted.error).toBeDefined();
      expect(formatted.error.message).toBe("Invalid symbol provided");
      expect(formatted.error.code).toBe("INVALID_SYMBOL");
      expect(formatted.error.type).toBe("CLIENT_ERROR");
      expect(formatted.statusCode).toBe(400);
    });

    test("should format server errors (5xx)", () => {
      const error = new Error("Database connection failed");
      error.statusCode = 500;
      error.code = "DATABASE_ERROR";

      const formatted = responseFormatter.error(error, "Internal Server Error");

      expect(formatted.success).toBe(false);
      expect(formatted.error).toBeDefined();
      expect(formatted.error.message).toBe("Database connection failed");
      expect(formatted.error.code).toBe("DATABASE_ERROR");
      expect(formatted.error.type).toBe("SERVER_ERROR");
      expect(formatted.statusCode).toBe(500);
    });

    test("should sanitize sensitive data in error responses", () => {
      const error = new Error(
        "Authentication failed for API key: secret_key_12345"
      );
      error.statusCode = 401;
      error.sensitiveData = {
        apiKey: "secret_key_12345",
        password: "user_password",
        token: "jwt_token_abcdef",
      };

      const formatted = responseFormatter.error(error, "Unauthorized");

      expect(formatted.success).toBe(false);
      expect(formatted.error.message).not.toContain("secret_key_12345");
      expect(formatted.error.message).toContain("***");
      expect(formatted.error.sanitized).toBe(true);
    });
  });

  describe("Validation Error Formatting", () => {
    test("should format validation errors", () => {
      const validationErrors = [
        { field: "symbol", message: "Symbol is required" },
        { field: "quantity", message: "Quantity must be greater than 0" },
        { field: "price", message: "Price must be a positive number" },
      ];

      const formatted = responseFormatter.validationError(validationErrors);

      expect(formatted.success).toBe(false);
      expect(formatted.error).toBeDefined();
      expect(formatted.error.type).toBe("VALIDATION_ERROR");
      expect(formatted.error.details).toEqual(validationErrors);
      expect(formatted.error.count).toBe(3);
      expect(formatted.statusCode).toBe(422);
    });

    test("should handle single validation error", () => {
      const singleError = { field: "email", message: "Invalid email format" };

      const formatted = responseFormatter.validationError(singleError);

      expect(formatted.success).toBe(false);
      expect(formatted.error.details).toEqual([singleError]);
      expect(formatted.error.count).toBe(1);
    });
  });

  describe("Custom Response Formatting", () => {
    test("should handle custom response formats", () => {
      const customData = {
        analysis: {
          technicalScore: 85,
          fundamentalScore: 92,
          recommendation: "BUY",
        },
        factors: ["strong_earnings", "positive_momentum"],
        confidence: 0.87,
      };

      const customMeta = {
        analysisDate: new Date().toISOString(),
        model: "quantitative_v2.1",
        region: "US",
      };

      const formatted = responseFormatter.custom(
        customData,
        "analysis",
        customMeta
      );

      expect(formatted.success).toBe(true);
      expect(formatted.analysis).toEqual(customData.analysis);
      expect(formatted.factors).toEqual(customData.factors);
      expect(formatted.confidence).toBe(customData.confidence);
      expect(formatted.metadata).toEqual(customMeta);
    });

    test("should support nested response structures", () => {
      const complexData = {
        portfolio: {
          holdings: [
            { symbol: "AAPL", weight: 0.35, value: 50000 },
            { symbol: "GOOGL", weight: 0.25, value: 35000 },
          ],
          performance: {
            totalReturn: 0.125,
            sharpeRatio: 1.45,
            maxDrawdown: -0.08,
          },
          risk: {
            beta: 1.12,
            volatility: 0.18,
            var95: -0.03,
          },
        },
      };

      const formatted = responseFormatter.success(
        complexData,
        "Portfolio analysis complete"
      );

      expect(formatted.success).toBe(true);
      expect(formatted.data.portfolio.holdings.length).toBe(2);
      expect(formatted.data.portfolio.performance.totalReturn).toBe(0.125);
      expect(formatted.data.portfolio.risk.beta).toBe(1.12);
    });
  });

  describe("Data Transformation", () => {
    test("should transform numerical data with precision", () => {
      const financialData = {
        price: 150.123456789,
        volume: 1234567.89,
        marketCap: 2500000000000.123,
        ratio: 0.123456789,
      };

      const formatted = responseFormatter.success(
        financialData,
        "Financial data",
        null,
        {
          precision: {
            price: 2,
            volume: 0,
            marketCap: -9, // Billions
            ratio: 4,
          },
        }
      );

      expect(formatted.data.price).toBe(150.12);
      expect(formatted.data.volume).toBe(1234568);
      expect(formatted.data.marketCap).toBe(2500.0); // In billions
      expect(formatted.data.ratio).toBe(0.1235);
    });

    test("should handle date formatting", () => {
      const dateData = {
        createdAt: new Date("2023-01-15T10:30:00Z"),
        updatedAt: new Date("2023-01-16T15:45:30Z"),
        expiry: new Date("2023-12-31T23:59:59Z"),
      };

      const formatted = responseFormatter.success(dateData, "Date data", null, {
        dateFormat: "ISO",
        timezone: "UTC",
      });

      expect(formatted.data.createdAt).toBe("2023-01-15T10:30:00.000Z");
      expect(formatted.data.updatedAt).toBe("2023-01-16T15:45:30.000Z");
      expect(formatted.data.expiry).toBe("2023-12-31T23:59:59.000Z");
    });

    test("should filter sensitive fields", () => {
      const userData = {
        id: 12345,
        username: "testuser",
        email: "test@example.com",
        password: "secret_password",
        apiKey: "api_key_12345",
        creditCard: "4111-1111-1111-1111",
        profile: {
          name: "Test User",
          ssn: "123-45-6789",
        },
      };

      const formatted = responseFormatter.success(userData, "User data", null, {
        excludeFields: ["password", "apiKey", "creditCard", "profile.ssn"],
      });

      expect(formatted.data.id).toBe(12345);
      expect(formatted.data.username).toBe("testuser");
      expect(formatted.data.email).toBe("test@example.com");
      expect(formatted.data.password).toBeUndefined();
      expect(formatted.data.apiKey).toBeUndefined();
      expect(formatted.data.creditCard).toBeUndefined();
      expect(formatted.data.profile.name).toBe("Test User");
      expect(formatted.data.profile.ssn).toBeUndefined();
    });
  });

  describe("Performance and Caching", () => {
    test("should handle large response formatting efficiently", () => {
      const largeDataset = Array.from({ length: 10000 }, (_, i) => ({
        id: i,
        symbol: `STOCK${i}`,
        price: 123.45 + i * 0.5, // deterministic values
        volume: 50000 + i * 1000,
        timestamp: new Date().toISOString(),
      }));

      const startTime = Date.now();
      const formatted = responseFormatter.success(
        largeDataset,
        "Large dataset"
      );
      const duration = Date.now() - startTime;

      expect(formatted.success).toBe(true);
      expect(formatted.data.length).toBe(10000);
      expect(formatted.count).toBe(10000);
      expect(duration).toBeLessThan(1000); // Should format within 1 second
    });

    test("should cache formatted responses when configured", () => {
      const testData = { symbol: "AAPL", price: 150.25 };
      const cacheKey = "aapl_quote";

      const formatted1 = responseFormatter.success(
        testData,
        "Cached response",
        null,
        {
          cache: { key: cacheKey, ttl: 300 },
        }
      );

      const formatted2 = responseFormatter.success(
        testData,
        "Cached response",
        null,
        {
          cache: { key: cacheKey, ttl: 300 },
        }
      );

      expect(formatted1.cache).toBeDefined();
      expect(formatted1.cache.hit).toBe(false);
      expect(formatted2.cache.hit).toBe(true);
      expect(formatted1.requestId).not.toBe(formatted2.requestId);
    });
  });

  describe("Integration with Request Context", () => {
    test("should include request context in responses", () => {
      const contextData = {
        userId: "user123",
        sessionId: "session456",
        clientIP: "192.168.1.100",
        userAgent: "Mozilla/5.0",
        apiVersion: "v1.0",
      };

      const testData = { message: "Context test" };
      const formatted = responseFormatter.success(
        testData,
        "Success with context",
        null,
        {
          context: contextData,
        }
      );

      expect(formatted.success).toBe(true);
      expect(formatted.context).toBeDefined();
      expect(formatted.context.userId).toBe("user123");
      expect(formatted.context.sessionId).toBe("session456");
      expect(formatted.context.apiVersion).toBe("v1.0");
      // Sensitive data should be excluded from response
      expect(formatted.context.clientIP).toBeUndefined();
    });

    test("should track request timing", () => {
      const requestStart = Date.now() - 150; // Simulate 150ms request
      const testData = { result: "timing test" };

      const formatted = responseFormatter.success(
        testData,
        "Timing test",
        null,
        {
          timing: { startTime: requestStart },
        }
      );

      expect(formatted.timing).toBeDefined();
      expect(formatted.timing.duration).toBeGreaterThan(100);
      expect(formatted.timing.duration).toBeLessThan(1000);
      expect(formatted.timing.startTime).toBe(requestStart);
    });
  });

  describe("Error Recovery and Fallbacks", () => {
    test("should handle formatting errors gracefully", () => {
      const problematicData = {
        circular: null,
      };
      // Create circular reference
      problematicData.circular = problematicData;

      const formatted = responseFormatter.success(
        problematicData,
        "Problematic data"
      );

      expect(formatted.success).toBe(true);
      expect(formatted.data).toBeDefined();
      expect(formatted.warning).toBeDefined();
      expect(formatted.warning).toContain("circular");
    });

    test("should provide fallback formatting for unknown errors", () => {
      const unknownError = {
        name: "UnknownError",
        message: "Something went wrong",
        stack: "Error: Something went wrong\n    at test.js:1:1",
      };

      const formatted = responseFormatter.error(
        unknownError,
        "Unknown error occurred"
      );

      expect(formatted.success).toBe(false);
      expect(formatted.error).toBeDefined();
      expect(formatted.error.type).toBe("UNKNOWN_ERROR");
      expect(formatted.error.message).toBe("Something went wrong");
      expect(formatted.statusCode).toBe(500);
    });
  });

  describe("Content Negotiation", () => {
    test("should support different content types", () => {
      const testData = { symbol: "AAPL", price: 150.25 };

      const jsonFormatted = responseFormatter.success(
        testData,
        "JSON response",
        null,
        {
          contentType: "application/json",
        }
      );

      const xmlFormatted = responseFormatter.success(
        testData,
        "XML response",
        null,
        {
          contentType: "application/xml",
        }
      );

      expect(jsonFormatted.success).toBe(true);
      expect(xmlFormatted.success).toBe(true);
      expect(jsonFormatted.contentType).toBe("application/json");
      expect(xmlFormatted.contentType).toBe("application/xml");
    });

    test("should compress large responses when requested", () => {
      const largeData = Array.from({ length: 1000 }, (_, i) => ({
        id: i,
        data: "x".repeat(100),
      }));

      const formatted = responseFormatter.success(
        largeData,
        "Large response",
        null,
        {
          compression: { algorithm: "gzip", threshold: 1024 },
        }
      );

      expect(formatted.success).toBe(true);
      expect(formatted.compression).toBeDefined();
      expect(formatted.compression.applied).toBe(true);
      expect(formatted.compression.algorithm).toBe("gzip");
      expect(formatted.compression.originalSize).toBeGreaterThan(
        formatted.compression.compressedSize
      );
    });
  });
});
