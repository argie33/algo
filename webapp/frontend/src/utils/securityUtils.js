/**
 * Security Utilities - Input validation, XSS prevention, and security hardening
 * Provides comprehensive security measures for the frontend application
 */

class SecurityUtils {
  constructor() {
    this.cspNonce = this.generateNonce();
    this.trustedDomains = [
      'localhost',
      '2m14opj30h.execute-api.us-east-1.amazonaws.com',
      'd1zb7knau41vl9.cloudfront.net'
    ];
    
    this.initializeSecurityMeasures();
  }

  /**
   * Initialize security measures
   */
  initializeSecurityMeasures() {
    this.setupCSP();
    this.preventClickjacking();
    this.setupSecureHeaders();
    this.monitorSecurityViolations();
  }

  /**
   * Generate cryptographically secure nonce
   */
  generateNonce() {
    if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
      const array = new Uint8Array(16);
      crypto.getRandomValues(array);
      return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
    }
    // Fallback for older browsers
    return Math.random().toString(36).substr(2, 16) + Date.now().toString(36);
  }

  /**
   * Setup Content Security Policy
   */
  setupCSP() {
    const cspPolicy = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "font-src 'self' https://fonts.gstatic.com data:",
      "img-src 'self' data: https: blob:",
      "connect-src 'self' https://*.amazonaws.com https://*.execute-api.us-east-1.amazonaws.com wss: ws:",
      "worker-src 'self' blob:",
      "frame-src 'none'",
      "object-src 'none'",
      "base-uri 'self'"
    ].join('; ');

    // Add CSP meta tag if not already present
    if (!document.querySelector('meta[http-equiv="Content-Security-Policy"]')) {
      const meta = document.createElement('meta');
      meta.httpEquiv = 'Content-Security-Policy';
      meta.content = cspPolicy;
      document.head.appendChild(meta);
    }
  }

  /**
   * Prevent clickjacking attacks
   */
  preventClickjacking() {
    // Add X-Frame-Options equivalent
    if (window.top !== window.self) {
      console.warn('🚨 Potential clickjacking attempt detected');
      window.top.location = window.self.location;
    }
  }

  /**
   * Setup secure headers
   */
  setupSecureHeaders() {
    // Add security-related meta tags
    const securityMetas = [
      { name: 'referrer', content: 'strict-origin-when-cross-origin' },
      { name: 'robots', content: 'noindex, nofollow' }, // Prevent indexing of financial data
      { httpEquiv: 'X-Content-Type-Options', content: 'nosniff' },
      { httpEquiv: 'X-XSS-Protection', content: '1; mode=block' }
    ];

    securityMetas.forEach(meta => {
      if (!document.querySelector(`meta[name="${meta.name}"], meta[http-equiv="${meta.httpEquiv}"]`)) {
        const element = document.createElement('meta');
        if (meta.name) element.name = meta.name;
        if (meta.httpEquiv) element.httpEquiv = meta.httpEquiv;
        element.content = meta.content;
        document.head.appendChild(element);
      }
    });
  }

  /**
   * Monitor security violations
   */
  monitorSecurityViolations() {
    // Monitor CSP violations
    document.addEventListener('securitypolicyviolation', (event) => {
      console.error('🚨 CSP Violation:', {
        blockedURI: event.blockedURI,
        violatedDirective: event.violatedDirective,
        originalPolicy: event.originalPolicy
      });
      
      this.reportSecurityViolation('csp', event);
    });

    // Monitor for potential XSS attempts
    this.monitorDOMChanges();
  }

  /**
   * Monitor DOM changes for potential XSS
   */
  monitorDOMChanges() {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'childList') {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE) {
              this.scanElementForThreats(node);
            }
          });
        }
      });
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  /**
   * Scan element for security threats
   */
  scanElementForThreats(element) {
    // Check for suspicious script tags
    const scripts = element.querySelectorAll('script');
    scripts.forEach(script => {
      if (script.src && !this.isUrlTrusted(script.src)) {
        console.warn('🚨 Untrusted script detected:', script.src);
        script.remove();
      }
    });

    // Check for suspicious inline event handlers
    const elementsWithEvents = element.querySelectorAll('*[onclick], *[onload], *[onerror]');
    elementsWithEvents.forEach(el => {
      console.warn('🚨 Inline event handler detected:', el.outerHTML.substring(0, 100));
    });
  }

  /**
   * Check if URL is trusted
   */
  isUrlTrusted(url) {
    try {
      const urlObj = new URL(url);
      return this.trustedDomains.some(domain => 
        urlObj.hostname === domain || urlObj.hostname.endsWith('.' + domain)
      );
    } catch (error) {
      return false;
    }
  }

  /**
   * Sanitize HTML input to prevent XSS
   */
  sanitizeHTML(html) {
    const div = document.createElement('div');
    div.textContent = html;
    return div.innerHTML;
  }

  /**
   * Sanitize URL to prevent XSS
   */
  sanitizeURL(url) {
    try {
      const urlObj = new URL(url);
      // Only allow http, https, and mailto protocols
      if (!['http:', 'https:', 'mailto:'].includes(urlObj.protocol)) {
        return '#';
      }
      return url;
    } catch (error) {
      return '#';
    }
  }

  /**
   * Validate and sanitize user input
   */
  validateInput(input, type = 'text', options = {}) {
    const validators = {
      email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
      phone: /^\+?[\d\s\-()]+$/,
      alphanumeric: /^[a-zA-Z0-9\s]*$/,
      numeric: /^\d*\.?\d*$/,
      url: /^https?:\/\/.+/,
      symbol: /^[A-Z]{1,5}$/,
      apiKey: /^[A-Za-z0-9\-_]{20,}$/
    };

    const result = {
      isValid: true,
      sanitized: input,
      errors: []
    };

    // Basic sanitization
    if (typeof input === 'string') {
      result.sanitized = input.trim();
      
      // Length validation
      if (options.maxLength && result.sanitized.length > options.maxLength) {
        result.isValid = false;
        result.errors.push(`Input too long (max ${options.maxLength} characters)`);
      }
      
      if (options.minLength && result.sanitized.length < options.minLength) {
        result.isValid = false;
        result.errors.push(`Input too short (min ${options.minLength} characters)`);
      }

      // Pattern validation
      if (validators[type] && !validators[type].test(result.sanitized)) {
        result.isValid = false;
        result.errors.push(`Invalid ${type} format`);
      }

      // XSS prevention
      if (result.sanitized.includes('<script') || result.sanitized.includes('javascript:')) {
        result.isValid = false;
        result.errors.push('Potentially malicious content detected');
        result.sanitized = this.sanitizeHTML(result.sanitized);
      }
    }

    return result;
  }

  /**
   * Generate CSRF token
   */
  generateCSRFToken() {
    const token = this.generateNonce();
    sessionStorage.setItem('csrfToken', token);
    return token;
  }

  /**
   * Validate CSRF token
   */
  validateCSRFToken(token) {
    const storedToken = sessionStorage.getItem('csrfToken');
    return storedToken === token;
  }

  /**
   * Secure local storage wrapper
   */
  secureStorage = {
    setItem: (key, value, encrypt = true) => {
      try {
        const data = encrypt ? this.encrypt(JSON.stringify(value)) : JSON.stringify(value);
        localStorage.setItem(key, data);
        return true;
      } catch (error) {
        console.error('Failed to set secure storage:', error);
        return false;
      }
    },

    getItem: (key, decrypt = true) => {
      try {
        const data = localStorage.getItem(key);
        if (!data) return null;
        
        const parsed = decrypt ? this.decrypt(data) : data;
        return JSON.parse(parsed);
      } catch (error) {
        console.error('Failed to get secure storage:', error);
        return null;
      }
    },

    removeItem: (key) => {
      localStorage.removeItem(key);
    }
  };

  /**
   * Simple encryption for client-side storage (not cryptographically secure)
   */
  encrypt(text) {
    // Simple XOR encryption for demo purposes
    // In production, use proper encryption libraries
    const key = this.cspNonce;
    let encrypted = '';
    for (let i = 0; i < text.length; i++) {
      encrypted += String.fromCharCode(
        text.charCodeAt(i) ^ key.charCodeAt(i % key.length)
      );
    }
    return btoa(encrypted);
  }

  /**
   * Simple decryption for client-side storage
   */
  decrypt(encryptedText) {
    try {
      const key = this.cspNonce;
      const encrypted = atob(encryptedText);
      let decrypted = '';
      for (let i = 0; i < encrypted.length; i++) {
        decrypted += String.fromCharCode(
          encrypted.charCodeAt(i) ^ key.charCodeAt(i % key.length)
        );
      }
      return decrypted;
    } catch (error) {
      throw new Error('Failed to decrypt data');
    }
  }

  /**
   * Rate limiting for API calls
   */
  createRateLimiter(maxRequests = 100, timeWindow = 60000) {
    const requests = new Map();
    
    return (identifier) => {
      const now = Date.now();
      const windowStart = now - timeWindow;
      
      // Clean old requests
      if (requests.has(identifier)) {
        requests.set(identifier, 
          requests.get(identifier).filter(time => time > windowStart)
        );
      } else {
        requests.set(identifier, []);
      }
      
      const userRequests = requests.get(identifier);
      
      if (userRequests.length >= maxRequests) {
        return {
          allowed: false,
          resetTime: userRequests[0] + timeWindow
        };
      }
      
      userRequests.push(now);
      return {
        allowed: true,
        remaining: maxRequests - userRequests.length
      };
    };
  }

  /**
   * Report security violation
   */
  reportSecurityViolation(type, details) {
    const report = {
      timestamp: new Date().toISOString(),
      type,
      details,
      userAgent: navigator.userAgent,
      url: window.location.href
    };

    console.error('🚨 Security Violation:', report);

    // Send to security monitoring service
    if (process.env.NODE_ENV === 'production') {
      fetch('/api/security/violations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(report)
      }).catch(error => {
        console.error('Failed to report security violation:', error);
      });
    }
  }

  /**
   * Get security status
   */
  getSecurityStatus() {
    return {
      cspEnabled: !!document.querySelector('meta[http-equiv="Content-Security-Policy"]'),
      httpsEnabled: window.location.protocol === 'https:',
      clickjackingProtection: window.top === window.self,
      secureStorage: this.isSecureStorageAvailable(),
      trustedDomain: this.isUrlTrusted(window.location.href)
    };
  }

  /**
   * Check if secure storage is available
   */
  isSecureStorageAvailable() {
    try {
      const test = 'test';
      this.secureStorage.setItem(test, test);
      this.secureStorage.removeItem(test);
      return true;
    } catch (error) {
      return false;
    }
  }
}

// Create singleton instance
const securityUtils = new SecurityUtils();

// React hook for input validation
export const useSecureInput = () => {
  const validateInput = React.useCallback((input, type, options) => {
    return securityUtils.validateInput(input, type, options);
  }, []);

  const sanitizeHTML = React.useCallback((html) => {
    return securityUtils.sanitizeHTML(html);
  }, []);

  const sanitizeURL = React.useCallback((url) => {
    return securityUtils.sanitizeURL(url);
  }, []);

  return {
    validateInput,
    sanitizeHTML,
    sanitizeURL,
    secureStorage: securityUtils.secureStorage
  };
};

// Add to React import
const React = require('react');

export default securityUtils;
export { SecurityUtils };

// Export utilities
export const validateInput = (input, type, options) => 
  securityUtils.validateInput(input, type, options);

export const sanitizeHTML = (html) => 
  securityUtils.sanitizeHTML(html);

export const sanitizeURL = (url) => 
  securityUtils.sanitizeURL(url);

export const secureStorage = securityUtils.secureStorage;

export const getSecurityStatus = () => 
  securityUtils.getSecurityStatus();