/**
 * Centralized token management service - SECURITY HARDENED
 * FIXED: Uses sessionStorage (cleared on browser close) + memory storage for XSS protection
 * Tokens are NOT accessible via localStorage (XSS attack vector)
 */

const TOKEN_KEYS = {
  access: 'authToken',
  id: 'idToken',
  refresh: 'refreshToken',
  dev_session: 'dev_session'
};

// In-memory token storage (cleared on page reload - most secure)
const memoryStorage = {};

export const tokenManager = {
  /**
   * Get a token by type
   * SECURITY: Uses sessionStorage (cleared on browser close) instead of localStorage
   * @param {string} type - 'access', 'id', 'refresh', 'dev_session'
   * @returns {string|null}
   */
  getToken(type = 'access') {
    try {
      // First check memory (most secure, cleared on reload)
      if (memoryStorage[type]) return memoryStorage[type];

      // Fall back to sessionStorage (cleared on browser close)
      return sessionStorage.getItem(TOKEN_KEYS[type] || type) || null;
    } catch {
      return null;
    }
  },

  /**
   * Get all tokens as object
   * @returns {object}
   */
  getAllTokens() {
    try {
      return {
        access: this.getToken('access'),
        id: this.getToken('id'),
        refresh: this.getToken('refresh'),
        dev_session: this.getToken('dev_session')
      };
    } catch {
      return {};
    }
  },

  /**
   * Set a token
   * SECURITY: Stores in sessionStorage (not persistent localStorage)
   * @param {string} token - token value
   * @param {string} type - 'access', 'id', 'refresh', 'dev_session'
   */
  setToken(token, type = 'access') {
    try {
      const key = TOKEN_KEYS[type] || type;
      if (token) {
        // Store in memory
        memoryStorage[type] = token;
        // Also store in sessionStorage (cleared when browser closes)
        sessionStorage.setItem(key, token);
        // Remove from localStorage to prevent persistence across sessions
        localStorage.removeItem(key);
      } else {
        memoryStorage[type] = null;
        sessionStorage.removeItem(key);
        localStorage.removeItem(key);
      }
    } catch (error) {
      console.error(`Failed to set token (${type}):`, error);
    }
  },

  /**
   * Set multiple tokens at once
   * @param {object} tokens - { access: '...', id: '...', refresh: '...' }
   */
  setTokens(tokens = {}) {
    Object.entries(tokens).forEach(([type, value]) => {
      if (value) this.setToken(value, type);
    });
  },

  /**
   * Clear all tokens from memory, sessionStorage, and localStorage
   */
  clearTokens() {
    try {
      // Clear memory
      Object.keys(memoryStorage).forEach(key => {
        memoryStorage[key] = null;
      });
      // Clear sessionStorage
      Object.values(TOKEN_KEYS).forEach(key => {
        sessionStorage.removeItem(key);
      });
      // Clear localStorage (belt and suspenders)
      Object.values(TOKEN_KEYS).forEach(key => {
        localStorage.removeItem(key);
      });
    } catch (error) {
      console.error('Failed to clear tokens:', error);
    }
  },

  /**
   * Clear a specific token
   * @param {string} type - 'access', 'id', 'refresh', 'dev_session'
   */
  clearToken(type = 'access') {
    try {
      const key = TOKEN_KEYS[type] || type;
      memoryStorage[type] = null;
      sessionStorage.removeItem(key);
      localStorage.removeItem(key);
    } catch (error) {
      console.error(`Failed to clear token (${type}):`, error);
    }
  },

  /**
   * Check if we have a valid access token
   * @returns {boolean}
   */
  hasValidToken() {
    const token = this.getToken('access');
    return !!token && token.length > 0;
  },

  /**
   * Get auth header for API requests
   * @returns {object|null}
   */
  getAuthHeader() {
    const token = this.getToken('access');
    return token ? { Authorization: `Bearer ${token}` } : null;
  }
};

export default tokenManager;
