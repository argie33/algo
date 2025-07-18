/**
 * Offline Support - Service worker, caching, and offline functionality
 * Provides comprehensive offline capabilities for the trading platform
 */

class OfflineSupport {
  constructor() {
    this.isOnline = navigator.onLine;
    this.cache = new Map();
    this.pendingRequests = [];
    this.cacheName = 'trading-platform-v1';
    this.offlineQueue = [];
    
    this.initializeOfflineSupport();
  }

  /**
   * Initialize offline support
   */
  async initializeOfflineSupport() {
    this.setupNetworkListener();
    await this.registerServiceWorker();
    this.setupOfflineUI();
    this.setupCaching();
    this.setupOfflineQueue();
  }

  /**
   * Setup network status listener
   */
  setupNetworkListener() {
    window.addEventListener('online', () => {
      this.isOnline = true;
      this.handleOnlineStatus();
      this.processPendingRequests();
    });

    window.addEventListener('offline', () => {
      this.isOnline = false;
      this.handleOfflineStatus();
    });

    // Periodic connectivity check
    setInterval(() => {
      this.checkConnectivity();
    }, 30000);
  }

  /**
   * Register service worker
   */
  async registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      try {
        const registration = await navigator.serviceWorker.register(
          await this.createServiceWorkerScript()
        );
        
        console.log('✅ Service Worker registered:', registration);
        
        // Listen for service worker updates
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed') {
              this.handleServiceWorkerUpdate();
            }
          });
        });

        return registration;
      } catch (error) {
        console.error('❌ Service Worker registration failed:', error);
      }
    }
  }

  /**
   * Create service worker script dynamically
   */
  async createServiceWorkerScript() {
    const swCode = `
      const CACHE_NAME = '${this.cacheName}';
      const urlsToCache = [
        '/',
        '/static/css/main.css',
        '/static/js/main.js',
        '/manifest.json'
      ];

      // Install event - cache resources
      self.addEventListener('install', (event) => {
        event.waitUntil(
          caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(urlsToCache))
        );
      });

      // Activate event - clean up old caches
      self.addEventListener('activate', (event) => {
        event.waitUntil(
          caches.keys().then((cacheNames) => {
            return Promise.all(
              cacheNames.map((cacheName) => {
                if (cacheName !== CACHE_NAME) {
                  return caches.delete(cacheName);
                }
              })
            );
          })
        );
      });

      // Fetch event - serve from cache when offline
      self.addEventListener('fetch', (event) => {
        event.respondWith(
          caches.match(event.request)
            .then((response) => {
              // Return cached version or fetch from network
              return response || fetch(event.request).then((response) => {
                // Cache successful responses
                if (response.status === 200) {
                  const responseClone = response.clone();
                  caches.open(CACHE_NAME)
                    .then((cache) => {
                      cache.put(event.request, responseClone);
                    });
                }
                return response;
              });
            })
            .catch(() => {
              // Return offline page for navigation requests
              if (event.request.mode === 'navigate') {
                return caches.match('/offline.html');
              }
            })
        );
      });

      // Background sync
      self.addEventListener('sync', (event) => {
        if (event.tag === 'background-sync') {
          event.waitUntil(self.registration.showNotification('Data synced'));
        }
      });
    `;

    const blob = new Blob([swCode], { type: 'application/javascript' });
    return URL.createObjectURL(blob);
  }

  /**
   * Setup offline UI indicators
   */
  setupOfflineUI() {
    // Create offline indicator
    const offlineIndicator = document.createElement('div');
    offlineIndicator.id = 'offline-indicator';
    offlineIndicator.innerHTML = `
      <div class="offline-banner">
        <span class="offline-icon">📶</span>
        <span class="offline-text">You're offline. Some features may be limited.</span>
        <button class="retry-button" onclick="window.location.reload()">Retry</button>
      </div>
    `;

    const style = document.createElement('style');
    style.textContent = `
      #offline-indicator {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 10000;
        transform: translateY(-100%);
        transition: transform 0.3s ease;
      }
      
      #offline-indicator.show {
        transform: translateY(0);
      }
      
      .offline-banner {
        background: #ff6b6b;
        color: white;
        padding: 12px 20px;
        text-align: center;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
      }
      
      .offline-icon {
        font-size: 18px;
      }
      
      .retry-button {
        background: rgba(255, 255, 255, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.3);
        color: white;
        padding: 6px 12px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
      }
      
      .retry-button:hover {
        background: rgba(255, 255, 255, 0.3);
      }
    `;

    document.head.appendChild(style);
    document.body.appendChild(offlineIndicator);
  }

  /**
   * Handle online status
   */
  handleOnlineStatus() {
    console.log('🌐 Connection restored');
    
    const indicator = document.getElementById('offline-indicator');
    if (indicator) {
      indicator.classList.remove('show');
    }

    // Notify components
    window.dispatchEvent(new CustomEvent('connectionStatusChange', {
      detail: { isOnline: true }
    }));

    // Show success notification
    this.showNotification('Connection restored', 'success');
  }

  /**
   * Handle offline status
   */
  handleOfflineStatus() {
    console.log('📡 Connection lost');
    
    const indicator = document.getElementById('offline-indicator');
    if (indicator) {
      indicator.classList.add('show');
    }

    // Notify components
    window.dispatchEvent(new CustomEvent('connectionStatusChange', {
      detail: { isOnline: false }
    }));

    // Show offline notification
    this.showNotification('You are offline', 'warning');
  }

  /**
   * Setup caching for offline access
   */
  setupCaching() {
    // Cache critical data
    this.cacheTypes = {
      portfolio: { ttl: 300000, key: 'portfolio-data' }, // 5 minutes
      markets: { ttl: 60000, key: 'market-data' },       // 1 minute
      settings: { ttl: 3600000, key: 'user-settings' },  // 1 hour
      watchlist: { ttl: 600000, key: 'watchlist-data' }  // 10 minutes
    };

    // Set up periodic cache cleanup
    setInterval(() => {
      this.cleanupExpiredCache();
    }, 60000); // Every minute
  }

  /**
   * Cache data with TTL
   */
  cacheData(key, data, ttl = 300000) {
    const cacheEntry = {
      data,
      timestamp: Date.now(),
      ttl
    };

    this.cache.set(key, cacheEntry);
    
    // Also store in localStorage for persistence
    try {
      localStorage.setItem(`cache_${key}`, JSON.stringify(cacheEntry));
    } catch (error) {
      console.warn('Failed to store cache in localStorage:', error);
    }
  }

  /**
   * Get cached data
   */
  getCachedData(key) {
    let cacheEntry = this.cache.get(key);
    
    // Try localStorage if not in memory
    if (!cacheEntry) {
      try {
        const stored = localStorage.getItem(`cache_${key}`);
        if (stored) {
          cacheEntry = JSON.parse(stored);
          this.cache.set(key, cacheEntry);
        }
      } catch (error) {
        console.warn('Failed to retrieve cache from localStorage:', error);
      }
    }

    if (!cacheEntry) return null;

    // Check if expired
    const now = Date.now();
    if (now - cacheEntry.timestamp > cacheEntry.ttl) {
      this.cache.delete(key);
      localStorage.removeItem(`cache_${key}`);
      return null;
    }

    return cacheEntry.data;
  }

  /**
   * Setup offline request queue
   */
  setupOfflineQueue() {
    // Load pending requests from storage
    try {
      const stored = localStorage.getItem('offline-queue');
      if (stored) {
        this.offlineQueue = JSON.parse(stored);
      }
    } catch (error) {
      console.warn('Failed to load offline queue:', error);
    }
  }

  /**
   * Add request to offline queue
   */
  queueOfflineRequest(url, options = {}) {
    const request = {
      id: Date.now() + Math.random(),
      url,
      options,
      timestamp: Date.now()
    };

    this.offlineQueue.push(request);
    
    // Persist to storage
    try {
      localStorage.setItem('offline-queue', JSON.stringify(this.offlineQueue));
    } catch (error) {
      console.warn('Failed to save offline queue:', error);
    }

    console.log('📤 Request queued for when online:', url);
  }

  /**
   * Process pending requests when online
   */
  async processPendingRequests() {
    if (!this.isOnline || this.offlineQueue.length === 0) return;

    console.log(`🔄 Processing ${this.offlineQueue.length} queued requests`);

    const requests = [...this.offlineQueue];
    this.offlineQueue = [];

    for (const request of requests) {
      try {
        const response = await fetch(request.url, request.options);
        if (response.ok) {
          console.log('✅ Offline request processed:', request.url);
        } else {
          // Re-queue failed requests
          this.offlineQueue.push(request);
        }
      } catch (error) {
        console.error('❌ Failed to process offline request:', error);
        // Re-queue failed requests
        this.offlineQueue.push(request);
      }
    }

    // Update storage
    try {
      localStorage.setItem('offline-queue', JSON.stringify(this.offlineQueue));
    } catch (error) {
      console.warn('Failed to update offline queue:', error);
    }
  }

  /**
   * Check connectivity
   */
  async checkConnectivity() {
    try {
      const response = await fetch('/api/health', { 
        method: 'HEAD',
        cache: 'no-cache'
      });
      
      const wasOnline = this.isOnline;
      this.isOnline = response.ok;
      
      if (this.isOnline !== wasOnline) {
        if (this.isOnline) {
          this.handleOnlineStatus();
        } else {
          this.handleOfflineStatus();
        }
      }
    } catch (error) {
      if (this.isOnline) {
        this.isOnline = false;
        this.handleOfflineStatus();
      }
    }
  }

  /**
   * Cleanup expired cache entries
   */
  cleanupExpiredCache() {
    const now = Date.now();
    
    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp > entry.ttl) {
        this.cache.delete(key);
        localStorage.removeItem(`cache_${key}`);
      }
    }
  }

  /**
   * Handle service worker update
   */
  handleServiceWorkerUpdate() {
    this.showNotification('App update available. Refresh to get the latest version.', 'info');
  }

  /**
   * Show notification
   */
  showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
      <span class="notification-message">${message}</span>
      <button class="notification-close">&times;</button>
    `;

    // Add styles if not already present
    if (!document.getElementById('notification-styles')) {
      const style = document.createElement('style');
      style.id = 'notification-styles';
      style.textContent = `
        .notification {
          position: fixed;
          top: 20px;
          right: 20px;
          padding: 12px 16px;
          border-radius: 6px;
          color: white;
          display: flex;
          align-items: center;
          gap: 10px;
          z-index: 10001;
          max-width: 350px;
          animation: slideIn 0.3s ease;
        }
        
        .notification-success { background: #4caf50; }
        .notification-warning { background: #ff9800; }
        .notification-error { background: #f44336; }
        .notification-info { background: #2196f3; }
        
        .notification-close {
          background: none;
          border: none;
          color: white;
          font-size: 18px;
          cursor: pointer;
          padding: 0;
          margin-left: auto;
        }
        
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
      `;
      document.head.appendChild(style);
    }

    // Add to page
    document.body.appendChild(notification);

    // Auto remove after 5 seconds
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, 5000);

    // Close button handler
    notification.querySelector('.notification-close').addEventListener('click', () => {
      notification.remove();
    });
  }

  /**
   * Get offline status
   */
  getOfflineStatus() {
    return {
      isOnline: this.isOnline,
      cacheSize: this.cache.size,
      queuedRequests: this.offlineQueue.length,
      serviceWorkerSupported: 'serviceWorker' in navigator,
      serviceWorkerRegistered: navigator.serviceWorker?.controller !== null
    };
  }
}

// Create singleton instance
const offlineSupport = new OfflineSupport();

// React hook for offline support
export const useOfflineSupport = () => {
  const [isOnline, setIsOnline] = React.useState(offlineSupport.isOnline);

  React.useEffect(() => {
    const handleConnectionChange = (e) => {
      setIsOnline(e.detail.isOnline);
    };

    window.addEventListener('connectionStatusChange', handleConnectionChange);
    return () => window.removeEventListener('connectionStatusChange', handleConnectionChange);
  }, []);

  return {
    isOnline,
    cacheData: offlineSupport.cacheData.bind(offlineSupport),
    getCachedData: offlineSupport.getCachedData.bind(offlineSupport),
    queueRequest: offlineSupport.queueOfflineRequest.bind(offlineSupport),
    status: offlineSupport.getOfflineStatus.bind(offlineSupport)
  };
};

// Add to React import
const React = require('react');

export default offlineSupport;
export { OfflineSupport };

// Export utilities
export const cacheData = (key, data, ttl) => offlineSupport.cacheData(key, data, ttl);
export const getCachedData = (key) => offlineSupport.getCachedData(key);
export const getOfflineStatus = () => offlineSupport.getOfflineStatus();