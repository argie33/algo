// Notification Service for Price Alerts and System Notifications
// Handles browser notifications, toast messages, and alert management

class NotificationService {
  constructor() {
    this.permission = 'default';
    this.alerts = new Map();
    this.listeners = new Map();
    this.settings = {
      enableBrowserNotifications: true,
      enableSoundAlerts: true,
      enableToastMessages: true,
      soundVolume: 0.5,
      priceAlertCooldown: 60000, // 1 minute cooldown between same alerts
      maxToastMessages: 5
    };
    
    this.toastQueue = [];
    this.alertHistory = [];
    this.maxHistorySize = 100;
    
    // Load settings from localStorage
    this.loadSettings();
    
    // Request notification permission
    this.requestPermission();
    
    // Initialize audio context for sound alerts
    this.initializeAudio();
  }

  // Load settings from localStorage
  loadSettings() {
    try {
      const saved = localStorage.getItem('notification_settings');
      if (saved) {
        this.settings = { ...this.settings, ...JSON.parse(saved) };
      }
    } catch (e) {
      console.warn('Failed to load notification settings:', e);
    }
  }

  // Save settings to localStorage
  saveSettings() {
    try {
      localStorage.setItem('notification_settings', JSON.stringify(this.settings));
    } catch (e) {
      console.warn('Failed to save notification settings:', e);
    }
  }

  // Request browser notification permission
  async requestPermission() {
    if (!('Notification' in window)) {
      console.warn('Browser does not support notifications');
      return 'denied';
    }

    if (Notification.permission === 'granted') {
      this.permission = 'granted';
      return 'granted';
    }

    if (Notification.permission !== 'denied') {
      const permission = await Notification.requestPermission();
      this.permission = permission;
      return permission;
    }

    this.permission = 'denied';
    return 'denied';
  }

  // Initialize audio for sound alerts
  initializeAudio() {
    try {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      this.gainNode = this.audioContext.createGain();
      this.gainNode.connect(this.audioContext.destination);
      this.gainNode.gain.value = this.settings.soundVolume;
    } catch (e) {
      console.warn('Audio context not supported:', e);
    }
  }

  // Play sound alert
  playSound(type = 'alert') {
    if (!this.settings.enableSoundAlerts || !this.audioContext) return;

    try {
      const oscillator = this.audioContext.createOscillator();
      const gainNode = this.audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(this.audioContext.destination);
      
      // Different tones for different alert types
      switch (type) {
        case 'price_alert':
          oscillator.frequency.setValueAtTime(800, this.audioContext.currentTime);
          oscillator.frequency.exponentialRampToValueAtTime(600, this.audioContext.currentTime + 0.1);
          break;
        case 'error':
          oscillator.frequency.setValueAtTime(400, this.audioContext.currentTime);
          oscillator.frequency.exponentialRampToValueAtTime(200, this.audioContext.currentTime + 0.2);
          break;
        case 'success':
          oscillator.frequency.setValueAtTime(600, this.audioContext.currentTime);
          oscillator.frequency.exponentialRampToValueAtTime(800, this.audioContext.currentTime + 0.1);
          break;
        default:
          oscillator.frequency.setValueAtTime(440, this.audioContext.currentTime);
      }
      
      oscillator.type = 'sine';
      gainNode.gain.setValueAtTime(0, this.audioContext.currentTime);
      gainNode.gain.linearRampToValueAtTime(this.settings.soundVolume, this.audioContext.currentTime + 0.01);
      gainNode.gain.exponentialRampToValueAtTime(0.001, this.audioContext.currentTime + 0.3);
      
      oscillator.start(this.audioContext.currentTime);
      oscillator.stop(this.audioContext.currentTime + 0.3);
    } catch (e) {
      console.warn('Failed to play sound:', e);
    }
  }

  // Show browser notification
  showBrowserNotification(title, options = {}) {
    if (!this.settings.enableBrowserNotifications || this.permission !== 'granted') {
      return null;
    }

    const defaultOptions = {
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      dir: 'auto',
      lang: 'en-US',
      renotify: false,
      requireInteraction: false,
      silent: false,
      tag: 'default',
      timestamp: Date.now(),
      vibrate: [200, 100, 200]
    };

    const finalOptions = { ...defaultOptions, ...options };

    try {
      const notification = new Notification(title, finalOptions);
      
      // Auto-close after 5 seconds unless requireInteraction is true
      if (!finalOptions.requireInteraction) {
        setTimeout(() => {
          notification.close();
        }, 5000);
      }
      
      return notification;
    } catch (e) {
      console.warn('Failed to show browser notification:', e);
      return null;
    }
  }

  // Show toast message
  showToast(message, type = 'info', duration = 5000) {
    if (!this.settings.enableToastMessages) return;

    const toast = {
      id: Date.now() + Math.random(),
      message,
      type,
      duration,
      timestamp: Date.now()
    };

    this.toastQueue.push(toast);
    
    // Keep only the latest toast messages
    if (this.toastQueue.length > this.settings.maxToastMessages) {
      this.toastQueue.shift();
    }

    // Emit toast event
    this.emit('toast', toast);

    // Auto-remove toast after duration
    setTimeout(() => {
      this.removeToast(toast.id);
    }, duration);

    return toast.id;
  }

  // Remove toast message
  removeToast(id) {
    const index = this.toastQueue.findIndex(toast => toast.id === id);
    if (index > -1) {
      this.toastQueue.splice(index, 1);
      this.emit('toastRemoved', id);
    }
  }

  // Create price alert
  createPriceAlert(symbol, price, type = 'above', options = {}) {
    const alertId = `${symbol}_${type}_${price}_${Date.now()}`;
    
    const alert = {
      id: alertId,
      symbol: symbol.toUpperCase(),
      price: parseFloat(price),
      type, // 'above' or 'below'
      enabled: true,
      triggered: false,
      createdAt: Date.now(),
      triggeredAt: null,
      lastChecked: null,
      cooldownUntil: null,
      ...options
    };

    this.alerts.set(alertId, alert);
    this.emit('alertCreated', alert);
    
    return alertId;
  }

  // Check price alerts
  checkPriceAlerts(symbol, currentPrice) {
    const now = Date.now();
    const symbolAlerts = Array.from(this.alerts.values()).filter(
      alert => alert.symbol === symbol.toUpperCase() && 
               alert.enabled && 
               !alert.triggered &&
               (alert.cooldownUntil === null || now > alert.cooldownUntil)
    );

    symbolAlerts.forEach(alert => {
      let shouldTrigger = false;
      
      if (alert.type === 'above' && currentPrice >= alert.price) {
        shouldTrigger = true;
      } else if (alert.type === 'below' && currentPrice <= alert.price) {
        shouldTrigger = true;
      }

      if (shouldTrigger) {
        this.triggerPriceAlert(alert, currentPrice);
      }
      
      alert.lastChecked = now;
    });
  }

  // Trigger price alert
  triggerPriceAlert(alert, currentPrice) {
    alert.triggered = true;
    alert.triggeredAt = Date.now();
    alert.cooldownUntil = Date.now() + this.settings.priceAlertCooldown;

    const message = `${alert.symbol} is ${alert.type} $${alert.price.toFixed(2)}! Current: $${currentPrice.toFixed(2)}`;
    
    // Show notifications
    this.showBrowserNotification(`Price Alert: ${alert.symbol}`, {
      body: message,
      tag: `price_alert_${alert.symbol}`,
      icon: '/favicon.ico',
      requireInteraction: true
    });
    
    this.showToast(message, 'warning', 10000);
    this.playSound('price_alert');
    
    // Add to history
    this.alertHistory.unshift({
      type: 'price_alert',
      symbol: alert.symbol,
      message,
      price: currentPrice,
      targetPrice: alert.price,
      direction: alert.type,
      timestamp: Date.now()
    });
    
    // Keep history size manageable
    if (this.alertHistory.length > this.maxHistorySize) {
      this.alertHistory.pop();
    }
    
    // Emit alert triggered event
    this.emit('alertTriggered', { alert, currentPrice });
  }

  // Get active alerts
  getActiveAlerts(symbol = null) {
    const alerts = Array.from(this.alerts.values()).filter(alert => alert.enabled);
    
    if (symbol) {
      return alerts.filter(alert => alert.symbol === symbol.toUpperCase());
    }
    
    return alerts;
  }

  // Delete alert
  deleteAlert(alertId) {
    const deleted = this.alerts.delete(alertId);
    if (deleted) {
      this.emit('alertDeleted', alertId);
    }
    return deleted;
  }

  // Toggle alert
  toggleAlert(alertId) {
    const alert = this.alerts.get(alertId);
    if (alert) {
      alert.enabled = !alert.enabled;
      this.emit('alertToggled', alert);
      return alert.enabled;
    }
    return false;
  }

  // Reset triggered alerts
  resetTriggeredAlerts(symbol = null) {
    let resetCount = 0;
    
    this.alerts.forEach(alert => {
      if (alert.triggered && (!symbol || alert.symbol === symbol.toUpperCase())) {
        alert.triggered = false;
        alert.triggeredAt = null;
        alert.cooldownUntil = null;
        resetCount++;
      }
    });
    
    if (resetCount > 0) {
      this.emit('alertsReset', { symbol, count: resetCount });
    }
    
    return resetCount;
  }

  // Update settings
  updateSettings(newSettings) {
    this.settings = { ...this.settings, ...newSettings };
    this.saveSettings();
    
    // Update audio volume
    if (this.gainNode && newSettings.soundVolume !== undefined) {
      this.gainNode.gain.value = newSettings.soundVolume;
    }
    
    this.emit('settingsUpdated', this.settings);
  }

  // Get settings
  getSettings() {
    return { ...this.settings };
  }

  // Get alert history
  getAlertHistory(limit = 50) {
    return this.alertHistory.slice(0, limit);
  }

  // Clear alert history
  clearAlertHistory() {
    this.alertHistory = [];
    this.emit('historyCleared');
  }

  // Get notification statistics
  getStats() {
    const activeAlerts = this.getActiveAlerts();
    const triggeredAlerts = Array.from(this.alerts.values()).filter(a => a.triggered);
    
    return {
      totalAlerts: this.alerts.size,
      activeAlerts: activeAlerts.length,
      triggeredAlerts: triggeredAlerts.length,
      historySize: this.alertHistory.length,
      permission: this.permission,
      browserSupport: 'Notification' in window,
      audioSupport: !!this.audioContext,
      toastQueueSize: this.toastQueue.length
    };
  }

  // Event handling
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  off(event, callback) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(callback => {
        try {
          callback(data);
        } catch (e) {
          console.error('Error in notification callback:', e);
        }
      });
    }
  }

  // System notifications
  notifyConnection(status) {
    if (status === 'connected') {
      this.showToast('Connected to real-time data feed', 'success');
      this.playSound('success');
    } else if (status === 'disconnected') {
      this.showToast('Disconnected from data feed', 'warning');
      this.playSound('error');
    }
  }

  notifyError(message) {
    this.showToast(message, 'error');
    this.playSound('error');
  }

  notifySuccess(message) {
    this.showToast(message, 'success');
    this.playSound('success');
  }

  // Cleanup
  destroy() {
    this.alerts.clear();
    this.listeners.clear();
    this.toastQueue = [];
    this.alertHistory = [];
    
    if (this.audioContext) {
      this.audioContext.close();
    }
  }
}

// Create singleton instance
const notificationService = new NotificationService();

export default notificationService;