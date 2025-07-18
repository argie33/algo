/**
 * Mobile Optimization - Responsive design, touch interactions, and mobile-specific features
 * Provides comprehensive mobile experience optimization
 */

class MobileOptimization {
  constructor() {
    this.breakpoints = {
      mobile: 768,
      tablet: 1024,
      desktop: 1200
    };
    
    this.touchGestures = new Map();
    this.currentDevice = this.detectDevice();
    
    this.initializeMobileOptimization();
  }

  /**
   * Initialize mobile optimization
   */
  initializeMobileOptimization() {
    this.setupViewportMeta();
    this.detectDeviceOrientation();
    this.setupTouchInteractions();
    this.optimizeForMobile();
    this.setupResizeHandler();
    this.preventZoom();
  }

  /**
   * Setup viewport meta tag
   */
  setupViewportMeta() {
    let viewport = document.querySelector('meta[name="viewport"]');
    if (!viewport) {
      viewport = document.createElement('meta');
      viewport.name = 'viewport';
      document.head.appendChild(viewport);
    }
    
    // Prevent zoom on financial apps for better UX
    viewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
    
    // Add apple-specific meta tags
    this.addAppleMeta();
  }

  /**
   * Add Apple-specific meta tags
   */
  addAppleMeta() {
    const appleMetas = [
      { name: 'apple-mobile-web-app-capable', content: 'yes' },
      { name: 'apple-mobile-web-app-status-bar-style', content: 'default' },
      { name: 'apple-mobile-web-app-title', content: 'Trading Platform' },
      { name: 'format-detection', content: 'telephone=no' }
    ];

    appleMetas.forEach(meta => {
      if (!document.querySelector(`meta[name="${meta.name}"]`)) {
        const element = document.createElement('meta');
        element.name = meta.name;
        element.content = meta.content;
        document.head.appendChild(element);
      }
    });
  }

  /**
   * Detect current device type
   */
  detectDevice() {
    const width = window.innerWidth;
    const userAgent = navigator.userAgent;
    
    const device = {
      type: width < this.breakpoints.mobile ? 'mobile' : 
            width < this.breakpoints.tablet ? 'tablet' : 'desktop',
      isIOS: /iPad|iPhone|iPod/.test(userAgent),
      isAndroid: /Android/.test(userAgent),
      isMobile: /Mobi|Android/i.test(userAgent),
      isTouch: 'ontouchstart' in window,
      width,
      height: window.innerHeight,
      pixelRatio: window.devicePixelRatio || 1
    };

    document.body.className = document.body.className.replace(/device-\w+/g, '');
    document.body.classList.add(`device-${device.type}`);
    
    if (device.isIOS) document.body.classList.add('device-ios');
    if (device.isAndroid) document.body.classList.add('device-android');
    if (device.isTouch) document.body.classList.add('device-touch');

    return device;
  }

  /**
   * Detect device orientation
   */
  detectDeviceOrientation() {
    const updateOrientation = () => {
      const orientation = window.innerWidth > window.innerHeight ? 'landscape' : 'portrait';
      document.body.className = document.body.className.replace(/orientation-\w+/g, '');
      document.body.classList.add(`orientation-${orientation}`);
      
      this.currentDevice.orientation = orientation;
      this.handleOrientationChange(orientation);
    };

    updateOrientation();
    window.addEventListener('orientationchange', () => {
      setTimeout(updateOrientation, 100); // Delay to get accurate dimensions
    });
    window.addEventListener('resize', updateOrientation);
  }

  /**
   * Handle orientation change
   */
  handleOrientationChange(orientation) {
    // Dispatch custom event for components to respond
    window.dispatchEvent(new CustomEvent('orientationUpdate', {
      detail: { orientation, device: this.currentDevice }
    }));

    // Adjust chart sizes for financial data
    setTimeout(() => {
      const charts = document.querySelectorAll('[data-chart], .recharts-wrapper');
      charts.forEach(chart => {
        const event = new Event('resize');
        window.dispatchEvent(event);
      });
    }, 300);
  }

  /**
   * Setup touch interactions
   */
  setupTouchInteractions() {
    if (!this.currentDevice.isTouch) return;

    this.setupSwipeGestures();
    this.setupPinchGestures();
    this.setupTouchFeedback();
    this.optimizeScrolling();
  }

  /**
   * Setup swipe gestures
   */
  setupSwipeGestures() {
    let startX, startY, startTime;

    document.addEventListener('touchstart', (e) => {
      const touch = e.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      startTime = Date.now();
    }, { passive: true });

    document.addEventListener('touchend', (e) => {
      if (!startX || !startY) return;

      const touch = e.changedTouches[0];
      const endX = touch.clientX;
      const endY = touch.clientY;
      const endTime = Date.now();

      const deltaX = endX - startX;
      const deltaY = endY - startY;
      const deltaTime = endTime - startTime;

      // Only detect swipes, not slow drags
      if (deltaTime > 300) return;

      const minSwipeDistance = 50;
      const maxVerticalDistance = 100;

      if (Math.abs(deltaX) > minSwipeDistance && Math.abs(deltaY) < maxVerticalDistance) {
        const direction = deltaX > 0 ? 'right' : 'left';
        this.handleSwipe(direction, e.target);
      }

      startX = startY = null;
    }, { passive: true });
  }

  /**
   * Handle swipe gestures
   */
  handleSwipe(direction, target) {
    // Custom swipe event for components
    target.dispatchEvent(new CustomEvent('swipe', {
      detail: { direction },
      bubbles: true
    }));

    // Handle specific swipe actions for trading interface
    if (target.closest('.chart-container')) {
      this.handleChartSwipe(direction, target);
    }
  }

  /**
   * Handle chart swipe for timeframe navigation
   */
  handleChartSwipe(direction, target) {
    const chartContainer = target.closest('.chart-container');
    if (!chartContainer) return;

    // Dispatch chart navigation event
    chartContainer.dispatchEvent(new CustomEvent('chart-navigate', {
      detail: { direction }
    }));
  }

  /**
   * Setup pinch gestures for zoom
   */
  setupPinchGestures() {
    let initialDistance = 0;
    let scale = 1;

    document.addEventListener('touchstart', (e) => {
      if (e.touches.length === 2) {
        initialDistance = this.getDistance(e.touches[0], e.touches[1]);
      }
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        const currentDistance = this.getDistance(e.touches[0], e.touches[1]);
        scale = currentDistance / initialDistance;
        
        this.handlePinch(scale, e.target);
      }
    });
  }

  /**
   * Get distance between two touches
   */
  getDistance(touch1, touch2) {
    const dx = touch1.clientX - touch2.clientX;
    const dy = touch1.clientY - touch2.clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  /**
   * Handle pinch gestures
   */
  handlePinch(scale, target) {
    const chartContainer = target.closest('.chart-container, [data-chart]');
    if (chartContainer) {
      chartContainer.dispatchEvent(new CustomEvent('chart-zoom', {
        detail: { scale }
      }));
    }
  }

  /**
   * Setup touch feedback
   */
  setupTouchFeedback() {
    const style = document.createElement('style');
    style.textContent = `
      .touch-feedback {
        position: relative;
        overflow: hidden;
      }
      
      .touch-feedback::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: translate(-50%, -50%);
        transition: width 0.3s, height 0.3s;
        pointer-events: none;
      }
      
      .touch-feedback.active::after {
        width: 100px;
        height: 100px;
      }
      
      /* Optimize touch targets */
      button, .btn, [role="button"] {
        min-height: 44px;
        min-width: 44px;
        padding: 12px;
      }
      
      /* Mobile-specific optimizations */
      @media (max-width: 768px) {
        .btn {
          font-size: 16px; /* Prevent zoom on iOS */
          padding: 14px 20px;
        }
        
        input, select, textarea {
          font-size: 16px; /* Prevent zoom on iOS */
        }
        
        .table-responsive {
          font-size: 14px;
        }
        
        .card {
          margin-bottom: 1rem;
        }
      }
    `;
    document.head.appendChild(style);

    // Add touch feedback to interactive elements
    document.addEventListener('touchstart', (e) => {
      const target = e.target.closest('button, .btn, [role="button"]');
      if (target) {
        target.classList.add('touch-feedback', 'active');
      }
    }, { passive: true });

    document.addEventListener('touchend', (e) => {
      const target = e.target.closest('button, .btn, [role="button"]');
      if (target) {
        setTimeout(() => {
          target.classList.remove('active');
        }, 300);
      }
    }, { passive: true });
  }

  /**
   * Optimize scrolling performance
   */
  optimizeScrolling() {
    // Add momentum scrolling for iOS
    const style = document.createElement('style');
    style.textContent = `
      .scroll-container,
      .table-responsive,
      .overflow-auto {
        -webkit-overflow-scrolling: touch;
        overflow-scrolling: touch;
      }
      
      /* Prevent rubber band scrolling */
      body {
        overscroll-behavior: contain;
      }
    `;
    document.head.appendChild(style);
  }

  /**
   * Prevent zoom on double tap
   */
  preventZoom() {
    let lastTouchEnd = 0;
    document.addEventListener('touchend', (e) => {
      const now = Date.now();
      if (now - lastTouchEnd <= 300) {
        e.preventDefault();
      }
      lastTouchEnd = now;
    }, false);
  }

  /**
   * Setup resize handler
   */
  setupResizeHandler() {
    let resizeTimeout;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        this.currentDevice = this.detectDevice();
        this.handleResize();
      }, 100);
    });
  }

  /**
   * Handle window resize
   */
  handleResize() {
    // Dispatch resize event for components
    window.dispatchEvent(new CustomEvent('deviceUpdate', {
      detail: { device: this.currentDevice }
    }));

    // Adjust table responsiveness
    this.adjustTableResponsiveness();
    
    // Adjust chart sizes
    this.adjustChartSizes();
  }

  /**
   * Adjust table responsiveness
   */
  adjustTableResponsiveness() {
    const tables = document.querySelectorAll('table');
    tables.forEach(table => {
      const wrapper = table.closest('.table-responsive');
      if (wrapper && this.currentDevice.type === 'mobile') {
        // Hide less important columns on mobile
        const hiddenColumns = table.querySelectorAll('.hide-mobile');
        hiddenColumns.forEach(col => {
          col.style.display = 'none';
        });
      }
    });
  }

  /**
   * Adjust chart sizes for mobile
   */
  adjustChartSizes() {
    const charts = document.querySelectorAll('[data-chart], .recharts-wrapper');
    charts.forEach(chart => {
      if (this.currentDevice.type === 'mobile') {
        chart.style.height = '250px';
      } else if (this.currentDevice.type === 'tablet') {
        chart.style.height = '300px';
      } else {
        chart.style.height = '400px';
      }
    });
  }

  /**
   * Optimize forms for mobile
   */
  optimizeForms() {
    const inputs = document.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
      // Add appropriate input types for mobile keyboards
      if (input.name?.includes('email')) {
        input.type = 'email';
      } else if (input.name?.includes('phone')) {
        input.type = 'tel';
      } else if (input.name?.includes('url')) {
        input.type = 'url';
      }

      // Add autocomplete attributes
      if (input.name?.includes('email')) {
        input.autocomplete = 'email';
      } else if (input.name?.includes('name')) {
        input.autocomplete = 'name';
      }
    });
  }

  /**
   * Get mobile optimization status
   */
  getMobileOptimizationStatus() {
    return {
      device: this.currentDevice,
      viewportConfigured: !!document.querySelector('meta[name="viewport"]'),
      touchOptimized: this.currentDevice.isTouch,
      orientationHandling: true,
      swipeGesturesEnabled: this.currentDevice.isTouch,
      touchTargetsOptimized: true
    };
  }

  /**
   * Get mobile performance recommendations
   */
  getMobileRecommendations() {
    const recommendations = [];

    if (this.currentDevice.type === 'mobile') {
      recommendations.push('Optimize images for mobile viewports');
      recommendations.push('Use lazy loading for below-the-fold content');
      recommendations.push('Minimize JavaScript for faster loading');
      recommendations.push('Use touch-friendly button sizes (44px minimum)');
    }

    if (this.currentDevice.pixelRatio > 2) {
      recommendations.push('Provide high-DPI images for sharp displays');
    }

    if (this.currentDevice.isIOS) {
      recommendations.push('Test iOS-specific features like momentum scrolling');
    }

    return recommendations;
  }
}

// Create singleton instance
const mobileOptimization = new MobileOptimization();

// React hook for mobile optimization
export const useMobileOptimization = () => {
  const [device, setDevice] = React.useState(mobileOptimization.currentDevice);

  React.useEffect(() => {
    const handleDeviceUpdate = (e) => {
      setDevice(e.detail.device);
    };

    window.addEventListener('deviceUpdate', handleDeviceUpdate);
    return () => window.removeEventListener('deviceUpdate', handleDeviceUpdate);
  }, []);

  return {
    device,
    isMobile: device.type === 'mobile',
    isTablet: device.type === 'tablet',
    isTouch: device.isTouch,
    orientation: device.orientation
  };
};

// Add to React import
const React = require('react');

export default mobileOptimization;
export { MobileOptimization };

// Export utilities
export const getCurrentDevice = () => mobileOptimization.currentDevice;
export const getMobileOptimizationStatus = () => mobileOptimization.getMobileOptimizationStatus();
export const getMobileRecommendations = () => mobileOptimization.getMobileRecommendations();