/**
 * Correlation ID Service
 * Provides request tracking across the entire application
 * Addresses REQ-010: Error Handling Critical Gaps - Correlation IDs
 */

import { v4 as uuidv4 } from 'uuid';

class CorrelationService {
  constructor() {
    this.currentCorrelationId = null;
    this.correlationHistory = [];
    this.maxHistorySize = 1000;
    this.sessionId = this.generateSessionId();
    this.requestCounter = 0;
    
    // Initialize session correlation ID
    this.initializeSessionCorrelation();
  }

  /**
   * Generate a new correlation ID
   */
  generateCorrelationId() {
    this.requestCounter++;
    const timestamp = Date.now().toString(36);
    const counter = this.requestCounter.toString(36).padStart(4, '0');
    const random = Math.random().toString(36).substring(2, 8);
    
    return `${timestamp}-${counter}-${random}`;
  }

  /**
   * Generate a session ID
   */
  generateSessionId() {
    const stored = sessionStorage.getItem('sessionId');
    if (stored) {
      return stored;
    }
    
    const sessionId = uuidv4();
    sessionStorage.setItem('sessionId', sessionId);
    return sessionId;
  }

  /**
   * Initialize session correlation
   */
  initializeSessionCorrelation() {
    this.currentCorrelationId = this.generateCorrelationId();
    
    // Store in session storage for persistence across page reloads
    sessionStorage.setItem('currentCorrelationId', this.currentCorrelationId);
    
    console.log('🔗 Session correlation initialized:', {
      sessionId: this.sessionId,
      correlationId: this.currentCorrelationId
    });
  }

  /**
   * Get current correlation ID
   */
  getCurrentCorrelationId() {
    if (!this.currentCorrelationId) {
      this.currentCorrelationId = this.generateCorrelationId();
    }
    return this.currentCorrelationId;
  }

  /**
   * Start a new correlation context
   */
  startCorrelation(context = {}) {
    const correlationId = this.generateCorrelationId();
    
    const correlationEntry = {
      id: correlationId,
      parentId: this.currentCorrelationId,
      sessionId: this.sessionId,
      startTime: Date.now(),
      context: {
        ...context,
        url: window.location.href,
        userAgent: navigator.userAgent,
        timestamp: new Date().toISOString()
      },
      events: [],
      status: 'active'
    };

    this.currentCorrelationId = correlationId;
    this.correlationHistory.push(correlationEntry);
    
    // Maintain history size
    if (this.correlationHistory.length > this.maxHistorySize) {
      this.correlationHistory.shift();
    }
    
    // Update session storage
    sessionStorage.setItem('currentCorrelationId', correlationId);
    
    console.log('🔗 Started correlation:', correlationId, context);
    
    return correlationId;
  }

  /**
   * Add event to current correlation
   */
  addEvent(event, data = {}) {
    const correlationId = this.getCurrentCorrelationId();
    const correlationEntry = this.correlationHistory.find(entry => entry.id === correlationId);
    
    if (correlationEntry) {
      correlationEntry.events.push({
        event,
        data,
        timestamp: Date.now(),
        isoTimestamp: new Date().toISOString()
      });
    }
    
    console.log('🔗 Added event to correlation:', correlationId, event, data);
  }

  /**
   * Complete current correlation
   */
  completeCorrelation(result = {}) {
    const correlationId = this.getCurrentCorrelationId();
    const correlationEntry = this.correlationHistory.find(entry => entry.id === correlationId);
    
    if (correlationEntry) {
      correlationEntry.status = 'completed';
      correlationEntry.endTime = Date.now();
      correlationEntry.duration = correlationEntry.endTime - correlationEntry.startTime;
      correlationEntry.result = result;
      
      // Return to parent correlation if exists
      if (correlationEntry.parentId) {
        this.currentCorrelationId = correlationEntry.parentId;
        sessionStorage.setItem('currentCorrelationId', correlationEntry.parentId);
      }
    }
    
    console.log('🔗 Completed correlation:', correlationId, result);
    
    return correlationId;
  }

  /**
   * Fail current correlation
   */
  failCorrelation(error) {
    const correlationId = this.getCurrentCorrelationId();
    const correlationEntry = this.correlationHistory.find(entry => entry.id === correlationId);
    
    if (correlationEntry) {
      correlationEntry.status = 'failed';
      correlationEntry.endTime = Date.now();
      correlationEntry.duration = correlationEntry.endTime - correlationEntry.startTime;
      correlationEntry.error = {
        message: error.message,
        stack: error.stack,
        name: error.name,
        code: error.code
      };
      
      // Return to parent correlation if exists
      if (correlationEntry.parentId) {
        this.currentCorrelationId = correlationEntry.parentId;
        sessionStorage.setItem('currentCorrelationId', correlationEntry.parentId);
      }
    }
    
    console.error('🔗 Failed correlation:', correlationId, error);
    
    return correlationId;
  }

  /**
   * Get correlation by ID
   */
  getCorrelation(correlationId) {
    return this.correlationHistory.find(entry => entry.id === correlationId);
  }

  /**
   * Get all correlations
   */
  getAllCorrelations() {
    return this.correlationHistory;
  }

  /**
   * Get correlation chain (parent-child relationships)
   */
  getCorrelationChain(correlationId) {
    const chain = [];
    let current = this.getCorrelation(correlationId);
    
    while (current) {
      chain.unshift(current);
      current = current.parentId ? this.getCorrelation(current.parentId) : null;
    }
    
    return chain;
  }

  /**
   * Get correlation statistics
   */
  getStatistics() {
    const stats = {
      totalCorrelations: this.correlationHistory.length,
      activeCorrelations: this.correlationHistory.filter(c => c.status === 'active').length,
      completedCorrelations: this.correlationHistory.filter(c => c.status === 'completed').length,
      failedCorrelations: this.correlationHistory.filter(c => c.status === 'failed').length,
      averageDuration: 0,
      sessionId: this.sessionId,
      currentCorrelationId: this.currentCorrelationId
    };
    
    const completedCorrelations = this.correlationHistory.filter(c => c.duration);
    if (completedCorrelations.length > 0) {
      stats.averageDuration = completedCorrelations.reduce((sum, c) => sum + c.duration, 0) / completedCorrelations.length;
    }
    
    return stats;
  }

  /**
   * Export correlation data for debugging
   */
  exportCorrelationData() {
    return {
      sessionId: this.sessionId,
      currentCorrelationId: this.currentCorrelationId,
      correlationHistory: this.correlationHistory,
      statistics: this.getStatistics(),
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Clear correlation history
   */
  clearHistory() {
    this.correlationHistory = [];
    console.log('🔗 Cleared correlation history');
  }

  /**
   * Create correlation context for API calls
   */
  createApiContext(method, url, data = {}) {
    return {
      type: 'api_call',
      method,
      url,
      data: typeof data === 'object' ? JSON.stringify(data).substring(0, 1000) : data,
      userAgent: navigator.userAgent,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Create correlation context for UI interactions
   */
  createUIContext(action, component, data = {}) {
    return {
      type: 'ui_interaction',
      action,
      component,
      data,
      url: window.location.href,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Create correlation context for errors
   */
  createErrorContext(error, component, data = {}) {
    return {
      type: 'error',
      error: {
        message: error.message,
        stack: error.stack,
        name: error.name
      },
      component,
      data,
      url: window.location.href,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Wrapper for API calls with correlation tracking
   */
  async withCorrelation(operation, context = {}) {
    const correlationId = this.startCorrelation(context);
    
    try {
      this.addEvent('operation_start', { operation: operation.name || 'anonymous' });
      
      const result = await operation();
      
      this.addEvent('operation_success', { result: typeof result === 'object' ? 'object' : result });
      this.completeCorrelation({ success: true, result });
      
      return result;
    } catch (error) {
      this.addEvent('operation_error', { error: error.message });
      this.failCorrelation(error);
      throw error;
    }
  }

  /**
   * Get correlation headers for HTTP requests
   */
  getCorrelationHeaders() {
    return {
      'X-Correlation-ID': this.getCurrentCorrelationId(),
      'X-Session-ID': this.sessionId,
      'X-Request-ID': this.generateCorrelationId()
    };
  }

  /**
   * Enhanced fetch with correlation tracking
   */
  async correlatedFetch(url, options = {}) {
    const correlationId = this.startCorrelation(
      this.createApiContext(options.method || 'GET', url, options.body)
    );
    
    const enhancedOptions = {
      ...options,
      headers: {
        ...options.headers,
        ...this.getCorrelationHeaders()
      }
    };
    
    try {
      this.addEvent('fetch_start', { url, method: options.method || 'GET' });
      
      const response = await fetch(url, enhancedOptions);
      
      this.addEvent('fetch_response', { 
        status: response.status, 
        statusText: response.statusText,
        headers: Object.fromEntries(response.headers.entries())
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      
      this.addEvent('fetch_success', { dataSize: JSON.stringify(data).length });
      this.completeCorrelation({ success: true, status: response.status });
      
      return data;
    } catch (error) {
      this.addEvent('fetch_error', { error: error.message });
      this.failCorrelation(error);
      throw error;
    }
  }
}

// Create singleton instance
const correlationService = new CorrelationService();

// React hook for correlation service
export const useCorrelation = () => {
  const startCorrelation = React.useCallback((context) => {
    return correlationService.startCorrelation(context);
  }, []);

  const addEvent = React.useCallback((event, data) => {
    return correlationService.addEvent(event, data);
  }, []);

  const completeCorrelation = React.useCallback((result) => {
    return correlationService.completeCorrelation(result);
  }, []);

  const failCorrelation = React.useCallback((error) => {
    return correlationService.failCorrelation(error);
  }, []);

  const getCurrentCorrelationId = React.useCallback(() => {
    return correlationService.getCurrentCorrelationId();
  }, []);

  const withCorrelation = React.useCallback((operation, context) => {
    return correlationService.withCorrelation(operation, context);
  }, []);

  const correlatedFetch = React.useCallback((url, options) => {
    return correlationService.correlatedFetch(url, options);
  }, []);

  return {
    startCorrelation,
    addEvent,
    completeCorrelation,
    failCorrelation,
    getCurrentCorrelationId,
    withCorrelation,
    correlatedFetch
  };
};

// Enhanced axios interceptor with correlation tracking
export const setupAxiosCorrelation = (axiosInstance) => {
  // Request interceptor
  axiosInstance.interceptors.request.use(
    (config) => {
      const correlationId = correlationService.startCorrelation(
        correlationService.createApiContext(config.method, config.url, config.data)
      );
      
      config.headers = {
        ...config.headers,
        ...correlationService.getCorrelationHeaders()
      };
      
      config.metadata = { correlationId };
      
      correlationService.addEvent('axios_request_start', {
        method: config.method,
        url: config.url,
        correlationId
      });
      
      return config;
    },
    (error) => {
      correlationService.failCorrelation(error);
      return Promise.reject(error);
    }
  );

  // Response interceptor
  axiosInstance.interceptors.response.use(
    (response) => {
      correlationService.addEvent('axios_response_success', {
        status: response.status,
        statusText: response.statusText,
        correlationId: response.config.metadata?.correlationId
      });
      
      correlationService.completeCorrelation({
        success: true,
        status: response.status,
        data: response.data
      });
      
      return response;
    },
    (error) => {
      correlationService.addEvent('axios_response_error', {
        error: error.message,
        status: error.response?.status,
        correlationId: error.config?.metadata?.correlationId
      });
      
      correlationService.failCorrelation(error);
      return Promise.reject(error);
    }
  );
};

export default correlationService;