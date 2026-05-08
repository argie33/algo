/**
 * Centralized token management service
 * Single source of truth for all auth tokens
 */

const TOKEN_KEYS = {
  access: 'authToken',
  id: 'idToken',
  refresh: 'refreshToken',
  dev_session: 'dev_session'
};

export const tokenManager = {
  /**
   * Get a token by type
   * @param {string} type - 'access', 'id', 'refresh', 'dev_session'
   * @returns {string|null}
   */
  getToken(type = 'access') {
    try {
      return localStorage.getItem(TOKEN_KEYS[type] || type) || null;
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
   * @param {string} token - token value
   * @param {string} type - 'access', 'id', 'refresh', 'dev_session'
   */
  setToken(token, type = 'access') {
    try {
      const key = TOKEN_KEYS[type] || type;
      if (token) {
        localStorage.setItem(key, token);
      } else {
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
   * Clear all tokens
   */
  clearTokens() {
    try {
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
