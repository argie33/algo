/**
 * Memory Leak Prevention Utility
 * Provides cleanup utilities and memory monitoring for React components
 */

class MemoryLeakPrevention {
  constructor() {
    this.activeTimers = new Set();
    this.activeIntervals = new Set();
    this.activeObservers = new Set();
    this.activeEventListeners = new Set();
    this.activeAbortControllers = new Set();
    this.componentCleanupFunctions = new Map();
    
    // Override global functions to track them
    this.overrideGlobalFunctions();
    
    // Monitor memory usage
    this.startMemoryMonitoring();
  }

  /**
   * Override global functions to track resource creation
   */
  overrideGlobalFunctions() {
    // Track setTimeout
    const originalSetTimeout = window.setTimeout;
    window.setTimeout = (...args) => {
      const timerId = originalSetTimeout(...args);
      this.activeTimers.add(timerId);
      return timerId;
    };

    // Track clearTimeout
    const originalClearTimeout = window.clearTimeout;
    window.clearTimeout = (timerId) => {
      this.activeTimers.delete(timerId);
      return originalClearTimeout(timerId);
    };

    // Track setInterval
    const originalSetInterval = window.setInterval;
    window.setInterval = (...args) => {
      const intervalId = originalSetInterval(...args);
      this.activeIntervals.add(intervalId);
      return intervalId;
    };

    // Track clearInterval
    const originalClearInterval = window.clearInterval;
    window.clearInterval = (intervalId) => {
      this.activeIntervals.delete(intervalId);
      return originalClearInterval(intervalId);
    };
  }

  /**
   * Register cleanup function for a component
   */
  registerCleanup(componentId, cleanupFunction) {
    if (!this.componentCleanupFunctions.has(componentId)) {
      this.componentCleanupFunctions.set(componentId, []);
    }
    this.componentCleanupFunctions.get(componentId).push(cleanupFunction);
  }

  /**
   * Execute cleanup for a component
   */
  cleanup(componentId) {
    const cleanupFunctions = this.componentCleanupFunctions.get(componentId);
    if (cleanupFunctions) {
      cleanupFunctions.forEach(cleanup => {
        try {
          cleanup();
        } catch (error) {
          console.warn('Cleanup function failed:', error);
        }
      });
      this.componentCleanupFunctions.delete(componentId);
    }
  }

  /**
   * Create a managed timer that auto-cleans
   */
  createManagedTimer(componentId, callback, delay) {
    const timerId = setTimeout(() => {
      callback();
      this.activeTimers.delete(timerId);
    }, delay);

    this.registerCleanup(componentId, () => {
      clearTimeout(timerId);
      this.activeTimers.delete(timerId);
    });

    return timerId;
  }

  /**
   * Create a managed interval that auto-cleans
   */
  createManagedInterval(componentId, callback, delay) {
    const intervalId = setInterval(callback, delay);

    this.registerCleanup(componentId, () => {
      clearInterval(intervalId);
      this.activeIntervals.delete(intervalId);
    });

    return intervalId;
  }

  /**
   * Create a managed event listener that auto-cleans
   */
  createManagedEventListener(componentId, element, event, handler, options) {
    element.addEventListener(event, handler, options);
    
    const listenerInfo = { element, event, handler, options };
    this.activeEventListeners.add(listenerInfo);

    this.registerCleanup(componentId, () => {
      element.removeEventListener(event, handler, options);
      this.activeEventListeners.delete(listenerInfo);
    });

    return () => {
      element.removeEventListener(event, handler, options);
      this.activeEventListeners.delete(listenerInfo);
    };
  }

  /**
   * Create a managed observer that auto-cleans
   */
  createManagedObserver(componentId, ObserverClass, callback, options = {}) {
    const observer = new ObserverClass(callback, options);
    this.activeObservers.add(observer);

    this.registerCleanup(componentId, () => {
      if (observer.disconnect) observer.disconnect();
      if (observer.unobserve) observer.unobserve();
      this.activeObservers.delete(observer);
    });

    return observer;
  }

  /**
   * Create a managed AbortController that auto-cleans
   */
  createManagedAbortController(componentId) {
    const controller = new AbortController();
    this.activeAbortControllers.add(controller);

    this.registerCleanup(componentId, () => {
      if (!controller.signal.aborted) {
        controller.abort();
      }
      this.activeAbortControllers.delete(controller);
    });

    return controller;
  }

  /**
   * Create a managed WebSocket that auto-cleans
   */
  createManagedWebSocket(componentId, url, protocols) {
    const ws = new WebSocket(url, protocols);

    this.registerCleanup(componentId, () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    });

    return ws;
  }

  /**
   * Start memory monitoring
   */
  startMemoryMonitoring() {
    if (!performance.memory) {
      console.warn('Memory monitoring not available in this browser');
      return;
    }

    this.memoryCheckInterval = setInterval(() => {
      const memory = performance.memory;
      const memoryUsage = {
        used: Math.round(memory.usedJSHeapSize / 1048576), // MB
        total: Math.round(memory.totalJSHeapSize / 1048576), // MB
        limit: Math.round(memory.jsHeapSizeLimit / 1048576) // MB
      };

      // Warn if memory usage is high
      const usagePercent = (memoryUsage.used / memoryUsage.limit) * 100;
      if (usagePercent > 75) {
        console.warn(`🚨 High memory usage: ${usagePercent.toFixed(1)}% (${memoryUsage.used}MB/${memoryUsage.limit}MB)`);
        this.reportMemoryStats();
      }
    }, 30000); // Check every 30 seconds
  }

  /**
   * Stop memory monitoring
   */
  stopMemoryMonitoring() {
    if (this.memoryCheckInterval) {
      clearInterval(this.memoryCheckInterval);
      this.memoryCheckInterval = null;
    }
  }

  /**
   * Get memory usage statistics
   */
  getMemoryStats() {
    const stats = {
      activeTimers: this.activeTimers.size,
      activeIntervals: this.activeIntervals.size,
      activeObservers: this.activeObservers.size,
      activeEventListeners: this.activeEventListeners.size,
      activeAbortControllers: this.activeAbortControllers.size,
      componentsWithCleanup: this.componentCleanupFunctions.size
    };

    if (performance.memory) {
      stats.memory = {
        used: Math.round(performance.memory.usedJSHeapSize / 1048576),
        total: Math.round(performance.memory.totalJSHeapSize / 1048576),
        limit: Math.round(performance.memory.jsHeapSizeLimit / 1048576)
      };
    }

    return stats;
  }

  /**
   * Report memory statistics
   */
  reportMemoryStats() {
    console.group('📊 Memory Usage Report');
    console.table(this.getMemoryStats());
    console.groupEnd();
  }

  /**
   * Force cleanup all resources (emergency cleanup)
   */
  emergencyCleanup() {
    console.warn('🚨 Performing emergency cleanup of all resources');

    // Clear all timers
    this.activeTimers.forEach(timerId => {
      try { clearTimeout(timerId); } catch (e) {}
    });
    this.activeTimers.clear();

    // Clear all intervals
    this.activeIntervals.forEach(intervalId => {
      try { clearInterval(intervalId); } catch (e) {}
    });
    this.activeIntervals.clear();

    // Disconnect all observers
    this.activeObservers.forEach(observer => {
      try {
        if (observer.disconnect) observer.disconnect();
        if (observer.unobserve) observer.unobserve();
      } catch (e) {}
    });
    this.activeObservers.clear();

    // Remove all event listeners
    this.activeEventListeners.forEach(({ element, event, handler, options }) => {
      try {
        element.removeEventListener(event, handler, options);
      } catch (e) {}
    });
    this.activeEventListeners.clear();

    // Abort all controllers
    this.activeAbortControllers.forEach(controller => {
      try {
        if (!controller.signal.aborted) {
          controller.abort();
        }
      } catch (e) {}
    });
    this.activeAbortControllers.clear();

    // Run all cleanup functions
    this.componentCleanupFunctions.forEach((cleanupFunctions, componentId) => {
      cleanupFunctions.forEach(cleanup => {
        try { cleanup(); } catch (e) {}
      });
    });
    this.componentCleanupFunctions.clear();
  }
}

// Create singleton instance
const memoryLeakPrevention = new MemoryLeakPrevention();

// React hook for component cleanup
export const useComponentCleanup = (componentName) => {
  const componentId = React.useRef(`${componentName}-${Math.random().toString(36).substr(2, 9)}`);

  React.useEffect(() => {
    return () => {
      memoryLeakPrevention.cleanup(componentId.current);
    };
  }, []);

  return {
    componentId: componentId.current,
    registerCleanup: (cleanupFn) => memoryLeakPrevention.registerCleanup(componentId.current, cleanupFn),
    createTimer: (callback, delay) => memoryLeakPrevention.createManagedTimer(componentId.current, callback, delay),
    createInterval: (callback, delay) => memoryLeakPrevention.createManagedInterval(componentId.current, callback, delay),
    createEventListener: (element, event, handler, options) => 
      memoryLeakPrevention.createManagedEventListener(componentId.current, element, event, handler, options),
    createObserver: (ObserverClass, callback, options) => 
      memoryLeakPrevention.createManagedObserver(componentId.current, ObserverClass, callback, options),
    createAbortController: () => memoryLeakPrevention.createManagedAbortController(componentId.current),
    createWebSocket: (url, protocols) => memoryLeakPrevention.createManagedWebSocket(componentId.current, url, protocols)
  };
};

// Add to React import
const React = require('react');

// Emergency cleanup on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    memoryLeakPrevention.emergencyCleanup();
  });
}

export default memoryLeakPrevention;
export { MemoryLeakPrevention };

// Export utilities
export const getMemoryStats = () => memoryLeakPrevention.getMemoryStats();
export const reportMemoryStats = () => memoryLeakPrevention.reportMemoryStats();
export const emergencyCleanup = () => memoryLeakPrevention.emergencyCleanup();