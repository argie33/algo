/**
 * Unit Tests for API Limit Manager
 * Tests intelligent API quota management and routing
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiLimitManager } from '../../../services/apiLimitManager.js';

// Mock fetch globally
global.fetch = vi.fn();

describe('ApiLimitManager', () => {
  let apiLimitManager;
  let consoleErrorSpy;
  let consoleSpy;

  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    
    // Create a new instance for each test
    apiLimitManager = new ApiLimitManager();
    
    // Mock localStorage
    global.localStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn()
    };
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    consoleSpy.mockRestore();
    vi.clearAllTimers();
  });

  describe('Initialization and Configuration', () => {
    it('initializes with default provider configurations', () => {
      expect(apiLimitManager.providers).toBeDefined();
      expect(apiLimitManager.providers.alpaca).toBeDefined();
      expect(apiLimitManager.providers.polygon).toBeDefined();
      expect(apiLimitManager.providers.yahoo).toBeDefined();
    });

    it('sets up correct default quotas for Alpaca', () => {
      const alpaca = apiLimitManager.providers.alpaca;
      expect(alpaca.quotas.market_data.limit).toBe(200);
      expect(alpaca.quotas.account_data.limit).toBe(100);
      expect(alpaca.priority).toBe(1);
      expect(alpaca.enabled).toBe(true);
    });

    it('configures optimization settings correctly', () => {
      const settings = apiLimitManager.optimizationSettings;
      expect(settings.hftReservedQuota).toBe(0.3);
      expect(settings.emergencyThreshold).toBe(0.9);
      expect(settings.warningThreshold).toBe(0.7);
    });

    it('initializes symbol priority sets', () => {
      expect(apiLimitManager.symbolPriority.critical).toBeInstanceOf(Set);
      expect(apiLimitManager.symbolPriority.high).toBeInstanceOf(Set);
      expect(apiLimitManager.symbolPriority.standard).toBeInstanceOf(Set);
      expect(apiLimitManager.symbolPriority.low).toBeInstanceOf(Set);
    });
  });

  describe('Quota Management', () => {
    it('checks if request can be made within limits', () => {
      const result = apiLimitManager.canMakeRequest('alpaca', 'market_data', 'standard');
      
      expect(result.allowed).toBe(true);
      expect(result.quotaRemaining).toBeDefined();
      expect(result.provider).toBe('Alpaca Markets');
    });

    it('reserves quota for HFT operations', () => {
      // Set up some usage
      apiLimitManager.providers.alpaca.quotas.market_data.used = 150;
      
      // Standard priority should have limited quota due to HFT reservation
      const standardResult = apiLimitManager.canMakeRequest('alpaca', 'market_data', 'standard');
      const criticalResult = apiLimitManager.canMakeRequest('alpaca', 'market_data', 'critical');
      
      expect(standardResult.quotaRemaining).toBeLessThan(criticalResult.quotaRemaining);
    });

    it('denies requests when quota exceeded', () => {
      // Exhaust quota
      apiLimitManager.providers.alpaca.quotas.market_data.used = 200;
      
      const result = apiLimitManager.canMakeRequest('alpaca', 'market_data', 'standard');
      expect(result.allowed).toBe(false);
      expect(result.reason).toBe('Quota exceeded');
    });

    it('handles disabled providers', () => {
      apiLimitManager.providers.alpaca.enabled = false;
      
      const result = apiLimitManager.canMakeRequest('alpaca', 'market_data');
      expect(result.allowed).toBe(false);
      expect(result.reason).toBe('Provider disabled or not found');
    });

    it('handles unsupported request types', () => {
      const result = apiLimitManager.canMakeRequest('alpaca', 'unsupported_type');
      expect(result.allowed).toBe(false);
      expect(result.reason).toBe('Request type not supported');
    });
  });

  describe('Rate Limiting', () => {
    it('enforces rate limits per provider', () => {
      // Simulate rapid requests
      const now = Date.now();
      const mockTimes = Array(10).fill(now);
      apiLimitManager.requestHistory.set('alpaca', mockTimes);
      
      const result = apiLimitManager.canMakeRequest('alpaca', 'market_data');
      expect(result.allowed).toBe(false);
      expect(result.reason).toBe('Rate limit exceeded');
      expect(result.retryAfter).toBeDefined();
    });

    it('allows requests within rate limits', () => {
      const now = Date.now();
      const mockTimes = [now - 2000, now - 3000]; // Old requests
      apiLimitManager.requestHistory.set('alpaca', mockTimes);
      
      const result = apiLimitManager.canMakeRequest('alpaca', 'market_data');
      expect(result.allowed).toBe(true);
    });

    it('enforces concurrent request limits', () => {
      apiLimitManager.activeRequests.set('alpaca', 10);
      
      const result = apiLimitManager.canMakeRequest('alpaca', 'market_data');
      expect(result.allowed).toBe(false);
      expect(result.reason).toBe('Concurrent request limit exceeded');
    });
  });

  describe('Request Recording and Health Tracking', () => {
    it('records successful requests', () => {
      const initialUsed = apiLimitManager.providers.alpaca.quotas.market_data.used;
      
      apiLimitManager.recordRequest('alpaca', 'market_data', true);
      
      expect(apiLimitManager.providers.alpaca.quotas.market_data.used).toBe(initialUsed + 1);
      expect(apiLimitManager.providers.alpaca.healthScore).toBeGreaterThanOrEqual(100);
    });

    it('records failed requests and updates health score', () => {
      const initialHealth = apiLimitManager.providers.alpaca.healthScore;
      
      apiLimitManager.recordRequest('alpaca', 'market_data', false);
      
      expect(apiLimitManager.providers.alpaca.healthScore).toBeLessThan(initialHealth);
    });

    it('cleans up old request history', () => {
      const oldTime = Date.now() - 400000; // 6+ minutes ago
      const recentTime = Date.now() - 60000; // 1 minute ago
      
      apiLimitManager.requestHistory.set('alpaca', [oldTime, recentTime]);
      apiLimitManager.recordRequest('alpaca', 'market_data', true);
      
      const history = apiLimitManager.requestHistory.get('alpaca');
      expect(history.length).toBe(2); // Recent time + new request
      expect(history.includes(oldTime)).toBe(false);
    });
  });

  describe('Provider Selection and Optimization', () => {
    it('selects optimal provider based on health and availability', () => {
      // Set up provider states
      apiLimitManager.providers.alpaca.healthScore = 80;
      apiLimitManager.providers.polygon.enabled = true;
      apiLimitManager.providers.polygon.healthScore = 95;
      
      const provider = apiLimitManager.getOptimalProvider('market_data', 'AAPL', 'standard');
      expect(provider).toBe('polygon'); // Better health score
    });

    it('calculates provider score correctly', () => {
      const score = apiLimitManager.calculateProviderScore('alpaca', 'market_data', 'standard');
      expect(typeof score).toBe('number');
      expect(score).toBeGreaterThan(0);
    });

    it('prioritizes providers for HFT requests', () => {
      const criticalScore = apiLimitManager.calculateProviderScore('alpaca', 'market_data', 'critical');
      const standardScore = apiLimitManager.calculateProviderScore('alpaca', 'market_data', 'standard');
      
      expect(criticalScore).toBeGreaterThan(standardScore);
    });
  });

  describe('Symbol Priority Management', () => {
    it('sets symbol priority correctly', () => {
      apiLimitManager.setSymbolPriority('AAPL', 'critical');
      
      expect(apiLimitManager.symbolPriority.critical.has('AAPL')).toBe(true);
      expect(apiLimitManager.symbolPriority.high.has('AAPL')).toBe(false);
    });

    it('moves symbol between priority levels', () => {
      apiLimitManager.setSymbolPriority('AAPL', 'high');
      apiLimitManager.setSymbolPriority('AAPL', 'critical');
      
      expect(apiLimitManager.symbolPriority.high.has('AAPL')).toBe(false);
      expect(apiLimitManager.symbolPriority.critical.has('AAPL')).toBe(true);
    });

    it('gets symbol priority correctly', () => {
      apiLimitManager.setSymbolPriority('AAPL', 'high');
      
      const priority = apiLimitManager.getSymbolPriority('AAPL');
      expect(priority).toBe('high');
    });

    it('returns standard priority for unknown symbols', () => {
      const priority = apiLimitManager.getSymbolPriority('UNKNOWN');
      expect(priority).toBe('standard');
    });
  });

  describe('Usage Statistics and Monitoring', () => {
    it('provides comprehensive usage statistics', () => {
      const stats = apiLimitManager.getAllUsageStats();
      
      expect(stats).toHaveProperty('alpaca');
      expect(stats).toHaveProperty('polygon');
      expect(stats).toHaveProperty('yahoo');
      
      expect(stats.alpaca.name).toBe('Alpaca Markets');
      expect(stats.alpaca.quotas).toBeDefined();
      expect(stats.alpaca.healthScore).toBeDefined();
    });

    it('calculates current request rate', () => {
      const now = Date.now();
      apiLimitManager.requestHistory.set('alpaca', [now - 100, now - 200, now - 1500]);
      
      const rate = apiLimitManager.getCurrentRequestRate('alpaca');
      expect(rate).toBe(2); // 2 requests in last second
    });

    it('gets total available quota across providers', () => {
      const total = apiLimitManager.getTotalAvailableQuota();
      expect(typeof total).toBe('number');
      expect(total).toBeGreaterThan(0);
    });
  });

  describe('Threshold Monitoring and Alerts', () => {
    it('emits quota warning at 70% usage', (done) => {
      apiLimitManager.on('quotaWarning', (warning) => {
        expect(warning.provider).toBe('Alpaca Markets');
        expect(warning.requestType).toBe('market_data');
        expect(warning.usageRate).toBeGreaterThanOrEqual(0.7);
        done();
      });
      
      apiLimitManager.providers.alpaca.quotas.market_data.used = 140; // 70%
      apiLimitManager.checkUsageThresholds('alpaca', 'market_data');
    });

    it('emits quota emergency at 90% usage', (done) => {
      apiLimitManager.on('quotaEmergency', (emergency) => {
        expect(emergency.provider).toBe('Alpaca Markets');
        expect(emergency.requestType).toBe('market_data');
        expect(emergency.usageRate).toBeGreaterThanOrEqual(0.9);
        done();
      });
      
      apiLimitManager.providers.alpaca.quotas.market_data.used = 180; // 90%
      apiLimitManager.checkUsageThresholds('alpaca', 'market_data');
    });
  });

  describe('Optimization Recommendations', () => {
    it('identifies high usage recommendations', () => {
      apiLimitManager.providers.alpaca.quotas.market_data.used = 160; // 80%
      
      const recommendations = apiLimitManager.getOptimizationRecommendations();
      const highUsageRec = recommendations.find(r => r.type === 'high_usage');
      
      expect(highUsageRec).toBeDefined();
      expect(highUsageRec.severity).toBe('warning');
    });

    it('identifies poor health recommendations', () => {
      apiLimitManager.providers.alpaca.healthScore = 60;
      
      const recommendations = apiLimitManager.getOptimizationRecommendations();
      const poorHealthRec = recommendations.find(r => r.type === 'poor_health');
      
      expect(poorHealthRec).toBeDefined();
      expect(poorHealthRec.severity).toBe('warning');
    });

    it('warns about too many HFT symbols', () => {
      // Add many HFT symbols
      for (let i = 0; i < 60; i++) {
        apiLimitManager.symbolPriority.critical.add(`SYMBOL${i}`);
      }
      
      const recommendations = apiLimitManager.getOptimizationRecommendations();
      const tooManyHftRec = recommendations.find(r => r.type === 'too_many_hft_symbols');
      
      expect(tooManyHftRec).toBeDefined();
      expect(tooManyHftRec.count).toBe(60);
    });
  });

  describe('Configuration Management', () => {
    it('exports configuration correctly', () => {
      apiLimitManager.setSymbolPriority('AAPL', 'critical');
      
      const config = apiLimitManager.exportConfiguration();
      
      expect(config.providers).toBeDefined();
      expect(config.symbolPriority).toBeDefined();
      expect(config.optimizationSettings).toBeDefined();
      expect(config.timestamp).toBeDefined();
      expect(config.symbolPriority.critical.includes('AAPL')).toBe(true);
    });

    it('imports configuration correctly', () => {
      const mockConfig = {
        symbolPriority: {
          critical: ['AAPL', 'MSFT'],
          high: ['GOOGL']
        },
        optimizationSettings: {
          hftReservedQuota: 0.4
        }
      };
      
      apiLimitManager.importConfiguration(mockConfig);
      
      expect(apiLimitManager.symbolPriority.critical.has('AAPL')).toBe(true);
      expect(apiLimitManager.symbolPriority.critical.has('MSFT')).toBe(true);
      expect(apiLimitManager.symbolPriority.high.has('GOOGL')).toBe(true);
      expect(apiLimitManager.optimizationSettings.hftReservedQuota).toBe(0.4);
    });
  });

  describe('Async Request Management', () => {
    it('makes optimal request with failover', async () => {
      const mockRequestFunction = vi.fn().mockResolvedValue({ data: 'test' });
      
      const result = await apiLimitManager.makeOptimalRequest(
        'market_data',
        'AAPL',
        mockRequestFunction,
        'standard'
      );
      
      expect(result.success).toBe(true);
      expect(result.data).toEqual({ data: 'test' });
      expect(result.provider).toBeDefined();
    });

    it('tries multiple providers on failure', async () => {
      let attempts = 0;
      const mockRequestFunction = vi.fn().mockImplementation(() => {
        attempts++;
        if (attempts < 2) {
          throw new Error('Provider failed');
        }
        return Promise.resolve({ data: 'success' });
      });
      
      // Enable multiple providers
      apiLimitManager.providers.polygon.enabled = true;
      
      const result = await apiLimitManager.makeOptimalRequest(
        'market_data',
        'AAPL',
        mockRequestFunction,
        'standard'
      );
      
      expect(result.success).toBe(true);
      expect(attempts).toBeGreaterThan(1);
    });

    it('throws error when all providers fail', async () => {
      const mockRequestFunction = vi.fn().mockRejectedValue(new Error('All failed'));
      
      await expect(
        apiLimitManager.makeOptimalRequest('market_data', 'AAPL', mockRequestFunction)
      ).rejects.toThrow('All providers exhausted');
    });

    it('tracks active requests during execution', async () => {
      let activeCount = 0;
      const mockRequestFunction = vi.fn().mockImplementation(async () => {
        activeCount = apiLimitManager.activeRequests.get('alpaca') || 0;
        return { data: 'test' };
      });
      
      await apiLimitManager.makeOptimalRequest('market_data', 'AAPL', mockRequestFunction);
      
      expect(activeCount).toBe(1);
      expect(apiLimitManager.activeRequests.get('alpaca') || 0).toBe(0);
    });
  });

  describe('Event Emission', () => {
    it('emits events for symbol priority changes', (done) => {
      apiLimitManager.on('symbolPriorityChanged', (event) => {
        expect(event.symbol).toBe('AAPL');
        expect(event.priority).toBe('critical');
        expect(event.totalHftSymbols).toBe(1);
        done();
      });
      
      apiLimitManager.setSymbolPriority('AAPL', 'critical');
    });

    it('emits events for usage updates', (done) => {
      apiLimitManager.on('usageUpdate', (event) => {
        expect(event.provider).toBe('alpaca');
        expect(event.requestType).toBe('market_data');
        expect(event.success).toBe(true);
        done();
      });
      
      apiLimitManager.recordRequest('alpaca', 'market_data', true);
    });
  });
});