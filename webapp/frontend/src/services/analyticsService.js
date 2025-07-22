// Analytics and Monitoring Service
// Tracks user behavior, performance metrics, and system health

import axios from 'axios';

class AnalyticsService {
  constructor() {
    this.sessionId = this.generateSessionId();
    this.userId = null;
    this.isEnabled = true;
    this.batchSize = 50;
    this.flushInterval = 30000; // 30 seconds
    this.eventQueue = [];
    this.performanceMetrics = new Map();
    
    // Performance observer for monitoring
    this.setupPerformanceObserver();
    
    // Auto-flush events periodically
    this.startAutoFlush();
    
    // Track page visibility
    this.setupVisibilityTracking();
    
    // Track errors
    this.setupErrorTracking();
  }

  // Initialize analytics with user context
  initialize(userId, userProps = {}) {
    this.userId = userId;
    this.identify(userId, userProps);
    this.track('session_start', {
      timestamp: new Date().toISOString(),
      user_agent: navigator.userAgent,
      screen_resolution: `${screen.width}x${screen.height}`,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
    });
  }

  // Identify user
  identify(userId, properties = {}) {
    this.userId = userId;
    this.track('user_identify', {
      user_id: userId,
      properties: {
        ...properties,
        session_id: this.sessionId,
        timestamp: new Date().toISOString()
      }
    });
  }

  // Track events
  track(eventName, properties = {}) {
    if (!this.isEnabled) return;

    const event = {
      event: eventName,
      user_id: this.userId,
      session_id: this.sessionId,
      timestamp: new Date().toISOString(),
      properties: {
        ...properties,
        page_url: typeof window !== 'undefined' ? window.location.href : 'test-url',
        page_title: document.title,
        referrer: document.referrer
      }
    };

    this.eventQueue.push(event);

    // Flush if queue is full
    if (this.eventQueue.length >= this.batchSize) {
      this.flush();
    }
  }

  // Track page views
  trackPageView(pageName, properties = {}) {
    this.track('page_view', {
      page_name: pageName,
      ...properties
    });
  }

  // Track user interactions
  trackClick(element, properties = {}) {
    this.track('click', {
      element_type: element.tagName?.toLowerCase(),
      element_id: element.id,
      element_class: element.className,
      element_text: element.textContent?.substring(0, 100),
      ...properties
    });
  }

  // Track form submissions
  trackFormSubmit(formName, properties = {}) {
    this.track('form_submit', {
      form_name: formName,
      ...properties
    });
  }

  // Track search events
  trackSearch(query, results = 0, properties = {}) {
    this.track('search', {
      query,
      results_count: results,
      ...properties
    });
  }

  // Track trading actions
  trackTrade(action, symbol, properties = {}) {
    this.track('trade_action', {
      action, // 'buy', 'sell', 'watchlist_add', etc.
      symbol,
      ...properties
    });
  }

  // Track portfolio actions
  trackPortfolio(action, properties = {}) {
    this.track('portfolio_action', {
      action, // 'view', 'optimize', 'rebalance', etc.
      ...properties
    });
  }

  // Track news interactions
  trackNews(action, articleId, properties = {}) {
    this.track('news_interaction', {
      action, // 'view', 'click', 'share', etc.
      article_id: articleId,
      ...properties
    });
  }

  // Track chart interactions
  trackChart(action, symbol, chartType, properties = {}) {
    this.track('chart_interaction', {
      action, // 'view', 'timeframe_change', 'indicator_add', etc.
      symbol,
      chart_type: chartType,
      ...properties
    });
  }

  // Track performance metrics
  trackPerformance(metricName, value, unit = 'ms') {
    const metric = {
      name: metricName,
      value,
      unit,
      timestamp: new Date().toISOString(),
      page: typeof window !== 'undefined' ? window.location.pathname : '/test'
    };

    this.performanceMetrics.set(metricName, metric);

    this.track('performance_metric', metric);
  }

  // Track API calls
  trackApiCall(endpoint, method, duration, status, properties = {}) {
    this.track('api_call', {
      endpoint,
      method,
      duration,
      status,
      success: status >= 200 && status < 400,
      ...properties
    });
  }

  // Track errors
  trackError(error, context = {}) {
    this.track('error', {
      error_message: error.message,
      error_stack: error.stack,
      error_name: error.name,
      context,
      user_agent: navigator.userAgent
    });
  }

  // Track feature usage
  trackFeatureUsage(featureName, properties = {}) {
    this.track('feature_usage', {
      feature: featureName,
      ...properties
    });
  }

  // Track user engagement
  trackEngagement(action, duration = null, properties = {}) {
    this.track('engagement', {
      action, // 'scroll', 'hover', 'focus', etc.
      duration,
      ...properties
    });
  }

  // Track conversion events
  trackConversion(goalName, value = 0, properties = {}) {
    this.track('conversion', {
      goal: goalName,
      value,
      ...properties
    });
  }

  // Track A/B test events
  trackExperiment(experimentName, variant, properties = {}) {
    this.track('experiment', {
      experiment: experimentName,
      variant,
      ...properties
    });
  }

  // Flush events to server
  async flush() {
    if (this.eventQueue.length === 0) return;

    const events = [...this.eventQueue];
    this.eventQueue = [];

    try {
      await axios.post('/api/analytics/events', {
        events,
        session_id: this.sessionId
      });
    } catch (error) {
      console.warn('Failed to send analytics events:', error);
      // Re-queue events on failure (with limit to prevent infinite growth)
      if (this.eventQueue.length < this.batchSize * 2) {
        this.eventQueue.unshift(...events);
      }
    }
  }

  // Get performance insights
  getPerformanceInsights() {
    const insights = {};
    
    // Page load metrics
    if (performance.timing) {
      const timing = performance.timing;
      insights.pageLoad = {
        domContentLoaded: timing.domContentLoadedEventEnd - timing.navigationStart,
        loadComplete: timing.loadEventEnd - timing.navigationStart,
        domReady: timing.domInteractive - timing.navigationStart,
        firstPaint: timing.responseEnd - timing.navigationStart
      };
    }

    // Resource timing
    if (performance.getEntriesByType) {
      const resources = performance.getEntriesByType('resource');
      insights.resources = {
        total: resources.length,
        slow: resources.filter(r => r.duration > 1000).length,
        failed: resources.filter(r => r.transferSize === 0).length,
        avgDuration: resources.reduce((sum, r) => sum + r.duration, 0) / resources.length
      };
    }

    // Memory usage (if available)
    if (performance.memory) {
      insights.memory = {
        used: performance.memory.usedJSHeapSize,
        total: performance.memory.totalJSHeapSize,
        limit: performance.memory.jsHeapSizeLimit
      };
    }

    // Custom metrics
    insights.custom = Object.fromEntries(this.performanceMetrics);

    return insights;
  }

  // Setup performance observer
  setupPerformanceObserver() {
    if (typeof window !== 'undefined' && 'PerformanceObserver' in window) {
      try {
        // Observe largest contentful paint
        const lcpObserver = new PerformanceObserver((entryList) => {
          const entries = entryList.getEntries();
          const lastEntry = entries[entries.length - 1];
          this.trackPerformance('largest_contentful_paint', lastEntry.startTime);
        });
        lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });

        // Observe first input delay
        const fidObserver = new PerformanceObserver((entryList) => {
          const entries = entryList.getEntries();
          entries.forEach(entry => {
            this.trackPerformance('first_input_delay', entry.processingStart - entry.startTime);
          });
        });
        fidObserver.observe({ entryTypes: ['first-input'] });

        // Observe cumulative layout shift
        const clsObserver = new PerformanceObserver((entryList) => {
          let clsValue = 0;
          const entries = entryList.getEntries();
          entries.forEach(entry => {
            if (!entry.hadRecentInput) {
              clsValue += entry.value;
            }
          });
          this.trackPerformance('cumulative_layout_shift', clsValue, 'score');
        });
        clsObserver.observe({ entryTypes: ['layout-shift'] });

      } catch (error) {
        console.warn('PerformanceObserver not fully supported:', error);
      }
    }
  }

  // Setup visibility tracking
  setupVisibilityTracking() {
    let visibilityStart = Date.now();
    let isVisible = !document.hidden;

    const handleVisibilityChange = () => {
      const now = Date.now();
      
      if (document.hidden && isVisible) {
        // Page became hidden
        const visibleDuration = now - visibilityStart;
        this.trackEngagement('page_visible', visibleDuration);
        isVisible = false;
      } else if (!document.hidden && !isVisible) {
        // Page became visible
        this.track('page_focus');
        visibilityStart = now;
        isVisible = true;
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Track page unload
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => {
        if (isVisible) {
          const visibleDuration = Date.now() - visibilityStart;
          this.trackEngagement('page_visible', visibleDuration);
        }
        this.track('session_end');
        this.flush(); // Final flush
      });
    }
  }

  // Setup error tracking
  setupErrorTracking() {
    // Global error handler
    if (typeof window !== 'undefined') {
      window.addEventListener('error', (event) => {
        this.trackError(event.error || new Error(event.message), {
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
          type: 'javascript_error'
        });
      });

      // Promise rejection handler
      window.addEventListener('unhandledrejection', (event) => {
        this.trackError(event.reason || new Error('Unhandled promise rejection'), {
          type: 'promise_rejection'
        });
      });
    }
  }

  // Setup automatic scroll tracking
  setupScrollTracking() {
    let maxScroll = 0;
    let scrollTimeout;

    const handleScroll = () => {
      const scrollPercent = Math.round(
        typeof window !== 'undefined' ? (window.scrollY / (document.documentElement.scrollHeight - window.innerHeight)) * 100 : 0
      );
      
      if (scrollPercent > maxScroll) {
        maxScroll = scrollPercent;
      }

      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        this.trackEngagement('scroll', null, { max_scroll_percent: maxScroll });
      }, 1000);
    };

    if (typeof window !== 'undefined') {
      window.addEventListener('scroll', handleScroll, { passive: true });
    }
  }

  // Start auto-flush timer
  startAutoFlush() {
    setInterval(() => {
      if (this.eventQueue.length > 0) {
        this.flush();
      }
    }, this.flushInterval);
  }

  // Generate unique session ID
  generateSessionId() {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  // Enable/disable analytics
  setEnabled(enabled) {
    this.isEnabled = enabled;
    if (!enabled) {
      this.eventQueue = [];
    }
  }

  // Set user properties
  setUserProperties(properties) {
    this.track('user_properties_updated', { properties });
  }

  // Track custom metric
  metric(name, value, tags = {}) {
    this.track('custom_metric', {
      metric_name: name,
      metric_value: value,
      tags
    });
  }

  // Track timing
  time(name) {
    const startTime = performance.now();
    return {
      end: () => {
        const duration = performance.now() - startTime;
        this.trackPerformance(name, duration);
        return duration;
      }
    };
  }

  // Create funnel tracking
  createFunnel(funnelName) {
    let step = 0;
    return {
      step: (stepName, properties = {}) => {
        step++;
        this.track('funnel_step', {
          funnel: funnelName,
          step_number: step,
          step_name: stepName,
          ...properties
        });
      }
    };
  }

  // Get analytics dashboard data
  async getDashboardData() {
    try {
      const response = await axios.get('/api/analytics/dashboard', {
        params: { session_id: this.sessionId }
      });
      return response.data;
    } catch (error) {
      console.warn('Failed to fetch analytics dashboard:', error);
      return this.getMockDashboardData();
    }
  }

  // Mock dashboard data for development
  getMockDashboardData() {
    return {
      pageViews: Math.floor(1000 + Math.random() * 5000),
      uniqueVisitors: Math.floor(500 + Math.random() * 2000),
      bounceRate: Number((0.3 + Math.random() * 0.4).toFixed(2)),
      avgSessionDuration: Math.floor(120 + Math.random() * 300), // seconds
      topPages: [
        { page: '/dashboard', views: 1500, duration: 245 },
        { page: '/portfolio', views: 890, duration: 180 },
        { page: '/stocks', views: 650, duration: 195 },
        { page: '/news', views: 420, duration: 120 },
        { page: '/settings', views: 280, duration: 90 }
      ],
      userJourney: [
        { step: 'Landing', users: 1000, conversion: 1.0 },
        { step: 'Registration', users: 750, conversion: 0.75 },
        { step: 'Dashboard View', users: 600, conversion: 0.8 },
        { step: 'Portfolio Setup', users: 450, conversion: 0.75 },
        { step: 'First Trade', users: 300, conversion: 0.67 }
      ],
      performanceMetrics: {
        avgPageLoad: 1200,
        avgApiResponse: 350,
        errorRate: 0.02,
        uptime: 99.9
      },
      featureUsage: [
        { feature: 'Stock Chart', usage: 85 },
        { feature: 'Portfolio Optimizer', usage: 65 },
        { feature: 'News Feed', usage: 70 },
        { feature: 'Watchlist', usage: 90 },
        { feature: 'Trading Signals', usage: 55 }
      ]
    };
  }
}

// Create singleton instance
const analyticsService = new AnalyticsService();

// Auto-setup scroll tracking
if (typeof window !== 'undefined') {
  analyticsService.setupScrollTracking();
}

export default analyticsService;