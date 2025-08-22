// Module loading tests - no mocks to test actual module exports
// Jest globals are automatically available

describe("Module Loading Tests - No Mocks", () => {
  describe("Database Module", () => {
    test("should load database module without errors", () => {
      expect(() => {
        require("../../utils/database");
      }).not.toThrow();
    });

    test("should export required database functions", () => {
      // Clear any existing mock from global setup
      jest.unmock("../../utils/database");
      delete require.cache[require.resolve("../../utils/database")];
      
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
    test("should load API key service without errors", () => {
      expect(() => {
        require("../../utils/apiKeyService");
      }).not.toThrow();
    });

    test("should export required API key service functions", () => {
      // Clear any existing mock from global setup
      jest.unmock("../../utils/apiKeyService");
      delete require.cache[require.resolve("../../utils/apiKeyService")];
      
      const apiKeyService = require("../../utils/apiKeyService");
      
      // Test all required exports
      expect(typeof apiKeyService.listProviders).toBe("function");
      expect(typeof apiKeyService.storeApiKey).toBe("function");
      expect(typeof apiKeyService.validateJwtToken).toBe("function");
      expect(typeof apiKeyService.getHealthStatus).toBe("function");
      expect(typeof apiKeyService.getApiKey).toBe("function");
      expect(typeof apiKeyService.getDecryptedApiKey).toBe("function");
      expect(typeof apiKeyService.deleteApiKey).toBe("function");
    });
  });

  describe("Middleware Modules", () => {
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
  });

  describe("Express App", () => {
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

    test("should create Express app successfully", () => {
      const originalWarn = console.warn;
      console.warn = () => {}; // Suppress warnings

      const { app } = require("../../index");
      expect(app).toBeDefined();
      expect(typeof app.listen).toBe("function");

      console.warn = originalWarn;
    });
  });
});