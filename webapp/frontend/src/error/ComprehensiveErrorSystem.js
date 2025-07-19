/**
 * Comprehensive Error System - Central initialization and management of all error handling
 * Orchestrates all error handling components for complete webapp coverage
 */

import ErrorManager from './ErrorManager';

class ComprehensiveErrorSystem {
  constructor() {
    this.isInitialized = false;
    this.initializationStatus = {
      errorManager: false
    };
    this.systemMetrics = {
      totalErrors: 0,
      errorsByCategory: {},
      errorsBySeverity: {},
      systemHealth: 100,
      lastHealthCheck: null
    };
  }

  /**
   * Initialize the comprehensive error handling system
   */
  async initialize() {
    if (this.isInitialized) {
      console.warn('Comprehensive Error System already initialized');
      return;
    }

    try {
      console.log('🚀 Initializing Comprehensive Error Handling System...');

      // Initialize core error manager first
      await this.initializeErrorManager();

      // Initialize all error handling components
      await this.initializeAllComponents();

      // Setup system-wide error monitoring
      this.setupSystemMonitoring();

      // Setup global error handlers
      this.setupGlobalErrorHandlers();

      // Perform initial health check
      this.performHealthCheck();

      this.isInitialized = true;

      ErrorManager.handleError({
        type: 'comprehensive_error_system_initialized',
        message: 'Comprehensive error handling system fully initialized',
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          initializationStatus: this.initializationStatus,
          componentsInitialized: Object.values(this.initializationStatus).filter(Boolean).length,
          totalComponents: Object.keys(this.initializationStatus).length,
          timestamp: new Date().toISOString()
        }
      });

      console.log('✅ Comprehensive Error Handling System initialized successfully');
      this.logInitializationStatus();

    } catch (error) {
      console.error('❌ Failed to initialize Comprehensive Error System:', error);
      
      ErrorManager.handleError({
        type: 'comprehensive_error_system_init_failed',
        message: `Failed to initialize comprehensive error system: ${error.message}`,
        error: error,
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.CRITICAL,
        context: {
          initializationStatus: this.initializationStatus,
          stack: error.stack,
          timestamp: new Date().toISOString()
        }
      });

      throw error;
    }
  }

  /**
   * Initialize Error Manager
   */
  async initializeErrorManager() {
    try {
      // ErrorManager is already available, just ensure it's ready
      this.initializationStatus.errorManager = true;
      
      ErrorManager.handleError({
        type: 'error_manager_ready',
        message: 'ErrorManager is ready and operational',
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          timestamp: new Date().toISOString()
        }
      });
    } catch (error) {
      console.error('Failed to initialize ErrorManager:', error);
      throw error;
    }
  }

  /**
   * Initialize all error handling components
   */
  async initializeAllComponents() {
    // Only initialize core error manager for now
    console.log('Core error handling components already initialized');
  }

  /**
   * Setup system-wide error monitoring
   */
  setupSystemMonitoring() {
    // Subscribe to ErrorManager events to track system metrics
    ErrorManager.subscribe((error) => {
      this.updateSystemMetrics(error);
    });

    // Periodic health checks
    setInterval(() => {
      this.performHealthCheck();
    }, 5 * 60 * 1000); // Every 5 minutes
  }

  /**
   * Setup global error handlers
   */
  setupGlobalErrorHandlers() {
    // Global unhandled error handler
    window.addEventListener('error', (event) => {
      ErrorManager.handleError({
        type: 'global_unhandled_error',
        message: `Global unhandled error: ${event.message}`,
        error: event.error,
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.HIGH,
        context: {
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
          source: 'global_error_handler',
          timestamp: new Date().toISOString()
        }
      });
    });

    // Global unhandled promise rejection handler
    window.addEventListener('unhandledrejection', (event) => {
      ErrorManager.handleError({
        type: 'global_unhandled_rejection',
        message: `Global unhandled promise rejection: ${event.reason}`,
        error: event.reason,
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.HIGH,
        context: {
          reason: event.reason,
          promise: event.promise,
          source: 'global_rejection_handler',
          timestamp: new Date().toISOString()
        }
      });

      // Prevent default browser error logging for handled rejections
      event.preventDefault();
    });

    // Page visibility change handler
    document.addEventListener('visibilitychange', () => {
      ErrorManager.handleError({
        type: 'page_visibility_changed',
        message: `Page visibility changed: ${document.hidden ? 'hidden' : 'visible'}`,
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          hidden: document.hidden,
          visibilityState: document.visibilityState,
          timestamp: new Date().toISOString()
        }
      });
    });

    // Before unload handler
    window.addEventListener('beforeunload', () => {
      ErrorManager.handleError({
        type: 'page_unloading',
        message: 'Page is being unloaded',
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          url: window.location.href,
          systemMetrics: this.systemMetrics,
          timestamp: new Date().toISOString()
        }
      });
    });
  }

  /**
   * Update system metrics based on errors
   */
  updateSystemMetrics(error) {
    this.systemMetrics.totalErrors++;
    
    // Track by category
    const category = error.category || 'unknown';
    this.systemMetrics.errorsByCategory[category] = 
      (this.systemMetrics.errorsByCategory[category] || 0) + 1;
    
    // Track by severity
    const severity = error.severity || 'unknown';
    this.systemMetrics.errorsBySeverity[severity] = 
      (this.systemMetrics.errorsBySeverity[severity] || 0) + 1;
    
    // Update system health based on error severity
    if (severity === ErrorManager.SEVERITY.CRITICAL) {
      this.systemMetrics.systemHealth = Math.max(0, this.systemMetrics.systemHealth - 10);
    } else if (severity === ErrorManager.SEVERITY.HIGH) {
      this.systemMetrics.systemHealth = Math.max(0, this.systemMetrics.systemHealth - 5);
    } else if (severity === ErrorManager.SEVERITY.MEDIUM) {
      this.systemMetrics.systemHealth = Math.max(0, this.systemMetrics.systemHealth - 2);
    }
    
    // Slowly recover health over time (if no critical errors)
    if (severity !== ErrorManager.SEVERITY.CRITICAL && this.systemMetrics.systemHealth < 100) {
      this.systemMetrics.systemHealth = Math.min(100, this.systemMetrics.systemHealth + 0.1);
    }
  }

  /**
   * Perform system health check
   */
  performHealthCheck() {
    const healthData = {
      timestamp: Date.now(),
      systemHealth: this.systemMetrics.systemHealth,
      componentsStatus: {},
      memoryUsage: null,
      performanceMetrics: null
    };

    // Check ErrorManager component health
    try {
      healthData.componentsStatus['errorManager'] = ErrorManager.getStats();
    } catch (error) {
      healthData.componentsStatus['errorManager'] = { error: error.message };
    }

    // Get memory usage if available
    if (performance.memory) {
      healthData.memoryUsage = {
        usedJSHeapSize: performance.memory.usedJSHeapSize,
        totalJSHeapSize: performance.memory.totalJSHeapSize,
        jsHeapSizeLimit: performance.memory.jsHeapSizeLimit,
        usedMB: Math.round(performance.memory.usedJSHeapSize / 1024 / 1024)
      };
    }

    // Get basic performance metrics
    if (performance.timing) {
      const timing = performance.timing;
      healthData.performanceMetrics = {
        pageLoadTime: timing.loadEventEnd - timing.navigationStart,
        domContentLoadedTime: timing.domContentLoadedEventEnd - timing.navigationStart,
        firstPaintTime: performance.getEntriesByType('paint').find(entry => entry.name === 'first-paint')?.startTime || null
      };
    }

    this.systemMetrics.lastHealthCheck = healthData.timestamp;

    ErrorManager.handleError({
      type: 'system_health_check',
      message: `System health check completed - Health: ${healthData.systemHealth}%`,
      category: ErrorManager.CATEGORIES.SYSTEM,
      severity: healthData.systemHealth < 50 ? ErrorManager.SEVERITY.HIGH : ErrorManager.SEVERITY.LOW,
      context: healthData
    });
  }

  /**
   * Log initialization status
   */
  logInitializationStatus() {
    const initialized = Object.values(this.initializationStatus).filter(Boolean).length;
    const total = Object.keys(this.initializationStatus).length;
    
    console.log('📊 Error Handling System Status:');
    console.log(`✅ Components Initialized: ${initialized}/${total}`);
    
    for (const [component, status] of Object.entries(this.initializationStatus)) {
      console.log(`${status ? '✅' : '❌'} ${component}: ${status ? 'Ready' : 'Failed'}`);
    }
    
    console.log(`📈 System Health: ${this.systemMetrics.systemHealth}%`);
    console.log(`🔢 Total Errors Handled: ${this.systemMetrics.totalErrors}`);
  }

  /**
   * Get comprehensive system status
   */
  getSystemStatus() {
    return {
      isInitialized: this.isInitialized,
      initializationStatus: this.initializationStatus,
      systemMetrics: this.systemMetrics,
      components: {
        errorManager: ErrorManager.getStats()
      },
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Cleanup all error handling components
   */
  cleanup() {
    try {
      // Reset initialization status
      for (const key of Object.keys(this.initializationStatus)) {
        this.initializationStatus[key] = false;
      }

      this.isInitialized = false;

      ErrorManager.handleError({
        type: 'comprehensive_error_system_cleanup',
        message: 'Comprehensive error handling system cleaned up',
        category: ErrorManager.CATEGORIES.SYSTEM,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          timestamp: new Date().toISOString()
        }
      });

      console.log('🧹 Comprehensive Error Handling System cleaned up');
    } catch (error) {
      console.error('Error during cleanup:', error);
    }
  }
}

// Create singleton instance
const comprehensiveErrorSystem = new ComprehensiveErrorSystem();

// Auto-initialize on import
if (typeof window !== 'undefined') {
  // Initialize after DOM is loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      comprehensiveErrorSystem.initialize().catch(console.error);
    });
  } else {
    // DOM already loaded
    setTimeout(() => {
      comprehensiveErrorSystem.initialize().catch(console.error);
    }, 0);
  }
}

export default comprehensiveErrorSystem;