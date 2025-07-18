// Real-Time Market Data Service
// Orchestrates WebSocket connections and data normalization for live market data

const EventEmitter = require('events');
const WebSocketManager = require('./webSocketManager');
const DataNormalizationService = require('./dataNormalizationService');

class RealTimeMarketDataService extends EventEmitter {
  constructor(options = {}) {
    super();
    
    this.options = {
      enabledProviders: options.enabledProviders || ['alpaca', 'polygon', 'finnhub'],
      primaryProvider: options.primaryProvider || 'alpaca',
      fallbackProviders: options.fallbackProviders || ['polygon', 'finnhub'],
      dataBufferSize: options.dataBufferSize || 1000,
      dataFlushInterval: options.dataFlushInterval || 5000,
      ...options
    };
    
    // Initialize services
    this.wsManager = new WebSocketManager();
    this.normalizer = new DataNormalizationService();
    
    // Data management
    this.dataBuffer = [];
    this.activeSubscriptions = new Map(); // symbol -> providers[]
    this.lastDataBySymbol = new Map(); // symbol -> lastData
    this.dataCache = new Map(); // symbol -> recent data
    
    // Connection management
    this.connectedProviders = new Set();
    this.apiKeys = new Map(); // provider -> apiKey
    
    // Setup WebSocket event handlers
    this.setupWebSocketHandlers();
    
    // Start data processing
    this.startDataProcessing();
  }
  
  setupWebSocketHandlers() {
    this.wsManager.on('connected', ({ provider }) => {
      console.log(`✅ Real-time service: ${provider} connected`);
      this.connectedProviders.add(provider);
      this.emit('providerConnected', { provider });
    });
    
    this.wsManager.on('disconnected', ({ provider }) => {
      console.log(`🔌 Real-time service: ${provider} disconnected`);
      this.connectedProviders.delete(provider);
      this.emit('providerDisconnected', { provider });
      
      // Handle fallback if primary provider disconnects
      this.handleProviderFailover(provider);
    });
    
    this.wsManager.on('message', ({ provider, data }) => {
      this.processRawMessage(provider, data);
    });
    
    this.wsManager.on('error', ({ provider, error }) => {
      console.error(`❌ Real-time service: ${provider} error:`, error.message);
      this.emit('providerError', { provider, error });
    });
    
    this.wsManager.on('trade', (trade) => {
      this.emit('trade', trade);
    });
    
    this.wsManager.on('quote', (quote) => {
      this.emit('quote', quote);
    });
  }
  
  async connectProvider(provider, apiKey) {
    try {
      if (!this.options.enabledProviders.includes(provider)) {
        throw new Error(`Provider ${provider} not enabled`);
      }
      
      this.apiKeys.set(provider, apiKey);
      await this.wsManager.connect(provider, apiKey);
      
      console.log(`🔌 Connected to ${provider} for real-time data`);
      return true;
      
    } catch (error) {
      console.error(`Failed to connect to ${provider}:`, error.message);
      throw error;
    }
  }
  
  async connectAllProviders(apiKeys) {
    const results = {};
    
    for (const provider of this.options.enabledProviders) {
      if (apiKeys[provider]) {
        try {
          await this.connectProvider(provider, apiKeys[provider]);
          results[provider] = { success: true };
        } catch (error) {
          results[provider] = { success: false, error: error.message };
        }
      } else {
        results[provider] = { success: false, error: 'No API key provided' };
      }
    }
    
    return results;
  }
  
  subscribe(symbols, providers = null) {
    if (!Array.isArray(symbols)) {
      symbols = [symbols];
    }
    
    // Use specified providers or all connected providers
    const targetProviders = providers || Array.from(this.connectedProviders);
    
    if (targetProviders.length === 0) {
      throw new Error('No providers available for subscription');
    }
    
    const results = {};
    
    symbols.forEach(symbol => {
      const subscribedProviders = [];
      
      targetProviders.forEach(provider => {
        if (this.connectedProviders.has(provider)) {
          try {
            this.wsManager.subscribe(provider, [symbol]);
            subscribedProviders.push(provider);
          } catch (error) {
            console.error(`Failed to subscribe ${symbol} on ${provider}:`, error.message);
          }
        }
      });
      
      if (subscribedProviders.length > 0) {
        this.activeSubscriptions.set(symbol, subscribedProviders);
        results[symbol] = { success: true, providers: subscribedProviders };
      } else {
        results[symbol] = { success: false, error: 'No providers available' };
      }
    });
    
    console.log(`📊 Subscribed to ${symbols.length} symbols across providers`);
    this.emit('subscribed', { symbols, results });
    
    return results;
  }
  
  unsubscribe(symbols, providers = null) {
    if (!Array.isArray(symbols)) {
      symbols = [symbols];
    }
    
    symbols.forEach(symbol => {
      const subscribedProviders = this.activeSubscriptions.get(symbol) || [];
      const targetProviders = providers || subscribedProviders;
      
      targetProviders.forEach(provider => {
        if (subscribedProviders.includes(provider)) {
          try {
            this.wsManager.unsubscribe(provider, [symbol]);
          } catch (error) {
            console.error(`Failed to unsubscribe ${symbol} from ${provider}:`, error.message);
          }
        }
      });
      
      if (!providers) {
        // Complete unsubscription
        this.activeSubscriptions.delete(symbol);
        this.lastDataBySymbol.delete(symbol);
        this.dataCache.delete(symbol);
      } else {
        // Partial unsubscription
        const remainingProviders = subscribedProviders.filter(p => !targetProviders.includes(p));
        if (remainingProviders.length > 0) {
          this.activeSubscriptions.set(symbol, remainingProviders);
        } else {
          this.activeSubscriptions.delete(symbol);
        }
      }
    });
    
    console.log(`📊 Unsubscribed from ${symbols.length} symbols`);
    this.emit('unsubscribed', { symbols });
  }
  
  processRawMessage(provider, rawData) {
    try {
      const normalizedData = this.normalizer.normalizeMessage(provider, rawData);
      
      if (normalizedData) {
        if (Array.isArray(normalizedData)) {
          normalizedData.forEach(data => this.processNormalizedData(data));
        } else {
          this.processNormalizedData(normalizedData);
        }
      }
      
    } catch (error) {
      console.error(`Error processing message from ${provider}:`, error.message);
    }
  }
  
  processNormalizedData(data) {
    // Add to buffer for batch processing
    this.dataBuffer.push(data);
    
    // Update latest data cache
    if (data.symbol) {
      this.lastDataBySymbol.set(data.symbol, data);
      
      // Maintain recent data cache
      if (!this.dataCache.has(data.symbol)) {
        this.dataCache.set(data.symbol, []);
      }
      
      const symbolCache = this.dataCache.get(data.symbol);
      symbolCache.push(data);
      
      // Keep only recent data (last 100 items)
      if (symbolCache.length > 100) {
        symbolCache.splice(0, symbolCache.length - 100);
      }
    }
    
    // Emit real-time events
    this.emit('data', data);
    this.emit(data.type, data);
    
    if (data.symbol) {
      this.emit(`${data.type}:${data.symbol}`, data);
    }
  }
  
  startDataProcessing() {
    // Process buffered data periodically
    setInterval(() => {
      this.flushDataBuffer();
    }, this.options.dataFlushInterval);
  }
  
  flushDataBuffer() {
    if (this.dataBuffer.length === 0) {
      return;
    }
    
    const batchData = [...this.dataBuffer];
    this.dataBuffer = [];
    
    // Aggregate data by symbol
    const aggregatedData = this.normalizer.aggregateBySymbol(batchData);
    
    // Emit batch events
    this.emit('dataBatch', {
      data: batchData,
      aggregated: aggregatedData,
      count: batchData.length,
      timestamp: new Date()
    });
    
    // Store aggregated data for API access
    Object.keys(aggregatedData).forEach(symbol => {
      this.emit(`aggregated:${symbol}`, aggregatedData[symbol]);
    });
  }
  
  handleProviderFailover(failedProvider) {
    if (failedProvider !== this.options.primaryProvider) {
      return; // Only handle primary provider failures
    }
    
    console.log(`🔄 Handling failover from primary provider: ${failedProvider}`);
    
    // Find symbols that were subscribed via the failed provider
    const affectedSymbols = [];
    this.activeSubscriptions.forEach((providers, symbol) => {
      if (providers.includes(failedProvider)) {
        affectedSymbols.push(symbol);
      }
    });
    
    if (affectedSymbols.length === 0) {
      return;
    }
    
    // Try to resubscribe using fallback providers
    const availableFallbacks = this.options.fallbackProviders.filter(p => 
      this.connectedProviders.has(p) && p !== failedProvider
    );
    
    if (availableFallbacks.length > 0) {
      const fallbackProvider = availableFallbacks[0];
      console.log(`🔄 Failing over ${affectedSymbols.length} symbols to ${fallbackProvider}`);
      
      try {
        this.subscribe(affectedSymbols, [fallbackProvider]);
        this.emit('failover', { 
          from: failedProvider, 
          to: fallbackProvider, 
          symbols: affectedSymbols 
        });
      } catch (error) {
        console.error('Failover failed:', error.message);
        this.emit('failoverFailed', { 
          from: failedProvider, 
          error: error.message,
          symbols: affectedSymbols 
        });
      }
    } else {
      console.warn('No fallback providers available for failover');
      this.emit('noFallbackAvailable', { 
        failedProvider, 
        symbols: affectedSymbols 
      });
    }
  }
  
  // API methods for accessing data
  getLastData(symbol) {
    return this.lastDataBySymbol.get(symbol) || null;
  }
  
  getRecentData(symbol, count = 50) {
    const symbolCache = this.dataCache.get(symbol);
    if (!symbolCache) {
      return [];
    }
    
    return symbolCache.slice(-count);
  }
  
  getConnectionStatus() {
    return {
      connectedProviders: Array.from(this.connectedProviders),
      totalProviders: this.options.enabledProviders.length,
      wsManagerStatus: this.wsManager.getConnectionStatus(),
      activeSubscriptions: Object.fromEntries(this.activeSubscriptions),
      dataQuality: this.normalizer.getQualityMetrics()
    };
  }
  
  getSubscriptions() {
    return {
      active: Object.fromEntries(this.activeSubscriptions),
      wsManager: this.wsManager.getSubscriptions()
    };
  }
  
  async healthCheck() {
    const status = this.getConnectionStatus();
    
    return {
      healthy: status.connectedProviders.length > 0,
      status: status.connectedProviders.length > 0 ? 'operational' : 'degraded',
      details: status,
      timestamp: new Date().toISOString()
    };
  }
  
  disconnect() {
    console.log('🔌 Disconnecting real-time market data service');
    this.wsManager.disconnectAll();
    this.activeSubscriptions.clear();
    this.lastDataBySymbol.clear();
    this.dataCache.clear();
    this.connectedProviders.clear();
    this.emit('disconnected');
  }
}

module.exports = RealTimeMarketDataService;