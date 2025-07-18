/**
 * Performance Monitor - Comprehensive performance tracking and optimization
 * Monitors page load, component render times, and user interactions
 */

class PerformanceMonitor {
  constructor() {
    this.metrics = new Map();
    this.observers = new Map();
    this.thresholds = {
      pageLoad: 3000, // 3 seconds
      componentRender: 16, // 60fps = 16ms per frame
      apiCall: 2000, // 2 seconds
      userInteraction: 100 // 100ms for immediate feedback
    };
    
    this.startMonitoring();
  }

  /**
   * Start performance monitoring
   */
  startMonitoring() {
    this.monitorPageLoad();
    this.monitorUserInteractions();
    this.monitorLongTasks();
    this.monitorMemoryUsage();
    this.setupPerformanceObserver();
  }

  /**
   * Monitor page load performance
   */
  monitorPageLoad() {
    // Wait for page to load
    window.addEventListener('load', () => {
      setTimeout(() => {
        const navigation = performance.getEntriesByType('navigation')[0];
        const paintEntries = performance.getEntriesByType('paint');
        
        const pageMetrics = {
          timestamp: Date.now(),
          loadTime: navigation.loadEventEnd - navigation.fetchStart,
          domContentLoaded: navigation.domContentLoadedEventEnd - navigation.fetchStart,
          firstPaint: paintEntries.find(entry => entry.name === 'first-paint')?.startTime || 0,
          firstContentfulPaint: paintEntries.find(entry => entry.name === 'first-contentful-paint')?.startTime || 0,
          domInteractive: navigation.domInteractive - navigation.fetchStart,
          domComplete: navigation.domComplete - navigation.fetchStart
        };

        this.metrics.set('pageLoad', pageMetrics);
        this.analyzePageLoad(pageMetrics);
        
        console.group('📊 Page Load Performance');
        console.table(pageMetrics);
        console.groupEnd();
      }, 100);
    });
  }

  /**
   * Monitor user interactions
   */
  monitorUserInteractions() {
    ['click', 'keypress', 'scroll', 'touchstart'].forEach(eventType => {
      document.addEventListener(eventType, (event) => {
        const startTime = performance.now();
        
        // Use requestAnimationFrame to measure until next frame
        requestAnimationFrame(() => {
          const duration = performance.now() - startTime;
          this.recordInteraction(eventType, duration, event.target);
        });
      }, { passive: true });
    });
  }

  /**
   * Monitor long tasks that block the main thread
   */
  monitorLongTasks() {
    if ('PerformanceObserver' in window) {
      try {
        const observer = new PerformanceObserver((list) => {
          list.getEntries().forEach((entry) => {
            console.warn(`🐌 Long task detected: ${entry.duration.toFixed(2)}ms`);
            this.recordLongTask(entry);
          });
        });
        
        observer.observe({ entryTypes: ['longtask'] });
        this.observers.set('longtask', observer);
      } catch (error) {
        console.warn('Long task monitoring not supported:', error);
      }
    }
  }

  /**
   * Monitor memory usage
   */
  monitorMemoryUsage() {
    if (performance.memory) {
      setInterval(() => {
        const memory = {
          used: Math.round(performance.memory.usedJSHeapSize / 1048576),
          total: Math.round(performance.memory.totalJSHeapSize / 1048576),
          limit: Math.round(performance.memory.jsHeapSizeLimit / 1048576)
        };
        
        this.metrics.set('memory', { ...memory, timestamp: Date.now() });
        
        // Warn if memory usage is high
        const usagePercent = (memory.used / memory.limit) * 100;
        if (usagePercent > 80) {
          console.warn(`🚨 High memory usage: ${usagePercent.toFixed(1)}%`);
        }
      }, 10000); // Check every 10 seconds
    }
  }

  /**
   * Setup performance observer for various metrics
   */
  setupPerformanceObserver() {
    if ('PerformanceObserver' in window) {
      try {
        // Monitor navigation and resource loading
        const observer = new PerformanceObserver((list) => {
          list.getEntries().forEach((entry) => {
            this.recordPerformanceEntry(entry);
          });
        });
        
        observer.observe({ 
          entryTypes: ['navigation', 'resource', 'measure', 'mark'] 
        });
        this.observers.set('general', observer);
      } catch (error) {
        console.warn('Performance observer setup failed:', error);
      }
    }
  }

  /**
   * Record component render performance
   */
  recordComponentRender(componentName, duration, props = {}) {
    const metric = {
      timestamp: Date.now(),
      component: componentName,
      duration,
      props: Object.keys(props).length,
      isSlowRender: duration > this.thresholds.componentRender
    };

    if (!this.metrics.has('componentRenders')) {
      this.metrics.set('componentRenders', []);
    }
    
    this.metrics.get('componentRenders').push(metric);

    if (metric.isSlowRender) {
      console.warn(`🐌 Slow component render: ${componentName} took ${duration.toFixed(2)}ms`);
    }

    // Keep only last 100 renders
    const renders = this.metrics.get('componentRenders');
    if (renders.length > 100) {
      renders.splice(0, renders.length - 100);
    }
  }

  /**
   * Record API call performance
   */
  recordApiCall(url, method, duration, status, size = 0) {
    const metric = {
      timestamp: Date.now(),
      url: url.replace(/\?.*/, ''), // Remove query params for privacy
      method,
      duration,
      status,
      size,
      isSlowCall: duration > this.thresholds.apiCall
    };

    if (!this.metrics.has('apiCalls')) {
      this.metrics.set('apiCalls', []);
    }
    
    this.metrics.get('apiCalls').push(metric);

    if (metric.isSlowCall) {
      console.warn(`🐌 Slow API call: ${method} ${url} took ${duration.toFixed(2)}ms`);
    }

    // Keep only last 50 API calls
    const calls = this.metrics.get('apiCalls');
    if (calls.length > 50) {
      calls.splice(0, calls.length - 50);
    }
  }

  /**
   * Record user interaction performance
   */
  recordInteraction(type, duration, target) {
    const metric = {
      timestamp: Date.now(),
      type,
      duration,
      element: target.tagName?.toLowerCase() || 'unknown',
      isSlowInteraction: duration > this.thresholds.userInteraction
    };

    if (!this.metrics.has('interactions')) {
      this.metrics.set('interactions', []);
    }
    
    this.metrics.get('interactions').push(metric);

    if (metric.isSlowInteraction) {
      console.warn(`🐌 Slow interaction: ${type} took ${duration.toFixed(2)}ms`);
    }

    // Keep only last 20 interactions
    const interactions = this.metrics.get('interactions');
    if (interactions.length > 20) {
      interactions.splice(0, interactions.length - 20);
    }
  }

  /**
   * Record long task
   */
  recordLongTask(entry) {
    if (!this.metrics.has('longTasks')) {
      this.metrics.set('longTasks', []);
    }
    
    this.metrics.get('longTasks').push({
      timestamp: Date.now(),
      duration: entry.duration,
      startTime: entry.startTime,
      name: entry.name
    });
  }

  /**
   * Record general performance entry
   */
  recordPerformanceEntry(entry) {
    if (entry.entryType === 'resource') {
      this.recordResourceLoad(entry);
    } else if (entry.entryType === 'measure') {
      this.recordCustomMeasure(entry);
    }
  }

  /**
   * Record resource loading performance
   */
  recordResourceLoad(entry) {
    const metric = {
      timestamp: Date.now(),
      name: entry.name,
      type: entry.initiatorType,
      size: entry.transferSize || 0,
      duration: entry.responseEnd - entry.startTime,
      cached: entry.transferSize === 0
    };

    if (!this.metrics.has('resources')) {
      this.metrics.set('resources', []);
    }
    
    this.metrics.get('resources').push(metric);

    // Keep only last 50 resources
    const resources = this.metrics.get('resources');
    if (resources.length > 50) {
      resources.splice(0, resources.length - 50);
    }
  }

  /**
   * Record custom measure
   */
  recordCustomMeasure(entry) {
    if (!this.metrics.has('customMeasures')) {
      this.metrics.set('customMeasures', []);
    }
    
    this.metrics.get('customMeasures').push({
      timestamp: Date.now(),
      name: entry.name,
      duration: entry.duration,
      startTime: entry.startTime
    });
  }

  /**
   * Analyze page load performance
   */
  analyzePageLoad(metrics) {
    const issues = [];

    if (metrics.loadTime > this.thresholds.pageLoad) {
      issues.push(`Slow page load: ${metrics.loadTime.toFixed(2)}ms`);
    }

    if (metrics.firstContentfulPaint > 2500) {
      issues.push(`Slow First Contentful Paint: ${metrics.firstContentfulPaint.toFixed(2)}ms`);
    }

    if (metrics.domContentLoaded > 2000) {
      issues.push(`Slow DOM Content Loaded: ${metrics.domContentLoaded.toFixed(2)}ms`);
    }

    if (issues.length > 0) {
      console.warn('🚨 Page Load Issues:', issues);
    }
  }

  /**
   * Create performance mark
   */
  mark(name) {
    if (performance.mark) {
      performance.mark(name);
    }
  }

  /**
   * Measure time between marks
   */
  measure(name, startMark, endMark) {
    if (performance.measure) {
      try {
        performance.measure(name, startMark, endMark);
      } catch (error) {
        console.warn('Failed to create measure:', error);
      }
    }
  }

  /**
   * Get performance report
   */
  getPerformanceReport() {
    const report = {
      timestamp: Date.now(),
      pageLoad: this.metrics.get('pageLoad'),
      memory: this.metrics.get('memory'),
      componentRenders: this.getComponentRenderStats(),
      apiCalls: this.getApiCallStats(),
      interactions: this.getInteractionStats(),
      longTasks: this.metrics.get('longTasks')?.length || 0,
      resources: this.getResourceStats()
    };

    return report;
  }

  /**
   * Get component render statistics
   */
  getComponentRenderStats() {
    const renders = this.metrics.get('componentRenders') || [];
    if (renders.length === 0) return null;

    const durations = renders.map(r => r.duration);
    return {
      total: renders.length,
      averageDuration: durations.reduce((a, b) => a + b, 0) / durations.length,
      maxDuration: Math.max(...durations),
      slowRenders: renders.filter(r => r.isSlowRender).length
    };
  }

  /**
   * Get API call statistics
   */
  getApiCallStats() {
    const calls = this.metrics.get('apiCalls') || [];
    if (calls.length === 0) return null;

    const durations = calls.map(c => c.duration);
    return {
      total: calls.length,
      averageDuration: durations.reduce((a, b) => a + b, 0) / durations.length,
      maxDuration: Math.max(...durations),
      slowCalls: calls.filter(c => c.isSlowCall).length,
      errors: calls.filter(c => c.status >= 400).length
    };
  }

  /**
   * Get interaction statistics
   */
  getInteractionStats() {
    const interactions = this.metrics.get('interactions') || [];
    if (interactions.length === 0) return null;

    const durations = interactions.map(i => i.duration);
    return {
      total: interactions.length,
      averageDuration: durations.reduce((a, b) => a + b, 0) / durations.length,
      maxDuration: Math.max(...durations),
      slowInteractions: interactions.filter(i => i.isSlowInteraction).length
    };
  }

  /**
   * Get resource loading statistics
   */
  getResourceStats() {
    const resources = this.metrics.get('resources') || [];
    if (resources.length === 0) return null;

    const totalSize = resources.reduce((sum, r) => sum + r.size, 0);
    const cachedResources = resources.filter(r => r.cached).length;

    return {
      total: resources.length,
      totalSize: Math.round(totalSize / 1024), // KB
      cached: cachedResources,
      cacheHitRate: cachedResources / resources.length * 100
    };
  }

  /**
   * Clean up observers
   */
  cleanup() {
    this.observers.forEach(observer => {
      try {
        observer.disconnect();
      } catch (error) {
        console.warn('Failed to disconnect observer:', error);
      }
    });
    this.observers.clear();
  }
}

// Create singleton instance
const performanceMonitor = new PerformanceMonitor();

// React hook for component performance monitoring
export const usePerformanceMonitor = (componentName) => {
  const startTime = React.useRef();
  
  React.useEffect(() => {
    startTime.current = performance.now();
    performanceMonitor.mark(`${componentName}-start`);
    
    return () => {
      const duration = performance.now() - startTime.current;
      performanceMonitor.mark(`${componentName}-end`);
      performanceMonitor.measure(`${componentName}-render`, `${componentName}-start`, `${componentName}-end`);
      performanceMonitor.recordComponentRender(componentName, duration);
    };
  });

  return {
    recordApiCall: performanceMonitor.recordApiCall.bind(performanceMonitor),
    mark: performanceMonitor.mark.bind(performanceMonitor),
    measure: performanceMonitor.measure.bind(performanceMonitor)
  };
};

export default performanceMonitor;
export { PerformanceMonitor };

// Export utilities
export const getPerformanceReport = () => performanceMonitor.getPerformanceReport();
export const recordApiCall = (...args) => performanceMonitor.recordApiCall(...args);
export const recordComponentRender = (...args) => performanceMonitor.recordComponentRender(...args);