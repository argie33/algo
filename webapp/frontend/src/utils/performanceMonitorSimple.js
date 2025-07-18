/**
 * Simple Browser-Compatible Performance Monitor
 * Lightweight performance tracking without Node.js dependencies
 */

class SimplePerformanceMonitor {
  constructor() {
    this.metrics = new Map();
    this.startTime = performance.now();
    this.init();
  }

  init() {
    // Monitor page load performance
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        this.recordPageLoad();
      });
    } else {
      this.recordPageLoad();
    }

    // Monitor window load
    window.addEventListener('load', () => {
      this.recordWindowLoad();
    });
  }

  recordPageLoad() {
    try {
      const navigation = performance.getEntriesByType('navigation')[0];
      if (navigation) {
        const pageMetrics = {
          timestamp: Date.now(),
          loadTime: navigation.loadEventEnd - navigation.fetchStart,
          domContentLoaded: navigation.domContentLoadedEventEnd - navigation.fetchStart,
          domInteractive: navigation.domInteractive - navigation.fetchStart,
          domComplete: navigation.domComplete - navigation.fetchStart
        };

        this.metrics.set('pageLoad', pageMetrics);
        console.log('📊 Page Load Performance:', pageMetrics);
      }
    } catch (error) {
      console.warn('Performance monitoring error:', error);
    }
  }

  recordWindowLoad() {
    try {
      const loadTime = performance.now() - this.startTime;
      console.log(`✅ Window loaded in ${loadTime.toFixed(2)}ms`);
      
      // Get paint metrics if available
      const paintEntries = performance.getEntriesByType('paint');
      if (paintEntries.length > 0) {
        paintEntries.forEach(entry => {
          console.log(`🎨 ${entry.name}: ${entry.startTime.toFixed(2)}ms`);
        });
      }
    } catch (error) {
      console.warn('Window load monitoring error:', error);
    }
  }

  recordComponentRender(componentName, renderTime) {
    try {
      const metric = {
        component: componentName,
        renderTime: renderTime,
        timestamp: Date.now()
      };
      
      this.metrics.set(`render_${componentName}`, metric);
      
      // Log slow renders
      if (renderTime > 100) {
        console.warn(`🐌 Slow render: ${componentName} took ${renderTime.toFixed(2)}ms`);
      }
    } catch (error) {
      console.warn('Component render monitoring error:', error);
    }
  }

  recordApiCall(url, method, duration, success = true) {
    try {
      const metric = {
        url,
        method,
        duration,
        success,
        timestamp: Date.now()
      };
      
      this.metrics.set(`api_${Date.now()}`, metric);
      
      // Log slow API calls
      if (duration > 2000) {
        console.warn(`🐌 Slow API call: ${method} ${url} took ${duration.toFixed(2)}ms`);
      }
    } catch (error) {
      console.warn('API call monitoring error:', error);
    }
  }

  getMetrics() {
    return Object.fromEntries(this.metrics);
  }

  getPerformanceReport() {
    const report = {
      metrics: this.getMetrics(),
      timestamp: Date.now(),
      userAgent: navigator.userAgent,
      connectionType: navigator.connection?.effectiveType || 'unknown'
    };
    
    return report;
  }

  // Simple memory monitoring (if available)
  checkMemory() {
    if (performance.memory) {
      const memory = {
        used: Math.round(performance.memory.usedJSHeapSize / 1048576),
        total: Math.round(performance.memory.totalJSHeapSize / 1048576),
        limit: Math.round(performance.memory.jsHeapSizeLimit / 1048576)
      };
      
      console.log('💾 Memory usage:', memory);
      return memory;
    }
    return null;
  }
}

// Create singleton instance
const performanceMonitor = new SimplePerformanceMonitor();

// Export the instance and class
export default performanceMonitor;
export { SimplePerformanceMonitor };

// Export utility functions
export const recordComponentRender = (componentName, renderTime) => {
  performanceMonitor.recordComponentRender(componentName, renderTime);
};

export const recordApiCall = (url, method, duration, success) => {
  performanceMonitor.recordApiCall(url, method, duration, success);
};

export const getPerformanceReport = () => {
  return performanceMonitor.getPerformanceReport();
};

export const checkMemory = () => {
  return performanceMonitor.checkMemory();
};