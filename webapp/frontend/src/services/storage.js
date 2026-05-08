/**
 * Centralized storage manager for localStorage/sessionStorage
 * Single place to manage all client-side persistence
 * Enables future encryption, validation, and cleanup
 */

const STORAGE_KEYS = {
  // Auth
  TOKEN: 'authToken',
  ID_TOKEN: 'idToken',
  REFRESH_TOKEN: 'refreshToken',
  DEV_SESSION: 'dev_session',

  // Theme
  THEME: 'theme',

  // Session
  SESSION_TIMEOUT: 'sessionTimeout',
  LAST_ACTIVITY: 'lastActivity',

  // Preferences
  REMEMBER_ME: 'rememberMe',
};

/**
 * Token storage
 */
export const storageToken = {
  set(token, type = 'access') {
    const key = type === 'access' ? STORAGE_KEYS.TOKEN : STORAGE_KEYS[`${type.toUpperCase()}_TOKEN`];
    try {
      localStorage.setItem(key, token);
    } catch (error) {
      console.error(`Failed to set ${type} token:`, error);
    }
  },

  get(type = 'access') {
    const key = type === 'access' ? STORAGE_KEYS.TOKEN : STORAGE_KEYS[`${type.toUpperCase()}_TOKEN`];
    try {
      return localStorage.getItem(key) || null;
    } catch {
      return null;
    }
  },

  clear(type) {
    try {
      if (type) {
        const key = type === 'access' ? STORAGE_KEYS.TOKEN : STORAGE_KEYS[`${type.toUpperCase()}_TOKEN`];
        localStorage.removeItem(key);
      } else {
        localStorage.removeItem(STORAGE_KEYS.TOKEN);
        localStorage.removeItem(STORAGE_KEYS.ID_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.DEV_SESSION);
      }
    } catch (error) {
      console.error('Failed to clear tokens:', error);
    }
  },

  has(type = 'access') {
    return !!this.get(type);
  },
};

/**
 * Theme storage
 */
export const storageTheme = {
  set(theme) {
    try {
      localStorage.setItem(STORAGE_KEYS.THEME, theme);
    } catch (error) {
      console.error('Failed to set theme:', error);
    }
  },

  get() {
    try {
      return localStorage.getItem(STORAGE_KEYS.THEME) || 'dark';
    } catch {
      return 'dark';
    }
  },

  clear() {
    try {
      localStorage.removeItem(STORAGE_KEYS.THEME);
    } catch (error) {
      console.error('Failed to clear theme:', error);
    }
  },
};

/**
 * Session storage
 */
export const storageSession = {
  set(key, value) {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.error(`Failed to set session ${key}:`, error);
    }
  },

  get(key) {
    try {
      const value = sessionStorage.getItem(key);
      return value ? JSON.parse(value) : null;
    } catch {
      return null;
    }
  },

  clear(key) {
    try {
      if (key) {
        sessionStorage.removeItem(key);
      } else {
        sessionStorage.clear();
      }
    } catch (error) {
      console.error('Failed to clear session:', error);
    }
  },
};

/**
 * Preference storage
 */
export const storagePreferences = {
  setRememberMe(value) {
    try {
      localStorage.setItem(STORAGE_KEYS.REMEMBER_ME, JSON.stringify(value));
    } catch (error) {
      console.error('Failed to set remember me:', error);
    }
  },

  getRememberMe() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEYS.REMEMBER_ME) || 'false');
    } catch {
      return false;
    }
  },

  clearRememberMe() {
    try {
      localStorage.removeItem(STORAGE_KEYS.REMEMBER_ME);
    } catch (error) {
      console.error('Failed to clear remember me:', error);
    }
  },
};

/**
 * Completely clear all storage
 */
export const clearAllStorage = () => {
  try {
    storageToken.clear();
    storageTheme.clear();
    storageSession.clear();
    storagePreferences.clearRememberMe();
  } catch (error) {
    console.error('Failed to clear all storage:', error);
  }
};

export default {
  token: storageToken,
  theme: storageTheme,
  session: storageSession,
  preferences: storagePreferences,
  clearAll: clearAllStorage,
};
