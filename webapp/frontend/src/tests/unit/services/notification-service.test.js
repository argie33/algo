/**
 * Notification Service Unit Tests
 * Comprehensive testing of notification management and delivery functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Real Notification Service - Import actual production service
import { NotificationService } from '../../../services/NotificationService';
import { apiClient } from '../../../services/api';
import { webSocketService } from '../../../services/webSocket';
import { storageService } from '../../../services/storage';
import { pushNotificationService } from '../../../services/pushNotifications';

// Mock external dependencies but use real service
vi.mock('../../../services/api');
vi.mock('../../../services/webSocket');
vi.mock('../../../services/storage');
vi.mock('../../../services/pushNotifications');

describe('🔔 Notification Service', () => {
  let notificationService;
  let mockApi;
  let mockWebSocket;
  let mockStorage;
  let mockPushService;

  const mockNotification = {
    id: 'notif_123',
    type: 'trade_executed',
    title: 'Trade Executed',
    message: 'Your buy order for 100 shares of AAPL has been executed at $150.00',
    userId: 'user_456',
    data: {
      symbol: 'AAPL',
      quantity: 100,
      price: 150.00,
      type: 'buy',
      orderId: 'order_789'
    },
    priority: 'high',
    channels: ['in_app', 'push', 'email'],
    readAt: null,
    createdAt: '2024-01-15T10:30:00Z',
    expiresAt: '2024-01-22T10:30:00Z'
  };

  const mockNotificationPreferences = {
    userId: 'user_456',
    channels: {
      email: {
        enabled: true,
        address: 'user@example.com',
        frequency: 'immediate'
      },
      push: {
        enabled: true,
        deviceTokens: ['token_123', 'token_456'],
        quietHours: { start: '22:00', end: '07:00' }
      },
      sms: {
        enabled: false,
        phoneNumber: '+1234567890'
      },
      in_app: {
        enabled: true,
        sound: true,
        badge: true
      }
    },
    types: {
      trade_executed: { enabled: true, channels: ['in_app', 'push', 'email'] },
      price_alert: { enabled: true, channels: ['in_app', 'push'] },
      market_news: { enabled: false, channels: [] },
      system_maintenance: { enabled: true, channels: ['in_app', 'email'] },
      security_alert: { enabled: true, channels: ['all'] }
    },
    timezone: 'America/New_York'
  };

  beforeEach(() => {
    mockApi = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn()
    };

    mockWebSocket = {
      on: vi.fn(),
      emit: vi.fn(),
      disconnect: vi.fn(),
      isConnected: vi.fn().mockReturnValue(true)
    };

    mockStorage = {
      get: vi.fn(),
      set: vi.fn(),
      remove: vi.fn(),
      clear: vi.fn()
    };

    mockPushService = {
      requestPermission: vi.fn(),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      sendNotification: vi.fn()
    };

    // Mock the imports
    apiClient.mockReturnValue(mockApi);
    webSocketService.mockReturnValue(mockWebSocket);
    storageService.mockReturnValue(mockStorage);
    pushNotificationService.mockReturnValue(mockPushService);

    notificationService = new NotificationService();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Notification Creation', () => {
    it('should create notification successfully', async () => {
      mockApi.post.mockResolvedValue({ 
        success: true, 
        notification: mockNotification 
      });

      const result = await notificationService.createNotification({
        type: 'trade_executed',
        title: 'Trade Executed',
        message: 'Your trade has been executed',
        userId: 'user_456',
        data: { orderId: 'order_789' }
      });

      expect(mockApi.post).toHaveBeenCalledWith('/notifications', {
        type: 'trade_executed',
        title: 'Trade Executed',
        message: 'Your trade has been executed',
        userId: 'user_456',
        data: { orderId: 'order_789' }
      });

      expect(result.notification.id).toBe('notif_123');
      expect(result.notification.type).toBe('trade_executed');
    });

    it('should validate notification data', async () => {
      await expect(notificationService.createNotification()).rejects.toThrow('Notification data is required');
      
      await expect(notificationService.createNotification({
        title: 'Test'
        // Missing required fields
      })).rejects.toThrow('Type and message are required');
    });

    it('should set default values for optional fields', async () => {
      const minimalNotification = {
        type: 'info',
        title: 'Info',
        message: 'Test message',
        userId: 'user_456'
      };

      mockApi.post.mockResolvedValue({ 
        success: true, 
        notification: { ...mockNotification, ...minimalNotification }
      });

      await notificationService.createNotification(minimalNotification);

      expect(mockApi.post).toHaveBeenCalledWith('/notifications', {
        ...minimalNotification,
        priority: 'normal',
        channels: ['in_app'],
        data: {}
      });
    });

    it('should handle template-based notifications', async () => {
      mockApi.post.mockResolvedValue({ 
        success: true, 
        notification: mockNotification 
      });

      await notificationService.createFromTemplate('trade_executed', {
        userId: 'user_456',
        symbol: 'AAPL',
        quantity: 100,
        price: 150.00
      });

      expect(mockApi.post).toHaveBeenCalledWith('/notifications/template', {
        template: 'trade_executed',
        variables: {
          userId: 'user_456',
          symbol: 'AAPL',
          quantity: 100,
          price: 150.00
        }
      });
    });

    it('should support bulk notification creation', async () => {
      const bulkNotifications = [
        { type: 'info', title: 'Info 1', message: 'Message 1', userId: 'user_1' },
        { type: 'warning', title: 'Warning 1', message: 'Message 2', userId: 'user_2' }
      ];

      mockApi.post.mockResolvedValue({ 
        success: true, 
        created: 2,
        notifications: bulkNotifications.map((n, i) => ({ ...n, id: `notif_${i}` }))
      });

      const result = await notificationService.createBulkNotifications(bulkNotifications);

      expect(mockApi.post).toHaveBeenCalledWith('/notifications/bulk', {
        notifications: bulkNotifications
      });

      expect(result.created).toBe(2);
      expect(result.notifications).toHaveLength(2);
    });
  });

  describe('Notification Retrieval', () => {
    it('should get user notifications with pagination', async () => {
      const mockNotifications = {
        notifications: [mockNotification],
        total: 1,
        page: 1,
        limit: 10,
        hasMore: false
      };

      mockApi.get.mockResolvedValue(mockNotifications);

      const result = await notificationService.getUserNotifications('user_456', {
        page: 1,
        limit: 10,
        unreadOnly: false
      });

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/user/user_456', {
        params: {
          page: 1,
          limit: 10,
          unreadOnly: false
        }
      });

      expect(result.notifications).toHaveLength(1);
      expect(result.total).toBe(1);
    });

    it('should filter notifications by type', async () => {
      mockApi.get.mockResolvedValue({
        notifications: [mockNotification],
        total: 1
      });

      await notificationService.getUserNotifications('user_456', {
        types: ['trade_executed', 'price_alert'],
        priority: 'high'
      });

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/user/user_456', {
        params: {
          types: ['trade_executed', 'price_alert'],
          priority: 'high'
        }
      });
    });

    it('should get notification by ID', async () => {
      mockApi.get.mockResolvedValue({ notification: mockNotification });

      const result = await notificationService.getNotification('notif_123');

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/notif_123');
      expect(result.notification.id).toBe('notif_123');
    });

    it('should get unread count', async () => {
      mockApi.get.mockResolvedValue({ count: 5 });

      const count = await notificationService.getUnreadCount('user_456');

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/user/user_456/unread-count');
      expect(count).toBe(5);
    });

    it('should handle cache for recent notifications', async () => {
      const cachedNotifications = [mockNotification];
      mockStorage.get.mockReturnValue(cachedNotifications);

      const result = await notificationService.getUserNotifications('user_456', {
        useCache: true,
        cacheMaxAge: 300000 // 5 minutes
      });

      expect(mockStorage.get).toHaveBeenCalledWith('notifications_user_456');
      expect(result.notifications).toEqual(cachedNotifications);
      expect(mockApi.get).not.toHaveBeenCalled();
    });
  });

  describe('Notification Updates', () => {
    it('should mark notification as read', async () => {
      mockApi.put.mockResolvedValue({ 
        success: true, 
        notification: { ...mockNotification, readAt: '2024-01-15T11:00:00Z' }
      });

      const result = await notificationService.markAsRead('notif_123');

      expect(mockApi.put).toHaveBeenCalledWith('/notifications/notif_123/read');
      expect(result.notification.readAt).toBeTruthy();
    });

    it('should mark multiple notifications as read', async () => {
      const notificationIds = ['notif_123', 'notif_456'];
      mockApi.put.mockResolvedValue({ 
        success: true, 
        updated: 2 
      });

      const result = await notificationService.markMultipleAsRead(notificationIds);

      expect(mockApi.put).toHaveBeenCalledWith('/notifications/mark-read', {
        notificationIds
      });
      expect(result.updated).toBe(2);
    });

    it('should mark all notifications as read for user', async () => {
      mockApi.put.mockResolvedValue({ 
        success: true, 
        updated: 10 
      });

      const result = await notificationService.markAllAsRead('user_456');

      expect(mockApi.put).toHaveBeenCalledWith('/notifications/user/user_456/mark-all-read');
      expect(result.updated).toBe(10);
    });

    it('should archive notification', async () => {
      mockApi.put.mockResolvedValue({ 
        success: true, 
        notification: { ...mockNotification, archived: true }
      });

      const result = await notificationService.archiveNotification('notif_123');

      expect(mockApi.put).toHaveBeenCalledWith('/notifications/notif_123/archive');
      expect(result.notification.archived).toBe(true);
    });

    it('should snooze notification', async () => {
      const snoozeUntil = '2024-01-15T15:00:00Z';
      mockApi.put.mockResolvedValue({ 
        success: true, 
        notification: { ...mockNotification, snoozedUntil: snoozeUntil }
      });

      const result = await notificationService.snoozeNotification('notif_123', snoozeUntil);

      expect(mockApi.put).toHaveBeenCalledWith('/notifications/notif_123/snooze', {
        snoozeUntil
      });
      expect(result.notification.snoozedUntil).toBe(snoozeUntil);
    });
  });

  describe('Notification Deletion', () => {
    it('should delete notification', async () => {
      mockApi.delete.mockResolvedValue({ success: true });

      const result = await notificationService.deleteNotification('notif_123');

      expect(mockApi.delete).toHaveBeenCalledWith('/notifications/notif_123');
      expect(result.success).toBe(true);
    });

    it('should delete multiple notifications', async () => {
      const notificationIds = ['notif_123', 'notif_456'];
      mockApi.delete.mockResolvedValue({ 
        success: true, 
        deleted: 2 
      });

      const result = await notificationService.deleteMultipleNotifications(notificationIds);

      expect(mockApi.delete).toHaveBeenCalledWith('/notifications/bulk', {
        data: { notificationIds }
      });
      expect(result.deleted).toBe(2);
    });

    it('should clear all notifications for user', async () => {
      mockApi.delete.mockResolvedValue({ 
        success: true, 
        deleted: 25 
      });

      const result = await notificationService.clearAllNotifications('user_456');

      expect(mockApi.delete).toHaveBeenCalledWith('/notifications/user/user_456');
      expect(result.deleted).toBe(25);
    });

    it('should auto-delete expired notifications', async () => {
      mockApi.delete.mockResolvedValue({ 
        success: true, 
        deleted: 5 
      });

      const result = await notificationService.cleanupExpiredNotifications();

      expect(mockApi.delete).toHaveBeenCalledWith('/notifications/cleanup-expired');
      expect(result.deleted).toBe(5);
    });
  });

  describe('Notification Preferences', () => {
    it('should get user preferences', async () => {
      mockApi.get.mockResolvedValue({ preferences: mockNotificationPreferences });

      const result = await notificationService.getUserPreferences('user_456');

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/preferences/user_456');
      expect(result.preferences.userId).toBe('user_456');
      expect(result.preferences.channels.email.enabled).toBe(true);
    });

    it('should update user preferences', async () => {
      const updatedPreferences = {
        ...mockNotificationPreferences,
        channels: {
          ...mockNotificationPreferences.channels,
          email: {
            ...mockNotificationPreferences.channels.email,
            enabled: false
          }
        }
      };

      mockApi.put.mockResolvedValue({ 
        success: true, 
        preferences: updatedPreferences 
      });

      const result = await notificationService.updateUserPreferences('user_456', {
        channels: {
          email: { enabled: false }
        }
      });

      expect(mockApi.put).toHaveBeenCalledWith('/notifications/preferences/user_456', {
        channels: {
          email: { enabled: false }
        }
      });
      expect(result.preferences.channels.email.enabled).toBe(false);
    });

    it('should validate preference updates', async () => {
      await expect(notificationService.updateUserPreferences('user_456', {
        channels: {
          invalid_channel: { enabled: true }
        }
      })).rejects.toThrow('Invalid channel: invalid_channel');

      await expect(notificationService.updateUserPreferences('user_456', {
        types: {
          invalid_type: { enabled: true }
        }
      })).rejects.toThrow('Invalid notification type: invalid_type');
    });

    it('should handle quiet hours', async () => {
      const currentTime = '23:00'; // During quiet hours
      
      const shouldDeliver = notificationService.shouldDeliverNotification(
        mockNotification,
        mockNotificationPreferences,
        currentTime
      );

      expect(shouldDeliver.push).toBe(false); // Should not send push during quiet hours
      expect(shouldDeliver.in_app).toBe(true); // In-app notifications not affected
    });

    it('should respect channel preferences by notification type', () => {
      const priceAlertNotification = {
        ...mockNotification,
        type: 'price_alert'
      };

      const allowedChannels = notificationService.getAllowedChannels(
        priceAlertNotification,
        mockNotificationPreferences
      );

      expect(allowedChannels).toEqual(['in_app', 'push']);
      expect(allowedChannels).not.toContain('email');
    });
  });

  describe('Real-time Notifications', () => {
    it('should subscribe to real-time notifications', async () => {
      const callback = vi.fn();

      await notificationService.subscribeToRealTime('user_456', callback);

      expect(mockWebSocket.on).toHaveBeenCalledWith('notification', expect.any(Function));
      expect(mockWebSocket.emit).toHaveBeenCalledWith('subscribe_notifications', {
        userId: 'user_456'
      });
    });

    it('should handle real-time notification delivery', async () => {
      const callback = vi.fn();
      let notificationHandler;

      mockWebSocket.on.mockImplementation((event, handler) => {
        if (event === 'notification') {
          notificationHandler = handler;
        }
      });

      await notificationService.subscribeToRealTime('user_456', callback);

      // Simulate receiving real-time notification
      notificationHandler(mockNotification);

      expect(callback).toHaveBeenCalledWith(mockNotification);
    });

    it('should unsubscribe from real-time notifications', async () => {
      await notificationService.unsubscribeFromRealTime('user_456');

      expect(mockWebSocket.emit).toHaveBeenCalledWith('unsubscribe_notifications', {
        userId: 'user_456'
      });
    });

    it('should handle connection loss gracefully', async () => {
      mockWebSocket.isConnected.mockReturnValue(false);
      const callback = vi.fn();

      await notificationService.subscribeToRealTime('user_456', callback);

      // Should attempt to reconnect
      expect(mockWebSocket.emit).toHaveBeenCalledWith('reconnect');
    });

    it('should queue notifications when offline', async () => {
      mockWebSocket.isConnected.mockReturnValue(false);
      
      await notificationService.createNotification({
        type: 'info',
        title: 'Test',
        message: 'Offline notification',
        userId: 'user_456'
      });

      // Should queue for when connection is restored
      expect(mockStorage.set).toHaveBeenCalledWith('notification_queue', expect.any(Array));
    });
  });

  describe('Push Notifications', () => {
    it('should request push notification permission', async () => {
      mockPushService.requestPermission.mockResolvedValue('granted');

      const permission = await notificationService.requestPushPermission();

      expect(mockPushService.requestPermission).toHaveBeenCalled();
      expect(permission).toBe('granted');
    });

    it('should subscribe to push notifications', async () => {
      const subscription = {
        endpoint: 'https://fcm.googleapis.com/fcm/send/abc123',
        keys: {
          p256dh: 'key1',
          auth: 'key2'
        }
      };

      mockPushService.subscribe.mockResolvedValue(subscription);
      mockApi.post.mockResolvedValue({ success: true });

      const result = await notificationService.subscribeToPush('user_456');

      expect(mockPushService.subscribe).toHaveBeenCalled();
      expect(mockApi.post).toHaveBeenCalledWith('/notifications/push/subscribe', {
        userId: 'user_456',
        subscription
      });
      expect(result.success).toBe(true);
    });

    it('should unsubscribe from push notifications', async () => {
      mockApi.delete.mockResolvedValue({ success: true });

      const result = await notificationService.unsubscribeFromPush('user_456', 'device_token_123');

      expect(mockApi.delete).toHaveBeenCalledWith('/notifications/push/unsubscribe', {
        data: {
          userId: 'user_456',
          deviceToken: 'device_token_123'
        }
      });
      expect(result.success).toBe(true);
    });

    it('should send push notification', async () => {
      mockPushService.sendNotification.mockResolvedValue({ success: true });

      const result = await notificationService.sendPushNotification({
        userId: 'user_456',
        title: 'Push Test',
        body: 'Test message',
        data: { url: '/dashboard' }
      });

      expect(mockPushService.sendNotification).toHaveBeenCalledWith({
        userId: 'user_456',
        title: 'Push Test',
        body: 'Test message',
        data: { url: '/dashboard' }
      });
      expect(result.success).toBe(true);
    });

    it('should handle push notification clicks', async () => {
      const onNotificationClick = vi.fn();
      
      notificationService.onPushNotificationClick(onNotificationClick);

      // Simulate push notification click
      const clickEvent = {
        notification: {
          data: { url: '/portfolio', notificationId: 'notif_123' }
        }
      };

      // This would be handled by service worker in real implementation
      onNotificationClick(clickEvent);
      expect(onNotificationClick).toHaveBeenCalledWith(clickEvent);
    });
  });

  describe('Email Notifications', () => {
    it('should send email notification', async () => {
      mockApi.post.mockResolvedValue({ 
        success: true, 
        messageId: 'email_123' 
      });

      const result = await notificationService.sendEmailNotification({
        userId: 'user_456',
        subject: 'Trade Executed',
        template: 'trade_executed',
        data: mockNotification.data
      });

      expect(mockApi.post).toHaveBeenCalledWith('/notifications/email', {
        userId: 'user_456',
        subject: 'Trade Executed',
        template: 'trade_executed',
        data: mockNotification.data
      });
      expect(result.messageId).toBe('email_123');
    });

    it('should handle email delivery status', async () => {
      mockApi.get.mockResolvedValue({
        status: 'delivered',
        deliveredAt: '2024-01-15T11:05:00Z'
      });

      const status = await notificationService.getEmailDeliveryStatus('email_123');

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/email/email_123/status');
      expect(status.status).toBe('delivered');
    });

    it('should handle email bounces and complaints', async () => {
      const bounceHandler = vi.fn();
      
      notificationService.onEmailBounce(bounceHandler);

      // Simulate bounce webhook
      const bounceEvent = {
        messageId: 'email_123',
        bounceType: 'Permanent',
        bounceSubType: 'General'
      };

      // Would be called by webhook handler
      bounceHandler(bounceEvent);
      expect(bounceHandler).toHaveBeenCalledWith(bounceEvent);
    });

    it('should support email templates', async () => {
      mockApi.get.mockResolvedValue({
        templates: [
          { id: 'trade_executed', name: 'Trade Executed', subject: 'Your trade has been executed' },
          { id: 'price_alert', name: 'Price Alert', subject: 'Price alert triggered' }
        ]
      });

      const templates = await notificationService.getEmailTemplates();

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/email/templates');
      expect(templates.templates).toHaveLength(2);
    });
  });

  describe('SMS Notifications', () => {
    it('should send SMS notification', async () => {
      mockApi.post.mockResolvedValue({ 
        success: true, 
        messageId: 'sms_123' 
      });

      const result = await notificationService.sendSMSNotification({
        userId: 'user_456',
        phoneNumber: '+1234567890',
        message: 'Your AAPL trade has been executed'
      });

      expect(mockApi.post).toHaveBeenCalledWith('/notifications/sms', {
        userId: 'user_456',
        phoneNumber: '+1234567890',
        message: 'Your AAPL trade has been executed'
      });
      expect(result.messageId).toBe('sms_123');
    });

    it('should validate phone numbers', async () => {
      await expect(notificationService.sendSMSNotification({
        userId: 'user_456',
        phoneNumber: 'invalid',
        message: 'Test'
      })).rejects.toThrow('Invalid phone number format');
    });

    it('should handle SMS delivery status', async () => {
      mockApi.get.mockResolvedValue({
        status: 'delivered',
        deliveredAt: '2024-01-15T11:02:00Z'
      });

      const status = await notificationService.getSMSDeliveryStatus('sms_123');

      expect(status.status).toBe('delivered');
    });

    it('should respect SMS rate limits', async () => {
      const rateLimitedResponse = {
        error: 'Rate limit exceeded',
        retryAfter: 60
      };

      mockApi.post.mockRejectedValue(new Error(JSON.stringify(rateLimitedResponse)));

      await expect(notificationService.sendSMSNotification({
        userId: 'user_456',
        phoneNumber: '+1234567890',
        message: 'Test'
      })).rejects.toThrow('Rate limit exceeded');
    });
  });

  describe('Analytics and Tracking', () => {
    it('should track notification delivery', async () => {
      mockApi.post.mockResolvedValue({ success: true });

      await notificationService.trackDelivery('notif_123', 'push', 'delivered');

      expect(mockApi.post).toHaveBeenCalledWith('/notifications/analytics/delivery', {
        notificationId: 'notif_123',
        channel: 'push',
        status: 'delivered',
        timestamp: expect.any(String)
      });
    });

    it('should track notification engagement', async () => {
      mockApi.post.mockResolvedValue({ success: true });

      await notificationService.trackEngagement('notif_123', 'click', {
        device: 'mobile',
        browser: 'chrome'
      });

      expect(mockApi.post).toHaveBeenCalledWith('/notifications/analytics/engagement', {
        notificationId: 'notif_123',
        action: 'click',
        metadata: {
          device: 'mobile',
          browser: 'chrome'
        },
        timestamp: expect.any(String)
      });
    });

    it('should get notification analytics', async () => {
      mockApi.get.mockResolvedValue({
        totalSent: 1000,
        deliveryRate: 0.95,
        openRate: 0.78,
        clickRate: 0.23,
        channelBreakdown: {
          email: { sent: 400, delivered: 380, opened: 290 },
          push: { sent: 400, delivered: 385, clicked: 95 },
          sms: { sent: 200, delivered: 195 }
        }
      });

      const analytics = await notificationService.getAnalytics('user_456', {
        startDate: '2024-01-01',
        endDate: '2024-01-31'
      });

      expect(mockApi.get).toHaveBeenCalledWith('/notifications/analytics/user_456', {
        params: {
          startDate: '2024-01-01',
          endDate: '2024-01-31'
        }
      });

      expect(analytics.deliveryRate).toBe(0.95);
      expect(analytics.channelBreakdown.email.sent).toBe(400);
    });

    it('should generate notification reports', async () => {
      mockApi.post.mockResolvedValue({
        reportId: 'report_123',
        downloadUrl: 'https://reports.example.com/notification_report_123.pdf'
      });

      const report = await notificationService.generateReport({
        type: 'engagement',
        period: '30d',
        format: 'pdf'
      });

      expect(mockApi.post).toHaveBeenCalledWith('/notifications/reports', {
        type: 'engagement',
        period: '30d',
        format: 'pdf'
      });

      expect(report.reportId).toBe('report_123');
      expect(report.downloadUrl).toBeTruthy();
    });
  });

  describe('Error Handling', () => {
    it('should handle API errors gracefully', async () => {
      mockApi.get.mockRejectedValue(new Error('API Error'));

      await expect(notificationService.getUserNotifications('user_456'))
        .rejects.toThrow('Failed to fetch notifications');
    });

    it('should handle network connectivity issues', async () => {
      mockApi.post.mockRejectedValue(new Error('Network Error'));

      // Should queue notification for retry
      await notificationService.createNotification({
        type: 'info',
        title: 'Test',
        message: 'Network error test',
        userId: 'user_456'
      });

      expect(mockStorage.set).toHaveBeenCalledWith('notification_queue', expect.any(Array));
    });

    it('should handle invalid notification IDs', async () => {
      mockApi.get.mockResolvedValue({ error: 'Notification not found' });

      await expect(notificationService.getNotification('invalid_id'))
        .rejects.toThrow('Notification not found');
    });

    it('should handle permission denied errors', async () => {
      mockPushService.requestPermission.mockResolvedValue('denied');

      const permission = await notificationService.requestPushPermission();
      expect(permission).toBe('denied');

      // Should not attempt to subscribe
      await expect(notificationService.subscribeToPush('user_456'))
        .rejects.toThrow('Push notifications not permitted');
    });

    it('should handle quota exceeded errors', async () => {
      mockStorage.set.mockImplementation(() => {
        throw new Error('QuotaExceededError');
      });

      // Should handle storage quota gracefully
      await notificationService.cacheNotifications('user_456', [mockNotification]);

      // Should not throw but log warning
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('Performance Optimization', () => {
    it('should debounce rapid notification updates', async () => {
      const notifications = ['notif_1', 'notif_2', 'notif_3'];
      
      // Rapid succession of mark as read calls
      const promises = notifications.map(id => 
        notificationService.markAsRead(id)
      );

      await Promise.all(promises);

      // Should batch the requests
      expect(mockApi.put).toHaveBeenCalledTimes(1);
      expect(mockApi.put).toHaveBeenCalledWith('/notifications/mark-read', {
        notificationIds: notifications
      });
    });

    it('should efficiently handle large notification lists', async () => {
      const largeNotificationList = Array.from({ length: 1000 }, (_, i) => ({
        ...mockNotification,
        id: `notif_${i}`
      }));

      mockApi.get.mockResolvedValue({
        notifications: largeNotificationList,
        total: 1000
      });

      const startTime = performance.now();
      await notificationService.getUserNotifications('user_456', {
        limit: 1000
      });
      const duration = performance.now() - startTime;

      expect(duration).toBeLessThan(100); // Should process within 100ms
    });

    it('should implement smart caching strategies', async () => {
      mockStorage.get.mockReturnValue(null);
      mockApi.get.mockResolvedValue({
        notifications: [mockNotification]
      });

      // First call - should hit API and cache
      await notificationService.getUserNotifications('user_456', { useCache: true });
      expect(mockApi.get).toHaveBeenCalledTimes(1);
      expect(mockStorage.set).toHaveBeenCalled();

      // Second call within cache TTL - should use cache
      mockStorage.get.mockReturnValue({
        data: [mockNotification],
        timestamp: Date.now()
      });

      await notificationService.getUserNotifications('user_456', { useCache: true });
      expect(mockApi.get).toHaveBeenCalledTimes(1); // Still only once
    });

    it('should optimize real-time notification rendering', async () => {
      const callback = vi.fn();
      let notificationHandler;

      mockWebSocket.on.mockImplementation((event, handler) => {
        if (event === 'notification') {
          notificationHandler = handler;
        }
      });

      await notificationService.subscribeToRealTime('user_456', callback);

      // Simulate burst of notifications
      const notifications = Array.from({ length: 50 }, (_, i) => ({
        ...mockNotification,
        id: `notif_${i}`
      }));

      notifications.forEach(notification => {
        notificationHandler(notification);
      });

      // Should throttle callback invocations
      expect(callback).toHaveBeenCalledTimes(1);
      expect(callback).toHaveBeenCalledWith(notifications);
    });
  });
});