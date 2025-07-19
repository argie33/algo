/**
 * Real Notification Service Unit Tests
 * Testing the actual notificationService.js with browser notifications, price alerts, and sound management
 * CRITICAL COMPONENT - Handles user notifications, price alerts, and system alerts
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock browser APIs
const mockNotification = vi.fn();
mockNotification.permission = 'default';
mockNotification.requestPermission = vi.fn();

const mockAudioContext = vi.fn(() => ({
  createOscillator: vi.fn(() => ({
    connect: vi.fn(),
    frequency: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn()
    },
    type: 'sine',
    start: vi.fn(),
    stop: vi.fn()
  })),
  createGain: vi.fn(() => ({
    connect: vi.fn(),
    gain: {
      setValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
      value: 0.5
    }
  })),
  destination: {},
  currentTime: 0,
  close: vi.fn()
}));

const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
};

// Mock global objects
Object.defineProperty(global, 'window', {
  value: {
    Notification: mockNotification,
    AudioContext: mockAudioContext,
    webkitAudioContext: mockAudioContext
  },
  writable: true
});

Object.defineProperty(global, 'Notification', {
  value: mockNotification,
  writable: true
});

Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
  writable: true
});

// Import the REAL NotificationService after mocking
let notificationService;

describe('🔔 Real Notification Service', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Reset notification permission
    mockNotification.permission = 'default';
    mockNotification.requestPermission.mockResolvedValue('granted');
    
    // Mock localStorage globally before importing the service
    mockLocalStorage.getItem.mockReturnValue(null);
    Object.defineProperty(global, 'localStorage', {
      value: mockLocalStorage,
      writable: true,
      configurable: true
    });
    
    // Mock console methods
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Dynamically import to get fresh instance
    vi.resetModules();
    const notificationServiceModule = await import('../../../services/notificationService');
    notificationService = notificationServiceModule.default;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (notificationService) {
      notificationService.destroy();
    }
  });

  describe('Service Initialization', () => {
    it('should initialize with default settings', () => {
      expect(notificationService.settings).toEqual(expect.objectContaining({
        enableBrowserNotifications: true,
        enableSoundAlerts: true,
        enableToastMessages: true,
        soundVolume: 0.5,
        priceAlertCooldown: 60000,
        maxToastMessages: 5
      }));
    });

    it('should initialize with empty collections', () => {
      expect(notificationService.alerts.size).toBe(0);
      expect(notificationService.toastQueue).toEqual([]);
      expect(notificationService.alertHistory).toEqual([]);
    });

    it('should set up audio context', () => {
      expect(mockAudioContext).toHaveBeenCalled();
      expect(notificationService.audioContext).toBeDefined();
    });

    it('should request notification permission on initialization', () => {
      expect(mockNotification.requestPermission).toHaveBeenCalled();
    });
  });

  describe('Settings Management', () => {
    it('should load settings from localStorage', () => {
      const savedSettings = {
        enableBrowserNotifications: false,
        soundVolume: 0.8
      };
      
      mockLocalStorage.getItem.mockReturnValue(JSON.stringify(savedSettings));
      
      // Re-initialize to test loading
      vi.resetModules();
      import('../../../services/notificationService').then(module => {
        const service = module.default;
        expect(service.settings.enableBrowserNotifications).toBe(false);
        expect(service.settings.soundVolume).toBe(0.8);
      });
    });

    it('should handle malformed localStorage settings gracefully', () => {
      mockLocalStorage.getItem.mockReturnValue('invalid json');
      
      // Should not throw and use defaults
      expect(() => {
        notificationService.loadSettings();
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalledWith(
        'Failed to load notification settings:',
        expect.any(Error)
      );
    });

    it('should save settings to localStorage', () => {
      notificationService.saveSettings();
      
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
        'notification_settings',
        JSON.stringify(notificationService.settings)
      );
    });

    it('should handle localStorage save failures gracefully', () => {
      mockLocalStorage.setItem.mockImplementation(() => {
        throw new Error('Storage quota exceeded');
      });
      
      expect(() => {
        notificationService.saveSettings();
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalledWith(
        'Failed to save notification settings:',
        expect.any(Error)
      );
    });

    it('should update settings and save them', () => {
      const newSettings = {
        enableBrowserNotifications: false,
        soundVolume: 0.8
      };
      
      notificationService.updateSettings(newSettings);
      
      expect(notificationService.settings.enableBrowserNotifications).toBe(false);
      expect(notificationService.settings.soundVolume).toBe(0.8);
      expect(mockLocalStorage.setItem).toHaveBeenCalled();
    });

    it('should update audio volume when settings change', () => {
      notificationService.updateSettings({ soundVolume: 0.9 });
      
      expect(notificationService.gainNode.gain.value).toBe(0.9);
    });

    it('should get settings copy', () => {
      const settings = notificationService.getSettings();
      
      expect(settings).toEqual(notificationService.settings);
      expect(settings).not.toBe(notificationService.settings); // Should be a copy
    });
  });

  describe('Permission Management', () => {
    it('should handle granted permission', async () => {
      mockNotification.permission = 'granted';
      
      const permission = await notificationService.requestPermission();
      
      expect(permission).toBe('granted');
      expect(notificationService.permission).toBe('granted');
    });

    it('should request permission when default', async () => {
      mockNotification.permission = 'default';
      mockNotification.requestPermission.mockResolvedValue('granted');
      
      const permission = await notificationService.requestPermission();
      
      expect(mockNotification.requestPermission).toHaveBeenCalled();
      expect(permission).toBe('granted');
    });

    it('should handle denied permission', async () => {
      mockNotification.permission = 'denied';
      
      const permission = await notificationService.requestPermission();
      
      expect(permission).toBe('denied');
      expect(notificationService.permission).toBe('denied');
    });

    it('should handle unsupported browser', async () => {
      delete window.Notification;
      
      const permission = await notificationService.requestPermission();
      
      expect(permission).toBe('denied');
      expect(console.warn).toHaveBeenCalledWith('Browser does not support notifications');
    });
  });

  describe('Sound Alerts', () => {
    it('should play alert sound with correct frequency', () => {
      const mockOscillator = {
        connect: vi.fn(),
        frequency: {
          setValueAtTime: vi.fn(),
          exponentialRampToValueAtTime: vi.fn()
        },
        type: 'sine',
        start: vi.fn(),
        stop: vi.fn()
      };
      
      notificationService.audioContext.createOscillator.mockReturnValue(mockOscillator);
      
      notificationService.playSound('price_alert');
      
      expect(mockOscillator.frequency.setValueAtTime).toHaveBeenCalledWith(800, 0);
      expect(mockOscillator.start).toHaveBeenCalled();
      expect(mockOscillator.stop).toHaveBeenCalled();
    });

    it('should play different tones for different alert types', () => {
      const mockOscillator = {
        connect: vi.fn(),
        frequency: {
          setValueAtTime: vi.fn(),
          exponentialRampToValueAtTime: vi.fn()
        },
        type: 'sine',
        start: vi.fn(),
        stop: vi.fn()
      };
      
      notificationService.audioContext.createOscillator.mockReturnValue(mockOscillator);
      
      // Test error sound
      notificationService.playSound('error');
      expect(mockOscillator.frequency.setValueAtTime).toHaveBeenCalledWith(400, 0);
      
      // Test success sound
      notificationService.playSound('success');
      expect(mockOscillator.frequency.setValueAtTime).toHaveBeenCalledWith(600, 0);
      
      // Test default sound
      notificationService.playSound('default');
      expect(mockOscillator.frequency.setValueAtTime).toHaveBeenCalledWith(440, 0);
    });

    it('should not play sound when disabled', () => {
      notificationService.updateSettings({ enableSoundAlerts: false });
      
      notificationService.playSound('alert');
      
      expect(notificationService.audioContext.createOscillator).not.toHaveBeenCalled();
    });

    it('should handle audio context errors gracefully', () => {
      notificationService.audioContext.createOscillator.mockImplementation(() => {
        throw new Error('Audio context error');
      });
      
      expect(() => {
        notificationService.playSound('alert');
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalledWith(
        'Failed to play sound:',
        expect.any(Error)
      );
    });

    it('should not play sound when no audio context', () => {
      notificationService.audioContext = null;
      
      notificationService.playSound('alert');
      
      // Should not throw error
      expect(console.warn).not.toHaveBeenCalled();
    });
  });

  describe('Browser Notifications', () => {
    beforeEach(() => {
      notificationService.permission = 'granted';
      notificationService.updateSettings({ enableBrowserNotifications: true });
    });

    it('should show browser notification with default options', () => {
      const mockNotificationInstance = {
        close: vi.fn()
      };
      mockNotification.mockReturnValue(mockNotificationInstance);
      
      const result = notificationService.showBrowserNotification('Test Title', {
        body: 'Test message'
      });
      
      expect(mockNotification).toHaveBeenCalledWith('Test Title', expect.objectContaining({
        body: 'Test message',
        icon: '/favicon.ico',
        tag: 'default'
      }));
      
      expect(result).toBe(mockNotificationInstance);
    });

    it('should auto-close notification after 5 seconds', () => {
      vi.useFakeTimers();
      
      const mockNotificationInstance = {
        close: vi.fn()
      };
      mockNotification.mockReturnValue(mockNotificationInstance);
      
      notificationService.showBrowserNotification('Test', {});
      
      vi.advanceTimersByTime(5000);
      
      expect(mockNotificationInstance.close).toHaveBeenCalled();
      
      vi.useRealTimers();
    });

    it('should not auto-close when requireInteraction is true', () => {
      vi.useFakeTimers();
      
      const mockNotificationInstance = {
        close: vi.fn()
      };
      mockNotification.mockReturnValue(mockNotificationInstance);
      
      notificationService.showBrowserNotification('Test', {
        requireInteraction: true
      });
      
      vi.advanceTimersByTime(5000);
      
      expect(mockNotificationInstance.close).not.toHaveBeenCalled();
      
      vi.useRealTimers();
    });

    it('should return null when notifications disabled', () => {
      notificationService.updateSettings({ enableBrowserNotifications: false });
      
      const result = notificationService.showBrowserNotification('Test');
      
      expect(result).toBeNull();
      expect(mockNotification).not.toHaveBeenCalled();
    });

    it('should return null when permission denied', () => {
      notificationService.permission = 'denied';
      
      const result = notificationService.showBrowserNotification('Test');
      
      expect(result).toBeNull();
      expect(mockNotification).not.toHaveBeenCalled();
    });

    it('should handle notification creation errors', () => {
      mockNotification.mockImplementation(() => {
        throw new Error('Notification error');
      });
      
      const result = notificationService.showBrowserNotification('Test');
      
      expect(result).toBeNull();
      expect(console.warn).toHaveBeenCalledWith(
        'Failed to show browser notification:',
        expect.any(Error)
      );
    });
  });

  describe('Toast Messages', () => {
    it('should show toast message', () => {
      const callback = vi.fn();
      notificationService.on('toast', callback);
      
      const toastId = notificationService.showToast('Test message', 'info', 3000);
      
      expect(toastId).toBeDefined();
      expect(notificationService.toastQueue).toHaveLength(1);
      expect(notificationService.toastQueue[0]).toEqual(expect.objectContaining({
        message: 'Test message',
        type: 'info',
        duration: 3000
      }));
      
      expect(callback).toHaveBeenCalledWith(expect.objectContaining({
        message: 'Test message',
        type: 'info'
      }));
    });

    it('should auto-remove toast after duration', () => {
      vi.useFakeTimers();
      
      const toastId = notificationService.showToast('Test', 'info', 1000);
      
      expect(notificationService.toastQueue).toHaveLength(1);
      
      vi.advanceTimersByTime(1000);
      
      expect(notificationService.toastQueue).toHaveLength(0);
      
      vi.useRealTimers();
    });

    it('should limit toast queue size', () => {
      notificationService.updateSettings({ maxToastMessages: 3 });
      
      // Add 5 toasts
      for (let i = 0; i < 5; i++) {
        notificationService.showToast(`Message ${i}`);
      }
      
      expect(notificationService.toastQueue).toHaveLength(3);
      expect(notificationService.toastQueue[0].message).toBe('Message 2'); // First two removed
    });

    it('should not show toast when disabled', () => {
      notificationService.updateSettings({ enableToastMessages: false });
      
      notificationService.showToast('Test message');
      
      expect(notificationService.toastQueue).toHaveLength(0);
    });

    it('should remove specific toast', () => {
      const callback = vi.fn();
      notificationService.on('toastRemoved', callback);
      
      const toastId = notificationService.showToast('Test message');
      expect(notificationService.toastQueue).toHaveLength(1);
      
      notificationService.removeToast(toastId);
      
      expect(notificationService.toastQueue).toHaveLength(0);
      expect(callback).toHaveBeenCalledWith(toastId);
    });

    it('should handle remove non-existent toast gracefully', () => {
      notificationService.removeToast('non-existent-id');
      
      // Should not throw error
      expect(notificationService.toastQueue).toHaveLength(0);
    });
  });

  describe('Price Alerts', () => {
    it('should create price alert', () => {
      const callback = vi.fn();
      notificationService.on('alertCreated', callback);
      
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      
      expect(alertId).toBeDefined();
      expect(notificationService.alerts.has(alertId)).toBe(true);
      
      const alert = notificationService.alerts.get(alertId);
      expect(alert).toEqual(expect.objectContaining({
        symbol: 'AAPL',
        price: 150,
        type: 'above',
        enabled: true,
        triggered: false
      }));
      
      expect(callback).toHaveBeenCalledWith(alert);
    });

    it('should trigger price alert when condition met', () => {
      const alertCallback = vi.fn();
      const toastCallback = vi.fn();
      
      notificationService.on('alertTriggered', alertCallback);
      notificationService.on('toast', toastCallback);
      
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      
      // Mock notification for alert
      const mockNotificationInstance = { close: vi.fn() };
      mockNotification.mockReturnValue(mockNotificationInstance);
      notificationService.permission = 'granted';
      
      notificationService.checkPriceAlerts('AAPL', 155);
      
      const alert = notificationService.alerts.get(alertId);
      expect(alert.triggered).toBe(true);
      expect(alert.triggeredAt).toBeDefined();
      
      expect(alertCallback).toHaveBeenCalledWith({
        alert,
        currentPrice: 155
      });
      
      expect(mockNotification).toHaveBeenCalledWith(
        'Price Alert: AAPL',
        expect.objectContaining({
          body: expect.stringContaining('AAPL is above $150.00'),
          requireInteraction: true
        })
      );
      
      expect(notificationService.alertHistory).toHaveLength(1);
    });

    it('should trigger below price alert', () => {
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'below');
      
      notificationService.checkPriceAlerts('AAPL', 145);
      
      const alert = notificationService.alerts.get(alertId);
      expect(alert.triggered).toBe(true);
    });

    it('should not trigger alert when condition not met', () => {
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      
      notificationService.checkPriceAlerts('AAPL', 145);
      
      const alert = notificationService.alerts.get(alertId);
      expect(alert.triggered).toBe(false);
    });

    it('should respect cooldown period', () => {
      vi.useFakeTimers();
      
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      
      // Trigger first time
      notificationService.checkPriceAlerts('AAPL', 155);
      expect(notificationService.alertHistory).toHaveLength(1);
      
      // Reset triggered state but keep cooldown
      const alert = notificationService.alerts.get(alertId);
      alert.triggered = false;
      
      // Should not trigger again due to cooldown
      notificationService.checkPriceAlerts('AAPL', 160);
      expect(notificationService.alertHistory).toHaveLength(1);
      
      // Advance past cooldown period
      vi.advanceTimersByTime(61000);
      
      // Should trigger again
      notificationService.checkPriceAlerts('AAPL', 165);
      expect(notificationService.alertHistory).toHaveLength(2);
      
      vi.useRealTimers();
    });

    it('should not check disabled alerts', () => {
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      notificationService.toggleAlert(alertId); // Disable
      
      notificationService.checkPriceAlerts('AAPL', 155);
      
      const alert = notificationService.alerts.get(alertId);
      expect(alert.triggered).toBe(false);
    });

    it('should get active alerts', () => {
      notificationService.createPriceAlert('AAPL', 150, 'above');
      notificationService.createPriceAlert('MSFT', 300, 'below');
      const disabledId = notificationService.createPriceAlert('GOOGL', 2500, 'above');
      notificationService.toggleAlert(disabledId);
      
      const allActive = notificationService.getActiveAlerts();
      const aaplActive = notificationService.getActiveAlerts('AAPL');
      
      expect(allActive).toHaveLength(2);
      expect(aaplActive).toHaveLength(1);
      expect(aaplActive[0].symbol).toBe('AAPL');
    });

    it('should delete alert', () => {
      const callback = vi.fn();
      notificationService.on('alertDeleted', callback);
      
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      
      const deleted = notificationService.deleteAlert(alertId);
      
      expect(deleted).toBe(true);
      expect(notificationService.alerts.has(alertId)).toBe(false);
      expect(callback).toHaveBeenCalledWith(alertId);
    });

    it('should toggle alert enabled state', () => {
      const callback = vi.fn();
      notificationService.on('alertToggled', callback);
      
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      
      const enabled = notificationService.toggleAlert(alertId);
      
      expect(enabled).toBe(false);
      expect(notificationService.alerts.get(alertId).enabled).toBe(false);
      expect(callback).toHaveBeenCalledWith(notificationService.alerts.get(alertId));
    });

    it('should reset triggered alerts', () => {
      const callback = vi.fn();
      notificationService.on('alertsReset', callback);
      
      const alertId1 = notificationService.createPriceAlert('AAPL', 150, 'above');
      const alertId2 = notificationService.createPriceAlert('MSFT', 300, 'above');
      
      // Trigger both alerts
      notificationService.checkPriceAlerts('AAPL', 155);
      notificationService.checkPriceAlerts('MSFT', 305);
      
      const resetCount = notificationService.resetTriggeredAlerts();
      
      expect(resetCount).toBe(2);
      expect(notificationService.alerts.get(alertId1).triggered).toBe(false);
      expect(notificationService.alerts.get(alertId2).triggered).toBe(false);
      expect(callback).toHaveBeenCalledWith({ symbol: null, count: 2 });
    });

    it('should reset triggered alerts for specific symbol', () => {
      const alertId1 = notificationService.createPriceAlert('AAPL', 150, 'above');
      const alertId2 = notificationService.createPriceAlert('MSFT', 300, 'above');
      
      // Trigger both alerts
      notificationService.checkPriceAlerts('AAPL', 155);
      notificationService.checkPriceAlerts('MSFT', 305);
      
      const resetCount = notificationService.resetTriggeredAlerts('AAPL');
      
      expect(resetCount).toBe(1);
      expect(notificationService.alerts.get(alertId1).triggered).toBe(false);
      expect(notificationService.alerts.get(alertId2).triggered).toBe(true);
    });
  });

  describe('Alert History', () => {
    it('should maintain alert history', () => {
      notificationService.createPriceAlert('AAPL', 150, 'above');
      notificationService.checkPriceAlerts('AAPL', 155);
      
      const history = notificationService.getAlertHistory();
      
      expect(history).toHaveLength(1);
      expect(history[0]).toEqual(expect.objectContaining({
        type: 'price_alert',
        symbol: 'AAPL',
        price: 155,
        targetPrice: 150,
        direction: 'above'
      }));
    });

    it('should limit history size', () => {
      notificationService.maxHistorySize = 3;
      
      // Create and trigger 5 alerts
      for (let i = 0; i < 5; i++) {
        notificationService.createPriceAlert('AAPL', 100 + i, 'above');
        notificationService.checkPriceAlerts('AAPL', 110 + i);
      }
      
      expect(notificationService.alertHistory).toHaveLength(3);
    });

    it('should get limited history', () => {
      // Create history entries
      for (let i = 0; i < 10; i++) {
        notificationService.alertHistory.push({
          type: 'price_alert',
          symbol: 'AAPL',
          timestamp: Date.now() - i * 1000
        });
      }
      
      const history = notificationService.getAlertHistory(5);
      
      expect(history).toHaveLength(5);
    });

    it('should clear alert history', () => {
      const callback = vi.fn();
      notificationService.on('historyCleared', callback);
      
      notificationService.alertHistory = [{ test: 'data' }];
      
      notificationService.clearAlertHistory();
      
      expect(notificationService.alertHistory).toHaveLength(0);
      expect(callback).toHaveBeenCalled();
    });
  });

  describe('System Notifications', () => {
    it('should notify connection status', () => {
      const toastCallback = vi.fn();
      notificationService.on('toast', toastCallback);
      
      notificationService.notifyConnection('connected');
      
      expect(toastCallback).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Connected to real-time data feed',
          type: 'success'
        })
      );
    });

    it('should notify disconnection', () => {
      const toastCallback = vi.fn();
      notificationService.on('toast', toastCallback);
      
      notificationService.notifyConnection('disconnected');
      
      expect(toastCallback).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Disconnected from data feed',
          type: 'warning'
        })
      );
    });

    it('should notify errors', () => {
      const toastCallback = vi.fn();
      notificationService.on('toast', toastCallback);
      
      notificationService.notifyError('Test error message');
      
      expect(toastCallback).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Test error message',
          type: 'error'
        })
      );
    });

    it('should notify success', () => {
      const toastCallback = vi.fn();
      notificationService.on('toast', toastCallback);
      
      notificationService.notifySuccess('Operation successful');
      
      expect(toastCallback).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Operation successful',
          type: 'success'
        })
      );
    });
  });

  describe('Statistics and Monitoring', () => {
    it('should provide comprehensive stats', () => {
      notificationService.createPriceAlert('AAPL', 150, 'above');
      notificationService.createPriceAlert('MSFT', 300, 'below');
      notificationService.showToast('Test message');
      
      // Trigger one alert
      notificationService.checkPriceAlerts('AAPL', 155);
      
      const stats = notificationService.getStats();
      
      expect(stats).toEqual({
        totalAlerts: 2,
        activeAlerts: 2,
        triggeredAlerts: 1,
        historySize: 1,
        permission: expect.any(String),
        browserSupport: true,
        audioSupport: true,
        toastQueueSize: 1
      });
    });
  });

  describe('Event System', () => {
    it('should add and call event listeners', () => {
      const callback = vi.fn();
      
      notificationService.on('test', callback);
      notificationService.emit('test', { data: 'test' });
      
      expect(callback).toHaveBeenCalledWith({ data: 'test' });
    });

    it('should remove event listeners', () => {
      const callback = vi.fn();
      
      notificationService.on('test', callback);
      notificationService.off('test', callback);
      notificationService.emit('test', { data: 'test' });
      
      expect(callback).not.toHaveBeenCalled();
    });

    it('should handle multiple listeners for same event', () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();
      
      notificationService.on('test', callback1);
      notificationService.on('test', callback2);
      notificationService.emit('test', { data: 'test' });
      
      expect(callback1).toHaveBeenCalled();
      expect(callback2).toHaveBeenCalled();
    });

    it('should handle callback errors gracefully', () => {
      const errorCallback = vi.fn(() => {
        throw new Error('Callback error');
      });
      const normalCallback = vi.fn();
      
      notificationService.on('test', errorCallback);
      notificationService.on('test', normalCallback);
      
      expect(() => {
        notificationService.emit('test', {});
      }).not.toThrow();
      
      expect(normalCallback).toHaveBeenCalled();
      expect(console.error).toHaveBeenCalledWith(
        'Error in notification callback:',
        expect.any(Error)
      );
    });
  });

  describe('Cleanup and Destruction', () => {
    it('should cleanup resources on destroy', () => {
      notificationService.createPriceAlert('AAPL', 150, 'above');
      notificationService.showToast('Test message');
      notificationService.on('test', () => {});
      
      notificationService.destroy();
      
      expect(notificationService.alerts.size).toBe(0);
      expect(notificationService.listeners.size).toBe(0);
      expect(notificationService.toastQueue).toHaveLength(0);
      expect(notificationService.alertHistory).toHaveLength(0);
      expect(notificationService.audioContext.close).toHaveBeenCalled();
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle audio initialization failures', () => {
      // Mock AudioContext to throw error
      const originalAudioContext = window.AudioContext;
      window.AudioContext = vi.fn(() => {
        throw new Error('Audio not supported');
      });
      
      expect(() => {
        notificationService.initializeAudio();
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalledWith(
        'Audio context not supported:',
        expect.any(Error)
      );
      
      // Restore
      window.AudioContext = originalAudioContext;
    });

    it('should handle concurrent alert checks safely', () => {
      const alertId = notificationService.createPriceAlert('AAPL', 150, 'above');
      
      // Simulate concurrent checks
      const promises = Array.from({ length: 10 }, () => 
        Promise.resolve(notificationService.checkPriceAlerts('AAPL', 155))
      );
      
      return Promise.all(promises).then(() => {
        const alert = notificationService.alerts.get(alertId);
        expect(alert.triggered).toBe(true);
        // Should only trigger once despite concurrent checks
        expect(notificationService.alertHistory).toHaveLength(1);
      });
    });

    it('should handle invalid alert operations gracefully', () => {
      expect(notificationService.deleteAlert('non-existent')).toBe(false);
      expect(notificationService.toggleAlert('non-existent')).toBe(false);
    });

    it('should handle large numbers of alerts efficiently', () => {
      // Create 1000 alerts
      for (let i = 0; i < 1000; i++) {
        notificationService.createPriceAlert(`STOCK${i}`, 100 + i, 'above');
      }
      
      const startTime = performance.now();
      const activeAlerts = notificationService.getActiveAlerts();
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(100); // Should complete within 100ms
      expect(activeAlerts).toHaveLength(1000);
    });
  });
});