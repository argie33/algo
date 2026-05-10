/**
 * Centralized theme management service
 * Single source of truth for theme state and persistence
 */

const THEME_KEY = 'theme';
const DEFAULT_THEME = 'dark';

// Subscribers for theme changes
let subscribers = [];

export const theme = {
  /**
   * Get current theme
   * @returns {string} 'dark' or 'light'
   */
  getTheme() {
    try {
      return localStorage.getItem(THEME_KEY) || DEFAULT_THEME;
    } catch {
      return DEFAULT_THEME;
    }
  },

  /**
   * Set theme and apply to DOM
   * @param {string} newTheme - 'dark' or 'light'
   */
  setTheme(newTheme) {
    try {
      const validTheme = ['dark', 'light'].includes(newTheme) ? newTheme : DEFAULT_THEME;
      localStorage.setItem(THEME_KEY, validTheme);
      this._applyTheme(validTheme);
      this._notifySubscribers(validTheme);
    } catch (error) {
      console.error('Failed to set theme:', error);
    }
  },

  /**
   * Toggle between dark and light
   * @returns {string} new theme
   */
  toggleTheme() {
    const current = this.getTheme();
    const newTheme = current === 'dark' ? 'light' : 'dark';
    this.setTheme(newTheme);
    return newTheme;
  },

  /**
   * Subscribe to theme changes
   * @param {function} callback - called with (newTheme) when theme changes
   * @returns {function} unsubscribe function
   */
  subscribe(callback) {
    subscribers.push(callback);
    return () => {
      subscribers = subscribers.filter(cb => cb !== callback);
    };
  },

  /**
   * Apply theme to DOM
   * @private
   */
  _applyTheme(themeName) {
    if (typeof document === 'undefined') return;
    document.documentElement.classList.toggle('light', themeName === 'light');
  },

  /**
   * Notify all subscribers
   * @private
   */
  _notifySubscribers(themeName) {
    subscribers.forEach(callback => {
      try {
        callback(themeName);
      } catch (error) {
        console.error('Theme subscriber error:', error);
      }
    });
  },

  /**
   * Initialize theme on app startup
   */
  initialize() {
    const currentTheme = this.getTheme();
    this._applyTheme(currentTheme);
  }
};

export default theme;
