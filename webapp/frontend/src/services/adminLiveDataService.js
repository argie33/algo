/**
 * Admin Live Data Service
 * Provides admin functionality for live data management
 */

import api from './api';

class AdminLiveDataService {
  constructor() {
    this.baseUrl = '/admin/live-data';
  }

  /**
   * Get live data statistics
   * @returns {Promise<Object>} Live data statistics
   */
  async getStatistics() {
    try {
      const response = await api.get(`${this.baseUrl}/statistics`);
      return response.data;
    } catch (error) {
      console.error('Failed to get live data statistics:', error);
      throw error;
    }
  }

  /**
   * Get active connections
   * @returns {Promise<Array>} List of active connections
   */
  async getActiveConnections() {
    try {
      const response = await api.get(`${this.baseUrl}/connections`);
      return response.data;
    } catch (error) {
      console.error('Failed to get active connections:', error);
      throw error;
    }
  }

  /**
   * Start live data feed for a symbol
   * @param {string} symbol - Stock symbol
   * @returns {Promise<Object>} Operation result
   */
  async startFeed(symbol) {
    try {
      const response = await api.post(`${this.baseUrl}/start`, { symbol });
      return response.data;
    } catch (error) {
      console.error(`Failed to start feed for ${symbol}:`, error);
      throw error;
    }
  }

  /**
   * Stop live data feed for a symbol
   * @param {string} symbol - Stock symbol
   * @returns {Promise<Object>} Operation result
   */
  async stopFeed(symbol) {
    try {
      const response = await api.post(`${this.baseUrl}/stop`, { symbol });
      return response.data;
    } catch (error) {
      console.error(`Failed to stop feed for ${symbol}:`, error);
      throw error;
    }
  }

  /**
   * Get feed status for all symbols
   * @returns {Promise<Object>} Feed status by symbol
   */
  async getFeedStatus() {
    try {
      const response = await api.get(`${this.baseUrl}/status`);
      return response.data;
    } catch (error) {
      console.error('Failed to get feed status:', error);
      throw error;
    }
  }

  /**
   * Update feed configuration
   * @param {Object} config - Configuration object
   * @returns {Promise<Object>} Operation result
   */
  async updateConfig(config) {
    try {
      const response = await api.put(`${this.baseUrl}/config`, config);
      return response.data;
    } catch (error) {
      console.error('Failed to update feed configuration:', error);
      throw error;
    }
  }

  /**
   * Get service health status
   * @returns {Promise<Object>} Health status
   */
  async getHealthStatus() {
    try {
      const response = await api.get(`${this.baseUrl}/health`);
      return response.data;
    } catch (error) {
      console.error('Failed to get health status:', error);
      throw error;
    }
  }
}

export default new AdminLiveDataService();