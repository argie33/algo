// Simple Alpaca WebSocket Service - Direct Connection
// Just connect to Alpaca WebSocket API with your API key

class SimpleAlpacaWebSocket {
  constructor() {
    this.ws = null;
    this.isConnected = false;
    this.subscriptions = new Map();
    this.listeners = new Map();
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
    
    // Your Alpaca credentials - set these via environment variables
    this.apiKey = process.env.REACT_APP_ALPACA_API_KEY;
    this.apiSecret = process.env.REACT_APP_ALPACA_API_SECRET;
    this.dataFeed = process.env.REACT_APP_ALPACA_DATA_FEED || 'iex'; // 'iex' for free, 'sip' for premium
    
    // Alpaca WebSocket URLs
    this.wsUrls = {
      'iex': 'wss://stream.data.alpaca.markets/v2/iex',
      'sip': 'wss://stream.data.alpaca.markets/v2/sip'
    };
    
    this.latestData = new Map();
    this.metrics = {
      messagesReceived: 0,
      connectionTime: null,
      lastLatency: 0
    };
  }

  // Connect to Alpaca WebSocket
  connect() {
    if (this.isConnected || this.ws) return;

    if (!this.apiKey || !this.apiSecret) {
      console.error('Alpaca API credentials not found. Set REACT_APP_ALPACA_API_KEY and REACT_APP_ALPACA_API_SECRET');
      return;
    }

    const wsUrl = this.wsUrls[this.dataFeed];
    console.log(`Connecting to Alpaca WebSocket: ${wsUrl}`);

    this.ws = new WebSocket(wsUrl);
    
    this.ws.onopen = () => {
      console.log('Connected to Alpaca WebSocket');
      this.authenticate();
    };

    this.ws.onmessage = (event) => {
      this.handleMessage(event.data);
    };

    this.ws.onclose = () => {
      console.log('Disconnected from Alpaca WebSocket');
      this.isConnected = false;
      this.emit('disconnected');
      this.scheduleReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('Alpaca WebSocket error:', error);
      this.emit('error', error);
    };
  }

  // Authenticate with Alpaca
  authenticate() {
    const authMsg = {
      action: 'auth',
      key: this.apiKey,
      secret: this.apiSecret
    };
    
    this.ws.send(JSON.stringify(authMsg));
  }

  // Handle incoming messages
  handleMessage(data) {
    try {
      const messages = JSON.parse(data);
      
      if (!Array.isArray(messages)) {
        return;
      }

      for (const msg of messages) {
        this.processMessage(msg);
      }
    } catch (error) {
      console.error('Error parsing message:', error);
    }
  }

  // Process individual message
  processMessage(msg) {
    const msgType = msg.T;
    
    switch (msgType) {
      case 'success':
        if (msg.msg === 'authenticated') {
          this.isConnected = true;
          this.metrics.connectionTime = Date.now();
          this.emit('connected');
          this.startHeartbeat();
        }
        break;
        
      case 'error':
        console.error('Alpaca error:', msg.msg);
        this.emit('error', new Error(msg.msg));
        break;
        
      case 'subscription':
        console.log('Subscription confirmed:', msg);
        this.emit('subscribed', msg);
        break;
        
      case 'q': // Quote
        this.handleQuote(msg);
        break;
        
      case 't': // Trade
        this.handleTrade(msg);
        break;
        
      case 'b': // Bar
        this.handleBar(msg);
        break;
        
      default:
        console.log('Unknown message type:', msgType);
    }
  }

  // Handle quote data
  handleQuote(msg) {
    const data = {
      symbol: msg.S,
      bid: msg.bp,
      ask: msg.ap,
      bidSize: msg.bs,
      askSize: msg.as,
      timestamp: msg.t
    };
    
    this.latestData.set(`${msg.S}:quote`, data);
    this.metrics.messagesReceived++;
    this.emit('quote', data);
    this.emit('data', { type: 'quote', data });
  }

  // Handle trade data
  handleTrade(msg) {
    const data = {
      symbol: msg.S,
      price: msg.p,
      size: msg.s,
      timestamp: msg.t,
      conditions: msg.c
    };
    
    this.latestData.set(`${msg.S}:trade`, data);
    this.metrics.messagesReceived++;
    this.emit('trade', data);
    this.emit('data', { type: 'trade', data });
  }

  // Handle bar data
  handleBar(msg) {
    const data = {
      symbol: msg.S,
      open: msg.o,
      high: msg.h,
      low: msg.l,
      close: msg.c,
      volume: msg.v,
      timestamp: msg.t
    };
    
    this.latestData.set(`${msg.S}:bar`, data);
    this.metrics.messagesReceived++;
    this.emit('bar', data);
    this.emit('data', { type: 'bar', data });
  }

  // Subscribe to quotes
  subscribeToQuotes(symbols) {
    if (!Array.isArray(symbols)) symbols = [symbols];
    
    const msg = {
      action: 'subscribe',
      quotes: symbols.map(s => s.toUpperCase())
    };
    
    this.send(msg);
    symbols.forEach(symbol => {
      this.subscriptions.set(`${symbol}:quotes`, { symbol, type: 'quotes' });
    });
  }

  // Subscribe to trades
  subscribeToTrades(symbols) {
    if (!Array.isArray(symbols)) symbols = [symbols];
    
    const msg = {
      action: 'subscribe',
      trades: symbols.map(s => s.toUpperCase())
    };
    
    this.send(msg);
    symbols.forEach(symbol => {
      this.subscriptions.set(`${symbol}:trades`, { symbol, type: 'trades' });
    });
  }

  // Subscribe to bars
  subscribeToBars(symbols) {
    if (!Array.isArray(symbols)) symbols = [symbols];
    
    const msg = {
      action: 'subscribe',
      bars: symbols.map(s => s.toUpperCase())
    };
    
    this.send(msg);
    symbols.forEach(symbol => {
      this.subscriptions.set(`${symbol}:bars`, { symbol, type: 'bars' });
    });
  }

  // Unsubscribe from all
  unsubscribeAll() {
    const quotes = [];
    const trades = [];
    const bars = [];
    
    for (const [key, sub] of this.subscriptions) {
      if (sub.type === 'quotes') quotes.push(sub.symbol);
      else if (sub.type === 'trades') trades.push(sub.symbol);
      else if (sub.type === 'bars') bars.push(sub.symbol);
    }
    
    if (quotes.length > 0) {
      this.send({ action: 'unsubscribe', quotes });
    }
    if (trades.length > 0) {
      this.send({ action: 'unsubscribe', trades });
    }
    if (bars.length > 0) {
      this.send({ action: 'unsubscribe', bars });
    }
    
    this.subscriptions.clear();
  }

  // Send message to Alpaca
  send(msg) {
    if (this.isConnected && this.ws) {
      this.ws.send(JSON.stringify(msg));
    } else {
      console.warn('Not connected to Alpaca WebSocket');
    }
  }

  // Disconnect
  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.isConnected = false;
  }

  // Schedule reconnect
  scheduleReconnect() {
    if (this.reconnectTimer) return;
    
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 5000); // Reconnect after 5 seconds
  }

  // Start heartbeat
  startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected) {
        // Alpaca doesn't need explicit ping, just check connection
        if (this.ws.readyState !== WebSocket.OPEN) {
          this.isConnected = false;
          this.emit('disconnected');
        }
      }
    }, 30000); // Check every 30 seconds
  }

  // Get latest data for symbol
  getLatestData(symbol, type = 'quote') {
    return this.latestData.get(`${symbol.toUpperCase()}:${type}`);
  }

  // Get all latest data
  getAllData() {
    const result = {};
    for (const [key, data] of this.latestData) {
      const [symbol, type] = key.split(':');
      if (!result[symbol]) result[symbol] = {};
      result[symbol][type] = data;
    }
    return result;
  }

  // Get metrics
  getMetrics() {
    return {
      ...this.metrics,
      subscriptions: this.subscriptions.size,
      isConnected: this.isConnected,
      uptime: this.metrics.connectionTime ? Date.now() - this.metrics.connectionTime : 0
    };
  }

  // Event handling
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  off(event, callback) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error('Error in event callback:', error);
        }
      });
    }
  }
}

// Create singleton instance
const simpleAlpacaWebSocket = new SimpleAlpacaWebSocket();

export default simpleAlpacaWebSocket;