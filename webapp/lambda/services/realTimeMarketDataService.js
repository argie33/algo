// Real-Time Market Data Service
// Orchestrates WebSocket connections and data normalization for live market data

const EventEmitter = require('events');
const WebSocketManager = require('./webSocketManager');
const DataNormalizationService = require('./dataNormalizationService');

class RealTimeMarketDataService extends EventEmitter {
  constructor(options = {}) {
    super();
    
    this.options = {
      enabledProviders: options.enabledProviders || ['crypto_binance', 'stocks_td', 'stocks_alpaca', 'economic_calendar'],
      primaryProvider: options.primaryProvider || 'crypto_binance',
      fallbackProviders: options.fallbackProviders || ['stocks_td', 'stocks_alpaca'],
      dataBufferSize: options.dataBufferSize || 1000,
      dataFlushInterval: options.dataFlushInterval || 5000,
      updateInterval: options.updateInterval || 5000, // 5 seconds for real data updates
      ...options
    };
    
    // Initialize services
    this.wsManager = new WebSocketManager();
    this.normalizer = new DataNormalizationService();
    
    // Real data services integration
    this.realDataSources = new Map();
    this.initializeRealDataSources();
    
    // Data management
    this.dataBuffer = [];
    this.activeSubscriptions = new Map(); // symbol -> providers[]
    this.lastDataBySymbol = new Map(); // symbol -> lastData
    this.dataCache = new Map(); // symbol -> recent data
    
    // Connection management
    this.connectedProviders = new Set();
    this.apiKeys = new Map(); // provider -> apiKey
    
    // Real-time update management
    this.updateTimers = new Map(); // symbol -> timer
    this.isRealTimeMode = false;
    
    // Setup WebSocket event handlers
    this.setupWebSocketHandlers();
    
    // Start data processing
    this.startDataProcessing();
  }

  /**
   * Initialize real data sources
   */
  initializeRealDataSources() {
    console.log('📊 Initializing real data sources...');
    
    // Crypto Exchange Service (Binance)
    try {
      const CryptoExchangeService = require('./cryptoExchangeService');
      this.realDataSources.set('crypto_binance', {
        service: new CryptoExchangeService('binance'),
        type: 'crypto',
        available: true,
        symbols: new Set(),
        lastUpdate: null
      });
      console.log('✅ Crypto exchange service (Binance) loaded');
    } catch (error) {
      console.warn('⚠️ Crypto exchange service not available:', error.message);
    }

    // TD Ameritrade Service
    try {
      const TDAmeritradeService = require('./tdAmeritradeService');
      this.realDataSources.set('stocks_td', {
        service: new TDAmeritradeService(),
        type: 'stocks',
        available: true,
        symbols: new Set(),
        lastUpdate: null
      });
      console.log('✅ TD Ameritrade service loaded');
    } catch (error) {
      console.warn('⚠️ TD Ameritrade service not available:', error.message);
    }

    // Alpaca Service (if available)
    try {
      const AlpacaService = require('../utils/alpacaService');
      if (process.env.ALPACA_API_KEY && process.env.ALPACA_API_SECRET) {
        this.realDataSources.set('stocks_alpaca', {
          service: new AlpacaService(
            process.env.ALPACA_API_KEY,
            process.env.ALPACA_API_SECRET,
            process.env.ALPACA_ENVIRONMENT !== 'live'
          ),
          type: 'stocks',
          available: true,
          symbols: new Set(),
          lastUpdate: null
        });
        console.log('✅ Alpaca service loaded');
      }
    } catch (error) {
      console.warn('⚠️ Alpaca service not available:', error.message);
    }

    // Economic Calendar Service
    try {
      const EconomicCalendarService = require('./economicCalendarService');
      this.realDataSources.set('economic_calendar', {
        service: new EconomicCalendarService(),
        type: 'economic',
        available: true,
        symbols: new Set(['ECONOMIC_EVENTS']),
        lastUpdate: null
      });
      console.log('✅ Economic calendar service loaded');
    } catch (error) {
      console.warn('⚠️ Economic calendar service not available:', error.message);
    }

    console.log(`📈 Initialized ${this.realDataSources.size} real data sources`);
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
    
    // Use specified providers or all available real data sources
    const targetProviders = providers || Array.from(this.realDataSources.keys());
    
    if (targetProviders.length === 0) {
      throw new Error('No providers available for subscription');
    }
    
    const results = {};
    
    symbols.forEach(symbol => {
      const subscribedProviders = [];
      
      targetProviders.forEach(provider => {
        // Check if provider is a real data source
        if (this.realDataSources.has(provider)) {
          const dataSource = this.realDataSources.get(provider);
          
          // Add symbol to the data source's symbol set
          dataSource.symbols.add(symbol.toUpperCase());
          subscribedProviders.push(provider);
          
          // Start real-time updates for this symbol
          this.startRealTimeUpdates(symbol, provider);
          
        } else if (this.connectedProviders.has(provider)) {
          // Legacy WebSocket provider
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
    
    console.log(`📊 Subscribed to ${symbols.length} symbols across ${targetProviders.length} providers`);
    this.emit('subscribed', { symbols, results });
    
    return results;
  }

  /**
   * Start real-time updates for a symbol from a specific provider
   */
  startRealTimeUpdates(symbol, provider) {
    const updateKey = `${symbol}_${provider}`;
    
    // Clear existing timer if any
    if (this.updateTimers.has(updateKey)) {
      clearInterval(this.updateTimers.get(updateKey));
    }
    
    // Start new update timer
    const timer = setInterval(async () => {
      await this.fetchRealTimeData(symbol, provider);
    }, this.options.updateInterval);
    
    this.updateTimers.set(updateKey, timer);
    
    // Fetch initial data immediately
    this.fetchRealTimeData(symbol, provider);
  }

  /**
   * Fetch real-time data for a symbol from a specific provider
   */
  async fetchRealTimeData(symbol, provider) {
    try {
      const dataSource = this.realDataSources.get(provider);
      if (!dataSource || !dataSource.available) {
        return;
      }
      
      let data = null;
      
      switch (dataSource.type) {
        case 'crypto':
          try {
            data = await dataSource.service.getPrice(symbol);
            data.type = 'quote';
            data.symbol = symbol;
            data.provider = provider;
            data.timestamp = new Date();
          } catch (error) {
            console.warn(`⚠️ Failed to fetch crypto data for ${symbol}:`, error.message);
          }
          break;
          
        case 'stocks':
          try {
            if (dataSource.service.getQuote) {
              data = await dataSource.service.getQuote(symbol);
            } else if (dataSource.service.getPositions) {
              // For Alpaca, get positions data
              const positions = await dataSource.service.getPositions();
              const position = positions.find(p => p.symbol === symbol);
              if (position) {
                data = {
                  symbol: symbol,
                  price: position.market_value / position.qty,
                  qty: position.qty,
                  market_value: position.market_value,
                  unrealized_pl: position.unrealized_pl
                };
              }
            }
            
            if (data) {
              data.type = 'quote';
              data.provider = provider;
              data.timestamp = new Date();
            }
          } catch (error) {
            console.warn(`⚠️ Failed to fetch stock data for ${symbol}:`, error.message);
          }
          break;
          
        case 'economic':
          try {
            const calendarData = await dataSource.service.getTodaysEvents();
            data = {
              symbol: 'ECONOMIC_EVENTS',
              type: 'economic',
              events: calendarData.events || [],
              provider: provider,
              timestamp: new Date()
            };
          } catch (error) {
            console.warn(`⚠️ Failed to fetch economic data:`, error.message);
          }
          break;
      }
      
      if (data) {
        // Process the data through existing pipeline
        this.processNormalizedData(data);
        dataSource.lastUpdate = new Date();
      }
      
    } catch (error) {
      console.error(`❌ Error fetching real-time data for ${symbol} from ${provider}:`, error.message);
    }
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
          // Handle real data sources
          if (this.realDataSources.has(provider)) {
            const dataSource = this.realDataSources.get(provider);
            dataSource.symbols.delete(symbol.toUpperCase());
            
            // Stop real-time updates
            this.stopRealTimeUpdates(symbol, provider);
            
          } else {
            // Handle legacy WebSocket providers
            try {
              this.wsManager.unsubscribe(provider, [symbol]);
            } catch (error) {
              console.error(`Failed to unsubscribe ${symbol} from ${provider}:`, error.message);
            }
          }
        }
      });
      
      if (!providers) {
        // Complete unsubscription
        this.activeSubscriptions.delete(symbol);
        this.lastDataBySymbol.delete(symbol);
        this.dataCache.delete(symbol);
        
        // Stop all real-time updates for this symbol
        this.stopAllRealTimeUpdates(symbol);
      } else {
        // Partial unsubscription
        const remainingProviders = subscribedProviders.filter(p => !targetProviders.includes(p));
        if (remainingProviders.length > 0) {
          this.activeSubscriptions.set(symbol, remainingProviders);
        } else {
          this.activeSubscriptions.delete(symbol);
          this.stopAllRealTimeUpdates(symbol);
        }
      }
    });
    
    console.log(`📊 Unsubscribed from ${symbols.length} symbols`);
    this.emit('unsubscribed', { symbols });
  }

  /**
   * Stop real-time updates for a specific symbol and provider
   */
  stopRealTimeUpdates(symbol, provider) {
    const updateKey = `${symbol}_${provider}`;
    const timer = this.updateTimers.get(updateKey);
    
    if (timer) {
      clearInterval(timer);
      this.updateTimers.delete(updateKey);
      console.log(`⏹️ Stopped real-time updates for ${symbol} from ${provider}`);
    }
  }

  /**
   * Stop all real-time updates for a symbol
   */
  stopAllRealTimeUpdates(symbol) {
    const keysToRemove = [];
    
    for (const updateKey of this.updateTimers.keys()) {
      if (updateKey.startsWith(`${symbol}_`)) {
        const timer = this.updateTimers.get(updateKey);
        clearInterval(timer);
        keysToRemove.push(updateKey);
      }
    }
    
    keysToRemove.forEach(key => this.updateTimers.delete(key));
    
    if (keysToRemove.length > 0) {
      console.log(`⏹️ Stopped ${keysToRemove.length} real-time update timers for ${symbol}`);
    }
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
    const realDataSourceStatus = {};
    for (const [sourceId, dataSource] of this.realDataSources) {
      realDataSourceStatus[sourceId] = {
        type: dataSource.type,
        available: dataSource.available,
        subscribedSymbols: Array.from(dataSource.symbols),
        lastUpdate: dataSource.lastUpdate
      };
    }
    
    return {
      connectedProviders: Array.from(this.connectedProviders),
      realDataSources: realDataSourceStatus,
      totalProviders: this.options.enabledProviders.length,
      wsManagerStatus: this.wsManager.getConnectionStatus(),
      activeSubscriptions: Object.fromEntries(this.activeSubscriptions),
      activeUpdateTimers: this.updateTimers.size,
      dataQuality: this.normalizer.getQualityMetrics(),
      isRealTimeMode: this.isRealTimeMode
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
    
    // Stop all real-time update timers
    for (const timer of this.updateTimers.values()) {
      clearInterval(timer);
    }
    this.updateTimers.clear();
    
    // Clear real data source symbols
    for (const dataSource of this.realDataSources.values()) {
      dataSource.symbols.clear();
    }
    
    // Legacy WebSocket cleanup
    this.wsManager.disconnectAll();
    
    // Clear all data structures
    this.activeSubscriptions.clear();
    this.lastDataBySymbol.clear();
    this.dataCache.clear();
    this.connectedProviders.clear();
    
    this.isRealTimeMode = false;
    
    console.log('✅ Real-time market data service disconnected');
    this.emit('disconnected');
  }
}

module.exports = RealTimeMarketDataService;