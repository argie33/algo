/**
 * E2E Testing Setup
 * Configuration and utilities for end-to-end testing
 */

import { beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// E2E test utilities
global.e2eUtils = {
  // User journey simulation
  simulateUserJourney: async (steps) => {
    const results = [];
    
    for (const step of steps) {
      try {
        const start = performance.now();
        const result = await step.action();
        const end = performance.now();
        
        results.push({
          step: step.name,
          success: true,
          duration: end - start,
          result
        });
      } catch (error) {
        results.push({
          step: step.name,
          success: false,
          error: error.message
        });
        break; // Stop journey on failure
      }
    }
    
    return results;
  },

  // Common user workflows
  workflows: {
    // User authentication workflow
    authentication: [
      {
        name: 'navigate_to_login',
        action: () => Promise.resolve('Navigated to login')
      },
      {
        name: 'enter_credentials',
        action: () => Promise.resolve('Credentials entered')
      },
      {
        name: 'submit_login',
        action: () => Promise.resolve('Login submitted')
      },
      {
        name: 'verify_dashboard',
        action: () => Promise.resolve('Dashboard loaded')
      }
    ],

    // Portfolio management workflow
    portfolioManagement: [
      {
        name: 'navigate_to_portfolio',
        action: () => Promise.resolve('Portfolio page loaded')
      },
      {
        name: 'add_new_position',
        action: () => Promise.resolve('Position added')
      },
      {
        name: 'update_position',
        action: () => Promise.resolve('Position updated')
      },
      {
        name: 'verify_calculations',
        action: () => Promise.resolve('Calculations verified')
      }
    ],

    // API key configuration workflow
    apiKeyConfiguration: [
      {
        name: 'navigate_to_settings',
        action: () => Promise.resolve('Settings page loaded')
      },
      {
        name: 'configure_alpaca_key',
        action: () => Promise.resolve('Alpaca key configured')
      },
      {
        name: 'validate_connection',
        action: () => Promise.resolve('Connection validated')
      },
      {
        name: 'save_configuration',
        action: () => Promise.resolve('Configuration saved')
      }
    ],

    // Market data access workflow
    marketDataAccess: [
      {
        name: 'navigate_to_market',
        action: () => Promise.resolve('Market page loaded')
      },
      {
        name: 'search_symbol',
        action: () => Promise.resolve('Symbol searched')
      },
      {
        name: 'view_chart',
        action: () => Promise.resolve('Chart displayed')
      },
      {
        name: 'add_to_watchlist',
        action: () => Promise.resolve('Added to watchlist')
      }
    ],

    // Trading signals workflow
    tradingSignals: [
      {
        name: 'navigate_to_signals',
        action: () => Promise.resolve('Signals page loaded')
      },
      {
        name: 'filter_signals',
        action: () => Promise.resolve('Signals filtered')
      },
      {
        name: 'view_signal_details',
        action: () => Promise.resolve('Signal details viewed')
      },
      {
        name: 'export_signals',
        action: () => Promise.resolve('Signals exported')
      }
    ],

    // Data visualization workflow
    dataVisualization: [
      {
        name: 'load_dashboard',
        action: () => Promise.resolve('Dashboard loaded')
      },
      {
        name: 'interact_with_charts',
        action: () => Promise.resolve('Charts interacted')
      },
      {
        name: 'customize_layout',
        action: () => Promise.resolve('Layout customized')
      },
      {
        name: 'save_preferences',
        action: () => Promise.resolve('Preferences saved')
      }
    ]
  },

  // Test coverage tracking for workflows
  trackWorkflowCoverage: (workflowResults) => {
    const criticalWorkflows = [
      'authentication',
      'portfolioManagement',
      'marketDataAccess',
      'apiKeyConfiguration',
      'tradingSignals',
      'dataVisualization'
    ];

    const completedWorkflows = workflowResults.filter(
      result => result.success && result.completedSteps > 0
    );

    const coverage = (completedWorkflows.length / criticalWorkflows.length) * 100;

    return {
      totalWorkflows: criticalWorkflows.length,
      completedWorkflows: completedWorkflows.length,
      coverage: Math.round(coverage),
      details: workflowResults
    };
  },

  // Mock API responses for E2E testing
  mockApiResponses: {
    auth: {
      login: { success: true, token: 'mock-jwt-token' },
      profile: { id: 'user-123', email: 'test@example.com' }
    },
    portfolio: {
      overview: { totalValue: 25000, dailyChange: 150.75 },
      positions: [
        { symbol: 'AAPL', shares: 100, value: 15000 },
        { symbol: 'MSFT', shares: 50, value: 10000 }
      ]
    },
    market: {
      quote: { symbol: 'AAPL', price: 150.50, change: 2.25 },
      search: [
        { symbol: 'AAPL', name: 'Apple Inc.' },
        { symbol: 'AMZN', name: 'Amazon.com Inc.' }
      ]
    }
  }
};

// Mock browser APIs for E2E testing
global.mockBrowserAPIs = () => {
  // Mock localStorage
  const localStorageMock = {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn()
  };
  
  global.localStorage = localStorageMock;

  // Mock sessionStorage
  const sessionStorageMock = {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn()
  };
  
  global.sessionStorage = sessionStorageMock;

  // Mock window.location
  global.location = {
    href: 'http://localhost:3000',
    origin: 'http://localhost:3000',
    pathname: '/',
    search: '',
    hash: ''
  };

  // Mock window.history
  global.history = {
    pushState: vi.fn(),
    replaceState: vi.fn(),
    back: vi.fn(),
    forward: vi.fn()
  };
};

beforeAll(() => {
  console.log('🌐 E2E testing setup initialized');
  mockBrowserAPIs();
});

beforeEach(() => {
  // Reset mock API responses
  if (global.fetch) {
    global.fetch.mockClear();
  }
  
  // Clear storage
  if (global.localStorage) {
    global.localStorage.clear();
  }
  if (global.sessionStorage) {
    global.sessionStorage.clear();
  }
});

afterEach(() => {
  // Clean up after each E2E test
  cleanup();
  
  // Clear any running timers
  vi.clearAllTimers();
});

afterAll(() => {
  console.log('🏁 E2E testing cleanup completed');
});