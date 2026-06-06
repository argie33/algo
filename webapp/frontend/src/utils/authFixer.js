/**
 * Development Authentication Helper
 * Provides utilities for testing and development authentication
 */

export class DevAuthHelper {
  constructor() {
    this.devToken = null;
    this.devUser = null;
  }

  static getInstance() {
    if (!DevAuthHelper.instance) {
      DevAuthHelper.instance = new DevAuthHelper();
    }
    return DevAuthHelper.instance;
  }

  setDevToken(token) {
    this.devToken = token;
    localStorage.setItem('devToken', token);
  }

  getDevToken() {
    if (!this.devToken) {
      this.devToken = localStorage.getItem('devToken');
    }
    return this.devToken;
  }

  setDevUser(user) {
    this.devUser = user;
    localStorage.setItem('devUser', JSON.stringify(user));
  }

  getDevUser() {
    if (!this.devUser) {
      const stored = localStorage.getItem('devUser');
      this.devUser = stored ? JSON.parse(stored) : null;
    }
    return this.devUser;
  }

  isLocalhost() {
    if (typeof window !== 'undefined') {
      return window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    }
    return false;
  }

  clearDevAuth() {
    this.devToken = null;
    this.devUser = null;
    localStorage.removeItem('devToken');
    localStorage.removeItem('devUser');
  }
}

export default DevAuthHelper;
