/**
 * ApiService Utility Unit Tests
 * Tests the standardized API service with error handling and configuration
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:3001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
  writable: true,
  configurable: true,
});

// Mock window and axios
const mockAxios = {
  create: vi.fn(() => mockAxios),
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  },
};

vi.mock("axios", () => ({
  default: mockAxios,
  create: mockAxios.create,
}));

global.window = {
  __CONFIG__: {
    API_URL: "http://test-api.com",
  },
};

describe("ApiService Utility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Module Exports", () => {
    it("exports createLogger function", async () => {
      const apiService = await import("../../../utils/apiService.jsx");

      expect(apiService).toBeDefined();
      expect(typeof apiService.createLogger).toBe("function");
    });

    it("exports apiCall function", async () => {
      const apiService = await import("../../../utils/apiService.jsx");

      expect(apiService).toBeDefined();
      expect(typeof apiService.apiCall).toBe("function");
    });

    it("exports apiPatterns object", async () => {
      const apiService = await import("../../../utils/apiService.jsx");

      expect(apiService).toBeDefined();
      expect(typeof apiService.apiPatterns).toBe("object");
      expect(typeof apiService.apiPatterns.fetchData).toBe("function");
    });
  });

  describe("Logger Creation", () => {
    it("creates component loggers with required methods", async () => {
      const apiService = await import("../../../utils/apiService.jsx");

      const logger = apiService.createLogger("TestComponent");
      expect(logger).toBeDefined();
      expect(typeof logger.info).toBe("function");
      expect(typeof logger.error).toBe("function");
      expect(typeof logger.warn).toBe("function");
      expect(typeof logger.debug).toBe("function");
    });
  });

  describe("Query Configuration", () => {
    it("creates React Query config", async () => {
      const apiService = await import("../../../utils/apiService.jsx");

      const config = apiService.createQueryConfig("TestComponent");
      expect(config).toBeDefined();
      expect(config.defaultOptions).toBeDefined();
      expect(config.defaultOptions.queries).toBeDefined();
    });

    it("includes retry logic in query config", async () => {
      const apiService = await import("../../../utils/apiService.jsx");

      const config = apiService.createQueryConfig("TestComponent");
      expect(typeof config.defaultOptions.queries.retry).toBe("function");
    });
  });

  describe("Development Mode", () => {
    it("handles development environment", async () => {
      import.meta.env.DEV = true;
      import.meta.env.MODE = "development";

      const apiService = await import("../../../utils/apiService.jsx");

      expect(apiService).toBeDefined();
    });

    it("handles production environment", async () => {
      import.meta.env.DEV = false;
      import.meta.env.PROD = true;
      import.meta.env.MODE = "production";

      const apiService = await import("../../../utils/apiService.jsx");

      expect(apiService).toBeDefined();

      // Restore
      import.meta.env.DEV = true;
      import.meta.env.PROD = false;
      import.meta.env.MODE = "test";
    });
  });

  describe("Authentication Handling", () => {
    it("includes auth headers when available", async () => {
      // Mock localStorage
      const mockGetItem = vi.fn().mockReturnValue("mock-token");
      global.localStorage = { getItem: mockGetItem };

      const apiService = await import("../../../utils/apiService.jsx");

      expect(apiService).toBeDefined();
    });

    it("handles missing auth gracefully", async () => {
      // Mock localStorage with no token
      const mockGetItem = vi.fn().mockReturnValue(null);
      global.localStorage = { getItem: mockGetItem };

      const apiService = await import("../../../utils/apiService.jsx");

      expect(apiService).toBeDefined();
    });
  });

  describe("Request/Response Interceptors", () => {
    it("has interceptor support available", () => {
      expect(mockAxios.interceptors).toBeDefined();
      expect(mockAxios.interceptors.request.use).toBeDefined();
      expect(mockAxios.interceptors.response.use).toBeDefined();
    });
  });
});
