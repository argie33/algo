/**
 * Secure Session Storage with Enhanced Security Features
 * Implements secure token storage, cross-tab synchronization, and session persistence
 */

import CryptoJS from 'crypto-js';

// Session configuration with enhanced security
const SECURE_SESSION_CONFIG = {
  // Storage keys
  ACCESS_TOKEN_KEY: 'secure_access_token',
  REFRESH_TOKEN_KEY: 'secure_refresh_token',
  SESSION_META_KEY: 'secure_session_meta',
  DEVICE_FINGERPRINT_KEY: 'device_fingerprint',
  
  // Security settings
  ENCRYPTION_KEY_LENGTH: 32,
  IV_LENGTH: 16,
  TOKEN_STORAGE_TYPE: 'sessionStorage', // Use sessionStorage for access tokens
  REFRESH_TOKEN_STORAGE_TYPE: 'localStorage', // Use localStorage for refresh tokens
  
  // Session thresholds
  SESSION_WARNING_THRESHOLD: 5 * 60 * 1000, // 5 minutes
  AUTO_REFRESH_THRESHOLD: 10 * 60 * 1000,   // 10 minutes
  IDLE_TIMEOUT: 30 * 60 * 1000,             // 30 minutes
  MAX_CONCURRENT_SESSIONS: 3,
  
  // Cross-tab communication
  BROADCAST_CHANNEL: 'secure_session_sync',
  SYNC_EVENTS: {
    LOGIN: 'session_login',
    LOGOUT: 'session_logout',
    REFRESH: 'session_refresh',
    IDLE_WARNING: 'session_idle_warning',
    ACTIVITY: 'session_activity'
  }
};

class SecureSessionStorage {
  constructor() {
    this.encryptionKey = this.generateEncryptionKey();
    this.deviceFingerprint = this.generateDeviceFingerprint();
    this.broadcastChannel = null;
    this.sessionMetadata = null;
    
    this.initializeBroadcastChannel();
    this.initializeDeviceFingerprint();
  }

  /**
   * Generate encryption key for secure storage
   */
  generateEncryptionKey() {
    const stored = sessionStorage.getItem('encryption_key');
    if (stored) {
      return stored;
    }
    
    const key = CryptoJS.lib.WordArray.random(SECURE_SESSION_CONFIG.ENCRYPTION_KEY_LENGTH).toString();
    sessionStorage.setItem('encryption_key', key);
    return key;
  }

  /**
   * Generate device fingerprint for session validation
   */
  generateDeviceFingerprint() {
    const components = [
      navigator.userAgent,
      navigator.language,
      navigator.platform,
      screen.width + 'x' + screen.height,
      new Date().getTimezoneOffset(),
      navigator.cookieEnabled,
      typeof window.localStorage,
      typeof window.sessionStorage
    ];
    
    return CryptoJS.SHA256(components.join('|')).toString();
  }

  /**
   * Initialize device fingerprint storage
   */
  initializeDeviceFingerprint() {
    const stored = localStorage.getItem(SECURE_SESSION_CONFIG.DEVICE_FINGERPRINT_KEY);
    if (!stored || stored !== this.deviceFingerprint) {
      localStorage.setItem(SECURE_SESSION_CONFIG.DEVICE_FINGERPRINT_KEY, this.deviceFingerprint);
    }
  }

  /**
   * Initialize broadcast channel for cross-tab communication
   */
  initializeBroadcastChannel() {
    if (typeof BroadcastChannel !== 'undefined') {
      this.broadcastChannel = new BroadcastChannel(SECURE_SESSION_CONFIG.BROADCAST_CHANNEL);
      this.broadcastChannel.addEventListener('message', this.handleBroadcastMessage.bind(this));
    }
  }

  /**
   * Handle broadcast messages from other tabs
   */
  handleBroadcastMessage(event) {
    const { type, data, timestamp, fingerprint } = event.data;
    
    // Validate message from same device
    if (fingerprint !== this.deviceFingerprint) {
      console.warn('🚨 Received session message from different device fingerprint');
      return;
    }

    switch (type) {
      case SECURE_SESSION_CONFIG.SYNC_EVENTS.LOGIN:
        this.handleCrossTabLogin(data);
        break;
      case SECURE_SESSION_CONFIG.SYNC_EVENTS.LOGOUT:
        this.handleCrossTabLogout(data);
        break;
      case SECURE_SESSION_CONFIG.SYNC_EVENTS.REFRESH:
        this.handleCrossTabRefresh(data);
        break;
      case SECURE_SESSION_CONFIG.SYNC_EVENTS.ACTIVITY:
        this.handleCrossTabActivity(data);
        break;
      default:
        console.log('Unknown broadcast message type:', type);
    }
  }

  /**
   * Broadcast message to other tabs
   */
  broadcastMessage(type, data) {
    if (this.broadcastChannel) {
      this.broadcastChannel.postMessage({
        type,
        data,
        timestamp: Date.now(),
        fingerprint: this.deviceFingerprint
      });
    }
  }

  /**
   * Encrypt data for secure storage
   */
  encrypt(data) {
    const iv = CryptoJS.lib.WordArray.random(SECURE_SESSION_CONFIG.IV_LENGTH);
    const encrypted = CryptoJS.AES.encrypt(JSON.stringify(data), this.encryptionKey, {
      iv: iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7
    });
    
    return {
      ciphertext: encrypted.toString(),
      iv: iv.toString()
    };
  }

  /**
   * Decrypt data from secure storage
   */
  decrypt(encryptedData) {
    try {
      const { ciphertext, iv } = encryptedData;
      const decrypted = CryptoJS.AES.decrypt(ciphertext, this.encryptionKey, {
        iv: CryptoJS.enc.Hex.parse(iv),
        mode: CryptoJS.mode.CBC,
        padding: CryptoJS.pad.Pkcs7
      });
      
      return JSON.parse(decrypted.toString(CryptoJS.enc.Utf8));
    } catch (error) {
      console.error('Failed to decrypt session data:', error);
      return null;
    }
  }

  /**
   * Store tokens securely
   */
  storeTokens(tokens) {
    try {
      // Store access token in sessionStorage (cleared on tab close)
      if (tokens.accessToken) {
        const encryptedAccess = this.encrypt({
          token: tokens.accessToken,
          timestamp: Date.now(),
          fingerprint: this.deviceFingerprint
        });
        sessionStorage.setItem(SECURE_SESSION_CONFIG.ACCESS_TOKEN_KEY, JSON.stringify(encryptedAccess));
      }

      // Store refresh token in localStorage (persists across sessions)
      if (tokens.refreshToken) {
        const encryptedRefresh = this.encrypt({
          token: tokens.refreshToken,
          timestamp: Date.now(),
          fingerprint: this.deviceFingerprint
        });
        localStorage.setItem(SECURE_SESSION_CONFIG.REFRESH_TOKEN_KEY, JSON.stringify(encryptedRefresh));
      }

      // Store session metadata
      const metadata = {
        userId: tokens.userId,
        username: tokens.username,
        email: tokens.email,
        loginTime: Date.now(),
        deviceFingerprint: this.deviceFingerprint,
        sessionId: this.generateSessionId(),
        lastActivity: Date.now()
      };

      const encryptedMetadata = this.encrypt(metadata);
      sessionStorage.setItem(SECURE_SESSION_CONFIG.SESSION_META_KEY, JSON.stringify(encryptedMetadata));

      this.sessionMetadata = metadata;

      // Broadcast login to other tabs
      this.broadcastMessage(SECURE_SESSION_CONFIG.SYNC_EVENTS.LOGIN, {
        sessionId: metadata.sessionId,
        userId: metadata.userId
      });

      return true;
    } catch (error) {
      console.error('Failed to store tokens securely:', error);
      return false;
    }
  }

  /**
   * Retrieve tokens securely
   */
  getTokens() {
    try {
      const accessTokenData = sessionStorage.getItem(SECURE_SESSION_CONFIG.ACCESS_TOKEN_KEY);
      const refreshTokenData = localStorage.getItem(SECURE_SESSION_CONFIG.REFRESH_TOKEN_KEY);

      const tokens = {};

      if (accessTokenData) {
        const decryptedAccess = this.decrypt(JSON.parse(accessTokenData));
        if (decryptedAccess && decryptedAccess.fingerprint === this.deviceFingerprint) {
          tokens.accessToken = decryptedAccess.token;
        }
      }

      if (refreshTokenData) {
        const decryptedRefresh = this.decrypt(JSON.parse(refreshTokenData));
        if (decryptedRefresh && decryptedRefresh.fingerprint === this.deviceFingerprint) {
          tokens.refreshToken = decryptedRefresh.token;
        }
      }

      return tokens;
    } catch (error) {
      console.error('Failed to retrieve tokens securely:', error);
      return {};
    }
  }

  /**
   * Get session metadata
   */
  getSessionMetadata() {
    if (this.sessionMetadata) {
      return this.sessionMetadata;
    }

    try {
      const metadataData = sessionStorage.getItem(SECURE_SESSION_CONFIG.SESSION_META_KEY);
      if (metadataData) {
        const decryptedMetadata = this.decrypt(JSON.parse(metadataData));
        if (decryptedMetadata && decryptedMetadata.deviceFingerprint === this.deviceFingerprint) {
          this.sessionMetadata = decryptedMetadata;
          return decryptedMetadata;
        }
      }
    } catch (error) {
      console.error('Failed to retrieve session metadata:', error);
    }

    return null;
  }

  /**
   * Update session activity
   */
  updateActivity() {
    const metadata = this.getSessionMetadata();
    if (metadata) {
      metadata.lastActivity = Date.now();
      const encryptedMetadata = this.encrypt(metadata);
      sessionStorage.setItem(SECURE_SESSION_CONFIG.SESSION_META_KEY, JSON.stringify(encryptedMetadata));
      this.sessionMetadata = metadata;

      // Broadcast activity to other tabs
      this.broadcastMessage(SECURE_SESSION_CONFIG.SYNC_EVENTS.ACTIVITY, {
        sessionId: metadata.sessionId,
        timestamp: Date.now()
      });
    }
  }

  /**
   * Clear all session data
   */
  clearSession() {
    try {
      // Clear tokens
      sessionStorage.removeItem(SECURE_SESSION_CONFIG.ACCESS_TOKEN_KEY);
      localStorage.removeItem(SECURE_SESSION_CONFIG.REFRESH_TOKEN_KEY);
      sessionStorage.removeItem(SECURE_SESSION_CONFIG.SESSION_META_KEY);

      // Broadcast logout to other tabs
      if (this.sessionMetadata) {
        this.broadcastMessage(SECURE_SESSION_CONFIG.SYNC_EVENTS.LOGOUT, {
          sessionId: this.sessionMetadata.sessionId
        });
      }

      this.sessionMetadata = null;

      return true;
    } catch (error) {
      console.error('Failed to clear session:', error);
      return false;
    }
  }

  /**
   * Generate unique session ID
   */
  generateSessionId() {
    return CryptoJS.lib.WordArray.random(16).toString() + '_' + Date.now();
  }

  /**
   * Validate session integrity
   */
  validateSession() {
    const metadata = this.getSessionMetadata();
    if (!metadata) {
      return { valid: false, reason: 'No session metadata' };
    }

    // Check device fingerprint
    if (metadata.deviceFingerprint !== this.deviceFingerprint) {
      return { valid: false, reason: 'Device fingerprint mismatch' };
    }

    // Check session age
    const sessionAge = Date.now() - metadata.loginTime;
    const maxSessionAge = 24 * 60 * 60 * 1000; // 24 hours
    if (sessionAge > maxSessionAge) {
      return { valid: false, reason: 'Session expired' };
    }

    // Check activity
    const timeSinceActivity = Date.now() - metadata.lastActivity;
    if (timeSinceActivity > SECURE_SESSION_CONFIG.IDLE_TIMEOUT) {
      return { valid: false, reason: 'Session idle timeout' };
    }

    return { valid: true, metadata };
  }

  /**
   * Cross-tab event handlers
   */
  handleCrossTabLogin(data) {
    // Another tab logged in - could implement concurrent session management here
    console.log('Another tab logged in:', data);
  }

  handleCrossTabLogout(data) {
    // Another tab logged out - clear local session
    this.clearSession();
    window.dispatchEvent(new CustomEvent('sessionLogout', { detail: data }));
  }

  handleCrossTabRefresh(data) {
    // Another tab refreshed tokens - sync if needed
    console.log('Another tab refreshed tokens:', data);
  }

  handleCrossTabActivity(data) {
    // Another tab had activity - update local activity timestamp
    if (this.sessionMetadata && this.sessionMetadata.sessionId === data.sessionId) {
      this.updateActivity();
    }
  }

  /**
   * Cleanup resources
   */
  cleanup() {
    if (this.broadcastChannel) {
      this.broadcastChannel.close();
    }
  }
}

// Create singleton instance
const secureSessionStorage = new SecureSessionStorage();

export default secureSessionStorage;
export { SECURE_SESSION_CONFIG };