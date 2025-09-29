// Real-time news service for sentiment analysis
export class RealTimeNewsService {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
    this.isConnected = false;
  }

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      this.ws = new WebSocket(import.meta.env.VITE_WS_URL || 'ws://localhost:3001');

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

  // Mock methods for testing
  getLatestSentiment() {
    return {
      score: 0.65,
      label: 'Positive',
      confidence: 0.82,
      articles: 15,
      timestamp: new Date().toISOString()
    };
  }

  getSentimentHistory(timeframe = '24h') {
    // Generate mock sentiment data
    const data = [];
    const now = Date.now();
    const points = timeframe === '24h' ? 24 : timeframe === '7d' ? 7 : 30;

    for (let i = points - 1; i >= 0; i--) {
      const timestamp = new Date(now - i * (timeframe === '24h' ? 3600000 : timeframe === '7d' ? 86400000 : 86400000));
      data.push({
        timestamp: timestamp.toISOString(),
        score: 0.5 + (Math.random() * 0.4 - 0.2), // Random between 0.3 and 0.7
        articles: Math.floor(Math.random() * 50) + 10
      });
    }

    return data;
  }
}

export default new RealTimeNewsService();