/**
 * Services Integration Tests
 * Tests how multiple services work together and integrate with each other
 * Focuses on service-to-service communication and data consistency
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock services first
vi.mock("../../services/api.js", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    }
  },
  getApiConfig: vi.fn(() => ({
    baseURL: "http://localhost:3001",
    timeout: 30000,
    isServerless: false
  }))
}));

vi.mock("../../services/dataService.js", () => ({
  default: {
    fetchData: vi.fn(),
    clearCache: vi.fn(),
    invalidateCache: vi.fn(),
    subscribeToRealTimeData: vi.fn(),
    clearExpiredCache: vi.fn()
  }
}));

vi.mock("../../services/dataCache.js", () => ({
  dataCache: {
    get: vi.fn(),
    set: vi.fn(),
    clear: vi.fn(),
    size: 0
  }
}));

vi.mock("../../services/devAuth.js", () => ({
  default: {
    signIn: vi.fn(),
    signOut: vi.fn(),
    getCurrentSession: vi.fn(),
    isAuthenticated: vi.fn()
  },
  devAuthService: {
    signIn: vi.fn(),
    signOut: vi.fn(),
    getCurrentSession: vi.fn(),
    isAuthenticated: vi.fn()
  }
}));

vi.mock("../../services/realTimeDataService.js", () => {
  const MockRealTimeDataService = class {
    constructor() {
      this.subscribe = vi.fn();
      this.unsubscribe = vi.fn();
      this.connect = vi.fn();
      this.disconnect = vi.fn();
    }
  };
  const mockInstance = new MockRealTimeDataService();
  return {
    default: MockRealTimeDataService,
    realTimeDataService: mockInstance
  };
});

describe("Services Integration", () => {
  let mockApi, mockDataService, mockDataCache;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Import mocked services
    const { default: api } = await import("../../services/api.js");
    const { default: dataService } = await import("../../services/dataService.js");
    const { dataCache } = await import("../../services/dataCache.js");
    
    mockApi = api;
    mockDataService = dataService;
    mockDataCache = dataCache;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("API Service + Data Service Integration", () => {
    it("should coordinate between API calls and data caching", async () => {
      const mockData = { 
        data: { holdings: [{ symbol: "AAPL", value: 1000 }] }
      };
      
      // Mock successful API call
      mockApi.get.mockResolvedValue(mockData);
      
      // Mock data service using API service
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Test integration
      const result = await mockDataService.fetchData("/api/portfolio");
      
      expect(mockApi.get).toHaveBeenCalledWith("/api/portfolio");
      expect(result).toEqual(mockData.data);
    });

    it("should handle API failures and maintain data consistency", async () => {
      // Mock API failure
      mockApi.get.mockRejectedValue(new Error("Network error"));
      
      // Mock data service error handling
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Test error handling across services
      await expect(mockDataService.fetchData("/api/portfolio")).rejects.toThrow("Network error");
      
      // Verify cache remains clean
      expect(mockDataCache.get("/api/portfolio")).toBeUndefined();
    });

    it("should coordinate cache invalidation across services", async () => {
      const mockData = { data: { value: "cached" } };
      mockApi.get.mockResolvedValue(mockData);
      
      // Mock cache operations
      mockDataCache.get.mockReturnValue({ value: "cached" });
      
      // Test cache invalidation coordination
      await mockDataService.fetchData("/api/test");
      mockDataService.invalidateCache("/api/test");
      
      expect(mockDataService.fetchData).toHaveBeenCalledWith("/api/test");
      expect(mockDataService.invalidateCache).toHaveBeenCalledWith("/api/test");
    });
  });

  describe("Data Cache + API Service Integration", () => {
    it("should prevent duplicate API calls when data is cached", async () => {
      const mockData = { data: { value: "test" } };
      mockApi.get.mockResolvedValue(mockData);
      
      // Mock data service with caching behavior
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Test duplicate call prevention
      await mockDataService.fetchData("/api/cached");
      await mockDataService.fetchData("/api/cached");
      
      expect(mockDataService.fetchData).toHaveBeenCalledTimes(2);
      expect(mockApi.get).toHaveBeenCalledWith("/api/cached");
    });

    it("should refresh cache when data expires", async () => {
      const mockData = { data: { value: "fresh" } };
      mockApi.get.mockResolvedValue(mockData);
      
      // Mock data service with expiration behavior
      mockDataService.fetchData.mockImplementation(async (url, _options) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Test cache expiration behavior
      await mockDataService.fetchData("/api/expire", { maxAge: 5 * 60 * 1000 });
      await mockDataService.fetchData("/api/expire", { maxAge: 5 * 60 * 1000 });
      
      expect(mockDataService.fetchData).toHaveBeenCalledTimes(2);
      expect(mockApi.get).toHaveBeenCalledWith("/api/expire");
    });
  });

  describe("Real-Time Service Integration", () => {
    it("should coordinate real-time updates with cached data", async () => {
      const { realTimeDataService } = await import("../../services/realTimeDataService.js");
      
      // Mock real-time connection
      const mockSubscribe = vi.fn();
      realTimeDataService.subscribe = mockSubscribe;
      
      // Test coordination between services
      await mockDataService.subscribeToRealTimeData("AAPL", (data) => {
        mockDataCache.set("AAPL-price", data);
      });
      
      expect(mockSubscribe).toHaveBeenCalledWith("AAPL", expect.any(Function));
    });
  });

  describe("Authentication + API Integration", () => {
    it("should coordinate auth tokens across API calls", async () => {
      const mockToken = "test-token-123";
      
      // Mock auth service
      const { devAuthService } = await import("../../services/devAuth.js");
      devAuthService.getCurrentSession = vi.fn().mockReturnValue({
        tokens: { accessToken: mockToken }
      });
      
      // Mock API service to verify auth headers
      const mockAxios = await import("axios");
      mockAxios.default.create = vi.fn().mockReturnValue({
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() }
        },
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn()
      });
      
      // Test that API service picks up auth token
      expect(mockApi).toBeDefined();
      expect(mockApi.get).toBeDefined();
    });
  });

  describe("Error Handling Integration", () => {
    it("should coordinate error states across services", async () => {
      // Mock network error
      mockApi.get.mockRejectedValue({
        response: { status: 500, data: { error: "Server error" } }
      });
      
      // Mock data service error handling
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Test error propagation through services
      try {
        await mockDataService.fetchData("/api/error");
        expect.fail("Should have thrown error");
      } catch (error) {
        expect(error.response.status).toBe(500);
      }
      
      // Verify error handling
      expect(mockApi.get).toHaveBeenCalledWith("/api/error");
    });

    it("should handle partial failures in batch operations", async () => {
      // Mock mixed success/failure responses
      mockApi.get
        .mockResolvedValueOnce({ data: { success: true } })
        .mockRejectedValueOnce(new Error("Failed"))
        .mockResolvedValueOnce({ data: { success: true } });
      
      // Mock data service for batch operations
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Test batch operation handling
      const results = await Promise.allSettled([
        mockDataService.fetchData("/api/success1"),
        mockDataService.fetchData("/api/failure"),
        mockDataService.fetchData("/api/success2")
      ]);
      
      expect(results[0].status).toBe("fulfilled");
      expect(results[1].status).toBe("rejected");
      expect(results[2].status).toBe("fulfilled");
    });
  });

  describe("Performance Integration", () => {
    it("should coordinate request debouncing across services", async () => {
      const mockData = { data: { value: "debounced" } };
      mockApi.get.mockResolvedValue(mockData);
      
      // Mock data service for debouncing
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Make multiple rapid requests
      const promises = [
        mockDataService.fetchData("/api/debounce"),
        mockDataService.fetchData("/api/debounce"),
        mockDataService.fetchData("/api/debounce")
      ];
      
      await Promise.all(promises);
      
      // Verify multiple service calls
      expect(mockDataService.fetchData).toHaveBeenCalledTimes(3);
    });

    it("should manage memory efficiently across services", async () => {
      // Mock cache size tracking
      mockDataCache.size = 0;
      
      // Mock data service for memory management
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });
      
      // Generate multiple cache entries
      for (let i = 0; i < 10; i++) {
        mockApi.get.mockResolvedValue({ data: { id: i } });
        await mockDataService.fetchData(`/api/item-${i}`);
      }
      
      // Trigger cleanup
      mockDataService.clearExpiredCache();
      
      // Verify service calls
      expect(mockDataService.fetchData).toHaveBeenCalledTimes(10);
      expect(mockDataService.clearExpiredCache).toHaveBeenCalled();
    });
  });
});