/**
 * Global Resource Cleanup Utility
 * Tracks and cleans up all active timers, intervals, and asynchronous operations
 * to prevent resource leaks in test environments
 */

class ResourceCleanup {
  constructor() {
    this.activeTimers = new Set();
    this.activeIntervals = new Set();
    this.activeImmediate = new Set();
    this.cleanupCallbacks = new Set();
    
    // Track original timer functions
    this.originalSetTimeout = global.setTimeout;
    this.originalSetInterval = global.setInterval;
    this.originalSetImmediate = global.setImmediate;
    this.originalClearTimeout = global.clearTimeout;
    this.originalClearInterval = global.clearInterval;
    this.originalClearImmediate = global.clearImmediate;
    
    this.isTracking = false;
  }

  /**
   * Start tracking all timer operations
   */
  startTracking() {
    if (this.isTracking) return;
    
    this.isTracking = true;
    
    // Override setTimeout to track active timers
    global.setTimeout = (callback, delay, ...args) => {
      const timerId = this.originalSetTimeout.call(global, (...callbackArgs) => {
        this.activeTimers.delete(timerId);
        callback(...callbackArgs);
      }, delay, ...args);
      
      this.activeTimers.add(timerId);
      return timerId;
    };

    // Override setInterval to track active intervals
    global.setInterval = (callback, delay, ...args) => {
      const intervalId = this.originalSetInterval.call(global, callback, delay, ...args);
      this.activeIntervals.add(intervalId);
      return intervalId;
    };

    // Override setImmediate to track active immediate callbacks
    global.setImmediate = (callback, ...args) => {
      const immediateId = this.originalSetImmediate.call(global, (...callbackArgs) => {
        this.activeImmediate.delete(immediateId);
        callback(...callbackArgs);
      }, ...args);
      
      this.activeImmediate.add(immediateId);
      return immediateId;
    };

    // Override clear functions to remove from tracking
    global.clearTimeout = (timerId) => {
      this.activeTimers.delete(timerId);
      return this.originalClearTimeout.call(global, timerId);
    };

    global.clearInterval = (intervalId) => {
      this.activeIntervals.delete(intervalId);
      return this.originalClearInterval.call(global, intervalId);
    };

    global.clearImmediate = (immediateId) => {
      this.activeImmediate.delete(immediateId);
      return this.originalClearImmediate.call(global, immediateId);
    };

    console.log('🔍 ResourceCleanup: Started tracking timers');
  }

  /**
   * Stop tracking timer operations and restore original functions
   */
  stopTracking() {
    if (!this.isTracking) return;
    
    this.isTracking = false;
    
    // Restore original functions
    global.setTimeout = this.originalSetTimeout;
    global.setInterval = this.originalSetInterval;
    global.setImmediate = this.originalSetImmediate;
    global.clearTimeout = this.originalClearTimeout;
    global.clearInterval = this.originalClearInterval;
    global.clearImmediate = this.originalClearImmediate;

    console.log('🔍 ResourceCleanup: Stopped tracking timers');
  }

  /**
   * Register a cleanup callback for custom resource cleanup
   */
  registerCleanupCallback(callback, name = 'anonymous') {
    this.cleanupCallbacks.add({ callback, name });
    console.log(`🧹 Registered cleanup callback: ${name}`);
  }

  /**
   * Unregister a cleanup callback
   */
  unregisterCleanupCallback(callbackOrName) {
    if (typeof callbackOrName === 'string') {
      // Find by name
      for (const item of this.cleanupCallbacks) {
        if (item.name === callbackOrName) {
          this.cleanupCallbacks.delete(item);
          console.log(`🧹 Unregistered cleanup callback: ${callbackOrName}`);
          return;
        }
      }
    } else {
      // Find by callback reference
      for (const item of this.cleanupCallbacks) {
        if (item.callback === callbackOrName) {
          this.cleanupCallbacks.delete(item);
          console.log(`🧹 Unregistered cleanup callback: ${item.name}`);
          return;
        }
      }
    }
  }

  /**
   * Get current resource statistics
   */
  getStats() {
    return {
      activeTimers: this.activeTimers.size,
      activeIntervals: this.activeIntervals.size,
      activeImmediate: this.activeImmediate.size,
      cleanupCallbacks: this.cleanupCallbacks.size,
      isTracking: this.isTracking,
      totalActiveResources: this.activeTimers.size + this.activeIntervals.size + this.activeImmediate.size
    };
  }

  /**
   * Log current resource usage
   */
  logStats() {
    const stats = this.getStats();
    console.log('📊 ResourceCleanup Stats:', {
      ...stats,
      activeTimerIds: Array.from(this.activeTimers).slice(0, 10), // Show first 10
      activeIntervalIds: Array.from(this.activeIntervals).slice(0, 10)
    });
  }

  /**
   * Clean up all tracked resources
   */
  async cleanup(options = {}) {
    const { 
      logDetails = true, 
      waitForCallbacks = 1000,
      forceCleanup = false 
    } = options;
    
    if (logDetails) {
      console.log('🧹 ResourceCleanup: Starting comprehensive cleanup...');
      this.logStats();
    }

    const cleanupResults = {
      timersCleared: 0,
      intervalsCleared: 0,
      immediateCleared: 0,
      callbacksExecuted: 0,
      errors: []
    };

    // Clear all active timers
    for (const timerId of this.activeTimers) {
      try {
        this.originalClearTimeout.call(global, timerId);
        cleanupResults.timersCleared++;
      } catch (error) {
        cleanupResults.errors.push({ type: 'timer', id: timerId, error: error.message });
      }
    }
    this.activeTimers.clear();

    // Clear all active intervals
    for (const intervalId of this.activeIntervals) {
      try {
        this.originalClearInterval.call(global, intervalId);
        cleanupResults.intervalsCleared++;
      } catch (error) {
        cleanupResults.errors.push({ type: 'interval', id: intervalId, error: error.message });
      }
    }
    this.activeIntervals.clear();

    // Clear all active immediate callbacks
    for (const immediateId of this.activeImmediate) {
      try {
        this.originalClearImmediate.call(global, immediateId);
        cleanupResults.immediateCleared++;
      } catch (error) {
        cleanupResults.errors.push({ type: 'immediate', id: immediateId, error: error.message });
      }
    }
    this.activeImmediate.clear();

    // Execute cleanup callbacks
    const callbackPromises = [];
    for (const { callback, name } of this.cleanupCallbacks) {
      try {
        const result = callback();
        if (result && typeof result.then === 'function') {
          callbackPromises.push(
            result.catch(error => ({ name, error: error.message }))
          );
        }
        cleanupResults.callbacksExecuted++;
      } catch (error) {
        cleanupResults.errors.push({ type: 'callback', name, error: error.message });
      }
    }

    // Wait for async cleanup callbacks with timeout
    if (callbackPromises.length > 0) {
      try {
        const timeoutPromise = new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Cleanup timeout')), waitForCallbacks)
        );
        
        await Promise.race([
          Promise.allSettled(callbackPromises),
          timeoutPromise
        ]);
      } catch (error) {
        if (logDetails) {
          console.warn('⚠️ Some cleanup callbacks timed out');
        }
      }
    }

    // Clear callback references
    this.cleanupCallbacks.clear();

    if (logDetails) {
      console.log('✅ ResourceCleanup: Cleanup completed', cleanupResults);
      
      if (cleanupResults.errors.length > 0) {
        console.warn('⚠️ ResourceCleanup: Errors during cleanup:', cleanupResults.errors);
      }
    }

    return cleanupResults;
  }

  /**
   * Force cleanup with additional Node.js specific operations
   */
  async forceCleanup() {
    await this.cleanup({ forceCleanup: true });
    
    // Additional Node.js cleanup
    try {
      // Force garbage collection if available
      if (global.gc) {
        global.gc();
        console.log('🗑️ Forced garbage collection');
      }
      
      // Clear any remaining handles
      if (process._getActiveHandles) {
        const handles = process._getActiveHandles();
        console.log(`🔧 Active handles remaining: ${handles.length}`);
        
        // Log handle types for debugging
        const handleTypes = {};
        handles.forEach(handle => {
          const type = handle.constructor.name;
          handleTypes[type] = (handleTypes[type] || 0) + 1;
        });
        
        if (Object.keys(handleTypes).length > 0) {
          console.log('🔧 Handle types:', handleTypes);
        }
      }
    } catch (error) {
      console.warn('⚠️ Error during force cleanup:', error.message);
    }
  }

  /**
   * Clean up specific resource types
   */
  cleanupTimers() {
    let cleared = 0;
    for (const timerId of this.activeTimers) {
      try {
        this.originalClearTimeout.call(global, timerId);
        cleared++;
      } catch (error) {
        // Ignore errors for already cleared timers
      }
    }
    this.activeTimers.clear();
    console.log(`🧹 Cleared ${cleared} timers`);
    return cleared;
  }

  cleanupIntervals() {
    let cleared = 0;
    for (const intervalId of this.activeIntervals) {
      try {
        this.originalClearInterval.call(global, intervalId);
        cleared++;
      } catch (error) {
        // Ignore errors for already cleared intervals
      }
    }
    this.activeIntervals.clear();
    console.log(`🧹 Cleared ${cleared} intervals`);
    return cleared;
  }

  /**
   * Set up Jest integration hooks
   */
  setupJestIntegration() {
    // Register Jest hooks if available
    if (typeof beforeEach !== 'undefined') {
      beforeEach(() => {
        this.startTracking();
      });
    }

    if (typeof afterEach !== 'undefined') {
      afterEach(async () => {
        await this.cleanup({ logDetails: false });
      });
    }

    if (typeof afterAll !== 'undefined') {
      afterAll(async () => {
        await this.forceCleanup();
        this.stopTracking();
      });
    }

    console.log('🧹 ResourceCleanup: Jest integration setup complete');
  }
}

// Create singleton instance
const resourceCleanup = new ResourceCleanup();

// Auto-setup for test environments
if (process.env.NODE_ENV === 'test') {
  resourceCleanup.setupJestIntegration();
}

module.exports = resourceCleanup;