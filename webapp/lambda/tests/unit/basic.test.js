// Jest globals are automatically available

describe("Lambda Backend - Basic Functionality Tests", () => {
  describe("Module Loading", () => {
    test("should load database module without errors", () => {
      expect(() => {
        require("../../utils/database");
      }).not.toThrow();
    });

    test("should load API key service without errors", () => {
      expect(() => {
        require("../../utils/apiKeyService");
      }).not.toThrow();
    });

    test("should load auth middleware without errors", () => {
      expect(() => {
        require("../../middleware/auth");
      }).not.toThrow();
    });

    test("should load error handler middleware without errors", () => {
      expect(() => {
        require("../../middleware/errorHandler");
      }).not.toThrow();
    });

    test("should load main index file without errors", () => {
      // Temporarily suppress console warnings for this test
      const originalWarn = console.warn;
      console.warn = () => {};

      expect(() => {
        require("../../index");
      }).not.toThrow();

      // Restore console.warn
      console.warn = originalWarn;
    });
  });

  describe("Environment Configuration", () => {
    test("should handle missing environment variables gracefully", () => {
      // Clear environment variables
      const originalCognitoPoolId = process.env.COGNITO_USER_POOL_ID;
      const originalCognitoClientId = process.env.COGNITO_CLIENT_ID;

      delete process.env.COGNITO_USER_POOL_ID;
      delete process.env.COGNITO_CLIENT_ID;

      expect(() => {
        // Clear module cache to reload with new env vars
        delete require.cache[require.resolve("../../middleware/auth")];
        require("../../middleware/auth");
      }).not.toThrow();

      // Restore original values
      if (originalCognitoPoolId)
        process.env.COGNITO_USER_POOL_ID = originalCognitoPoolId;
      if (originalCognitoClientId)
        process.env.COGNITO_CLIENT_ID = originalCognitoClientId;
    });
  });

  describe("Database Module", () => {
    test("should export required functions", () => {
      const database = require("../../utils/database");

      expect(typeof database.initializeDatabase).toBe("function");
      expect(typeof database.query).toBe("function");
      expect(typeof database.healthCheck).toBe("function");
      expect(typeof database.closeDatabase).toBe("function");
      expect(typeof database.transaction).toBe("function");
      expect(typeof database.getPool).toBe("function");
    });
  });

  describe("API Key Service Module", () => {
    test("should export required functions", () => {
      const apiKeyService = require("../../utils/apiKeyService");

      // API key service exports an object with methods
      expect(typeof apiKeyService.listProviders).toBe("function");
      expect(typeof apiKeyService.storeApiKey).toBe("function");
      expect(typeof apiKeyService.validateJwtToken).toBe("function");
      expect(typeof apiKeyService.getHealthStatus).toBe("function");
    });
  });

  describe("Express App", () => {
    test("should create Express app successfully", () => {
      const originalWarn = console.warn;
      console.warn = () => {}; // Suppress warnings

      const { app } = require("../../index");
      expect(app).toBeDefined();
      expect(typeof app.listen).toBe("function");

      console.warn = originalWarn;
    });
  });

  describe("Route Loading", () => {
    test("should load all route modules without errors", () => {
      const routes = [
        "health",
        "stocks",
        "portfolio",
        "settings",
        "market",
        "technical",
        "financials",
        "trading",
      ];

      routes.forEach((route) => {
        expect(() => {
          require(`../../routes/${route}`);
        }).not.toThrow();
      });
    });
  });

  describe("Utility Functions", () => {
    test("should handle basic JavaScript operations", () => {
      expect(1 + 1).toBe(2);
      expect("hello".toUpperCase()).toBe("HELLO");
      expect([1, 2, 3].length).toBe(3);
    });

    test("should handle async operations", async () => {
      const asyncFunction = async () => {
        return new Promise((resolve) =>
          setTimeout(() => resolve("success"), 10)
        );
      };

      const result = await asyncFunction();
      expect(result).toBe("success");
    });

    test("should handle error objects", () => {
      const error = new Error("Test error");
      expect(error.message).toBe("Test error");
      expect(error.name).toBe("Error");
      expect(error.stack).toBeDefined();
    });
  });

  describe("JSON Operations", () => {
    test("should parse and stringify JSON correctly", () => {
      const obj = { test: "value", number: 42, array: [1, 2, 3] };
      const jsonString = JSON.stringify(obj);
      const parsed = JSON.parse(jsonString);

      expect(parsed).toEqual(obj);
    });

    test("should handle JSON errors gracefully", () => {
      expect(() => {
        JSON.parse("invalid json");
      }).toThrow();
    });
  });

  describe("Node.js Core Modules", () => {
    test("should load crypto module", () => {
      expect(() => {
        require("crypto");
      }).not.toThrow();
    });

    test("should load path module", () => {
      expect(() => {
        require("path");
      }).not.toThrow();
    });

    test("should load fs module", () => {
      expect(() => {
        require("fs");
      }).not.toThrow();
    });
  });
});
