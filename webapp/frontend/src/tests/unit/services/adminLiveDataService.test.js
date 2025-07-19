/**
 * Admin Live Data Service Unit Tests
 * Tests for admin live data management functionality
 */

import { describe, test, expect, vi, beforeEach } from 'vitest';
import adminLiveDataService from '../../../services/adminLiveDataService';
import api from '../../../services/api';

// Mock the api service
vi.mock('../../../services/api');

describe('AdminLiveDataService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getStatistics', () => {
    test('should fetch statistics successfully', async () => {
      const mockStats = {
        activeConnections: 5,
        totalSymbols: 10,
        dataPoints: 1000,
        uptime: '2h 30m'
      };
      
      api.get.mockResolvedValue({ data: mockStats });
      
      const result = await adminLiveDataService.getStatistics();
      
      expect(api.get).toHaveBeenCalledWith('/admin/live-data/statistics');
      expect(result).toEqual(mockStats);
    });

    test('should handle API errors gracefully', async () => {
      const mockError = new Error('Network error');
      api.get.mockRejectedValue(mockError);
      
      await expect(adminLiveDataService.getStatistics()).rejects.toThrow('Network error');
    });
  });

  describe('getActiveConnections', () => {
    test('should fetch active connections successfully', async () => {
      const mockConnections = [
        { id: 1, symbol: 'AAPL', status: 'active' },
        { id: 2, symbol: 'GOOGL', status: 'active' }
      ];
      
      api.get.mockResolvedValue({ data: mockConnections });
      
      const result = await adminLiveDataService.getActiveConnections();
      
      expect(api.get).toHaveBeenCalledWith('/admin/live-data/connections');
      expect(result).toEqual(mockConnections);
    });

    test('should handle empty connections list', async () => {
      api.get.mockResolvedValue({ data: [] });
      
      const result = await adminLiveDataService.getActiveConnections();
      
      expect(result).toEqual([]);
    });
  });

  describe('startFeed', () => {
    test('should start feed for symbol successfully', async () => {
      const symbol = 'AAPL';
      const mockResponse = { success: true, message: 'Feed started' };
      
      api.post.mockResolvedValue({ data: mockResponse });
      
      const result = await adminLiveDataService.startFeed(symbol);
      
      expect(api.post).toHaveBeenCalledWith('/admin/live-data/start', { symbol });
      expect(result).toEqual(mockResponse);
    });

    test('should handle start feed errors', async () => {
      const symbol = 'INVALID';
      const mockError = new Error('Invalid symbol');
      api.post.mockRejectedValue(mockError);
      
      await expect(adminLiveDataService.startFeed(symbol)).rejects.toThrow('Invalid symbol');
    });
  });

  describe('stopFeed', () => {
    test('should stop feed for symbol successfully', async () => {
      const symbol = 'AAPL';
      const mockResponse = { success: true, message: 'Feed stopped' };
      
      api.post.mockResolvedValue({ data: mockResponse });
      
      const result = await adminLiveDataService.stopFeed(symbol);
      
      expect(api.post).toHaveBeenCalledWith('/admin/live-data/stop', { symbol });
      expect(result).toEqual(mockResponse);
    });
  });

  describe('getFeedStatus', () => {
    test('should get feed status successfully', async () => {
      const mockStatus = {
        AAPL: { active: true, lastUpdate: '2025-07-19T10:00:00Z' },
        GOOGL: { active: false, lastUpdate: '2025-07-19T09:30:00Z' }
      };
      
      api.get.mockResolvedValue({ data: mockStatus });
      
      const result = await adminLiveDataService.getFeedStatus();
      
      expect(api.get).toHaveBeenCalledWith('/admin/live-data/status');
      expect(result).toEqual(mockStatus);
    });
  });

  describe('updateConfig', () => {
    test('should update configuration successfully', async () => {
      const config = { refreshInterval: 1000, maxConnections: 100 };
      const mockResponse = { success: true, config };
      
      api.put.mockResolvedValue({ data: mockResponse });
      
      const result = await adminLiveDataService.updateConfig(config);
      
      expect(api.put).toHaveBeenCalledWith('/admin/live-data/config', config);
      expect(result).toEqual(mockResponse);
    });

    test('should validate config before update', async () => {
      const invalidConfig = { refreshInterval: -1 };
      const mockError = new Error('Invalid configuration');
      api.put.mockRejectedValue(mockError);
      
      await expect(adminLiveDataService.updateConfig(invalidConfig)).rejects.toThrow('Invalid configuration');
    });
  });

  describe('getHealthStatus', () => {
    test('should get health status successfully', async () => {
      const mockHealth = {
        status: 'healthy',
        uptime: 86400,
        memoryUsage: '45%',
        cpuUsage: '12%'
      };
      
      api.get.mockResolvedValue({ data: mockHealth });
      
      const result = await adminLiveDataService.getHealthStatus();
      
      expect(api.get).toHaveBeenCalledWith('/admin/live-data/health');
      expect(result).toEqual(mockHealth);
    });

    test('should handle unhealthy status', async () => {
      const mockHealth = {
        status: 'unhealthy',
        errors: ['Database connection failed']
      };
      
      api.get.mockResolvedValue({ data: mockHealth });
      
      const result = await adminLiveDataService.getHealthStatus();
      
      expect(result.status).toBe('unhealthy');
      expect(result.errors).toContain('Database connection failed');
    });
  });

  describe('Error Handling', () => {
    test('should log errors appropriately', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const mockError = new Error('API Error');
      api.get.mockRejectedValue(mockError);
      
      try {
        await adminLiveDataService.getStatistics();
      } catch (error) {
        // Expected to throw
      }
      
      expect(consoleSpy).toHaveBeenCalledWith('Failed to get live data statistics:', mockError);
      
      consoleSpy.mockRestore();
    });
  });

  describe('Integration Scenarios', () => {
    test('should handle rapid start/stop operations', async () => {
      const symbol = 'AAPL';
      
      api.post.mockResolvedValue({ data: { success: true } });
      
      // Start feed
      await adminLiveDataService.startFeed(symbol);
      
      // Stop feed immediately
      await adminLiveDataService.stopFeed(symbol);
      
      expect(api.post).toHaveBeenCalledTimes(2);
      expect(api.post).toHaveBeenNthCalledWith(1, '/admin/live-data/start', { symbol });
      expect(api.post).toHaveBeenNthCalledWith(2, '/admin/live-data/stop', { symbol });
    });

    test('should handle multiple symbol operations', async () => {
      const symbols = ['AAPL', 'GOOGL', 'MSFT'];
      
      api.post.mockResolvedValue({ data: { success: true } });
      
      // Start all feeds concurrently
      const startPromises = symbols.map(symbol => 
        adminLiveDataService.startFeed(symbol)
      );
      
      await Promise.all(startPromises);
      
      expect(api.post).toHaveBeenCalledTimes(3);
    });
  });
});