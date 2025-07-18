/**
 * Accessibility Utilities - WCAG 2.1 compliance and a11y enhancements
 * Provides comprehensive accessibility features for all users
 */

class AccessibilityUtils {
  constructor() {
    this.focusableElements = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
      '[contenteditable="true"]'
    ].join(', ');

    this.preferences = this.loadUserPreferences();
    this.announcer = this.createScreenReaderAnnouncer();
    
    this.initializeAccessibility();
  }

  /**
   * Initialize accessibility features
   */
  initializeAccessibility() {
    this.setupKeyboardNavigation();
    this.setupFocusManagement();
    this.setupScreenReaderSupport();
    this.setupColorContrastChecking();
    this.setupMotionPreferences();
    this.addSkipLinks();
  }

  /**
   * Setup keyboard navigation
   */
  setupKeyboardNavigation() {
    document.addEventListener('keydown', (event) => {
      // Escape key handling
      if (event.key === 'Escape') {
        this.handleEscape();
      }

      // Tab navigation improvements
      if (event.key === 'Tab') {
        this.handleTabNavigation(event);
      }

      // Arrow key navigation for custom components
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) {
        this.handleArrowNavigation(event);
      }

      // Enter and Space for activation
      if (event.key === 'Enter' || event.key === ' ') {
        this.handleActivation(event);
      }
    });

    // Show focus indicators for keyboard users only
    document.addEventListener('mousedown', () => {
      document.body.classList.add('using-mouse');
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Tab') {
        document.body.classList.remove('using-mouse');
      }
    });
  }

  /**
   * Setup focus management
   */
  setupFocusManagement() {
    // Track focus for better UX
    let lastFocusedElement = null;

    document.addEventListener('focusin', (event) => {
      lastFocusedElement = event.target;
      this.updateFocusIndicator(event.target);
    });

    // Restore focus when modals close
    window.addEventListener('modal-closed', () => {
      if (lastFocusedElement && document.contains(lastFocusedElement)) {
        lastFocusedElement.focus();
      }
    });
  }

  /**
   * Create screen reader announcer
   */
  createScreenReaderAnnouncer() {
    const announcer = document.createElement('div');
    announcer.setAttribute('aria-live', 'polite');
    announcer.setAttribute('aria-atomic', 'true');
    announcer.style.cssText = `
      position: absolute !important;
      left: -10000px !important;
      width: 1px !important;
      height: 1px !important;
      overflow: hidden !important;
    `;
    document.body.appendChild(announcer);
    return announcer;
  }

  /**
   * Setup screen reader support
   */
  setupScreenReaderSupport() {
    // Add landmark roles to improve navigation
    this.addLandmarkRoles();
    
    // Enhance dynamic content announcements
    this.setupLiveRegions();
    
    // Add descriptive labels to interactive elements
    this.enhanceInteractiveElements();
  }

  /**
   * Add landmark roles
   */
  addLandmarkRoles() {
    // Add main landmark if not present
    if (!document.querySelector('main, [role="main"]')) {
      const mainContent = document.querySelector('#root > div') || document.querySelector('#root');
      if (mainContent) {
        mainContent.setAttribute('role', 'main');
        mainContent.setAttribute('aria-label', 'Main content');
      }
    }

    // Add navigation landmark
    const nav = document.querySelector('nav');
    if (nav && !nav.getAttribute('role')) {
      nav.setAttribute('role', 'navigation');
      nav.setAttribute('aria-label', 'Main navigation');
    }
  }

  /**
   * Setup live regions for dynamic content
   */
  setupLiveRegions() {
    // Create status announcer for important updates
    const statusAnnouncer = document.createElement('div');
    statusAnnouncer.id = 'status-announcer';
    statusAnnouncer.setAttribute('aria-live', 'assertive');
    statusAnnouncer.setAttribute('aria-atomic', 'true');
    statusAnnouncer.style.cssText = `
      position: absolute !important;
      left: -10000px !important;
      width: 1px !important;
      height: 1px !important;
      overflow: hidden !important;
    `;
    document.body.appendChild(statusAnnouncer);
  }

  /**
   * Enhance interactive elements
   */
  enhanceInteractiveElements() {
    // Add proper labels to buttons without text
    document.querySelectorAll('button:not([aria-label]):not([aria-labelledby])').forEach(button => {
      if (!button.textContent.trim()) {
        const icon = button.querySelector('svg, i, [class*="icon"]');
        if (icon) {
          button.setAttribute('aria-label', this.generateButtonLabel(button));
        }
      }
    });

    // Add proper labels to form inputs
    document.querySelectorAll('input:not([aria-label]):not([aria-labelledby])').forEach(input => {
      if (!document.querySelector(`label[for="${input.id}"]`)) {
        const placeholder = input.getAttribute('placeholder');
        if (placeholder) {
          input.setAttribute('aria-label', placeholder);
        }
      }
    });
  }

  /**
   * Generate button label from context
   */
  generateButtonLabel(button) {
    const classes = button.className;
    const parent = button.closest('[data-testid], [aria-label], [title]');
    
    if (classes.includes('close')) return 'Close';
    if (classes.includes('menu')) return 'Open menu';
    if (classes.includes('search')) return 'Search';
    if (classes.includes('refresh')) return 'Refresh';
    if (classes.includes('edit')) return 'Edit';
    if (classes.includes('delete')) return 'Delete';
    if (classes.includes('save')) return 'Save';
    if (classes.includes('cancel')) return 'Cancel';
    
    if (parent) {
      const parentLabel = parent.getAttribute('aria-label') || parent.getAttribute('title');
      if (parentLabel) return `Action for ${parentLabel}`;
    }
    
    return 'Button';
  }

  /**
   * Setup color contrast checking
   */
  setupColorContrastChecking() {
    if (process.env.NODE_ENV === 'development') {
      this.checkColorContrast();
    }
  }

  /**
   * Check color contrast ratios
   */
  checkColorContrast() {
    const textElements = document.querySelectorAll('p, span, a, button, h1, h2, h3, h4, h5, h6, label');
    
    textElements.forEach(element => {
      if (element.textContent.trim()) {
        const contrast = this.calculateContrast(element);
        if (contrast < 4.5) {
          console.warn(`🎨 Low contrast detected (${contrast.toFixed(2)}:1):`, element);
        }
      }
    });
  }

  /**
   * Calculate contrast ratio between text and background
   */
  calculateContrast(element) {
    const styles = window.getComputedStyle(element);
    const textColor = this.getRGB(styles.color);
    const backgroundColor = this.getRGB(styles.backgroundColor);
    
    if (!textColor || !backgroundColor) return 21; // Assume good contrast if can't calculate
    
    const textLum = this.getLuminance(textColor);
    const bgLum = this.getLuminance(backgroundColor);
    
    const lighter = Math.max(textLum, bgLum);
    const darker = Math.min(textLum, bgLum);
    
    return (lighter + 0.05) / (darker + 0.05);
  }

  /**
   * Convert color string to RGB values
   */
  getRGB(colorStr) {
    const match = colorStr.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])];
    }
    return null;
  }

  /**
   * Calculate relative luminance
   */
  getLuminance([r, g, b]) {
    const [rs, gs, bs] = [r, g, b].map(c => {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  }

  /**
   * Setup motion preferences
   */
  setupMotionPreferences() {
    // Respect prefers-reduced-motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    
    if (prefersReducedMotion.matches) {
      document.body.classList.add('reduce-motion');
      this.disableAnimations();
    }
    
    prefersReducedMotion.addListener(() => {
      if (prefersReducedMotion.matches) {
        document.body.classList.add('reduce-motion');
        this.disableAnimations();
      } else {
        document.body.classList.remove('reduce-motion');
      }
    });
  }

  /**
   * Disable animations for users who prefer reduced motion
   */
  disableAnimations() {
    const style = document.createElement('style');
    style.textContent = `
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
    `;
    document.head.appendChild(style);
  }

  /**
   * Add skip links for keyboard navigation
   */
  addSkipLinks() {
    if (document.querySelector('.skip-links')) return;
    
    const skipLinks = document.createElement('div');
    skipLinks.className = 'skip-links';
    skipLinks.innerHTML = `
      <a href="#main-content" class="skip-link">Skip to main content</a>
      <a href="#navigation" class="skip-link">Skip to navigation</a>
    `;
    
    const style = document.createElement('style');
    style.textContent = `
      .skip-links {
        position: absolute;
        top: 0;
        left: 0;
        z-index: 9999;
      }
      .skip-link {
        position: absolute;
        top: -40px;
        left: 6px;
        background: #000;
        color: #fff;
        padding: 8px;
        text-decoration: none;
        font-size: 14px;
        border-radius: 0 0 4px 4px;
        transition: top 0.3s;
      }
      .skip-link:focus {
        top: 0;
      }
    `;
    
    document.head.appendChild(style);
    document.body.insertBefore(skipLinks, document.body.firstChild);
  }

  /**
   * Handle keyboard events
   */
  handleEscape() {
    // Close any open modals or dropdowns
    const openModals = document.querySelectorAll('[role="dialog"][aria-hidden="false"], .modal.open');
    openModals.forEach(modal => {
      const closeButton = modal.querySelector('[aria-label*="close"], .close-button');
      if (closeButton) {
        closeButton.click();
      }
    });

    // Close dropdowns
    const openDropdowns = document.querySelectorAll('[aria-expanded="true"]');
    openDropdowns.forEach(dropdown => {
      dropdown.setAttribute('aria-expanded', 'false');
    });
  }

  handleTabNavigation(event) {
    const modal = document.querySelector('[role="dialog"]:not([aria-hidden="true"])');
    if (modal) {
      this.trapFocus(modal, event);
    }
  }

  handleArrowNavigation(event) {
    const target = event.target;
    const role = target.getAttribute('role');
    
    // Handle listbox, menu, and tablist navigation
    if (['listbox', 'menu', 'tablist'].includes(role)) {
      event.preventDefault();
      this.navigateWithArrows(target, event.key);
    }
  }

  handleActivation(event) {
    const target = event.target;
    const role = target.getAttribute('role');
    
    // Handle custom interactive elements
    if (['button', 'tab', 'option'].includes(role) && !target.disabled) {
      if (event.key === ' ') {
        event.preventDefault();
      }
      target.click();
    }
  }

  /**
   * Trap focus within modal
   */
  trapFocus(modal, event) {
    const focusableElements = modal.querySelectorAll(this.focusableElements);
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement.focus();
    } else if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement.focus();
    }
  }

  /**
   * Navigate with arrow keys
   */
  navigateWithArrows(container, key) {
    const items = container.querySelectorAll('[role="option"], [role="tab"], [role="menuitem"]');
    const currentIndex = Array.from(items).indexOf(document.activeElement);
    let nextIndex;

    switch (key) {
      case 'ArrowDown':
      case 'ArrowRight':
        nextIndex = (currentIndex + 1) % items.length;
        break;
      case 'ArrowUp':
      case 'ArrowLeft':
        nextIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
        break;
      default:
        return;
    }

    items[nextIndex].focus();
  }

  /**
   * Update focus indicator
   */
  updateFocusIndicator(element) {
    // Remove existing focus indicators
    document.querySelectorAll('.custom-focus').forEach(el => {
      el.classList.remove('custom-focus');
    });

    // Add focus indicator to current element
    element.classList.add('custom-focus');
  }

  /**
   * Announce to screen readers
   */
  announce(message, priority = 'polite') {
    const announcer = priority === 'assertive' 
      ? document.getElementById('status-announcer') 
      : this.announcer;
    
    if (announcer) {
      announcer.textContent = '';
      setTimeout(() => {
        announcer.textContent = message;
      }, 100);
    }
  }

  /**
   * Load user accessibility preferences
   */
  loadUserPreferences() {
    try {
      const stored = localStorage.getItem('a11y-preferences');
      return stored ? JSON.parse(stored) : {
        highContrast: false,
        largeText: false,
        reducedMotion: false,
        screenReader: false
      };
    } catch (error) {
      return {
        highContrast: false,
        largeText: false,
        reducedMotion: false,
        screenReader: false
      };
    }
  }

  /**
   * Save user accessibility preferences
   */
  saveUserPreferences(preferences) {
    this.preferences = { ...this.preferences, ...preferences };
    try {
      localStorage.setItem('a11y-preferences', JSON.stringify(this.preferences));
      this.applyUserPreferences();
    } catch (error) {
      console.error('Failed to save accessibility preferences:', error);
    }
  }

  /**
   * Apply user accessibility preferences
   */
  applyUserPreferences() {
    const { highContrast, largeText, reducedMotion } = this.preferences;

    document.body.classList.toggle('high-contrast', highContrast);
    document.body.classList.toggle('large-text', largeText);
    document.body.classList.toggle('reduce-motion', reducedMotion);

    if (highContrast || largeText || reducedMotion) {
      this.addAccessibilityStyles();
    }
  }

  /**
   * Add accessibility-specific styles
   */
  addAccessibilityStyles() {
    if (document.getElementById('a11y-styles')) return;

    const style = document.createElement('style');
    style.id = 'a11y-styles';
    style.textContent = `
      /* High contrast mode */
      .high-contrast {
        filter: contrast(1.2);
      }
      .high-contrast button, .high-contrast input, .high-contrast select {
        border: 2px solid #000 !important;
      }
      
      /* Large text mode */
      .large-text {
        font-size: 120% !important;
      }
      .large-text * {
        line-height: 1.6 !important;
      }
      
      /* Custom focus indicators */
      .custom-focus {
        outline: 3px solid #005fcc !important;
        outline-offset: 2px !important;
      }
      
      /* Hide focus for mouse users */
      .using-mouse *:focus {
        outline: none !important;
      }
    `;
    
    document.head.appendChild(style);
  }

  /**
   * Get accessibility audit report
   */
  getAccessibilityAudit() {
    const issues = [];
    
    // Check for missing alt text
    document.querySelectorAll('img:not([alt])').forEach(img => {
      issues.push({
        type: 'missing-alt-text',
        element: img,
        message: 'Image missing alt text'
      });
    });

    // Check for missing form labels
    document.querySelectorAll('input:not([aria-label]):not([aria-labelledby])').forEach(input => {
      if (!document.querySelector(`label[for="${input.id}"]`)) {
        issues.push({
          type: 'missing-form-label',
          element: input,
          message: 'Form input missing label'
        });
      }
    });

    // Check for low contrast
    // This would be more comprehensive in a real implementation
    
    return {
      timestamp: new Date().toISOString(),
      issuesFound: issues.length,
      issues,
      score: Math.max(0, 100 - (issues.length * 10))
    };
  }
}

// Create singleton instance
const accessibilityUtils = new AccessibilityUtils();

// React hook for accessibility features
export const useAccessibility = () => {
  const announce = React.useCallback((message, priority) => {
    accessibilityUtils.announce(message, priority);
  }, []);

  const savePreferences = React.useCallback((prefs) => {
    accessibilityUtils.saveUserPreferences(prefs);
  }, []);

  return {
    announce,
    savePreferences,
    preferences: accessibilityUtils.preferences,
    audit: accessibilityUtils.getAccessibilityAudit.bind(accessibilityUtils)
  };
};

// Add to React import
const React = require('react');

export default accessibilityUtils;
export { AccessibilityUtils };

// Export utilities
export const announce = (message, priority) => 
  accessibilityUtils.announce(message, priority);

export const getAccessibilityAudit = () => 
  accessibilityUtils.getAccessibilityAudit();