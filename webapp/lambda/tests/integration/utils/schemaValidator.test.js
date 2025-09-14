/**
 * Schema Validator Integration Tests
 * Tests data validation with real schemas and edge cases
 */

const { initializeDatabase, closeDatabase } = require("../../../utils/database");
const schemaValidator = require("../../../utils/schemaValidator");

describe("Schema Validator Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Stock Data Validation", () => {
    test("should validate stock quote data", () => {
      const validQuote = {
        symbol: "AAPL",
        price: 150.25,
        volume: 1000000,
        timestamp: "2023-01-15T10:30:00Z",
        change: 2.5,
        changePercent: 1.68
      };

      const validation = schemaValidator.validate(validQuote, 'stockQuote');
      
      expect(validation.isValid).toBe(true);
      expect(validation.errors).toEqual([]);
      expect(validation.sanitizedData).toBeDefined();
      expect(validation.sanitizedData.symbol).toBe("AAPL");
    });

    test("should reject invalid stock data", () => {
      const invalidQuote = {
        symbol: "", // Empty symbol
        price: -100, // Negative price
        volume: "invalid", // Non-numeric volume
        timestamp: "not-a-date", // Invalid date
        change: null,
        changePercent: undefined
      };

      const validation = schemaValidator.validate(invalidQuote, 'stockQuote');
      
      expect(validation.isValid).toBe(false);
      expect(Array.isArray(validation.errors)).toBe(true);
      expect(validation.errors.length).toBeGreaterThan(0);
      
      const errorFields = validation.errors.map(err => err.field);
      expect(errorFields).toContain('symbol');
      expect(errorFields).toContain('price');
      expect(errorFields).toContain('volume');
      expect(errorFields).toContain('timestamp');
    });

    test("should validate portfolio data", () => {
      const validPortfolio = {
        userId: "user123",
        holdings: [
          {
            symbol: "AAPL",
            quantity: 100,
            averageCost: 145.50,
            currentValue: 15025
          },
          {
            symbol: "GOOGL",
            quantity: 50,
            averageCost: 2800,
            currentValue: 140000
          }
        ],
        totalValue: 155025,
        cash: 10000,
        lastUpdated: "2023-01-15T15:30:00Z"
      };

      const validation = schemaValidator.validate(validPortfolio, 'portfolio');
      
      expect(validation.isValid).toBe(true);
      expect(validation.errors).toEqual([]);
      expect(validation.sanitizedData.holdings.length).toBe(2);
    });
  });

  describe("Trading Order Validation", () => {
    test("should validate buy order", () => {
      const buyOrder = {
        userId: "user123",
        symbol: "AAPL",
        side: "buy",
        type: "market",
        quantity: 100,
        timeInForce: "day",
        timestamp: new Date().toISOString()
      };

      const validation = schemaValidator.validate(buyOrder, 'tradingOrder');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.side).toBe("buy");
      expect(validation.sanitizedData.type).toBe("market");
      expect(validation.sanitizedData.quantity).toBe(100);
    });

    test("should validate limit order with price", () => {
      const limitOrder = {
        userId: "user123",
        symbol: "AAPL",
        side: "sell",
        type: "limit",
        quantity: 50,
        limitPrice: 155.00,
        timeInForce: "gtc",
        timestamp: new Date().toISOString()
      };

      const validation = schemaValidator.validate(limitOrder, 'tradingOrder');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.type).toBe("limit");
      expect(validation.sanitizedData.limitPrice).toBe(155.00);
    });

    test("should reject invalid trading orders", () => {
      const invalidOrder = {
        userId: "",
        symbol: "INVALID_SYMBOL_TOO_LONG",
        side: "invalid_side",
        type: "limit", // Limit order without price
        quantity: -10, // Negative quantity
        timeInForce: "invalid_tif"
      };

      const validation = schemaValidator.validate(invalidOrder, 'tradingOrder');
      
      expect(validation.isValid).toBe(false);
      expect(validation.errors.length).toBeGreaterThan(0);
      
      const errorCodes = validation.errors.map(err => err.code);
      expect(errorCodes).toContain('INVALID_USER_ID');
      expect(errorCodes).toContain('INVALID_SYMBOL');
      expect(errorCodes).toContain('INVALID_SIDE');
      expect(errorCodes).toContain('INVALID_QUANTITY');
    });
  });

  describe("User Data Validation", () => {
    test("should validate user registration data", () => {
      const userData = {
        username: "testuser123",
        email: "test@example.com",
        password: "SecurePass123!",
        firstName: "Test",
        lastName: "User",
        dateOfBirth: "1990-01-15",
        country: "US",
        riskTolerance: "moderate"
      };

      const validation = schemaValidator.validate(userData, 'userRegistration');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.email).toBe("test@example.com");
      expect(validation.sanitizedData.country).toBe("US");
      // Password should be excluded from sanitized data for security
      expect(validation.sanitizedData.password).toBeUndefined();
    });

    test("should validate API key configuration", () => {
      const apiKeyConfig = {
        userId: "user123",
        provider: "alpaca",
        keyId: "PKTEST12345678",
        secretKey: "encrypted_secret_key_data",
        environment: "paper",
        permissions: ["read", "trade"],
        isActive: true,
        createdAt: new Date().toISOString()
      };

      const validation = schemaValidator.validate(apiKeyConfig, 'apiKeyConfig');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.provider).toBe("alpaca");
      expect(validation.sanitizedData.environment).toBe("paper");
      expect(Array.isArray(validation.sanitizedData.permissions)).toBe(true);
    });
  });

  describe("Market Data Validation", () => {
    test("should validate technical indicators", () => {
      const technicalData = {
        symbol: "AAPL",
        timestamp: new Date().toISOString(),
        indicators: {
          sma20: 145.50,
          sma50: 150.25,
          rsi: 65.5,
          macd: {
            macd: 1.25,
            signal: 1.10,
            histogram: 0.15
          },
          bollinger: {
            upper: 155.00,
            middle: 150.00,
            lower: 145.00
          }
        }
      };

      const validation = schemaValidator.validate(technicalData, 'technicalIndicators');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.indicators.rsi).toBe(65.5);
      expect(validation.sanitizedData.indicators.macd.macd).toBe(1.25);
      expect(validation.sanitizedData.indicators.bollinger.upper).toBe(155.00);
    });

    test("should validate earnings data", () => {
      const earningsData = {
        symbol: "AAPL",
        quarter: "Q1",
        year: 2023,
        reportDate: "2023-04-28",
        estimatedEPS: 1.45,
        actualEPS: 1.52,
        estimatedRevenue: 95000000000,
        actualRevenue: 97000000000,
        surprise: {
          eps: 0.07,
          epsPercent: 4.83,
          revenue: 2000000000,
          revenuePercent: 2.11
        }
      };

      const validation = schemaValidator.validate(earningsData, 'earningsData');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.quarter).toBe("Q1");
      expect(validation.sanitizedData.year).toBe(2023);
      expect(validation.sanitizedData.surprise.epsPercent).toBe(4.83);
    });
  });

  describe("Real-time Data Validation", () => {
    test("should validate WebSocket message format", () => {
      const wsMessage = {
        type: "quote",
        symbol: "AAPL",
        data: {
          price: 150.25,
          size: 100,
          timestamp: Date.now(),
          exchange: "NASDAQ"
        },
        channel: "quotes",
        messageId: "msg_123456789"
      };

      const validation = schemaValidator.validate(wsMessage, 'webSocketMessage');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.type).toBe("quote");
      expect(validation.sanitizedData.symbol).toBe("AAPL");
      expect(validation.sanitizedData.data.price).toBe(150.25);
    });

    test("should validate streaming data batch", () => {
      const streamBatch = {
        batchId: "batch_123",
        timestamp: new Date().toISOString(),
        source: "alpaca",
        messages: [
          {
            type: "trade",
            symbol: "AAPL",
            price: 150.25,
            size: 100,
            timestamp: Date.now()
          },
          {
            type: "quote",
            symbol: "AAPL",
            bidPrice: 150.20,
            askPrice: 150.30,
            bidSize: 500,
            askSize: 300,
            timestamp: Date.now()
          }
        ]
      };

      const validation = schemaValidator.validate(streamBatch, 'streamingBatch');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.messages.length).toBe(2);
      expect(validation.sanitizedData.source).toBe("alpaca");
    });
  });

  describe("Custom Schema Validation", () => {
    test("should validate with custom schema", () => {
      const customSchema = {
        type: 'object',
        properties: {
          customField: { type: 'string', minLength: 1 },
          numericField: { type: 'number', minimum: 0 },
          arrayField: {
            type: 'array',
            items: { type: 'string' },
            minItems: 1
          }
        },
        required: ['customField', 'numericField']
      };

      const testData = {
        customField: "test_value",
        numericField: 42,
        arrayField: ["item1", "item2"]
      };

      const validation = schemaValidator.validateWithCustomSchema(testData, customSchema);
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.customField).toBe("test_value");
      expect(validation.sanitizedData.numericField).toBe(42);
    });

    test("should register and use persistent custom schemas", () => {
      const schemaName = "testCustomSchema";
      const schema = {
        type: 'object',
        properties: {
          id: { type: 'string' },
          value: { type: 'number' }
        },
        required: ['id']
      };

      // Register schema
      schemaValidator.registerSchema(schemaName, schema);
      
      // Use registered schema
      const testData = { id: "test_123", value: 456 };
      const validation = schemaValidator.validate(testData, schemaName);
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.id).toBe("test_123");
      expect(validation.sanitizedData.value).toBe(456);
    });
  });

  describe("Data Sanitization", () => {
    test("should sanitize and transform data", () => {
      const dirtyData = {
        symbol: "  aapl  ", // Trim and uppercase
        price: "150.25", // Convert to number
        timestamp: "2023-01-15T10:30:00.000Z", // Parse date
        description: "<script>alert('xss')</script>Safe content", // HTML sanitization
        tags: ["  tag1  ", "TAG2", "tag3  "] // Trim and normalize
      };

      const validation = schemaValidator.validate(dirtyData, 'stockQuote', {
        sanitize: true,
        transform: true
      });
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData.symbol).toBe("AAPL");
      expect(validation.sanitizedData.price).toBe(150.25);
      expect(validation.sanitizedData.description).not.toContain("<script>");
      expect(validation.sanitizedData.tags).toEqual(["tag1", "tag2", "tag3"]);
    });

    test("should handle SQL injection attempts", () => {
      const maliciousData = {
        symbol: "AAPL'; DROP TABLE stocks; --",
        userId: "user123' OR '1'='1",
        description: "'; DELETE FROM users WHERE '1'='1'; --"
      };

      const validation = schemaValidator.validate(maliciousData, 'stockQuote', {
        sanitize: true,
        sqlInjectionProtection: true
      });
      
      expect(validation.sanitized).toBe(true);
      expect(validation.sanitizedData.symbol).not.toContain("DROP TABLE");
      expect(validation.sanitizedData.userId).not.toContain("OR '1'='1");
      expect(validation.sanitizedData.description).not.toContain("DELETE FROM");
    });
  });

  describe("Performance and Scalability", () => {
    test("should validate large datasets efficiently", () => {
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        symbol: `STOCK${i}`,
        price: (i * 13 + 17) % 1000, // deterministic price
        volume: Math.floor((i * 19 + 23) % 1000000), // deterministic volume
        timestamp: new Date().toISOString()
      }));

      const startTime = Date.now();
      const validations = largeDataset.map(data => 
        schemaValidator.validate(data, 'stockQuote')
      );
      const duration = Date.now() - startTime;
      
      expect(validations.length).toBe(1000);
      expect(duration).toBeLessThan(5000); // Should validate 1000 items in under 5 seconds
      
      const validItems = validations.filter(v => v.isValid);
      expect(validItems.length).toBe(1000); // All should be valid
    });

    test("should cache compiled schemas for performance", () => {
      const testData = { symbol: "AAPL", price: 150.25 };
      
      // First validation (compiles schema)
      const startTime1 = Date.now();
      const validation1 = schemaValidator.validate(testData, 'stockQuote');
      const duration1 = Date.now() - startTime1;
      
      // Second validation (uses cached schema)
      const startTime2 = Date.now();
      const validation2 = schemaValidator.validate(testData, 'stockQuote');
      const duration2 = Date.now() - startTime2;
      
      expect(validation1.isValid).toBe(true);
      expect(validation2.isValid).toBe(true);
      expect(duration2).toBeLessThan(duration1); // Cached should be faster
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle malformed data gracefully", () => {
      const malformedData = [
        null,
        undefined,
        "",
        0,
        [],
        function() {}
      ];

      malformedData.forEach(data => {
        const validation = schemaValidator.validate(data, 'stockQuote');
        expect(validation.isValid).toBe(false);
        expect(validation.errors).toBeDefined();
        expect(Array.isArray(validation.errors)).toBe(true);
      });
    });

    test("should handle circular references", () => {
      const circularData = { symbol: "AAPL" };
      circularData.self = circularData; // Create circular reference
      
      const validation = schemaValidator.validate(circularData, 'stockQuote');
      
      expect(validation.isValid).toBe(false);
      expect(validation.errors.some(err => err.code === 'CIRCULAR_REFERENCE')).toBe(true);
    });

    test("should handle very large numbers", () => {
      const largeNumberData = {
        symbol: "AAPL",
        price: Number.MAX_SAFE_INTEGER + 1,
        volume: Infinity,
        marketCap: -Infinity
      };

      const validation = schemaValidator.validate(largeNumberData, 'stockQuote');
      
      expect(validation.isValid).toBe(false);
      expect(validation.errors.some(err => err.code === 'INVALID_NUMBER')).toBe(true);
    });
  });

  describe("Integration with Database", () => {
    test("should validate data before database insertion", async () => {
      const stockData = {
        symbol: "TEST",
        price: 100.00,
        volume: 50000,
        timestamp: new Date().toISOString()
      };

      const validation = await schemaValidator.validateForDatabase(stockData, 'stock_quotes');
      
      expect(validation.isValid).toBe(true);
      expect(validation.sanitizedData).toBeDefined();
      expect(validation.databaseReady).toBe(true);
    });

    test("should handle database constraint violations", async () => {
      const duplicateData = {
        symbol: "AAPL", // Assume this already exists
        price: 150.25,
        volume: 1000000,
        timestamp: new Date().toISOString()
      };

      const validation = await schemaValidator.validateForDatabase(duplicateData, 'stock_quotes');
      
      if (!validation.isValid) {
        expect(validation.errors.some(err => err.code === 'DUPLICATE_KEY')).toBeTruthy();
      }
    });
  });

  describe("Multi-language Support", () => {
    test("should support localized error messages", () => {
      const invalidData = {
        symbol: "",
        price: -100
      };

      const validationEn = schemaValidator.validate(invalidData, 'stockQuote', { 
        locale: 'en' 
      });
      const validationEs = schemaValidator.validate(invalidData, 'stockQuote', { 
        locale: 'es' 
      });

      expect(validationEn.isValid).toBe(false);
      expect(validationEs.isValid).toBe(false);
      expect(validationEn.errors[0].message).not.toBe(validationEs.errors[0].message);
    });
  });
});