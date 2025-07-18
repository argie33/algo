// Data Normalization Service - Real-time Market Data
// Normalizes data from multiple providers into consistent format

class DataNormalizationService {
  constructor() {
    this.dataValidators = {
      trade: this.validateTrade.bind(this),
      quote: this.validateQuote.bind(this),
      bar: this.validateBar.bind(this)
    };
    
    // Quality metrics tracking
    this.qualityMetrics = {
      totalMessages: 0,
      validMessages: 0,
      invalidMessages: 0,
      providerStats: new Map(),
      lastUpdate: Date.now()
    };
  }
  
  normalizeMessage(provider, rawData) {
    this.qualityMetrics.totalMessages++;
    
    if (!this.qualityMetrics.providerStats.has(provider)) {
      this.qualityMetrics.providerStats.set(provider, {
        total: 0,
        valid: 0,
        invalid: 0,
        types: new Map()
      });
    }
    
    const providerStats = this.qualityMetrics.providerStats.get(provider);
    providerStats.total++;
    
    try {
      let normalizedData;
      
      switch (provider) {
        case 'alpaca':
          normalizedData = this.normalizeAlpacaData(rawData);
          break;
        case 'polygon':
          normalizedData = this.normalizePolygonData(rawData);
          break;
        case 'finnhub':
          normalizedData = this.normalizeFinnhubData(rawData);
          break;
        default:
          throw new Error(`Unknown provider: ${provider}`);
      }
      
      // Validate normalized data
      if (this.validateNormalizedData(normalizedData)) {
        this.qualityMetrics.validMessages++;
        providerStats.valid++;
        
        // Track message types
        const type = normalizedData.type;
        if (!providerStats.types.has(type)) {
          providerStats.types.set(type, 0);
        }
        providerStats.types.set(type, providerStats.types.get(type) + 1);
        
        return normalizedData;
      } else {
        throw new Error('Data validation failed');
      }
      
    } catch (error) {
      this.qualityMetrics.invalidMessages++;
      providerStats.invalid++;
      
      console.warn(`Failed to normalize data from ${provider}:`, error.message, rawData);
      return null;
    }
  }
  
  normalizeAlpacaData(data) {
    switch (data.T) {
      case 't': // Trade
        return {
          type: 'trade',
          provider: 'alpaca',
          symbol: data.S,
          price: parseFloat(data.p),
          size: parseInt(data.s),
          timestamp: new Date(data.t),
          conditions: data.c || [],
          exchange: data.x,
          id: data.i,
          raw: data
        };
        
      case 'q': // Quote
        return {
          type: 'quote',
          provider: 'alpaca',
          symbol: data.S,
          bid: parseFloat(data.bp),
          ask: parseFloat(data.ap),
          bidSize: parseInt(data.bs),
          askSize: parseInt(data.as),
          timestamp: new Date(data.t),
          bidExchange: data.bx,
          askExchange: data.ax,
          raw: data
        };
        
      case 'b': // Bar (minute bar)
        return {
          type: 'bar',
          provider: 'alpaca',
          symbol: data.S,
          open: parseFloat(data.o),
          high: parseFloat(data.h),
          low: parseFloat(data.l),
          close: parseFloat(data.c),
          volume: parseInt(data.v),
          timestamp: new Date(data.t),
          period: '1min',
          raw: data
        };
        
      default:
        if (data.T === 'success') {
          return {
            type: 'status',
            provider: 'alpaca',
            status: 'authenticated',
            message: data.msg,
            timestamp: new Date()
          };
        }
        throw new Error(`Unknown Alpaca message type: ${data.T}`);
    }
  }
  
  normalizePolygonData(data) {
    switch (data.ev) {
      case 'T': // Trade
        return {
          type: 'trade',
          provider: 'polygon',
          symbol: data.sym,
          price: parseFloat(data.p),
          size: parseInt(data.s),
          timestamp: new Date(data.t),
          conditions: data.c || [],
          exchange: data.x,
          id: data.i,
          raw: data
        };
        
      case 'Q': // Quote
        return {
          type: 'quote',
          provider: 'polygon',
          symbol: data.sym,
          bid: parseFloat(data.bp),
          ask: parseFloat(data.ap),
          bidSize: parseInt(data.bs),
          askSize: parseInt(data.as),
          timestamp: new Date(data.t),
          bidExchange: data.bx,
          askExchange: data.ax,
          raw: data
        };
        
      case 'A': // Aggregate (bar)
        return {
          type: 'bar',
          provider: 'polygon',
          symbol: data.sym,
          open: parseFloat(data.o),
          high: parseFloat(data.h),
          low: parseFloat(data.l),
          close: parseFloat(data.c),
          volume: parseInt(data.v),
          timestamp: new Date(data.s), // start time
          period: '1min',
          raw: data
        };
        
      default:
        if (data.status === 'auth_success') {
          return {
            type: 'status',
            provider: 'polygon',
            status: 'authenticated',
            message: data.message,
            timestamp: new Date()
          };
        }
        throw new Error(`Unknown Polygon message type: ${data.ev}`);
    }
  }
  
  normalizeFinnhubData(data) {
    if (data.type === 'trade') {
      // Finnhub sends arrays of trades
      const trades = data.data || [];
      return trades.map(trade => ({
        type: 'trade',
        provider: 'finnhub',
        symbol: trade.s,
        price: parseFloat(trade.p),
        size: parseInt(trade.v),
        timestamp: new Date(trade.t),
        conditions: trade.c || [],
        raw: trade
      }));
    } else if (data.type === 'ping') {
      return {
        type: 'status',
        provider: 'finnhub',
        status: 'ping',
        timestamp: new Date()
      };
    } else {
      throw new Error(`Unknown Finnhub message type: ${data.type}`);
    }
  }
  
  validateNormalizedData(data) {
    if (Array.isArray(data)) {
      return data.every(item => this.validateSingleItem(item));
    } else {
      return this.validateSingleItem(data);
    }
  }
  
  validateSingleItem(data) {
    if (!data || typeof data !== 'object') {
      return false;
    }
    
    const validator = this.dataValidators[data.type];
    if (!validator) {
      // For unknown types (like status), just check basic structure
      return !!(data.type && data.provider && data.timestamp);
    }
    
    return validator(data);
  }
  
  validateTrade(trade) {
    return !!(
      trade.symbol &&
      typeof trade.price === 'number' &&
      trade.price > 0 &&
      typeof trade.size === 'number' &&
      trade.size > 0 &&
      trade.timestamp instanceof Date &&
      !isNaN(trade.timestamp.getTime())
    );
  }
  
  validateQuote(quote) {
    return !!(
      quote.symbol &&
      typeof quote.bid === 'number' &&
      typeof quote.ask === 'number' &&
      quote.bid > 0 &&
      quote.ask > 0 &&
      quote.ask >= quote.bid &&
      typeof quote.bidSize === 'number' &&
      typeof quote.askSize === 'number' &&
      quote.bidSize > 0 &&
      quote.askSize > 0 &&
      quote.timestamp instanceof Date &&
      !isNaN(quote.timestamp.getTime())
    );
  }
  
  validateBar(bar) {
    return !!(
      bar.symbol &&
      typeof bar.open === 'number' &&
      typeof bar.high === 'number' &&
      typeof bar.low === 'number' &&
      typeof bar.close === 'number' &&
      typeof bar.volume === 'number' &&
      bar.open > 0 &&
      bar.high > 0 &&
      bar.low > 0 &&
      bar.close > 0 &&
      bar.volume >= 0 &&
      bar.high >= bar.low &&
      bar.high >= bar.open &&
      bar.high >= bar.close &&
      bar.low <= bar.open &&
      bar.low <= bar.close &&
      bar.timestamp instanceof Date &&
      !isNaN(bar.timestamp.getTime())
    );
  }
  
  // Convert normalized data to different output formats
  toStandardFormat(normalizedData) {
    if (Array.isArray(normalizedData)) {
      return normalizedData.map(item => this.convertSingleItem(item));
    } else {
      return this.convertSingleItem(normalizedData);
    }
  }
  
  convertSingleItem(data) {
    const base = {
      type: data.type,
      provider: data.provider,
      symbol: data.symbol,
      timestamp: data.timestamp.toISOString()
    };
    
    switch (data.type) {
      case 'trade':
        return {
          ...base,
          price: data.price,
          size: data.size,
          conditions: data.conditions,
          exchange: data.exchange
        };
        
      case 'quote':
        return {
          ...base,
          bid: data.bid,
          ask: data.ask,
          bidSize: data.bidSize,
          askSize: data.askSize,
          spread: Number((data.ask - data.bid).toFixed(4)),
          midpoint: Number(((data.ask + data.bid) / 2).toFixed(4))
        };
        
      case 'bar':
        return {
          ...base,
          open: data.open,
          high: data.high,
          low: data.low,
          close: data.close,
          volume: data.volume,
          period: data.period,
          change: Number((data.close - data.open).toFixed(4)),
          changePercent: Number(((data.close - data.open) / data.open * 100).toFixed(2))
        };
        
      default:
        return base;
    }
  }
  
  // Aggregate data for analytics
  aggregateBySymbol(normalizedDataArray, timeWindow = 60000) { // 1 minute default
    const aggregated = new Map();
    const now = Date.now();
    
    normalizedDataArray.forEach(data => {
      if (Array.isArray(data)) {
        data.forEach(item => this.processItemForAggregation(item, aggregated, now, timeWindow));
      } else {
        this.processItemForAggregation(data, aggregated, now, timeWindow);
      }
    });
    
    return Object.fromEntries(aggregated);
  }
  
  processItemForAggregation(item, aggregated, now, timeWindow) {
    const timeDiff = now - item.timestamp.getTime();
    if (timeDiff > timeWindow) {
      return; // Too old
    }
    
    const symbol = item.symbol;
    if (!aggregated.has(symbol)) {
      aggregated.set(symbol, {
        symbol,
        trades: [],
        quotes: [],
        bars: [],
        lastUpdate: item.timestamp,
        providers: new Set()
      });
    }
    
    const symbolData = aggregated.get(symbol);
    symbolData.providers.add(item.provider);
    
    if (item.timestamp > symbolData.lastUpdate) {
      symbolData.lastUpdate = item.timestamp;
    }
    
    switch (item.type) {
      case 'trade':
        symbolData.trades.push(item);
        break;
      case 'quote':
        symbolData.quotes.push(item);
        break;
      case 'bar':
        symbolData.bars.push(item);
        break;
    }
    
    // Convert Set to Array for JSON serialization
    symbolData.providers = Array.from(symbolData.providers);
  }
  
  getQualityMetrics() {
    const metrics = {
      ...this.qualityMetrics,
      successRate: this.qualityMetrics.totalMessages > 0 
        ? (this.qualityMetrics.validMessages / this.qualityMetrics.totalMessages * 100).toFixed(2)
        : 0,
      providerStats: {}
    };
    
    this.qualityMetrics.providerStats.forEach((stats, provider) => {
      metrics.providerStats[provider] = {
        ...stats,
        successRate: stats.total > 0 ? (stats.valid / stats.total * 100).toFixed(2) : 0,
        types: Object.fromEntries(stats.types)
      };
    });
    
    return metrics;
  }
  
  resetMetrics() {
    this.qualityMetrics = {
      totalMessages: 0,
      validMessages: 0,
      invalidMessages: 0,
      providerStats: new Map(),
      lastUpdate: Date.now()
    };
  }
}

module.exports = DataNormalizationService;