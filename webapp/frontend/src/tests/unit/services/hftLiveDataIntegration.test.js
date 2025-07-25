/**
 * Unit Tests for HFT Live Data Integration
 * Tests HFT-optimized data pipeline and performance monitoring
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { HFTLiveDataIntegration } from '../../../services/hftLiveDataIntegration.js';

// Mock dependencies
vi.mock('../../../services/liveDataService.js', () => ({
  default: {
    on: vi.fn(),
    off: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    getSubscriptions: vi.fn(() => [])
  }
}));

vi.mock('../../../services/apiLimitManager.js', () => ({
  default: {
    setSymbolPriority: vi.fn(),
    on: vi.fn()
  }
}));

vi.mock('../../../services/hftEngine.js', () => ({
  default: {
    processMarketData: vi.fn()
  }
}));

describe('HFTLiveDataIntegration', () => {
  let hftIntegration;
  let consoleErrorSpy;
  let consoleSpy;

  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    
    // Create a new instance for each test
    hftIntegration = new HFTLiveDataIntegration();
    
    // Mock localStorage
    global.localStorage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn()
    };

    // Clear timers
    vi.clearAllTimers();
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    consoleSpy.mockRestore();
    vi.clearAllTimers();
    if (hftIntegration.cleanup) {
      hftIntegration.cleanup();
    }
  });

  describe('Initialization and Configuration', () => {
    it('initializes with HFT-specific configuration', () => {
      expect(hftIntegration.config.maxAcceptableLatency).toBe(50);
      expect(hftIntegration.config.targetLatency).toBe(25);
      expect(hftIntegration.config.maxDataAge).toBe(1000);
    });

    it('initializes data structures for HFT management', () => {
      expect(hftIntegration.hftSymbols).toBeInstanceOf(Map);
      expect(hftIntegration.symbolMetrics).toBeInstanceOf(Map);
      expect(hftIntegration.activeStrategies).toBeInstanceOf(Map);
    });

    it('initializes performance tracking structures', () => {
      expect(hftIntegration.latencyHistory).toBeInstanceOf(Array);
      expect(hftIntegration.throughputMetrics).toBeDefined();
      expect(hftIntegration.connectionHealth).toBeDefined();
    });

    it('sets up connection health monitoring', () => {
      expect(hftIntegration.connectionHealth.primary).toBeDefined();
      expect(hftIntegration.connectionHealth.fallback).toBeDefined();
    });
  });

  describe('HFT Symbol Management', () => {
    it('adds HFT symbol with default configuration', () => {
      const config = hftIntegration.addHftSymbol('AAPL');
      
      expect(config.symbol).toBe('AAPL');
      expect(config.priority).toBe('critical');
      expect(config.channels).toContain('trades');
      expect(config.enabled).toBe(true);
      expect(hftIntegration.hftSymbols.has('AAPL')).toBe(true);
    });

    it('adds HFT symbol with custom configuration', () => {
      const customConfig = {
        priority: 'high',
        strategies: ['scalping', 'arbitrage'],
        channels: ['trades', 'quotes'],
        latencyRequirement: 30
      };
      
      const config = hftIntegration.addHftSymbol('MSFT', customConfig);
      
      expect(config.priority).toBe('high');
      expect(config.strategies).toEqual(['scalping', 'arbitrage']);
      expect(config.latencyRequirement).toBe(30);
    });

    it('initializes symbol metrics when adding HFT symbol', () => {
      hftIntegration.addHftSymbol('AAPL');
      
      const metrics = hftIntegration.symbolMetrics.get('AAPL');
      expect(metrics.latencyStats).toBeDefined();
      expect(metrics.messageCount).toBe(0);
      expect(metrics.performanceScore).toBe(100);
    });

    it('removes HFT symbol and cleans up data', () => {
      hftIntegration.addHftSymbol('AAPL');
      expect(hftIntegration.hftSymbols.has('AAPL')).toBe(true);
      
      const result = hftIntegration.removeHftSymbol('AAPL');
      
      expect(result).toBe(true);
      expect(hftIntegration.hftSymbols.has('AAPL')).toBe(false);
      expect(hftIntegration.symbolMetrics.has('AAPL')).toBe(false);
    });

    it('returns false when removing non-existent symbol', () => {
      const result = hftIntegration.removeHftSymbol('NONEXISTENT');
      expect(result).toBe(false);
    });
  });

  describe('Market Data Processing', () => {
    beforeEach(() => {
      hftIntegration.addHftSymbol('AAPL', { priority: 'critical' });
    });

    it('processes HFT market data with latency calculation', () => {
      const mockData = {
        symbol: 'AAPL',
        timestamp: Date.now() / 1000 - 0.025, // 25ms ago
        data: { price: 150.00, volume: 1000 }
      };

      hftIntegration.handleHftMarketData(mockData);
      
      const metrics = hftIntegration.symbolMetrics.get('AAPL');
      expect(metrics.latencyStats.count).toBe(1);
      expect(metrics.latencyStats.avg).toBeGreaterThan(0);
    });

    it('warns about latency violations', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      const mockData = {
        symbol: 'AAPL',
        timestamp: Date.now() / 1000 - 0.1, // 100ms ago (exceeds 50ms limit)
        data: { price: 150.00 }
      };

      hftIntegration.handleHftMarketData(mockData);
      
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('HFT latency warning for AAPL')
      );
      
      consoleSpy.mockRestore();
    });

    it('ignores non-HFT symbols', () => {
      const mockData = {
        symbol: 'UNKNOWN',
        data: { price: 100.00 }
      };

      // Should not throw or process
      expect(() => {
        hftIntegration.handleHftMarketData(mockData);
      }).not.toThrow();
      
      expect(hftIntegration.symbolMetrics.has('UNKNOWN')).toBe(false);
    });

    it('updates symbol metrics correctly', () => {
      const symbol = 'AAPL';
      const latency = 30;
      const timestamp = Date.now();
      
      hftIntegration.updateSymbolMetrics(symbol, latency, timestamp);
      
      const metrics = hftIntegration.symbolMetrics.get(symbol);
      expect(metrics.latencyStats.count).toBe(1);
      expect(metrics.latencyStats.min).toBe(30);
      expect(metrics.latencyStats.max).toBe(30);
      expect(metrics.latencyStats.avg).toBe(30);
    });

    it('forwards data to HFT engine', async () => {
      const mockHftEngine = await import('../../../services/hftEngine.js');
      
      const mockData = {
        symbol: 'AAPL',
        timestamp: Date.now() / 1000,
        data: { price: 150.00 }
      };

      hftIntegration.handleHftMarketData(mockData);
      
      expect(mockHftEngine.default.processMarketData).toHaveBeenCalled();
    });
  });

  describe('Performance Monitoring', () => {
    it('tracks latency history with size limits', () => {
      // Add more than 100 latency measurements
      for (let i = 0; i < 120; i++) {
        hftIntegration.trackLatency(25 + i);
      }
      
      expect(hftIntegration.latencyHistory.length).toBe(100);
      expect(hftIntegration.latencyHistory[0].latency).toBe(45); // First 20 removed
    });

    it('updates connection health based on latency', () => {
      hftIntegration.trackLatency(20); // Good latency
      expect(hftIntegration.connectionHealth.primary.healthy).toBe(true);
      
      hftIntegration.trackLatency(60); // Bad latency
      expect(hftIntegration.connectionHealth.primary.healthy).toBe(false);
    });

    it('calculates latency statistics correctly', () => {
      const latencies = [10, 20, 30, 40, 50];
      latencies.forEach(l => hftIntegration.trackLatency(l));
      
      const stats = hftIntegration.getLatencyStats();
      expect(stats.min).toBe(10);
      expect(stats.max).toBe(50);
      expect(stats.avg).toBe(30);
      expect(stats.p95).toBeDefined();
      expect(stats.p99).toBeDefined();
    });

    it('updates throughput metrics', () => {
      const tradeData = { price: 150.00, volume: 1000 };
      const quoteData = { bid: 149.50, ask: 150.50 };
      
      hftIntegration.updateThroughputMetrics(tradeData);
      hftIntegration.updateThroughputMetrics(quoteData);
      
      // Wait for window to reset (mocked)
      vi.advanceTimersByTime(1000);
      
      expect(hftIntegration.throughputMetrics.tradesPerSecond).toBeGreaterThanOrEqual(0);
      expect(hftIntegration.throughputMetrics.quotesPerSecond).toBeGreaterThanOrEqual(0);
    });

    it('collects comprehensive performance metrics', () => {
      hftIntegration.addHftSymbol('AAPL', { priority: 'critical' });
      hftIntegration.addHftSymbol('MSFT', { priority: 'high' });
      hftIntegration.trackLatency(25);
      
      const metrics = hftIntegration.collectPerformanceMetrics();
      
      expect(metrics.timestamp).toBeDefined();
      expect(metrics.latency).toBeDefined();
      expect(metrics.throughput).toBeDefined();
      expect(metrics.symbols.total).toBe(2);
      expect(metrics.symbols.byPriority.critical).toBe(1);
      expect(metrics.symbols.byPriority.high).toBe(1);
    });
  });

  describe('Data Quality Assessment', () => {
    beforeEach(() => {
      hftIntegration.addHftSymbol('AAPL');
    });

    it('assesses data quality based on required fields', () => {
      const goodData = {
        data: { price: 150.00, timestamp: Date.now() }
      };
      
      hftIntegration.updateDataQualityScore('AAPL', goodData);
      
      const metrics = hftIntegration.symbolMetrics.get('AAPL');
      expect(metrics.dataQuality).toBe('excellent');
    });

    it('penalizes missing required fields', () => {
      const incompleteData = {
        data: { price: 150.00 } // Missing timestamp
      };
      
      hftIntegration.updateDataQualityScore('AAPL', incompleteData);
      
      const metrics = hftIntegration.symbolMetrics.get('AAPL');
      expect(['good', 'fair', 'poor']).toContain(metrics.dataQuality);
    });

    it('detects suspicious price movements', () => {
      const metrics = hftIntegration.symbolMetrics.get('AAPL');
      metrics.lastPrice = 100.00;
      
      const suspiciousData = {
        data: { price: 150.00, timestamp: Date.now() } // 50% jump
      };
      
      hftIntegration.updateDataQualityScore('AAPL', suspiciousData);
      expect(['good', 'fair', 'poor']).toContain(metrics.dataQuality);
    });

    it('gets overall data quality assessment', () => {
      hftIntegration.addHftSymbol('MSFT');
      
      const metrics1 = hftIntegration.symbolMetrics.get('AAPL');
      const metrics2 = hftIntegration.symbolMetrics.get('MSFT');
      
      metrics1.dataQuality = 'excellent';
      metrics2.dataQuality = 'good';
      
      const overall = hftIntegration.getOverallDataQuality();
      expect(overall.excellent).toBe(1);
      expect(overall.good).toBe(1);
    });
  });

  describe('Latency Violation Handling', () => {
    beforeEach(() => {
      hftIntegration.addHftSymbol('AAPL', { priority: 'critical' });
    });

    it('handles latency violations with warnings', (done) => {
      hftIntegration.on('latencyViolation', (violation) => {
        expect(violation.symbol).toBe('AAPL');
        expect(violation.severity).toBe('warning');
        done();
      });
      
      hftIntegration.handleLatencyViolation('AAPL', 60, 50);
    });

    it('handles critical latency violations', (done) => {
      hftIntegration.on('latencyViolation', (violation) => {
        expect(violation.severity).toBe('critical');
        done();
      });
      
      hftIntegration.handleLatencyViolation('AAPL', 120, 50); // 2x threshold
    });

    it('disables symbol after repeated violations', () => {
      const config = hftIntegration.hftSymbols.get('AAPL');
      
      // Simulate 5 critical violations
      for (let i = 0; i < 5; i++) {
        hftIntegration.handleCriticalLatencyViolation('AAPL', {
          severity: 'critical',
          actualLatency: 120
        });
      }
      
      expect(config.enabled).toBe(false);
    });

    it('re-enables symbol after cooldown period', (done) => {
      const config = hftIntegration.hftSymbols.get('AAPL');
      
      // Disable symbol
      for (let i = 0; i < 5; i++) {
        hftIntegration.handleCriticalLatencyViolation('AAPL', {
          severity: 'critical'
        });
      }
      
      expect(config.enabled).toBe(false);
      
      // Advance time and check re-enable
      setTimeout(() => {
        expect(config.enabled).toBe(true);
        expect(config.violationCount).toBe(0);
        done();
      }, 30100); // Slightly more than cooldown
      
      vi.advanceTimersByTime(30100);
    });
  });

  describe('Quota Management Integration', () => {
    it('handles quota warnings by optimizing subscriptions', async () => {
      const mockLiveDataService = await import('../../../services/liveDataService.js');
      mockLiveDataService.default.getSubscriptions.mockReturnValue(['AAPL', 'MSFT', 'GOOGL']);
      
      hftIntegration.addHftSymbol('AAPL');
      
      hftIntegration.handleQuotaWarning({
        provider: 'alpaca',
        usageRate: 0.75
      });
      
      expect(mockLiveDataService.default.unsubscribe).toHaveBeenCalled();
    });

    it('activates emergency mode on quota emergency', async () => {
      const mockLiveDataService = await import('../../../services/liveDataService.js');
      mockLiveDataService.default.getSubscriptions.mockReturnValue(['AAPL', 'MSFT', 'GOOGL']);
      
      hftIntegration.addHftSymbol('AAPL', { priority: 'critical' });
      
      hftIntegration.handleQuotaEmergency({
        provider: 'alpaca',
        usageRate: 0.95
      });
      
      expect(mockLiveDataService.default.unsubscribe).toHaveBeenCalled();
    });

    it('preserves critical symbols in emergency mode', async () => {
      const mockLiveDataService = await import('../../../services/liveDataService.js');
      mockLiveDataService.default.getSubscriptions.mockReturnValue(['AAPL', 'MSFT', 'GOOGL']);
      
      hftIntegration.addHftSymbol('AAPL', { priority: 'critical' });
      
      hftIntegration.activateEmergencyMode();
      
      const unsubscribeCall = mockLiveDataService.default.unsubscribe.mock.calls[0];
      expect(unsubscribeCall[0]).not.toContain('AAPL');
      expect(unsubscribeCall[0]).toContain('MSFT');
      expect(unsubscribeCall[0]).toContain('GOOGL');
    });
  });

  describe('System Health Scoring', () => {
    it('calculates system health score correctly', () => {
      hftIntegration.trackLatency(25); // Good latency
      hftIntegration.connectionHealth.primary.healthy = true;
      
      const score = hftIntegration.calculateSystemHealthScore();
      expect(score).toBeGreaterThanOrEqual(70);
      expect(score).toBeLessThanOrEqual(100);
    });

    it('penalizes poor latency in health score', () => {
      hftIntegration.trackLatency(80); // Bad latency
      
      const score = hftIntegration.calculateSystemHealthScore();
      expect(score).toBeLessThan(100);
    });

    it('penalizes connection issues in health score', () => {
      hftIntegration.connectionHealth.primary.healthy = false;
      
      const score = hftIntegration.calculateSystemHealthScore();
      expect(score).toBeLessThanOrEqual(70);
    });

    it('provides comprehensive HFT performance summary', () => {
      hftIntegration.addHftSymbol('AAPL', { priority: 'critical' });
      hftIntegration.addHftSymbol('MSFT', { priority: 'high' });
      hftIntegration.trackLatency(25);
      
      const summary = hftIntegration.getHftPerformanceSummary();
      
      expect(summary.symbols.total).toBe(2);
      expect(summary.symbols.active).toBe(2);
      expect(summary.performance.latency).toBeDefined();
      expect(summary.health.systemScore).toBeDefined();
    });
  });

  describe('Configuration Persistence', () => {
    it('loads HFT symbol configurations from localStorage', async () => {
      const mockConfig = {
        symbols: [
          { symbol: 'AAPL', priority: 'critical' },
          { symbol: 'MSFT', priority: 'high' }
        ]
      };
      
      global.localStorage.getItem.mockReturnValue(JSON.stringify(mockConfig));
      
      await hftIntegration.loadHftSymbolConfigurations();
      
      expect(hftIntegration.hftSymbols.has('AAPL')).toBe(true);
      expect(hftIntegration.hftSymbols.has('MSFT')).toBe(true);
    });

    it('saves HFT symbol configurations to localStorage', () => {
      hftIntegration.addHftSymbol('AAPL', { priority: 'critical' });
      
      hftIntegration.saveHftSymbolConfigurations();
      
      expect(global.localStorage.setItem).toHaveBeenCalledWith(
        'hft_symbol_config',
        expect.stringContaining('AAPL')
      );
    });

    it('handles corrupt configuration gracefully', async () => {
      global.localStorage.getItem.mockReturnValue('invalid json');
      
      // Should not throw
      await expect(hftIntegration.loadHftSymbolConfigurations()).resolves.toBeUndefined();
    });
  });

  describe('Resource Cleanup', () => {
    it('cleans up performance monitoring interval', () => {
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      
      hftIntegration.cleanup();
      
      expect(clearIntervalSpy).toHaveBeenCalled();
    });

    it('removes event listeners on cleanup', async () => {
      const mockLiveDataService = await import('../../../services/liveDataService.js');
      
      hftIntegration.addHftSymbol('AAPL');
      hftIntegration.cleanup();
      
      expect(mockLiveDataService.default.off).toHaveBeenCalled();
    });

    it('saves configuration before cleanup', () => {
      hftIntegration.addHftSymbol('AAPL');
      
      hftIntegration.cleanup();
      
      expect(global.localStorage.setItem).toHaveBeenCalledWith(
        'hft_symbol_config',
        expect.any(String)
      );
    });
  });
});