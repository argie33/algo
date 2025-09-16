/**
 * Real-Time Data Service
 * Handles real-time data subscriptions and updates using WebSocket connection to backend
 * Gets live stock prices and market data from database via WebSocket
 */

import { getApiConfig } from "./api.js";

class RealTimeDataService {
  constructor() {
    this.subscribers = new Map();
    this.connectionListeners = new Map();
    this.isConnectedState = false;
    this.connectionStatus = "disconnected";
    this.latestData = new Map();
    this.webSocket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.pingInterval = null;
    this.apiConfig = getApiConfig();
  }

  subscribe(dataType, callback) {
    if (!this.subscribers.has(dataType)) {
      this.subscribers.set(dataType, new Set());
    }
    this.subscribers.get(dataType).add(callback);

    if (import.meta.env.DEV) {
      console.log(`📡 RealTimeDataService: Subscribed to ${dataType}`);
    }

    // Auto-connect if not connected
    if (!this.isConnectedState) {
      this.connect().catch((error) => {
        console.error("❌ RealTimeDataService: Auto-connect failed:", error);
      });
    }
  }

  unsubscribe(dataType, callback) {
    if (this.subscribers.has(dataType)) {
      this.subscribers.get(dataType).delete(callback);
      if (this.subscribers.get(dataType).size === 0) {
        this.subscribers.delete(dataType);
      }
    }

    if (import.meta.env.DEV) {
      console.log(`📡 RealTimeDataService: Unsubscribed from ${dataType}`);
    }
  }

  emit(dataType, data) {
    if (this.subscribers.has(dataType)) {
      this.subscribers.get(dataType).forEach((callback) => {
        try {
          callback(data);
        } catch (error) {
          console.error(
            `❌ RealTimeDataService: Error in ${dataType} callback:`,
            error
          );
        }
      });
    }

    // Store latest data
    this.latestData.set(dataType, data);
  }

  handleMessage(message) {
    try {
      const data = typeof message === "string" ? JSON.parse(message) : message;

      if (data.type && (data.payload || data.data)) {
        // Support both 'payload' and 'data' for backward compatibility
        const messageData = data.payload || data.data;
        this.emit(data.type, messageData);
      }
    } catch (error) {
      console.error("❌ RealTimeDataService: Error handling message:", error);
    }
  }

  getLatestData(dataType) {
    return this.latestData.get(dataType) || null;
  }

  getAllLatestData() {
    const result = {};
    this.latestData.forEach((value, key) => {
      result[key] = value;
    });
    return result;
  }

  clearAllSubscriptions() {
    this.subscribers.clear();
    this.latestData.clear();

    if (import.meta.env.DEV) {
      console.log("📡 RealTimeDataService: All subscriptions cleared");
    }
  }

  addConnectionListener(nameOrCallback, callback) {
    // Support both patterns: addConnectionListener(callback) and addConnectionListener(name, callback)
    const actualCallback =
      typeof nameOrCallback === "function" ? nameOrCallback : callback;

    if (typeof actualCallback === "function") {
      const listenerId = Symbol("connectionListener");
      this.connectionListeners.set(listenerId, actualCallback);
      return listenerId;
    }
    return null;
  }

  removeConnectionListener(listenerId) {
    if (listenerId && this.connectionListeners.has(listenerId)) {
      this.connectionListeners.delete(listenerId);
      return true;
    }
    return false;
  }

  async getLatestPrice(symbol) {
    try {
      // First check cached data
      const priceData = this.latestData.get("prices");
      if (priceData && priceData[symbol]) {
        return priceData[symbol];
      }

      // Fetch from API if not in cache
      const response = await fetch(
        `${this.apiConfig.baseURL}/api/price/${symbol}`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer dev-bypass-token",
          },
          timeout: 5000,
        }
      );

      if (!response.ok) {
        throw new Error(
          `Failed to fetch price for ${symbol}: ${response.status} ${response.statusText}`
        );
      }

      const data = await response.json();

      if (data.symbol && data.data) {
        // Transform API response to expected format
        const priceData = {
          symbol: data.symbol,
          price: parseFloat(data.data.current_price),
          change: data.data.change || 0,
          changePercent: data.data.change_percent || 0,
          timestamp: new Date(data.timestamp).getTime(),
        };

        // Cache the price data
        const currentPrices = this.latestData.get("prices") || {};
        currentPrices[symbol] = priceData;
        this.latestData.set("prices", currentPrices);

        return priceData;
      } else {
        throw new Error(
          `Invalid price data received for ${symbol}: ${data.error || "Unknown error"}`
        );
      }
    } catch (error) {
      console.error(
        `❌ RealTimeDataService: Failed to get price for ${symbol}:`,
        {
          error: error.message,
          symbol,
          hasCache: this.latestData.has("prices"),
          apiUrl: this.apiConfig.baseURL,
        }
      );
      throw new Error(
        `Unable to fetch current price for ${symbol}. Please check your connection and try again.`
      );
    }
  }

  isConnected() {
    return (
      this.isConnectedState &&
      this.webSocket &&
      this.webSocket.readyState === WebSocket.OPEN
    );
  }

  async connect() {
    if (this.isConnected()) {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      try {
        // Convert HTTP URL to WebSocket URL
        const wsUrl =
          this.apiConfig.baseURL
            .replace("http://", "ws://")
            .replace("https://", "wss://") + "/ws";

        if (import.meta.env.DEV) {
          console.log(
            "📡 RealTimeDataService: Connecting to WebSocket:",
            wsUrl
          );
        }

        this.webSocket = new WebSocket(wsUrl);

        this.webSocket.onopen = () => {
          this.isConnectedState = true;
          this.connectionStatus = "connected";
          this.reconnectAttempts = 0;

          if (import.meta.env.DEV) {
            console.log("📡 RealTimeDataService: WebSocket connected");
          }

          // Start ping to keep connection alive
          this.startPing();

          // Subscribe to price updates
          this.webSocket.send(
            JSON.stringify({
              type: "subscribe",
              topics: ["prices", "market_overview", "portfolio_updates"],
            })
          );

          // Notify connection listeners
          this.connectionListeners.forEach((callback) => {
            callback("connected");
          });

          resolve();
        };

        this.webSocket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.type && data.payload) {
              this.emit(data.type, data.payload);
            }
          } catch (error) {
            console.error(
              "❌ RealTimeDataService: Error parsing WebSocket message:",
              error
            );
          }
        };

        this.webSocket.onerror = (error) => {
          console.error("❌ RealTimeDataService: WebSocket error:", error);
          this.connectionStatus = "error";
          reject(new Error("Connection failed"));
        };

        this.webSocket.onclose = (event) => {
          this.isConnectedState = false;
          this.connectionStatus = "disconnected";
          this.stopPing();

          if (import.meta.env.DEV) {
            console.log("📡 RealTimeDataService: WebSocket disconnected", {
              code: event.code,
              reason: event.reason,
              wasClean: event.wasClean,
            });
          }

          // Notify connection listeners
          this.connectionListeners.forEach((callback) => {
            callback("disconnected");
          });

          // Attempt to reconnect if not closed cleanly
          if (
            !event.wasClean &&
            this.reconnectAttempts < this.maxReconnectAttempts
          ) {
            this.scheduleReconnect();
          }
        };

        // Connection timeout
        setTimeout(() => {
          if (this.webSocket.readyState === WebSocket.CONNECTING) {
            this.webSocket.close();
            reject(
              new Error(
                "WebSocket connection timeout. Please check if the backend server is running."
              )
            );
          }
        }, 10000);
      } catch (error) {
        console.error(
          "❌ RealTimeDataService: Connection setup failed:",
          error
        );
        reject(
          new Error(
            `Failed to establish WebSocket connection: ${error.message}`
          )
        );
      }
    });
  }

  disconnect() {
    this.stopPing();

    if (this.webSocket) {
      this.webSocket.close(1000, "User disconnected");
      this.webSocket = null;
    }

    this.isConnectedState = false;
    this.connectionStatus = "disconnected";

    if (import.meta.env.DEV) {
      console.log("📡 RealTimeDataService: Disconnected");
    }

    // Notify connection listeners
    this.connectionListeners.forEach((callback) => {
      callback("disconnected");
    });

    return Promise.resolve();
  }

  scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff

    if (import.meta.env.DEV) {
      console.log(
        `📡 RealTimeDataService: Scheduling reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`
      );
    }

    setTimeout(() => {
      this.connect().catch((error) => {
        console.error("❌ RealTimeDataService: Reconnect failed:", error);
      });
    }, delay);
  }

  startPing() {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      if (this.isConnected()) {
        this.webSocket.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000); // Ping every 30 seconds
  }

  stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  notifyConnectionListeners(status) {
    this.connectionListeners.forEach((callback) => {
      callback(status);
    });
  }

  getConnectionStatus() {
    return this.connectionStatus;
  }

  addEventListener(event, callback) {
    if (event === "connectionChange") {
      this.connectionListeners.set(callback, callback);
    }
  }

  removeEventListener(event, callback) {
    if (event === "connectionChange") {
      this.connectionListeners.delete(callback);
    }
  }

  // Cleanup method
  destroy() {
    this.disconnect();
    this.subscribers.clear();
    this.connectionListeners.clear();
    this.latestData.clear();
  }
}

// Create singleton instance
const realTimeDataService = new RealTimeDataService();

export default realTimeDataService;
