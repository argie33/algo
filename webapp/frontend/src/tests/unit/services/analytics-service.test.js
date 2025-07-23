/**
 * Analytics Service Unit Tests
 * Testing the actual user behavior and performance tracking service
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// Real Analytics Service - Import actual production service
import analyticsService from '../../../services/analyticsService';

// Mock axios to avoid real API calls
vi.mock('axios');
const mockedAxios = vi.mocked(axios);

describe('📊 Analytics Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedAxios.post.mockResolvedValue({ data: { success: true } });
    
    // Reset the service state
    analyticsService.eventQueue = [];
    analyticsService.userId = null;
    analyticsService.isEnabled = true;
  });

  afterEach(() => {
    vi.clearAllMocks();
    
    // Clean up any timers or intervals
    analyticsService.eventQueue = [];
  });

  describe('Service Initialization', () => {
    it('should initialize with default configuration', () => {
      expect(analyticsService.sessionId).toBeDefined();
      expect(analyticsService.isEnabled).toBe(true);
      expect(analyticsService.batchSize).toBe(50);
      expect(analyticsService.flushInterval).toBe(30000);
      expect(analyticsService.eventQueue).toEqual([]);
    });

    it('should initialize user context', () => {
      const userId = 'test-user-123';
      const userProps = { email: 'test@example.com', plan: 'premium' };
      
      analyticsService.initialize(userId, userProps);
      
      expect(analyticsService.userId).toBe(userId);
      expect(analyticsService.eventQueue).toHaveLength(2); // identify + session_start events
    });
  });

  describe('Event Tracking', () => {
    it('should track basic events', () => {
      const eventName = 'button_click';
      const properties = { button_id: 'save-portfolio', location: 'header' };
      
      analyticsService.track(eventName, properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe(eventName);
      expect(event.properties).toMatchObject(properties);
      expect(event.timestamp).toBeDefined();
      expect(event.session_id).toBe(analyticsService.sessionId);
    });

    it('should track page views', () => {
      const pageName = '/portfolio';
      const properties = { title: 'Portfolio Dashboard', category: 'portfolio' };
      
      analyticsService.trackPageView(pageName, properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('page_view');
      expect(event.properties.page_name).toBe(pageName);
      expect(event.properties).toMatchObject(properties);
    });

    it('should track user clicks', () => {
      const mockElement = {
        tagName: 'BUTTON',
        id: 'buy-button',
        className: 'btn-primary',
        textContent: 'Buy Stock'
      };
      const properties = { symbol: 'AAPL', quantity: 100 };
      
      analyticsService.trackClick(mockElement, properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('click');
      expect(event.properties.element_type).toBe('button');
      expect(event.properties.element_id).toBe('buy-button');
      expect(event.properties).toMatchObject(properties);
    });

    it('should track engagement events', () => {
      const action = 'scroll';
      const duration = 1500;
      const properties = { max_scroll_percent: 75 };
      
      analyticsService.trackEngagement(action, duration, properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('engagement');
      expect(event.properties.action).toBe(action);
      expect(event.properties.duration).toBe(duration);
      expect(event.properties).toMatchObject(properties);
    });

    it('should track conversions', () => {
      const goalName = 'portfolio_created';
      const value = 1000;
      const properties = { plan: 'premium', method: 'credit_card' };
      
      analyticsService.trackConversion(goalName, value, properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('conversion');
      expect(event.properties.goal).toBe(goalName);
      expect(event.properties.value).toBe(value);
      expect(event.properties).toMatchObject(properties);
    });

    it('should track A/B test experiments', () => {
      const experimentName = 'new_dashboard_layout';
      const variant = 'variant_b';
      const properties = { user_segment: 'premium' };
      
      analyticsService.trackExperiment(experimentName, variant, properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('experiment');
      expect(event.properties.experiment).toBe(experimentName);
      expect(event.properties.variant).toBe(variant);
      expect(event.properties).toMatchObject(properties);
    });
  });

  describe('Performance Tracking', () => {
    it('should track custom metrics', () => {
      const metricName = 'portfolio_load_time';
      const value = 1250;
      const tags = { page: 'dashboard', user_type: 'premium' };
      
      analyticsService.metric(metricName, value, tags);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('custom_metric');
      expect(event.properties.metric_name).toBe(metricName);
      expect(event.properties.metric_value).toBe(value);
      expect(event.properties.tags).toMatchObject(tags);
    });

    it('should track timing measurements', () => {
      const timer = analyticsService.time('api_call_duration');
      
      // Simulate some work
      setTimeout(() => {
        timer.end();
      }, 100);
      
      // Timer should return an object with end method
      expect(timer).toHaveProperty('end');
      expect(typeof timer.end).toBe('function');
    });
  });

  describe('Event Queue Management', () => {
    it('should queue events when enabled', () => {
      analyticsService.setEnabled(true);
      
      analyticsService.track('test_event', { test: 'data' });
      
      expect(analyticsService.eventQueue).toHaveLength(1);
    });

    it('should not queue events when disabled', () => {
      analyticsService.setEnabled(false);
      
      analyticsService.track('test_event', { test: 'data' });
      
      expect(analyticsService.eventQueue).toHaveLength(0);
    });

    it('should flush events to server', async () => {
      analyticsService.track('event1', { data: 'test1' });
      analyticsService.track('event2', { data: 'test2' });
      
      expect(analyticsService.eventQueue).toHaveLength(2);
      
      await analyticsService.flush();
      
      expect(mockedAxios.post).toHaveBeenCalledWith('/api/analytics/events', {
        events: expect.arrayContaining([
          expect.objectContaining({ event: 'event1' }),
          expect.objectContaining({ event: 'event2' })
        ]),
        session_id: analyticsService.sessionId
      });
      
      expect(analyticsService.eventQueue).toHaveLength(0);
    });

    it('should handle flush errors gracefully', async () => {
      mockedAxios.post.mockRejectedValueOnce(new Error('Network error'));
      
      analyticsService.track('test_event');
      
      await expect(analyticsService.flush()).resolves.not.toThrow();
      
      // Events should be re-queued on failure
      expect(analyticsService.eventQueue).toHaveLength(1);
    });

    it('should limit re-queued events to prevent memory leaks', async () => {
      mockedAxios.post.mockRejectedValue(new Error('Network error'));
      
      // Fill queue beyond batch size
      for (let i = 0; i < 120; i++) {
        analyticsService.track(`event_${i}`);
      }
      
      await analyticsService.flush();
      
      // Should not exceed 2x batch size
      expect(analyticsService.eventQueue.length).toBeLessThanOrEqual(100);
    });
  });

  describe('User Management', () => {
    it('should identify users', () => {
      const userId = 'user-456';
      const properties = { email: 'user@example.com', plan: 'basic' };
      
      analyticsService.identify(userId, properties);
      
      expect(analyticsService.userId).toBe(userId);
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('user_identify');
      expect(event.properties.user_id).toBe(userId);
      expect(event.properties.properties).toMatchObject(properties);
    });

    it('should update user properties', () => {
      const properties = { subscription_tier: 'premium', last_login: '2024-01-15' };
      
      analyticsService.setUserProperties(properties);
      
      expect(analyticsService.eventQueue).toHaveLength(1);
      
      const event = analyticsService.eventQueue[0];
      expect(event.event).toBe('user_properties_updated');
      expect(event.properties.properties).toMatchObject(properties);
    });
  });

  describe('Error Handling', () => {
    it('should handle missing parameters gracefully', () => {
      expect(() => analyticsService.track()).not.toThrow();
      expect(() => analyticsService.track('')).not.toThrow();
      expect(() => analyticsService.trackPageView()).not.toThrow();
    });

    it('should generate unique session IDs', () => {
      const sessionId1 = analyticsService.generateSessionId();
      const sessionId2 = analyticsService.generateSessionId();
      
      expect(sessionId1).toBeDefined();
      expect(sessionId2).toBeDefined();
      expect(sessionId1).not.toBe(sessionId2);
      expect(sessionId1).toMatch(/^session_\d+_[a-z0-9]+$/);
    });
  });

  describe('Configuration', () => {
    it('should allow enabling/disabling analytics', () => {
      analyticsService.setEnabled(false);
      expect(analyticsService.isEnabled).toBe(false);
      expect(analyticsService.eventQueue).toHaveLength(0);
      
      analyticsService.setEnabled(true);
      expect(analyticsService.isEnabled).toBe(true);
    });

    it('should clear queue when disabled', () => {
      analyticsService.track('event1');
      analyticsService.track('event2');
      expect(analyticsService.eventQueue).toHaveLength(2);
      
      analyticsService.setEnabled(false);
      expect(analyticsService.eventQueue).toHaveLength(0);
    });
  });
});