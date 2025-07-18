/**
 * Offline Service
 * Comprehensive offline error handling and data synchronization
 * Addresses REQ-010: Error Handling Critical Gaps - Offline Handling
 */

import correlationService from './correlationService';

class OfflineService {
  constructor() {
    this.isOnline = navigator.onLine;
    this.pendingRequests = new Map();
    this.offlineQueue = [];
    this.syncQueue = [];
    this.maxQueueSize = 100;
    this.retryAttempts = 3;
    this.retryDelay = 1000;
    this.storage = window.localStorage;
    this.subscribers = new Set();
    this.offlineData = new Map();
    this.lastSyncTime = null;
    
    // Initialize offline detection
    this.initializeOfflineDetection();
    
    // Load persisted data
    this.loadOfflineData();
    
    // Setup periodic sync
    this.setupPeriodicSync();
  }

  /**
   * Initialize offline detection with multiple strategies
   */
  initializeOfflineDetection() {
    // Standard online/offline events
    window.addEventListener('online', () => {
      this.handleOnline();
    });
    
    window.addEventListener('offline', () => {
      this.handleOffline();
    });
    
    // Enhanced connectivity checking
    this.startConnectivityMonitoring();
    
    console.log('🌐 Offline service initialized, current status:', this.isOnline ? 'online' : 'offline');
  }

  /**
   * Advanced connectivity monitoring
   */
  startConnectivityMonitoring() {
    setInterval(async () => {
      await this.checkConnectivity();
    }, 30000); // Check every 30 seconds
  }

  /**
   * Check actual connectivity with fallback methods
   */
  async checkConnectivity() {
    try {
      // Try multiple methods to detect connectivity
      const methods = [
        () => this.pingServer(),
        () => this.checkDNS(),
        () => this.checkFetch()
      ];
      
      const results = await Promise.allSettled(
        methods.map(method => method())
      );
      
      const onlineCount = results.filter(r => r.status === 'fulfilled' && r.value).length;
      const wasOnline = this.isOnline;
      this.isOnline = onlineCount > 0 || navigator.onLine;
      
      // Notify if status changed
      if (this.isOnline !== wasOnline) {
        if (this.isOnline) {
          this.handleOnline();
        } else {
          this.handleOffline();
        }
      }
      
    } catch (error) {
      console.warn('Connectivity check failed:', error.message);
    }
  }

  /**
   * Ping server for connectivity
   */
  async pingServer() {
    try {
      const response = await fetch('/api/health', {
        method: 'GET',
        cache: 'no-cache',
        timeout: 5000
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  /**
   * Check DNS resolution
   */
  async checkDNS() {
    try {
      const response = await fetch('https://dns.google/resolve?name=google.com&type=A', {
        method: 'GET',
        cache: 'no-cache',
        timeout: 5000
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  /**
   * Simple fetch check
   */
  async checkFetch() {
    try {
      const response = await fetch('/favicon.ico', {
        method: 'HEAD',
        cache: 'no-cache',
        timeout: 5000
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  /**
   * Handle online state
   */
  handleOnline() {
    console.log('🟢 Back online - starting sync process');
    this.isOnline = true;
    this.notifySubscribers('online');
    
    // Process offline queue
    this.processOfflineQueue();
    
    // Sync offline data
    this.syncOfflineData();
  }

  /**
   * Handle offline state
   */
  handleOffline() {
    console.log('🔴 Gone offline - enabling offline mode');
    this.isOnline = false;
    this.notifySubscribers('offline');
    
    // Save current state
    this.saveOfflineData();
  }

  /**
   * Subscribe to online/offline events
   */
  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  /**
   * Notify subscribers of status change
   */
  notifySubscribers(status) {
    this.subscribers.forEach(callback => {
      try {
        callback(status, this.isOnline);
      } catch (error) {
        console.error('Error notifying offline subscriber:', error);
      }
    });
  }

  /**
   * Queue request for offline processing
   */
  queueRequest(request) {
    if (this.offlineQueue.length >= this.maxQueueSize) {
      // Remove oldest request
      const removed = this.offlineQueue.shift();
      console.warn('Offline queue full, removing oldest request:', removed.id);
    }
    
    const queuedRequest = {
      id: correlationService.generateCorrelationId(),
      timestamp: Date.now(),
      request,
      attempts: 0,
      maxAttempts: this.retryAttempts
    };
    
    this.offlineQueue.push(queuedRequest);
    this.persistOfflineQueue();
    
    console.log('📤 Queued request for offline processing:', queuedRequest.id);
    return queuedRequest.id;
  }

  /**
   * Process offline queue when coming back online
   */
  async processOfflineQueue() {
    if (this.offlineQueue.length === 0) {
      return;
    }
    
    console.log('🔄 Processing offline queue:', this.offlineQueue.length, 'requests');
    
    const results = {
      success: 0,
      failed: 0,
      total: this.offlineQueue.length
    };
    
    // Process requests in order
    for (const queuedRequest of [...this.offlineQueue]) {
      try {
        await this.processQueuedRequest(queuedRequest);
        results.success++;
        
        // Remove from queue
        this.offlineQueue = this.offlineQueue.filter(req => req.id !== queuedRequest.id);
        
      } catch (error) {
        queuedRequest.attempts++;
        queuedRequest.lastError = error.message;
        
        if (queuedRequest.attempts >= queuedRequest.maxAttempts) {
          console.error('Max attempts reached for queued request:', queuedRequest.id);
          this.offlineQueue = this.offlineQueue.filter(req => req.id !== queuedRequest.id);
          results.failed++;
        }
      }
    }
    
    this.persistOfflineQueue();
    
    console.log('✅ Offline queue processed:', results);
    this.notifySubscribers('queue_processed', results);
  }

  /**
   * Process individual queued request
   */
  async processQueuedRequest(queuedRequest) {
    const { request } = queuedRequest;
    
    console.log('🔄 Processing queued request:', queuedRequest.id);
    
    // Recreate the request
    const response = await fetch(request.url, {
      method: request.method,
      headers: request.headers,
      body: request.body,
      ...correlationService.getCorrelationHeaders()
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    // Notify success
    this.notifySubscribers('request_processed', {
      id: queuedRequest.id,
      success: true,
      data
    });
    
    return data;
  }

  /**
   * Enhanced fetch with offline support
   */
  async fetch(url, options = {}) {
    const correlationId = correlationService.startCorrelation(
      correlationService.createApiContext(options.method || 'GET', url, options.body)
    );
    
    if (!this.isOnline) {
      // Handle offline request
      return this.handleOfflineRequest(url, options, correlationId);
    }
    
    try {
      correlationService.addEvent('fetch_start', { url, method: options.method || 'GET' });
      
      const response = await fetch(url, {
        ...options,
        headers: {
          ...options.headers,
          ...correlationService.getCorrelationHeaders()
        }
      });
      
      correlationService.addEvent('fetch_response', {
        status: response.status,
        statusText: response.statusText
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      
      // Cache successful response
      this.cacheResponse(url, options, data);
      
      correlationService.addEvent('fetch_success', { dataSize: JSON.stringify(data).length });
      correlationService.completeCorrelation({ success: true, status: response.status });
      
      return data;
      
    } catch (error) {
      correlationService.addEvent('fetch_error', { error: error.message });
      correlationService.failCorrelation(error);
      
      // Try to serve from cache
      const cachedData = this.getCachedResponse(url, options);
      if (cachedData) {
        console.log('📦 Serving cached response for:', url);
        return cachedData;
      }
      
      throw error;
    }
  }

  /**
   * Handle offline request
   */
  async handleOfflineRequest(url, options, correlationId) {
    console.log('📱 Handling offline request:', url);
    
    // Try to serve from cache first
    const cachedData = this.getCachedResponse(url, options);
    if (cachedData) {
      console.log('📦 Serving cached response for offline request:', url);
      correlationService.completeCorrelation({ success: true, source: 'cache' });
      return cachedData;
    }
    
    // If it's a GET request, queue it for later
    if ((options.method || 'GET') === 'GET') {
      this.queueRequest({
        url,
        method: options.method || 'GET',
        headers: options.headers,
        body: options.body,
        correlationId
      });
      
      throw new Error('Request queued for offline processing');
    }
    
    // For POST/PUT/DELETE, try to queue if appropriate
    if (this.isModificationRequest(options.method)) {
      const queueId = this.queueRequest({
        url,
        method: options.method,
        headers: options.headers,
        body: options.body,
        correlationId
      });
      
      // Return optimistic response
      return {
        success: true,
        queued: true,
        queueId,
        message: 'Request queued for processing when online'
      };
    }
    
    throw new Error('No cached data available for offline request');
  }

  /**
   * Check if request is a modification request
   */
  isModificationRequest(method) {
    return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method?.toUpperCase());
  }

  /**
   * Cache response data
   */
  cacheResponse(url, options, data) {
    const key = this.getCacheKey(url, options);
    const cacheEntry = {
      data,
      timestamp: Date.now(),
      url,
      method: options.method || 'GET',
      headers: options.headers
    };
    
    this.offlineData.set(key, cacheEntry);
    this.persistOfflineData();
  }

  /**
   * Get cached response
   */
  getCachedResponse(url, options) {
    const key = this.getCacheKey(url, options);
    const cacheEntry = this.offlineData.get(key);
    
    if (!cacheEntry) {
      return null;
    }
    
    // Check if cache is still valid (24 hours)
    const maxAge = 24 * 60 * 60 * 1000;
    if (Date.now() - cacheEntry.timestamp > maxAge) {
      this.offlineData.delete(key);
      return null;
    }
    
    return cacheEntry.data;
  }

  /**
   * Generate cache key
   */
  getCacheKey(url, options) {
    const method = options.method || 'GET';
    const body = options.body ? JSON.stringify(options.body) : '';
    return `${method}:${url}:${body}`;
  }

  /**
   * Persist offline data to localStorage
   */
  persistOfflineData() {
    try {
      const data = Array.from(this.offlineData.entries());
      this.storage.setItem('offlineData', JSON.stringify(data));
    } catch (error) {
      console.error('Failed to persist offline data:', error);
    }
  }

  /**
   * Load offline data from localStorage
   */
  loadOfflineData() {
    try {
      const data = this.storage.getItem('offlineData');
      if (data) {
        const entries = JSON.parse(data);
        this.offlineData = new Map(entries);
        console.log('📦 Loaded offline data:', this.offlineData.size, 'entries');
      }
    } catch (error) {
      console.error('Failed to load offline data:', error);
    }
  }

  /**
   * Persist offline queue to localStorage
   */
  persistOfflineQueue() {
    try {
      this.storage.setItem('offlineQueue', JSON.stringify(this.offlineQueue));
    } catch (error) {
      console.error('Failed to persist offline queue:', error);
    }
  }

  /**
   * Load offline queue from localStorage
   */
  loadOfflineQueue() {
    try {
      const data = this.storage.getItem('offlineQueue');
      if (data) {
        this.offlineQueue = JSON.parse(data);
        console.log('📤 Loaded offline queue:', this.offlineQueue.length, 'requests');
      }
    } catch (error) {
      console.error('Failed to load offline queue:', error);
    }
  }

  /**
   * Save current offline data
   */
  saveOfflineData() {
    this.persistOfflineData();
    this.persistOfflineQueue();
  }

  /**
   * Sync offline data when coming back online
   */
  async syncOfflineData() {
    if (!this.isOnline) {
      return;
    }
    
    console.log('🔄 Syncing offline data...');
    
    // Send sync telemetry
    try {
      await fetch('/api/sync/telemetry', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...correlationService.getCorrelationHeaders()
        },
        body: JSON.stringify({
          offlineDataSize: this.offlineData.size,
          queueSize: this.offlineQueue.length,
          lastSyncTime: this.lastSyncTime,
          currentTime: Date.now()
        })
      });
    } catch (error) {
      console.warn('Failed to send sync telemetry:', error);
    }
    
    this.lastSyncTime = Date.now();
  }

  /**
   * Setup periodic sync
   */
  setupPeriodicSync() {
    setInterval(() => {
      if (this.isOnline) {
        this.syncOfflineData();
      }
    }, 5 * 60 * 1000); // Every 5 minutes
  }

  /**
   * Clear offline data
   */
  clearOfflineData() {
    this.offlineData.clear();
    this.offlineQueue = [];
    this.storage.removeItem('offlineData');
    this.storage.removeItem('offlineQueue');
    console.log('🗑️ Cleared offline data');
  }

  /**
   * Get offline service statistics
   */
  getStatistics() {
    return {
      isOnline: this.isOnline,
      offlineDataSize: this.offlineData.size,
      queueSize: this.offlineQueue.length,
      lastSyncTime: this.lastSyncTime,
      subscribers: this.subscribers.size,
      maxQueueSize: this.maxQueueSize
    };
  }

  /**
   * Export offline data for debugging
   */
  exportOfflineData() {
    return {
      isOnline: this.isOnline,
      offlineData: Array.from(this.offlineData.entries()),
      offlineQueue: this.offlineQueue,
      statistics: this.getStatistics(),
      timestamp: new Date().toISOString()
    };
  }
}

// Create singleton instance
const offlineService = new OfflineService();

// React hook for offline service
export const useOffline = () => {
  const [isOnline, setIsOnline] = React.useState(offlineService.isOnline);
  const [queueSize, setQueueSize] = React.useState(offlineService.offlineQueue.length);
  
  React.useEffect(() => {
    const unsubscribe = offlineService.subscribe((status, online) => {
      setIsOnline(online);
      setQueueSize(offlineService.offlineQueue.length);
    });
    
    return unsubscribe;
  }, []);
  
  const fetch = React.useCallback((url, options) => {
    return offlineService.fetch(url, options);
  }, []);
  
  const clearOfflineData = React.useCallback(() => {
    offlineService.clearOfflineData();
  }, []);
  
  const getStatistics = React.useCallback(() => {
    return offlineService.getStatistics();
  }, []);
  
  return {
    isOnline,
    queueSize,
    fetch,
    clearOfflineData,
    getStatistics,
    subscribe: offlineService.subscribe.bind(offlineService)
  };
};

export default offlineService;