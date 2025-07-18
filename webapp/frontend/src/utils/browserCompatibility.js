/**
 * Browser Compatibility Checker and Polyfill Loader
 * Ensures the app works across different browsers and versions
 */

class BrowserCompatibility {
  constructor() {
    this.browserInfo = this.detectBrowser();
    this.supportedFeatures = new Map();
    this.polyfillsLoaded = new Set();
    
    // Initialize on construction
    this.checkCompatibility();
    this.loadEssentialPolyfills();
  }

  /**
   * Detect browser type and version
   */
  detectBrowser() {
    const userAgent = navigator.userAgent;
    const browserInfo = {
      name: 'unknown',
      version: 0,
      isSupported: false,
      features: {}
    };

    // Detect browser type
    if (userAgent.includes('Chrome') && !userAgent.includes('Edge')) {
      browserInfo.name = 'chrome';
      browserInfo.version = parseInt(userAgent.match(/Chrome\/(\d+)/)?.[1] || '0');
    } else if (userAgent.includes('Firefox')) {
      browserInfo.name = 'firefox';
      browserInfo.version = parseInt(userAgent.match(/Firefox\/(\d+)/)?.[1] || '0');
    } else if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) {
      browserInfo.name = 'safari';
      browserInfo.version = parseInt(userAgent.match(/Version\/(\d+)/)?.[1] || '0');
    } else if (userAgent.includes('Edge')) {
      browserInfo.name = 'edge';
      browserInfo.version = parseInt(userAgent.match(/Edge\/(\d+)/)?.[1] || '0');
    } else if (userAgent.includes('MSIE') || userAgent.includes('Trident')) {
      browserInfo.name = 'ie';
      browserInfo.version = parseInt(userAgent.match(/(?:MSIE |rv:)(\d+)/)?.[1] || '0');
    }

    // Check if browser version is supported
    browserInfo.isSupported = this.isBrowserSupported(browserInfo);

    return browserInfo;
  }

  /**
   * Check if browser version is supported
   */
  isBrowserSupported(browser) {
    const minimumVersions = {
      chrome: 70,
      firefox: 65,
      safari: 12,
      edge: 79,
      ie: 0 // Not supported
    };

    return browser.version >= (minimumVersions[browser.name] || 0);
  }

  /**
   * Check browser compatibility for essential features
   */
  checkCompatibility() {
    const features = {
      fetch: 'fetch' in window,
      promise: 'Promise' in window,
      arrow_functions: true, // Can't runtime check this
      const_let: true, // Can't runtime check this
      async_await: true, // Can't runtime check this
      modules: 'noModule' in document.createElement('script'),
      intersectionObserver: 'IntersectionObserver' in window,
      resizeObserver: 'ResizeObserver' in window,
      webSockets: 'WebSocket' in window,
      localStorage: this.checkLocalStorage(),
      sessionStorage: this.checkSessionStorage(),
      indexedDB: 'indexedDB' in window,
      serviceWorker: 'serviceWorker' in navigator,
      webWorker: 'Worker' in window,
      fileApi: 'File' in window && 'FileReader' in window,
      geolocation: 'geolocation' in navigator,
      notifications: 'Notification' in window,
      webGL: this.checkWebGL(),
      canvas: 'getContext' in document.createElement('canvas'),
      svg: document.implementation.hasFeature('http://www.w3.org/TR/SVG11/feature#BasicStructure', '1.1'),
      flexbox: this.checkCSSFeature('flex'),
      grid: this.checkCSSFeature('grid'),
      customProperties: this.checkCSSFeature('--test'),
      transforms3d: this.checkCSS3DTransforms()
    };

    this.supportedFeatures = new Map(Object.entries(features));
    this.browserInfo.features = features;

    return features;
  }

  /**
   * Check localStorage support
   */
  checkLocalStorage() {
    try {
      const test = 'test';
      localStorage.setItem(test, test);
      localStorage.removeItem(test);
      return true;
    } catch (e) {
      return false;
    }
  }

  /**
   * Check sessionStorage support
   */
  checkSessionStorage() {
    try {
      const test = 'test';
      sessionStorage.setItem(test, test);
      sessionStorage.removeItem(test);
      return true;
    } catch (e) {
      return false;
    }
  }

  /**
   * Check WebGL support
   */
  checkWebGL() {
    try {
      const canvas = document.createElement('canvas');
      return !!(window.WebGLRenderingContext && 
        (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
    } catch (e) {
      return false;
    }
  }

  /**
   * Check CSS feature support
   */
  checkCSSFeature(property) {
    const element = document.createElement('div');
    const prefixes = ['', '-webkit-', '-moz-', '-ms-', '-o-'];
    
    for (const prefix of prefixes) {
      if (`${prefix}${property}` in element.style) {
        return true;
      }
    }
    return false;
  }

  /**
   * Check CSS 3D transforms support
   */
  checkCSS3DTransforms() {
    const element = document.createElement('div');
    element.style.transform = 'translate3d(0,0,0)';
    return element.style.transform !== '';
  }

  /**
   * Load essential polyfills based on feature detection
   */
  async loadEssentialPolyfills() {
    const polyfills = [];

    // Fetch polyfill
    if (!this.supportedFeatures.get('fetch')) {
      polyfills.push(this.loadPolyfill('fetch', () => {
        return import('https://cdn.jsdelivr.net/npm/whatwg-fetch@3.6.2/fetch.js');
      }));
    }

    // Promise polyfill
    if (!this.supportedFeatures.get('promise')) {
      polyfills.push(this.loadPolyfill('promise', () => {
        return import('https://cdn.jsdelivr.net/npm/es6-promise@4.2.8/dist/es6-promise.auto.min.js');
      }));
    }

    // IntersectionObserver polyfill
    if (!this.supportedFeatures.get('intersectionObserver')) {
      polyfills.push(this.loadPolyfill('intersectionObserver', () => {
        return import('https://cdn.jsdelivr.net/npm/intersection-observer@0.12.0/intersection-observer.js');
      }));
    }

    // ResizeObserver polyfill
    if (!this.supportedFeatures.get('resizeObserver')) {
      polyfills.push(this.loadPolyfill('resizeObserver', () => {
        return import('https://cdn.jsdelivr.net/npm/@juggle/resize-observer@3.4.0/lib/exports/resize-observer.umd.js');
      }));
    }

    try {
      await Promise.all(polyfills);
      console.log('✅ All essential polyfills loaded');
    } catch (error) {
      console.warn('⚠️ Some polyfills failed to load:', error);
    }
  }

  /**
   * Load a specific polyfill
   */
  async loadPolyfill(name, loader) {
    if (this.polyfillsLoaded.has(name)) {
      return;
    }

    try {
      console.log(`📦 Loading ${name} polyfill...`);
      await loader();
      this.polyfillsLoaded.add(name);
      console.log(`✅ ${name} polyfill loaded`);
    } catch (error) {
      console.warn(`❌ Failed to load ${name} polyfill:`, error);
    }
  }

  /**
   * Get compatibility report
   */
  getCompatibilityReport() {
    const unsupportedFeatures = Array.from(this.supportedFeatures.entries())
      .filter(([, supported]) => !supported)
      .map(([feature]) => feature);

    return {
      browser: this.browserInfo,
      isCompatible: this.browserInfo.isSupported,
      supportedFeatures: Object.fromEntries(this.supportedFeatures),
      unsupportedFeatures,
      polyfillsLoaded: Array.from(this.polyfillsLoaded),
      recommendations: this.getRecommendations()
    };
  }

  /**
   * Get upgrade recommendations
   */
  getRecommendations() {
    const recommendations = [];

    if (!this.browserInfo.isSupported) {
      recommendations.push({
        type: 'critical',
        message: `Your browser (${this.browserInfo.name} ${this.browserInfo.version}) is not supported. Please upgrade to a modern browser.`,
        action: 'upgrade_browser'
      });
    }

    if (!this.supportedFeatures.get('localStorage')) {
      recommendations.push({
        type: 'warning',
        message: 'Local storage is not available. Some features may not work properly.',
        action: 'enable_storage'
      });
    }

    if (!this.supportedFeatures.get('webSockets')) {
      recommendations.push({
        type: 'info',
        message: 'WebSocket support is limited. Real-time features will use polling.',
        action: 'upgrade_browser'
      });
    }

    return recommendations;
  }

  /**
   * Show compatibility warning if needed
   */
  showCompatibilityWarning() {
    if (!this.browserInfo.isSupported) {
      const warningHTML = `
        <div id="browser-warning" style="
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          background: #f59e0b;
          color: #92400e;
          padding: 12px;
          text-align: center;
          z-index: 10000;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          font-size: 14px;
        ">
          <strong>Browser Not Supported:</strong> 
          Your browser (${this.browserInfo.name} ${this.browserInfo.version}) may not work properly. 
          <a href="https://browsehappy.com/" target="_blank" style="color: #92400e; text-decoration: underline;">
            Please upgrade to a modern browser.
          </a>
          <button onclick="document.getElementById('browser-warning').remove()" style="
            background: none;
            border: none;
            color: #92400e;
            cursor: pointer;
            font-size: 16px;
            margin-left: 10px;
          ">×</button>
        </div>
      `;
      
      document.body.insertAdjacentHTML('afterbegin', warningHTML);
    }
  }
}

// Create singleton instance
const browserCompatibility = new BrowserCompatibility();

// Initialize compatibility checking
if (typeof window !== 'undefined') {
  // Show warning if needed
  document.addEventListener('DOMContentLoaded', () => {
    browserCompatibility.showCompatibilityWarning();
  });
}

export default browserCompatibility;
export { BrowserCompatibility };

// Export utilities
export const isFeatureSupported = (feature) => 
  browserCompatibility.supportedFeatures.get(feature);

export const getBrowserInfo = () => 
  browserCompatibility.browserInfo;

export const getCompatibilityReport = () => 
  browserCompatibility.getCompatibilityReport();