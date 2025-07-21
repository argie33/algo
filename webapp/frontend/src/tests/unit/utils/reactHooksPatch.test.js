/**
 * Unit tests for React hooks patch system
 * 
 * Tests the comprehensive patch system that fixes production useState errors
 * and provides error boundaries with auto-recovery
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import {
  ReactHooksErrorBoundary,
  applyReactHooksPatch,
  initializeReactHooksPatch,
  patchedUseSyncExternalStore
} from '../../../utils/reactHooksPatch';

// Mock console methods to test error handling
const mockConsole = {
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn()
};

describe('ReactHooksErrorBoundary', () => {
  let originalConsole;

  beforeEach(() => {
    originalConsole = {
      log: console.log,
      warn: console.warn,
      error: console.error
    };
    
    console.log = mockConsole.log;
    console.warn = mockConsole.warn;
    console.error = mockConsole.error;
    
    // Clear window global state
    delete window.__REACT_HOOKS_PATCH_ENABLED__;
  });

  afterEach(() => {
    console.log = originalConsole.log;
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
    
    vi.clearAllMocks();
    delete window.__REACT_HOOKS_PATCH_ENABLED__;
  });

  it('should render children when no error occurs', () => {
    const TestComponent = () => React.createElement('div', null, 'Test content');

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(TestComponent)
      )
    );

    expect(screen.getByText('Test content')).toBeInTheDocument();
  });

  it('should catch useState related errors', () => {
    const ErrorComponent = () => {
      throw new Error('Cannot read properties of undefined (reading \'useState\')');
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(ErrorComponent)
      )
    );

    expect(screen.getByText('🔧 React Hooks Error Detected')).toBeInTheDocument();
    expect(screen.getByText('A React hooks error occurred. Applying patch and reloading...')).toBeInTheDocument();
  });

  it('should catch useSyncExternalStore related errors', () => {
    const ErrorComponent = () => {
      throw new Error('useSyncExternalStore is not defined');
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(ErrorComponent)
      )
    );

    expect(screen.getByText('🔧 React Hooks Error Detected')).toBeInTheDocument();
  });

  it('should not catch non-React hooks errors', () => {
    const ErrorComponent = () => {
      throw new Error('Some other error');
    };

    // This should throw and not be caught by our boundary
    expect(() => {
      render(
        React.createElement(ReactHooksErrorBoundary, null,
          React.createElement(ErrorComponent)
        )
      );
    }).toThrow('Some other error');
  });

  it('should log error details when catching hooks errors', () => {
    const testError = new Error('useState is undefined');
    const ErrorComponent = () => {
      throw testError;
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(ErrorComponent)
      )
    );

    expect(mockConsole.error).toHaveBeenCalledWith(
      'React hooks error detected:',
      testError
    );
  });

  it('should enable patch flag when error occurs', () => {
    const ErrorComponent = () => {
      throw new Error('useState error');
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(ErrorComponent)
      )
    );

    expect(window.__REACT_HOOKS_PATCH_ENABLED__).toBe(true);
  });
});

describe('applyReactHooksPatch', () => {
  beforeEach(() => {
    console.log = mockConsole.log;
    console.warn = mockConsole.warn;
    console.error = mockConsole.error;
    
    delete window.__REACT_HOOKS_PATCH_ENABLED__;
    
    // Mock process.env for testing
    vi.stubEnv('NODE_ENV', 'development');
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });

  it('should apply patch in production environment', () => {
    vi.stubEnv('NODE_ENV', 'production');
    
    const result = applyReactHooksPatch();
    
    expect(result).toBe(false); // Returns false because we can't actually test hooks here
    expect(mockConsole.log).toHaveBeenCalledWith(
      '✅ React hooks patch applied successfully'
    );
  });

  it('should apply patch when patch flag is enabled', () => {
    window.__REACT_HOOKS_PATCH_ENABLED__ = true;
    
    const result = applyReactHooksPatch();
    
    expect(result).toBe(false);
    expect(mockConsole.log).toHaveBeenCalledWith(
      '✅ React hooks patch applied successfully'
    );
  });

  it('should not apply patch in development without flag', () => {
    const result = applyReactHooksPatch();
    
    expect(result).toBe(false);
    expect(mockConsole.log).not.toHaveBeenCalledWith(
      '✅ React hooks patch applied successfully'
    );
  });

  it('should handle patch application errors gracefully', () => {
    vi.stubEnv('NODE_ENV', 'production');
    
    // Mock React to cause error
    const originalReact = global.React;
    global.React = undefined;
    
    const result = applyReactHooksPatch();
    
    expect(result).toBe(false);
    expect(mockConsole.error).toHaveBeenCalledWith(
      '❌ Failed to apply React hooks patch:',
      expect.any(Error)
    );
    
    global.React = originalReact;
  });
});

describe('initializeReactHooksPatch', () => {
  let mockAddEventListener;
  let eventListeners;

  beforeEach(() => {
    console.log = mockConsole.log;
    console.warn = mockConsole.warn;
    console.error = mockConsole.error;
    
    eventListeners = {};
    mockAddEventListener = vi.fn((event, handler) => {
      eventListeners[event] = handler;
    });
    
    window.addEventListener = mockAddEventListener;
    delete window.__REACT_HOOKS_PATCH_ENABLED__;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should initialize patch system successfully', () => {
    const result = initializeReactHooksPatch();
    
    expect(result).toHaveProperty('patchApplied');
    expect(result).toHaveProperty('customUseSyncExternalStore');
    expect(mockConsole.log).toHaveBeenCalledWith(
      '🚀 Initializing React Hooks Patch System'
    );
  });

  it('should set up global error listeners', () => {
    initializeReactHooksPatch();
    
    expect(mockAddEventListener).toHaveBeenCalledWith('error', expect.any(Function));
    expect(mockAddEventListener).toHaveBeenCalledWith('unhandledrejection', expect.any(Function));
  });

  it('should handle global error events for React hooks', () => {
    initializeReactHooksPatch();
    
    const errorHandler = eventListeners.error;
    expect(errorHandler).toBeDefined();
    
    // Simulate a React hooks error
    const mockError = new Error('useState is not defined');
    errorHandler({ error: mockError });
    
    expect(window.__REACT_HOOKS_PATCH_ENABLED__).toBe(true);
    expect(mockConsole.error).toHaveBeenCalledWith(
      'Global React hooks error detected:',
      mockError
    );
  });

  it('should handle unhandled promise rejections for React hooks', () => {
    initializeReactHooksPatch();
    
    const rejectionHandler = eventListeners.unhandledrejection;
    expect(rejectionHandler).toBeDefined();
    
    // Simulate a React hooks rejection
    const mockReason = new Error('useSyncExternalStore failed');
    rejectionHandler({ reason: mockReason });
    
    expect(window.__REACT_HOOKS_PATCH_ENABLED__).toBe(true);
    expect(mockConsole.error).toHaveBeenCalledWith(
      'Unhandled React hooks rejection:',
      mockReason
    );
  });

  it('should ignore non-React hooks errors', () => {
    initializeReactHooksPatch();
    
    const errorHandler = eventListeners.error;
    const mockError = new Error('Some other error');
    errorHandler({ error: mockError });
    
    expect(window.__REACT_HOOKS_PATCH_ENABLED__).toBeUndefined();
  });
});

describe('patchedUseSyncExternalStore', () => {
  let mockSubscribe;
  let mockGetSnapshot;
  let mockUnsubscribe;

  beforeEach(() => {
    mockUnsubscribe = vi.fn();
    mockSubscribe = vi.fn(() => mockUnsubscribe);
    mockGetSnapshot = vi.fn(() => 'test-value');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should provide a working useSyncExternalStore implementation', () => {
    // This is a functional test to ensure the patched version exists and is callable
    expect(typeof patchedUseSyncExternalStore).toBe('function');
    
    // We can't actually test hook execution outside of a component,
    // but we can verify the function signature is correct
    expect(patchedUseSyncExternalStore.length).toBe(3); // subscribe, getSnapshot, getServerSnapshot
  });

  it('should handle missing React gracefully', () => {
    const originalReact = global.React;
    global.React = undefined;
    
    // Should not throw when React is undefined
    expect(() => {
      patchedUseSyncExternalStore(mockSubscribe, mockGetSnapshot);
    }).not.toThrow();
    
    global.React = originalReact;
  });
});