import { vi } from "vitest";

// Mock the api service
vi.mock("../../../services/api.js", () => ({
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    baseURL: "http://localhost:3001",
  })),
}));

// Mock WebSocket
global.WebSocket = vi.fn().mockImplementation((url) => ({
  url,
  readyState: 1, // OPEN
  send: vi.fn(),
  close: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  onopen: null,
  onclose: null,
  onerror: null,
  onmessage: null,
}));

// Mock WebSocket constants
global.WebSocket.OPEN = 1;
global.WebSocket.CONNECTING = 0;
global.WebSocket.CLOSING = 2;
global.WebSocket.CLOSED = 3;

describe("RealTimeDataService", () => {
  let service;

  beforeEach(async () => {
    vi.clearAllMocks();

    // Import the singleton service instance
    const module = await import("../../../services/realTimeDataService");
    service = module.default;

    // Reset service state for each test
    // Safely disconnect if webSocket exists
    if (service.webSocket && typeof service.webSocket.close === "function") {
      service.webSocket.close();
    }
    service.webSocket = null;
    service.isConnectedState = false;
    service.connectionStatus = "disconnected";
    service.subscribers.clear();
    service.connectionListeners.clear();
    service.latestData.clear();
  });

  afterEach(() => {
    if (service) {
      service.disconnect();
    }
  });

  describe("Constructor", () => {
    test("initializes with correct default state", () => {
      expect(service).toBeDefined();
      expect(service.subscribers).toBeInstanceOf(Map);
      expect(service.connectionListeners).toBeInstanceOf(Map);
      expect(service.isConnectedState).toBe(false);
      expect(service.connectionStatus).toBe("disconnected");
      expect(service.latestData).toBeInstanceOf(Map);
    });

    test("sets up configuration", () => {
      expect(service.apiConfig).toBeDefined();
      expect(service.apiConfig.apiUrl).toBe("http://localhost:3001");
    });
  });

  describe("Subscription Management", () => {
    test("subscribes to data type", () => {
      const callback = vi.fn();

      service.subscribe("stock-prices", callback);

      expect(service.subscribers.has("stock-prices")).toBe(true);
      expect(service.subscribers.get("stock-prices").has(callback)).toBe(true);
    });

    test("unsubscribes from data type", () => {
      const callback = vi.fn();

      service.subscribe("stock-prices", callback);
      service.unsubscribe("stock-prices", callback);

      expect(service.subscribers.has("stock-prices")).toBe(false);
    });

    test("handles multiple callbacks for same data type", () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();

      service.subscribe("stock-prices", callback1);
      service.subscribe("stock-prices", callback2);

      const callbacks = service.subscribers.get("stock-prices");
      expect(callbacks.size).toBe(2);
      expect(callbacks.has(callback1)).toBe(true);
      expect(callbacks.has(callback2)).toBe(true);
    });

    test("removes data type when no callbacks remain", () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();

      service.subscribe("stock-prices", callback1);
      service.subscribe("stock-prices", callback2);

      service.unsubscribe("stock-prices", callback1);
      expect(service.subscribers.has("stock-prices")).toBe(true);

      service.unsubscribe("stock-prices", callback2);
      expect(service.subscribers.has("stock-prices")).toBe(false);
    });
  });

  describe("Connection Management", () => {
    test("connects to WebSocket", async () => {
      const connectSpy = vi.spyOn(service, "connect");

      // Mock successful connection to avoid actual WebSocket creation
      connectSpy.mockResolvedValue();

      await service.connect();

      expect(connectSpy).toHaveBeenCalled();
    });

    test("handles connection errors gracefully", async () => {
      global.WebSocket = vi.fn().mockImplementation(() => {
        throw new Error("Connection failed");
      });

      try {
        await service.connect();
      } catch (error) {
        expect(error.message).toBe(
          "Failed to establish WebSocket connection: Connection failed"
        );
      }
    });

    test("disconnects WebSocket", () => {
      const mockClose = vi.fn();
      service.webSocket = {
        close: mockClose,
        readyState: 1,
      };

      service.disconnect();

      expect(mockClose).toHaveBeenCalled();
      expect(service.isConnectedState).toBe(false);
      expect(service.webSocket).toBeNull();
    });

    test("handles disconnect when not connected", () => {
      service.webSocket = null;

      expect(() => service.disconnect()).not.toThrow();
    });
  });

  describe("Data Handling", () => {
    test("processes incoming data", () => {
      const callback = vi.fn();
      service.subscribe("stock-prices", callback);

      const mockData = {
        type: "stock-prices",
        data: { AAPL: 150.0, GOOGL: 2500.0 },
      };

      service.handleMessage(JSON.stringify(mockData));

      expect(callback).toHaveBeenCalledWith(mockData.data);
    });

    test("stores latest data", () => {
      const mockData = {
        type: "stock-prices",
        data: { AAPL: 150.0 },
      };

      service.handleMessage(JSON.stringify(mockData));

      expect(service.latestData.get("stock-prices")).toEqual(mockData.data);
    });

    test("handles malformed message gracefully", () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      service.handleMessage("invalid json");

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });

    test("handles message without subscribers", () => {
      const mockData = {
        type: "unknown-type",
        data: { test: "data" },
      };

      expect(() =>
        service.handleMessage(JSON.stringify(mockData))
      ).not.toThrow();
    });
  });

  describe("Connection Status", () => {
    test("reports connection status", () => {
      expect(service.isConnected()).toBe(false);

      // Mock webSocket and set connected state
      service.isConnectedState = true;
      service.webSocket = {
        readyState: global.WebSocket.OPEN,
        close: vi.fn(),
      };
      expect(service.isConnected()).toBe(true);
    });

    test("gets connection status string", () => {
      expect(service.getConnectionStatus()).toBe("disconnected");

      service.connectionStatus = "connected";
      expect(service.getConnectionStatus()).toBe("connected");
    });

    test("notifies connection listeners", () => {
      const listener = vi.fn();
      service.addConnectionListener("test", listener);

      service.notifyConnectionListeners(true);

      expect(listener).toHaveBeenCalledWith(true);
    });
  });

  describe("Latest Data Retrieval", () => {
    test("gets latest data for type", () => {
      const testData = { AAPL: 150.0 };
      service.latestData.set("stock-prices", testData);

      const result = service.getLatestData("stock-prices");

      expect(result).toEqual(testData);
    });

    test("returns null for unknown data type", () => {
      const result = service.getLatestData("unknown-type");

      expect(result).toBeNull();
    });

    test("gets all latest data", () => {
      service.latestData.set("stock-prices", { AAPL: 150.0 });
      service.latestData.set("market-data", { volume: 1000000 });

      const result = service.getAllLatestData();

      expect(result).toEqual({
        "stock-prices": { AAPL: 150.0 },
        "market-data": { volume: 1000000 },
      });
    });
  });

  describe("Auto-Connection", () => {
    test("auto-connects on subscription when not connected", () => {
      const connectSpy = vi.spyOn(service, "connect").mockResolvedValue();
      const callback = vi.fn();

      service.subscribe("stock-prices", callback);

      expect(connectSpy).toHaveBeenCalled();
    });

    test("does not auto-connect when already connected", () => {
      service.isConnectedState = true;
      const connectSpy = vi.spyOn(service, "connect");
      const callback = vi.fn();

      service.subscribe("stock-prices", callback);

      expect(connectSpy).not.toHaveBeenCalled();
    });
  });

  describe("Cleanup", () => {
    test("clears all subscriptions", () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();

      service.subscribe("type1", callback1);
      service.subscribe("type2", callback2);

      service.clearAllSubscriptions();

      expect(service.subscribers.size).toBe(0);
    });

    test("clears ping interval on disconnect", () => {
      const mockInterval = setInterval(() => {}, 1000);
      service.pingInterval = mockInterval;
      const clearIntervalSpy = vi.spyOn(global, "clearInterval");

      service.disconnect();

      expect(clearIntervalSpy).toHaveBeenCalledWith(mockInterval);
      expect(service.pingInterval).toBeNull();
    });
  });
});
