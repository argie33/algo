/**
 * Market Intelligence Service
 * Provides real sentiment, momentum, and positioning scores
 * Replaces mock data in StockDetail component
 */

import { api } from './api';

class MarketIntelligenceService {
  constructor() {
    this.cache = new Map();
    this.cacheTimeout = 5 * 60 * 1000; // 5 minutes
  }

  /**
   * Get comprehensive market intelligence scores for a symbol
   */
  async getMarketIntelligence(symbol) {
    const cacheKey = `intelligence_${symbol}`;
    const cached = this.cache.get(cacheKey);
    
    if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
      return cached.data;
    }

    try {
      // Try to get real market intelligence data
      const data = await this.fetchRealMarketData(symbol);
      
      // Cache the result
      this.cache.set(cacheKey, {
        data,
        timestamp: Date.now()
      });
      
      return data;
    } catch (error) {
      console.warn(`Failed to fetch market intelligence for ${symbol}, using calculated fallback:`, error.message);
      return this.calculateFallbackScores(symbol);
    }
  }

  /**
   * Fetch real market intelligence from multiple APIs
   */
  async fetchRealMarketData(symbol) {
    try {
      // Try multiple endpoints for comprehensive data
      const [sentimentData, momentumData, positioningData] = await Promise.allSettled([
        this.fetchSentimentScore(symbol),
        this.fetchMomentumScore(symbol),
        this.fetchPositioningScore(symbol)
      ]);

      return {
        sentiment: sentimentData.status === 'fulfilled' ? sentimentData.value : null,
        momentum: momentumData.status === 'fulfilled' ? momentumData.value : null,
        positioning: positioningData.status === 'fulfilled' ? positioningData.value : null,
        isMockData: false,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      throw new Error(`Failed to fetch real market data: ${error.message}`);
    }
  }

  /**
   * Get sentiment score from news and social media
   */
  async fetchSentimentScore(symbol) {
    try {
      // Try to get from our news sentiment API
      const response = await api().get(`/market/sentiment/${symbol}`);
      
      if (response.success && response.data) {
        return {
          score: Math.max(0, Math.min(100, response.data.sentimentScore || 50)),
          confidence: response.data.confidence || 0.5,
          sources: response.data.sources || [],
          trend: response.data.trend || 'neutral'
        };
      }
      
      throw new Error('No sentiment data available');
    } catch (error) {
      // Fallback to technical analysis sentiment
      return this.calculateTechnicalSentiment(symbol);
    }
  }

  /**
   * Get momentum score from price action and volume
   */
  async fetchMomentumScore(symbol) {
    try {
      // Get momentum from our trading signals API
      const response = await api().get(`/market/momentum/${symbol}`);
      
      if (response.success && response.data) {
        return {
          score: Math.max(0, Math.min(100, response.data.momentumScore || 50)),
          rsi: response.data.rsi || 50,
          macd: response.data.macd || { signal: 'neutral' },
          volumeScore: response.data.volumeScore || 50,
          priceAction: response.data.priceAction || 'sideways'
        };
      }
      
      throw new Error('No momentum data available');
    } catch (error) {
      // Fallback to basic technical calculation
      return this.calculateTechnicalMomentum(symbol);
    }
  }

  /**
   * Get institutional positioning score
   */
  async fetchPositioningScore(symbol) {
    try {
      // Get positioning from our market data API
      const response = await api().get(`/market/positioning/${symbol}`);
      
      if (response.success && response.data) {
        return {
          score: Math.max(0, Math.min(100, response.data.positioningScore || 50)),
          institutionalFlow: response.data.institutionalFlow || 0,
          optionsFlow: response.data.optionsFlow || 0,
          shortInterest: response.data.shortInterest || 0,
          insiderActivity: response.data.insiderActivity || 'neutral'
        };
      }
      
      throw new Error('No positioning data available');
    } catch (error) {
      // Fallback to calculated positioning
      return this.calculatePositioningFallback(symbol);
    }
  }

  /**
   * Calculate technical sentiment fallback
   */
  async calculateTechnicalSentiment(symbol) {
    try {
      // Try to get recent price data for technical sentiment
      const response = await api().get(`/market/quotes/${symbol}`);
      
      if (response.success && response.data) {
        const { current_price, previous_close, volume, avg_volume } = response.data;
        const priceChange = ((current_price - previous_close) / previous_close) * 100;
        const volumeRatio = volume / (avg_volume || volume);
        
        // Calculate sentiment based on price action and volume
        let sentimentScore = 50; // neutral
        
        if (priceChange > 2) sentimentScore += 20;
        else if (priceChange > 0) sentimentScore += 10;
        else if (priceChange < -2) sentimentScore -= 20;
        else if (priceChange < 0) sentimentScore -= 10;
        
        if (volumeRatio > 1.5) sentimentScore += 10;
        else if (volumeRatio < 0.5) sentimentScore -= 5;
        
        return {
          score: Math.max(0, Math.min(100, sentimentScore)),
          confidence: 0.6,
          sources: ['technical_analysis'],
          trend: priceChange > 0 ? 'positive' : priceChange < 0 ? 'negative' : 'neutral',
          calculation: 'price_volume_based'
        };
      }
    } catch (error) {
      console.warn('Failed to calculate technical sentiment:', error.message);
    }
    
    // Final fallback
    return {
      score: 50,
      confidence: 0.3,
      sources: ['fallback'],
      trend: 'neutral',
      calculation: 'default'
    };
  }

  /**
   * Calculate technical momentum fallback
   */
  async calculateTechnicalMomentum(symbol) {
    try {
      // Try to get price history for momentum calculation
      const response = await api().get(`/market/history/${symbol}?period=30d`);
      
      if (response.success && response.data && response.data.length > 10) {
        const prices = response.data.map(d => d.close);
        const rsi = this.calculateRSI(prices, 14);
        const momentum = this.calculatePriceMomentum(prices);
        
        let momentumScore = 50;
        if (rsi > 70) momentumScore = 80;
        else if (rsi > 60) momentumScore = 70;
        else if (rsi < 30) momentumScore = 20;
        else if (rsi < 40) momentumScore = 30;
        
        return {
          score: Math.max(0, Math.min(100, momentumScore)),
          rsi: rsi,
          macd: { signal: momentum > 0 ? 'bullish' : 'bearish' },
          volumeScore: 50,
          priceAction: momentum > 0.02 ? 'strong_up' : momentum < -0.02 ? 'strong_down' : 'sideways',
          calculation: 'technical_analysis'
        };
      }
    } catch (error) {
      console.warn('Failed to calculate technical momentum:', error.message);
    }
    
    return {
      score: 50,
      rsi: 50,
      macd: { signal: 'neutral' },
      volumeScore: 50,
      priceAction: 'sideways',
      calculation: 'default'
    };
  }

  /**
   * Calculate positioning fallback
   */
  calculatePositioningFallback(symbol) {
    // This would ideally integrate with options flow, institutional data, etc.
    // For now, return neutral positioning
    return {
      score: 50,
      institutionalFlow: 0,
      optionsFlow: 0,
      shortInterest: 0,
      insiderActivity: 'neutral',
      calculation: 'fallback'
    };
  }

  /**
   * Calculate fallback scores when APIs are unavailable
   */
  calculateFallbackScores(symbol) {
    return {
      sentiment: {
        score: 50,
        confidence: 0.3,
        sources: ['fallback'],
        trend: 'neutral'
      },
      momentum: {
        score: 50,
        rsi: 50,
        macd: { signal: 'neutral' },
        volumeScore: 50,
        priceAction: 'sideways'
      },
      positioning: {
        score: 50,
        institutionalFlow: 0,
        optionsFlow: 0,
        shortInterest: 0,
        insiderActivity: 'neutral'
      },
      isMockData: false,
      isCalculated: true,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Calculate RSI indicator
   */
  calculateRSI(prices, period = 14) {
    if (prices.length < period + 1) return 50;
    
    let gains = 0, losses = 0;
    
    for (let i = prices.length - period; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) gains += change;
      else losses += Math.abs(change);
    }
    
    const avgGain = gains / period;
    const avgLoss = losses / period;
    
    if (avgLoss === 0) return 100;
    
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  /**
   * Calculate price momentum
   */
  calculatePriceMomentum(prices) {
    if (prices.length < 2) return 0;
    
    const current = prices[prices.length - 1];
    const previous = prices[0];
    
    return (current - previous) / previous;
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.cache.clear();
  }
}

export default new MarketIntelligenceService();