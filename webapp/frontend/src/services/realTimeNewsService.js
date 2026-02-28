// Real-time news service for sentiment analysis
export class RealTimeNewsService {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
    this.isConnected = false;
  }

  // Get WebSocket URL dynamically
  getWebSocketUrl() {
    if (import.meta.env.VITE_WS_URL) {
      return import.meta.env.VITE_WS_URL;
    }

    // Infer from current location (works in all environments)
    if (typeof window !== "undefined") {
      const { hostname, origin, protocol } = window.location;

      // Convert HTTP/HTTPS to WS/WSS
      const wsProtocol = protocol === "https:" ? "wss:" : "ws:";

      if (hostname === "localhost" || hostname === "127.0.0.1") {
        return "ws://localhost:3000";
      }

      // AWS or production - use same origin with port 3000
      const baseUrl = origin.replace(/:\d+$/, ":3000");
      return baseUrl
        .replace(/^https:/, "wss:")
        .replace(/^http:/, "ws:");
    }

    // Final fallback
    return "ws://localhost:3000";
  }

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      this.ws = new WebSocket(this.getWebSocketUrl());

      this.ws.onopen = () => {
        this.isConnected = true;
        this.notifyListeners({ type: 'connected' });
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        this.notifyListeners(data);
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.notifyListeners({ type: 'disconnected' });
      };

      this.ws.onerror = (error) => {
        this.notifyListeners({ type: 'error', error });
      };
    } catch (error) {
      console.error('Failed to connect to real-time news service:', error);
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.isConnected = false;
    }
  }

  subscribe(callback) {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  notifyListeners(data) {
    this.listeners.forEach(callback => callback(data));
  }

  // CRITICAL: Do NOT generate mock data in production
  // These methods should ONLY be called if real WebSocket connection is established
  // Return null to indicate data unavailable (no fake data)

  getLatestSentiment() {
    if (!this.isConnected) {
      console.warn('RealTimeNewsService: Not connected - returning null instead of fake sentiment data');
      return null;
    }
    // This should only be called when WebSocket is actively providing data
    throw new Error('getLatestSentiment: Real data should come from WebSocket, not mocked');
  }

  getSentimentHistory(timeframe = '24h') {
    // CRITICAL: Do NOT generate fake sentiment history
    // If real data isn't available, return null (no fake data with Math.random())
    if (!this.isConnected) {
      console.warn(`RealTimeNewsService: Not connected - cannot provide ${timeframe} sentiment history`);
      return null;
    }
    throw new Error('getSentimentHistory: Real data should come from WebSocket, not mocked');
  }
}

export default new RealTimeNewsService();