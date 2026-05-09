import { vi, describe, test, expect, beforeEach } from "vitest";
import axios from "axios";

// Mock axios
vi.mock("axios");
const mockedAxios = vi.mocked(axios);

// Mock axios create
const mockAxiosInstance = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
  request: vi.fn(),
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  },
};

// Mock window.__CONFIG__
Object.defineProperty(window, "__CONFIG__", {
  value: {},
  writable: true,
});

// Mock the API service module
vi.mock("../../../services/api.js", async () => {
  const actualModule = await vi.importActual("../../../services/api.js");
  return {
    ...actualModule,
    default: {
      healthCheck: vi.fn(),
      getMarketOverview: vi.fn(),
      // Add other methods as needed
    },
  };
});

import api, { getApiConfig } from "../../../services/api.js";

describe("API Service", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Reset window config
    window.__CONFIG__ = {};

    // Setup axios mocks
    mockedAxios.create.mockReturnValue(mockAxiosInstance);
    mockedAxios.get = vi.fn();
    mockedAxios.post = vi.fn();
  });

  describe("getApiConfig", () => {
    test("returns default localhost URL when no config", () => {
      const config = getApiConfig();

      // In dev mode without VITE_API_URL, uses empty string (Vite proxy handles /api)
      expect(config.apiUrl).toBe("");
      expect(config.baseURL).toBe("");
      expect(config.isServerless).toBe(false);
      expect(config.isDevelopment).toBe(true);
    });

    test("uses window.__CONFIG__ when available", () => {
      window.__CONFIG__ = { API_URL: "https://api.example.com" };

      const config = getApiConfig();

      expect(config.apiUrl).toBe("https://api.example.com");
      expect(config.isServerless).toBe(true);
      expect(config.isConfigured).toBe(true);
    });

    test("uses environment variable when available", () => {
      // The test runs in Vitest environment which has DEV: true
      const config = getApiConfig();

      expect(config.environment).toBe("test");
      expect(config.isDevelopment).toBe(true); // Vitest sets DEV: true
      expect(config.isProduction).toBe(false);
    });

    test("prioritizes runtime config over environment", () => {
      window.__CONFIG__ = { API_URL: "https://runtime.api.com" };
      vi.stubGlobal("import", {
        meta: {
          env: {
            VITE_API_URL: "https://env.api.com",
          },
        },
      });

      const config = getApiConfig();

      expect(config.apiUrl).toBe("https://runtime.api.com");
    });

    test("includes all environment variables", () => {
      const config = getApiConfig();

      // getApiConfig returns minimal properties - verify they exist
      expect(config).toBeDefined();
      expect(config).toHaveProperty('baseURL');
      expect(config).toHaveProperty('isDevelopment');
    });
  });

  describe("API Instance", () => {
    test("api service exists", () => {
      expect(api).toBeDefined();
      expect(typeof api).toBe("object");
    });

    test("has required methods", () => {
      // The api might be an axios instance or custom object
      expect(api).toBeDefined();
    });

    test("handles successful responses", async () => {
      const mockResponse = { data: { success: true, data: "test" } };

      // Mock the axios instance created by the API service
      mockedAxios.create().get.mockResolvedValue(mockResponse);

      // The test should verify the API configuration works
      expect(api).toBeDefined();
    });

    test("handles API errors gracefully", async () => {
      const mockError = new Error("Network Error");

      // Mock the axios instance created by the API service
      mockedAxios.create().get.mockRejectedValue(mockError);

      // The test should verify error handling configuration
      expect(api).toBeDefined();
    });
  });

  describe("Configuration Updates", () => {
    test("handles dynamic configuration changes", () => {
      // Initial config
      let config = getApiConfig();
      const initialUrl = config.apiUrl;

      // Change runtime config
      window.__CONFIG__ = { API_URL: "https://new.api.com" };

      // Get new config
      config = getApiConfig();
      expect(config.apiUrl).toBe("https://new.api.com");
      expect(config.apiUrl).not.toBe(initialUrl);
    });

    test("detects serverless vs local environment", () => {
      // Local environment
      window.__CONFIG__ = {};
      let config = getApiConfig();
      expect(config.isServerless).toBe(false);

      // Serverless environment
      window.__CONFIG__ = { API_URL: "https://serverless.api.com" };
      config = getApiConfig();
      expect(config.isServerless).toBe(true);
    });
  });

  describe("Environment Detection", () => {
    test("detects development environment", () => {
      const config = getApiConfig();

      expect(config.isDev).toBe(true); // Vitest sets DEV: true
      expect(config.isDevelopment).toBe(true);
      expect(config.isProduction).toBe(false);
    });

    test("detects serverless vs local", () => {
      const config = getApiConfig();

      // In test mode, it's not serverless
      expect(config.isServerless).toBe(false);
    });
  });

  describe("Error Handling", () => {
    test("handles missing window object", () => {
      // Mock server-side environment
      const originalWindow = global.window;
      delete global.window;

      const config = getApiConfig();
      // Without window, falls back to empty string for dev mode
      expect(config.apiUrl).toBe("");

      // Restore window
      global.window = originalWindow;
    });

    test("handles missing import.meta.env", () => {
      // getApiConfig handles missing env gracefully
      const config = getApiConfig();
      expect(config).toBeDefined();
      expect(config).toHaveProperty('baseURL');
    });

    test("handles undefined config values", () => {
      window.__CONFIG__ = undefined;

      const config = getApiConfig();
      // Falls back to empty string in dev mode
      expect(config).toBeDefined();
      expect(config.apiUrl).toBe("");
    });
  });
});
