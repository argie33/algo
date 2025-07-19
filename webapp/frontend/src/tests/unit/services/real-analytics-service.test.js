/**
 * Real Analytics Service Unit Tests
 * Testing the actual analyticsService.js with event tracking and performance monitoring
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// Mock axios
vi.mock('axios');

// Mock DOM APIs
const mockPerformance = {
  timing: {
    navigationStart: 1000,
    domContentLoadedEventEnd: 1500,
    loadEventEnd: 2000,
    domInteractive: 1300,
    responseEnd: 1200
  },
  memory: {
    usedJSHeapSize: 1000000,
    totalJSHeapSize: 2000000,
    jsHeapSizeLimit: 4000000
  },
  now: vi.fn(() => Date.now()),
  getEntriesByType: vi.fn(() => [
    { duration: 100, transferSize: 1000 },
    { duration: 1500, transferSize: 0 },
    { duration: 200, transferSize: 500 }
  ])
};

const mockPerformanceObserver = vi.fn().mockImplementation((callback) => ({
  observe: vi.fn(),
  disconnect: vi.fn()
}));

Object.defineProperty(global, 'performance', {
  value: mockPerformance,
  writable: true
});

Object.defineProperty(global, 'PerformanceObserver', {
  value: mockPerformanceObserver,
  writable: true
});

// Mock window and document
Object.defineProperty(global, 'window', {
  value: {
    location: {
      href: 'https://example.com/test',
      pathname: '/test'
    },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    screen: { width: 1920, height: 1080 },
    navigator: { userAgent: 'test-browser' },
    scrollY: 0,
    innerHeight: 800
  },
  writable: true
});

Object.defineProperty(global, 'document', {
  value: {
    title: 'Test Page',
    referrer: 'https://example.com/previous',
    hidden: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    documentElement: { scrollHeight: 2000 }
  },
  writable: true
});

Object.defineProperty(global, 'Intl', {
  value: {
    DateTimeFormat: vi.fn(() => ({
      resolvedOptions: vi.fn(() => ({ timeZone: 'UTC' }))
    }))
  },
  writable: true
});

// Import the REAL AnalyticsService after mocks
import analyticsService from '../../../services/analyticsService';

describe('📊 Real Analytics Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    
    // Reset service state
    analyticsService.eventQueue = [];
    analyticsService.userId = null;
    analyticsService.isEnabled = true;
    analyticsService.performanceMetrics.clear();
    
    // Mock axios post
    axios.post.mockResolvedValue({ data: { success: true } });
    
    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with default configuration', () => {
      expect(analyticsService.sessionId).toMatch(/^session_\d+_[a-z0-9]+$/);
      expect(analyticsService.userId).toBeNull();
      expect(analyticsService.isEnabled).toBe(true);
      expect(analyticsService.batchSize).toBe(50);
      expect(analyticsService.flushInterval).toBe(30000);
      expect(analyticsService.eventQueue).toEqual([]);
      expect(analyticsService.performanceMetrics).toBeInstanceOf(Map);
    });

    it('should generate unique session IDs', () => {
      const sessionId1 = analyticsService.generateSessionId();
      const sessionId2 = analyticsService.generateSessionId();
      
      expect(sessionId1).not.toBe(sessionId2);
      expect(sessionId1).toMatch(/^session_\d+_[a-z0-9]+$/);
      expect(sessionId2).toMatch(/^session_\d+_[a-z0-9]+$/);
    });

    it('should initialize user with properties', () => {
      const userId = 'user123';
      const userProps = { plan: 'premium', region: 'US' };
      
      analyticsService.initialize(userId, userProps);
      
      expect(analyticsService.userId).toBe(userId);
      expect(analyticsService.eventQueue.length).toBeGreaterThan(0);
      
      const sessionStartEvent = analyticsService.eventQueue.find(e => e.event === 'session_start');
      expect(sessionStartEvent).toBeDefined();
      expect(sessionStartEvent.properties.user_agent).toBe('test-browser');
    });
  });

  describe('Event Tracking', () => {
    it('should track basic events with properties', () => {
      const eventName = 'test_event';
      const properties = { action: 'click', value: 100 };
      
      analyticsService.track(eventName, properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe(eventName);
      expect(event.session_id).toBe(analyticsService.sessionId);
      expect(event.timestamp).toBeDefined();
      expect(event.properties).toEqual(expect.objectContaining({
        action: 'click',
        value: 100,
        page_url: 'https://example.com/test',
        page_title: 'Test Page',
        referrer: 'https://example.com/previous'
      }));
    });

    it('should not track events when disabled', () => {
      analyticsService.setEnabled(false);
      
      analyticsService.track('disabled_event');
      
      expect(analyticsService.eventQueue).toHaveLength(0);
      expect(analyticsService.isEnabled).toBe(false);
    });

    it('should track page views with correct properties', () => {
      const pageName = 'dashboard';
      const properties = { section: 'main' };
      
      analyticsService.trackPageView(pageName, properties);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('page_view');
      expect(event.properties.page_name).toBe(pageName);
      expect(event.properties.section).toBe('main');
    });

    it('should track click events with element information', () => {
      const mockElement = {
        tagName: 'BUTTON',
        id: 'submit-btn',
        className: 'btn btn-primary',
        textContent: 'Submit Form'
      };
      
      analyticsService.trackClick(mockElement, { position: 'header' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('click');
      expect(event.properties.element_type).toBe('button');
      expect(event.properties.element_id).toBe('submit-btn');
      expect(event.properties.element_class).toBe('btn btn-primary');
      expect(event.properties.element_text).toBe('Submit Form');
      expect(event.properties.position).toBe('header');
    });

    it('should track form submissions', () => {
      analyticsService.trackFormSubmit('login_form', { fields: 3 });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('form_submit');
      expect(event.properties.form_name).toBe('login_form');
      expect(event.properties.fields).toBe(3);
    });

    it('should track search events', () => {
      analyticsService.trackSearch('AAPL stock price', 25, { category: 'stocks' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('search');
      expect(event.properties.query).toBe('AAPL stock price');
      expect(event.properties.results_count).toBe(25);
      expect(event.properties.category).toBe('stocks');
    });

    it('should track trading actions', () => {
      analyticsService.trackTrade('buy', 'AAPL', { quantity: 10, price: 185.50 });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('trade_action');
      expect(event.properties.action).toBe('buy');
      expect(event.properties.symbol).toBe('AAPL');
      expect(event.properties.quantity).toBe(10);
      expect(event.properties.price).toBe(185.50);
    });

    it('should track portfolio actions', () => {
      analyticsService.trackPortfolio('rebalance', { strategy: 'aggressive' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('portfolio_action');
      expect(event.properties.action).toBe('rebalance');
      expect(event.properties.strategy).toBe('aggressive');
    });

    it('should track news interactions', () => {
      analyticsService.trackNews('click', 'article_123', { source: 'reuters' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('news_interaction');
      expect(event.properties.action).toBe('click');
      expect(event.properties.article_id).toBe('article_123');
      expect(event.properties.source).toBe('reuters');
    });

    it('should track chart interactions', () => {
      analyticsService.trackChart('timeframe_change', 'AAPL', 'candlestick', { timeframe: '1D' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('chart_interaction');
      expect(event.properties.action).toBe('timeframe_change');
      expect(event.properties.symbol).toBe('AAPL');
      expect(event.properties.chart_type).toBe('candlestick');
      expect(event.properties.timeframe).toBe('1D');
    });
  });

  describe('Performance Tracking', () => {
    it('should track performance metrics', () => {
      analyticsService.trackPerformance('api_response_time', 250, 'ms');
      
      expect(analyticsService.performanceMetrics.has('api_response_time')).toBe(true);
      
      const metric = analyticsService.performanceMetrics.get('api_response_time');
      expect(metric.name).toBe('api_response_time');
      expect(metric.value).toBe(250);
      expect(metric.unit).toBe('ms');
      expect(metric.page).toBe('/test');
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('performance_metric');
    });

    it('should track API calls with timing and status', () => {
      analyticsService.trackApiCall('/api/stocks', 'GET', 150, 200, { cached: false });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('api_call');
      expect(event.properties.endpoint).toBe('/api/stocks');
      expect(event.properties.method).toBe('GET');
      expect(event.properties.duration).toBe(150);
      expect(event.properties.status).toBe(200);
      expect(event.properties.success).toBe(true);
      expect(event.properties.cached).toBe(false);
    });

    it('should track API failures correctly', () => {
      analyticsService.trackApiCall('/api/trading', 'POST', 5000, 500);
      
      const event = analyticsService.eventQueue[0];
      expect(event.properties.success).toBe(false);
      expect(event.properties.status).toBe(500);
    });

    it('should provide timing utility', () => {
      const timer = analyticsService.time('component_render');
      
      expect(typeof timer.end).toBe('function');
      
      vi.advanceTimersByTime(100);
      const duration = timer.end();
      
      expect(duration).toBeCloseTo(100, -1);
      expect(analyticsService.performanceMetrics.has('component_render')).toBe(true);
    });

    it('should get performance insights', () => {
      const insights = analyticsService.getPerformanceInsights();
      
      expect(insights.pageLoad).toEqual({
        domContentLoaded: 500,
        loadComplete: 1000,
        domReady: 300,
        firstPaint: 200
      });
      
      expect(insights.resources).toEqual({
        total: 3,
        slow: 1,
        failed: 1,
        avgDuration: expect.any(Number)
      });
      
      expect(insights.memory).toEqual({
        used: 1000000,
        total: 2000000,
        limit: 4000000
      });
    });
  });

  describe('Error Tracking', () => {
    it('should track errors with context', () => {
      const error = new Error('Test error');
      error.stack = 'Error: Test error\n    at test.js:10:5';
      
      analyticsService.trackError(error, { component: 'StockChart' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('error');
      expect(event.properties.error_message).toBe('Test error');
      expect(event.properties.error_stack).toBe('Error: Test error\n    at test.js:10:5');
      expect(event.properties.error_name).toBe('Error');
      expect(event.properties.context.component).toBe('StockChart');
    });

    it('should set up global error handlers', () => {
      expect(window.addEventListener).toHaveBeenCalledWith('error', expect.any(Function));
      expect(window.addEventListener).toHaveBeenCalledWith('unhandledrejection', expect.any(Function));
    });
  });

  describe('User Engagement Tracking', () => {
    it('should track engagement events', () => {
      analyticsService.trackEngagement('scroll', 1500, { direction: 'down' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('engagement');
      expect(event.properties.action).toBe('scroll');
      expect(event.properties.duration).toBe(1500);
      expect(event.properties.direction).toBe('down');
    });

    it('should track feature usage', () => {
      analyticsService.trackFeatureUsage('portfolio_optimizer', { version: 'v2' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('feature_usage');
      expect(event.properties.feature).toBe('portfolio_optimizer');
      expect(event.properties.version).toBe('v2');
    });

    it('should track conversion events', () => {
      analyticsService.trackConversion('user_signup', 1, { channel: 'organic' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('conversion');
      expect(event.properties.goal).toBe('user_signup');
      expect(event.properties.value).toBe(1);
      expect(event.properties.channel).toBe('organic');
    });

    it('should track A/B test experiments', () => {
      analyticsService.trackExperiment('button_color_test', 'variant_b', { color: 'blue' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('experiment');
      expect(event.properties.experiment).toBe('button_color_test');
      expect(event.properties.variant).toBe('variant_b');
      expect(event.properties.color).toBe('blue');
    });

    it('should create funnel tracking', () => {
      const funnel = analyticsService.createFunnel('user_onboarding');
      
      funnel.step('registration', { source: 'landing_page' });
      funnel.step('email_verification');
      funnel.step('profile_setup');
      
      expect(analyticsService.eventQueue).toHaveLength(3);
      
      const steps = analyticsService.eventQueue.filter(e => e.event === 'funnel_step');
      expect(steps[0].properties.step_number).toBe(1);
      expect(steps[0].properties.step_name).toBe('registration');
      expect(steps[1].properties.step_number).toBe(2);
      expect(steps[2].properties.step_number).toBe(3);
    });
  });

  describe('Event Batching and Flushing', () => {
    it('should batch events until batch size is reached', () => {
      for (let i = 0; i < 49; i++) {
        analyticsService.track(`event_${i}`);
      }
      
      expect(analyticsService.eventQueue).toHaveLength(49);
      expect(axios.post).not.toHaveBeenCalled();
      
      // This should trigger flush
      analyticsService.track('event_50');
      
      expect(axios.post).toHaveBeenCalledWith('/api/analytics/events', {
        events: expect.any(Array),
        session_id: analyticsService.sessionId
      });
    });

    it('should flush events manually', async () => {
      analyticsService.track('manual_flush_test');
      
      await analyticsService.flush();
      
      expect(axios.post).toHaveBeenCalledWith('/api/analytics/events', {
        events: expect.arrayContaining([
          expect.objectContaining({ event: 'manual_flush_test' })
        ]),
        session_id: analyticsService.sessionId
      });
      
      expect(analyticsService.eventQueue).toHaveLength(0);
    });

    it('should handle flush failures gracefully', async () => {
      axios.post.mockRejectedValue(new Error('Network error'));
      
      analyticsService.track('retry_test');
      const originalEvent = { ...analyticsService.eventQueue[0] };
      
      await analyticsService.flush();
      
      // Event should be re-queued on failure
      expect(analyticsService.eventQueue).toHaveLength(1);
      expect(analyticsService.eventQueue[0].event).toBe('retry_test');
      expect(console.warn).toHaveBeenCalledWith('Failed to send analytics events:', expect.any(Error));
    });

    it('should auto-flush events at intervals', () => {
      analyticsService.track('auto_flush_test');
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      // Fast forward to trigger auto-flush
      vi.advanceTimersByTime(30000);
      
      expect(axios.post).toHaveBeenCalled();
    });

    it('should limit re-queued events to prevent memory issues', async () => {
      axios.post.mockRejectedValue(new Error('Network error'));
      
      // Fill queue beyond limit
      for (let i = 0; i < 150; i++) {
        analyticsService.track(`event_${i}`);
      }
      
      await analyticsService.flush();
      
      // Should not exceed 2x batch size
      expect(analyticsService.eventQueue.length).toBeLessThanOrEqual(100);
    });
  });

  describe('User Identification and Properties', () => {
    it('should identify users with properties', () => {
      const userId = 'user456';
      const properties = { email: 'test@example.com', plan: 'pro' };
      
      analyticsService.identify(userId, properties);
      
      expect(analyticsService.userId).toBe(userId);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('user_identify');
      expect(event.properties.user_id).toBe(userId);
      expect(event.properties.properties.email).toBe('test@example.com');
    });

    it('should set user properties', () => {
      analyticsService.setUserProperties({ subscription: 'premium', region: 'EU' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('user_properties_updated');
      expect(event.properties.properties.subscription).toBe('premium');
      expect(event.properties.properties.region).toBe('EU');
    });
  });

  describe('Custom Metrics and Tracking', () => {
    it('should track custom metrics', () => {
      analyticsService.metric('portfolio_value', 50000, { currency: 'USD' });
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('custom_metric');
      expect(event.properties.metric_name).toBe('portfolio_value');
      expect(event.properties.metric_value).toBe(50000);
      expect(event.properties.tags.currency).toBe('USD');
    });
  });

  describe('Dashboard Data and Analytics', () => {
    it('should fetch dashboard data from API', async () => {
      const mockDashboardData = {
        pageViews: 5000,
        uniqueVisitors: 2000,
        bounceRate: 0.35
      };
      
      axios.get.mockResolvedValue({ data: mockDashboardData });
      
      const data = await analyticsService.getDashboardData();
      
      expect(axios.get).toHaveBeenCalledWith('/api/analytics/dashboard', {
        params: { session_id: analyticsService.sessionId }
      });
      expect(data).toEqual(mockDashboardData);
    });

    it('should return mock data when API fails', async () => {
      axios.get.mockRejectedValue(new Error('API error'));
      
      const data = await analyticsService.getDashboardData();
      
      expect(data.pageViews).toBeGreaterThan(0);
      expect(data.uniqueVisitors).toBeGreaterThan(0);
      expect(data.topPages).toHaveLength(5);
      expect(data.userJourney).toHaveLength(5);
      expect(data.performanceMetrics).toBeDefined();
      expect(console.warn).toHaveBeenCalledWith('Failed to fetch analytics dashboard:', expect.any(Error));
    });

    it('should provide mock dashboard data structure', () => {
      const mockData = analyticsService.getMockDashboardData();
      
      expect(mockData).toEqual(expect.objectContaining({
        pageViews: expect.any(Number),
        uniqueVisitors: expect.any(Number),
        bounceRate: expect.any(Number),
        avgSessionDuration: expect.any(Number),
        topPages: expect.any(Array),
        userJourney: expect.any(Array),
        performanceMetrics: expect.any(Object),
        featureUsage: expect.any(Array)
      }));
      
      expect(mockData.topPages[0]).toEqual(expect.objectContaining({
        page: expect.any(String),
        views: expect.any(Number),
        duration: expect.any(Number)
      }));
    });
  });

  describe('Performance Observer Integration', () => {
    it('should set up performance observers', () => {
      expect(mockPerformanceObserver).toHaveBeenCalledTimes(3);
      
      // Should observe LCP, FID, and CLS
      const calls = mockPerformanceObserver.mock.calls;
      expect(calls[0][0]).toBeInstanceOf(Function);
      expect(calls[1][0]).toBeInstanceOf(Function);
      expect(calls[2][0]).toBeInstanceOf(Function);
    });

    it('should handle performance observer failures gracefully', () => {
      mockPerformanceObserver.mockImplementation(() => {
        throw new Error('Observer not supported');
      });
      
      expect(() => {
        analyticsService.setupPerformanceObserver();
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalledWith('PerformanceObserver not fully supported:', expect.any(Error));
    });
  });

  describe('Visibility and Session Tracking', () => {
    it('should set up visibility change tracking', () => {
      expect(document.addEventListener).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
      expect(window.addEventListener).toHaveBeenCalledWith('beforeunload', expect.any(Function));
    });
  });

  describe('Service Management', () => {
    it('should enable and disable analytics', () => {
      analyticsService.track('before_disable');
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      analyticsService.setEnabled(false);
      
      analyticsService.track('after_disable');
      expect(analyticsService.eventQueue).toHaveLength(0);
      expect(analyticsService.isEnabled).toBe(false);
      
      analyticsService.setEnabled(true);
      analyticsService.track('after_enable');
      expect(analyticsService.eventQueue).toHaveLength(1);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should handle missing element properties in click tracking', () => {
      const incompleteElement = { tagName: 'DIV' };
      
      analyticsService.trackClick(incompleteElement);
      
      const event = analyticsService.eventQueue[0];
      expect(event.properties.element_type).toBe('div');
      expect(event.properties.element_id).toBeUndefined();
      expect(event.properties.element_class).toBeUndefined();
    });

    it('should handle long element text content', () => {
      const longTextElement = {
        tagName: 'P',
        textContent: 'A'.repeat(200)
      };
      
      analyticsService.trackClick(longTextElement);
      
      const event = analyticsService.eventQueue[0];
      expect(event.properties.element_text).toHaveLength(100);
    });

    it('should handle empty event queues during flush', async () => {
      await analyticsService.flush();
      
      expect(axios.post).not.toHaveBeenCalled();
    });
  });
});