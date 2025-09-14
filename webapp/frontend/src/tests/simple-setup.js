import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from 'react';

// Simple setup - only essential mocks
vi.mock('@mui/icons-material', () => {
  const createIconMock = (iconName) => (props) => 
    React.createElement('div', { 
      'data-testid': `${iconName.toLowerCase()}-icon`,
      'data-icon': iconName,
      ...props 
    });

  // Create comprehensive icon mocks - all as named exports
  const iconMocks = {
    // Educational content icons - VideoLibrary first to ensure it's available
    VideoLibrary: createIconMock('VideoLibrary'),
    School: createIconMock('School'),
    Article: createIconMock('Article'),
    MenuBook: createIconMock('MenuBook'),
    BookmarkBorder: createIconMock('BookmarkBorder'),
    
    // Media and interaction icons
    PlayArrow: createIconMock('PlayArrow'),
    Pause: createIconMock('Pause'),
    Stop: createIconMock('Stop'),
    Share: createIconMock('Share'),
    
    // UI and navigation icons
    Home: createIconMock('Home'),
    Dashboard: createIconMock('Dashboard'),
    Settings: createIconMock('Settings'),
    Person: createIconMock('Person'),
    Search: createIconMock('Search'),
    List: createIconMock('List'),
    MoreVert: createIconMock('MoreVert'),
    ArrowDropDown: createIconMock('ArrowDropDown'),
    Close: createIconMock('Close'),
    
    // Status icons
    Check: createIconMock('Check'),
    Error: createIconMock('Error'),
    ErrorOutline: createIconMock('ErrorOutline'),
    Warning: createIconMock('Warning'),
    WarningOutlined: createIconMock('WarningOutlined'),
    Info: createIconMock('Info'),
    InfoOutlined: createIconMock('InfoOutlined'),
    Success: createIconMock('Success'),
    CheckCircle: createIconMock('CheckCircle'),
    CheckCircleOutline: createIconMock('CheckCircleOutline'),
    Refresh: createIconMock('Refresh'),
    
    // Financial and business icons
    AccountBalance: createIconMock('AccountBalance'),
    AttachMoney: createIconMock('AttachMoney'),
    TrendingUp: createIconMock('TrendingUp'),
    TrendingDown: createIconMock('TrendingDown'),
    ShowChart: createIconMock('ShowChart'),
    Assessment: createIconMock('Assessment'),
    Business: createIconMock('Business'),
    
    // Authentication and security
    VpnKey: createIconMock('VpnKey'),
    Login: createIconMock('Login'),
    
    // Content and data icons
    Description: createIconMock('Description'),
    AccessTime: createIconMock('AccessTime'),
    DateRange: createIconMock('DateRange'),
    Folder: createIconMock('Folder'),
    FileDownload: createIconMock('FileDownload'),
    GetApp: createIconMock('GetApp'),
    Preview: createIconMock('Preview'),
    
    // Rating and interaction
    Star: createIconMock('Star'),
    StarBorder: createIconMock('StarBorder'),
    FilterList: createIconMock('FilterList'),
    Visibility: createIconMock('Visibility'),
    Notifications: createIconMock('Notifications'),
    
    // Layout and display
    Fullscreen: createIconMock('Fullscreen'),
    FullscreenExit: createIconMock('FullscreenExit'),
    Expand: createIconMock('Expand'),
    ExpandMore: createIconMock('ExpandMore'),
    ExpandLess: createIconMock('ExpandLess'),
    
    // Analytics and AI
    Psychology: createIconMock('Psychology'),
    Analytics: createIconMock('Analytics'),
    Timeline: createIconMock('Timeline'),
    Public: createIconMock('Public'),
    CalendarToday: createIconMock('CalendarToday'),
    Equalizer: createIconMock('Equalizer'),
    BarChart: createIconMock('BarChart'),
    
    // Actions
    Add: createIconMock('Add'),
    Remove: createIconMock('Remove'),
    Edit: createIconMock('Edit'),
    Delete: createIconMock('Delete'),
    Save: createIconMock('Save'),
    Cancel: createIconMock('Cancel'),
    Send: createIconMock('Send'),
    
    // Additional Dashboard icons
    Bolt: createIconMock('Bolt'),
    Security: createIconMock('Security'),
    Insights: createIconMock('Insights'),
    LocalFireDepartment: createIconMock('LocalFireDepartment'),
    Event: createIconMock('Event'),
    AutoGraph: createIconMock('AutoGraph'),
    Download: createIconMock('Download'),
    Speed: createIconMock('Speed'),
    HorizontalRule: createIconMock('HorizontalRule'),
    
    // Navigation arrows
    ChevronLeft: createIconMock('ChevronLeft'),
    ChevronRight: createIconMock('ChevronRight'),
    ArrowBack: createIconMock('ArrowBack'),
    ArrowForward: createIconMock('ArrowForward'),
    ArrowUpward: createIconMock('ArrowUpward'),
    ArrowDownward: createIconMock('ArrowDownward'),

    // Support and contact icons
    ContactSupport: createIconMock('ContactSupport'),
    HelpOutline: createIconMock('HelpOutline'),
    Support: createIconMock('Support'),
  };

  // Create a proxy to handle any missing icons dynamically
  const iconProxy = new Proxy(iconMocks, {
    get(target, prop) {
      if (target[prop]) return target[prop];
      if (typeof prop === 'string' && /^[A-Z][A-Za-z0-9]*$/.test(prop)) {
        console.warn(`Missing MUI icon: ${prop} - creating dynamic mock`);
        target[prop] = createIconMock(prop);
        return target[prop];
      }
      return target[prop];
    }
  });

  // Return all icons with proxy fallback
  return iconProxy;
});

// Essential environment setup
if (typeof process !== 'undefined') {
  process.env.NODE_ENV = 'test';
}

// Mock localStorage
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn(), clear: vi.fn(), key: vi.fn(), length: 0
  },
  writable: true
});

// Mock ResizeObserver for recharts and MUI components
// ResizeObserver is a constructor function that creates instances with methods
class MockResizeObserver {
  constructor(callback) {
    this.callback = callback;
    this.observe = vi.fn((target) => {
      // Trigger callback to simulate resize
      if (this.callback && typeof this.callback === 'function') {
        const entries = [{
          target,
          contentRect: { width: 100, height: 100 },
          borderBoxSize: [{ inlineSize: 100, blockSize: 100 }],
          contentBoxSize: [{ inlineSize: 100, blockSize: 100 }],
          devicePixelContentBoxSize: [{ inlineSize: 100, blockSize: 100 }]
        }];
        try {
          this.callback(entries, this);
        } catch (e) {
          // Ignore callback errors in tests
        }
      }
    });
    this.unobserve = vi.fn();
    this.disconnect = vi.fn();
  }
}

// Always use the mock implementation for all cases
global.ResizeObserver = MockResizeObserver;
window.ResizeObserver = MockResizeObserver;

// Ensure it works both as constructor and mock function
if (typeof vi !== 'undefined') {
  // Create a function that can be called as constructor or regular function
  const ResizeObserverMock = vi.fn(function(callback) {
    const instance = new MockResizeObserver(callback);
    return instance;
  });
  
  // Add the constructor behavior
  ResizeObserverMock.mockImplementation((callback) => new MockResizeObserver(callback));
  
  global.ResizeObserver = ResizeObserverMock;
  window.ResizeObserver = ResizeObserverMock;
}

// Mock IntersectionObserver - use simple function approach that always works
global.IntersectionObserver = vi.fn(function IntersectionObserver(callback, options) {
  this.callback = callback;
  this.options = options;
  this.observe = vi.fn((target) => {
    // Trigger callback to simulate intersection
    if (this.callback && typeof this.callback === 'function') {
      const entries = [{
        target,
        isIntersecting: true,
        intersectionRatio: 1,
        boundingClientRect: { top: 0, left: 0, bottom: 100, right: 100, width: 100, height: 100 },
        rootBounds: { top: 0, left: 0, bottom: 500, right: 500, width: 500, height: 500 },
        intersectionRect: { top: 0, left: 0, bottom: 100, right: 100, width: 100, height: 100 }
      }];
      try {
        this.callback(entries, this);
      } catch (e) {
        // Ignore callback errors in tests
      }
    }
  });
  this.unobserve = vi.fn();
  this.disconnect = vi.fn();
});

window.IntersectionObserver = global.IntersectionObserver;

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock additional browser APIs that might cause issues
global.fetch = vi.fn();
global.Request = vi.fn();
global.Response = vi.fn();
global.Headers = vi.fn();

// Mock performance API
global.performance = {
  now: vi.fn(() => Date.now()),
  mark: vi.fn(),
  measure: vi.fn(),
  clearMarks: vi.fn(),
  clearMeasures: vi.fn(),
  getEntriesByName: vi.fn(() => []),
  getEntriesByType: vi.fn(() => []),
};

// Mock requestAnimationFrame and cancelAnimationFrame
global.requestAnimationFrame = vi.fn((cb) => setTimeout(cb, 16));
global.cancelAnimationFrame = vi.fn((id) => clearTimeout(id));

// Mock URL API
global.URL = {
  createObjectURL: vi.fn(() => 'mock-object-url'),
  revokeObjectURL: vi.fn(),
};

// Mock Blob API
global.Blob = vi.fn((content, options) => ({
  content,
  options,
  size: content ? content.length : 0,
  type: options?.type || '',
}));

// Mock WebSocket for real-time features
global.WebSocket = vi.fn().mockImplementation(() => ({
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  send: vi.fn(),
  close: vi.fn(),
  readyState: 1, // OPEN
}));

// Suppress React act() warnings and Router warnings in tests (they don't affect functionality)
const originalError = console.error;
const originalWarn = console.warn;

beforeEach(() => {
  console.error = (...args) => {
    if (
      typeof args[0] === 'string' &&
      args[0].includes('Warning: An update to TestComponent inside a test was not wrapped in act')
    ) {
      return;
    }
    originalError.call(console, ...args);
  };
  
  console.warn = (...args) => {
    if (
      typeof args[0] === 'string' &&
      (args[0].includes('React Router Future Flag Warning') ||
       args[0].includes('v7_startTransition') ||
       args[0].includes('v7_relativeSplatPath'))
    ) {
      return;
    }
    originalWarn.call(console, ...args);
  };
});

// Cleanup after each test
afterEach(() => {
  console.error = originalError;
  console.warn = originalWarn;
  cleanup();
});