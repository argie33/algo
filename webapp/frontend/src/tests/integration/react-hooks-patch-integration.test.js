/**
 * Integration tests for React hooks patch system
 * 
 * Tests the complete integration of the patch system with real React components
 * and ensures it properly handles production useState errors
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React, { useState, useEffect } from 'react';
import { ReactHooksErrorBoundary } from '../../utils/reactHooksPatch';
import { useCustomSyncExternalStore } from '../../hooks/useCustomSyncExternalStore';

// Mock store for testing
class TestStore {
  constructor(initialValue = 'initial') {
    this.value = initialValue;
    this.listeners = new Set();
  }

  subscribe = (callback) => {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  };

  getSnapshot = () => {
    return this.value;
  };

  setValue = (newValue) => {
    this.value = newValue;
    this.listeners.forEach(callback => callback());
  };
}

describe('React Hooks Patch Integration', () => {
  let testStore;
  let originalConsole;

  beforeEach(() => {
    testStore = new TestStore();
    originalConsole = {
      log: console.log,
      warn: console.warn,
      error: console.error
    };
    
    // Mock console to capture logs
    console.log = vi.fn();
    console.warn = vi.fn();
    console.error = vi.fn();
    
    delete window.__REACT_HOOKS_PATCH_ENABLED__;
  });

  afterEach(() => {
    console.log = originalConsole.log;
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
    vi.clearAllMocks();
  });

  it('should integrate custom sync external store with React components', async () => {
    const TestComponent = () => {
      const value = useCustomSyncExternalStore(
        testStore.subscribe,
        testStore.getSnapshot
      );
      
      return React.createElement('div', {
        'data-testid': 'test-value'
      }, `Value: ${value}`);
    };

    render(React.createElement(TestComponent));

    expect(screen.getByTestId('test-value')).toHaveTextContent('Value: initial');

    // Update store value
    testStore.setValue('updated');

    await waitFor(() => {
      expect(screen.getByTestId('test-value')).toHaveTextContent('Value: updated');
    });
  });

  it('should handle component with useState errors using error boundary', () => {
    const ProblematicComponent = () => {
      // Simulate the production useState error
      throw new Error('Cannot read properties of undefined (reading \'useState\')');
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(ProblematicComponent)
      )
    );

    expect(screen.getByText('🔧 React Hooks Error Detected')).toBeInTheDocument();
    expect(window.__REACT_HOOKS_PATCH_ENABLED__).toBe(true);
  });

  it('should allow normal React hooks to work within error boundary', () => {
    const NormalComponent = () => {
      const [count, setCount] = useState(0);
      
      useEffect(() => {
        setCount(1);
      }, []);
      
      return React.createElement('div', {
        'data-testid': 'normal-component'
      }, `Count: ${count}`);
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(NormalComponent)
      )
    );

    expect(screen.getByTestId('normal-component')).toHaveTextContent('Count: 1');
  });

  it('should integrate with complex component hierarchies', async () => {
    const ParentComponent = () => {
      const [parentState, setParentState] = useState('parent');
      
      return React.createElement('div', null, [
        React.createElement('div', {
          key: 'parent',
          'data-testid': 'parent'
        }, parentState),
        React.createElement(ChildWithCustomHook, {
          key: 'child'
        })
      ]);
    };

    const ChildWithCustomHook = () => {
      const storeValue = useCustomSyncExternalStore(
        testStore.subscribe,
        testStore.getSnapshot
      );
      
      return React.createElement('div', {
        'data-testid': 'child'
      }, `Child: ${storeValue}`);
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(ParentComponent)
      )
    );

    expect(screen.getByTestId('parent')).toHaveTextContent('parent');
    expect(screen.getByTestId('child')).toHaveTextContent('Child: initial');

    // Update store
    testStore.setValue('child-updated');

    await waitFor(() => {
      expect(screen.getByTestId('child')).toHaveTextContent('Child: child-updated');
    });
  });

  it('should handle multiple store subscriptions correctly', async () => {
    const store1 = new TestStore('store1');
    const store2 = new TestStore('store2');

    const MultiStoreComponent = () => {
      const value1 = useCustomSyncExternalStore(
        store1.subscribe,
        store1.getSnapshot
      );
      
      const value2 = useCustomSyncExternalStore(
        store2.subscribe,
        store2.getSnapshot
      );
      
      return React.createElement('div', null, [
        React.createElement('div', {
          key: 'store1',
          'data-testid': 'store1'
        }, value1),
        React.createElement('div', {
          key: 'store2',
          'data-testid': 'store2'
        }, value2)
      ]);
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(MultiStoreComponent)
      )
    );

    expect(screen.getByTestId('store1')).toHaveTextContent('store1');
    expect(screen.getByTestId('store2')).toHaveTextContent('store2');

    // Update both stores
    store1.setValue('updated1');
    store2.setValue('updated2');

    await waitFor(() => {
      expect(screen.getByTestId('store1')).toHaveTextContent('updated1');
      expect(screen.getByTestId('store2')).toHaveTextContent('updated2');
    });
  });

  it('should handle store errors without crashing the app', async () => {
    const errorStore = {
      subscribe: vi.fn((callback) => {
        return () => {}; // unsubscribe
      }),
      getSnapshot: vi.fn(() => {
        throw new Error('Store snapshot failed');
      })
    };

    const ErrorStoreComponent = () => {
      const value = useCustomSyncExternalStore(
        errorStore.subscribe,
        errorStore.getSnapshot
      );
      
      return React.createElement('div', {
        'data-testid': 'error-store'
      }, `Value: ${value || 'undefined'}`);
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(ErrorStoreComponent)
      )
    );

    expect(screen.getByTestId('error-store')).toHaveTextContent('Value: undefined');
    expect(console.warn).toHaveBeenCalledWith(
      'useSyncExternalStore: Error in initial getSnapshot:',
      expect.any(Error)
    );
  });

  it('should properly clean up subscriptions on component unmount', () => {
    const unsubscribeMock = vi.fn();
    const mockStore = {
      subscribe: vi.fn(() => unsubscribeMock),
      getSnapshot: vi.fn(() => 'test')
    };

    const TestComponent = () => {
      const value = useCustomSyncExternalStore(
        mockStore.subscribe,
        mockStore.getSnapshot
      );
      
      return React.createElement('div', null, value);
    };

    const { unmount } = render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(TestComponent)
      )
    );

    expect(mockStore.subscribe).toHaveBeenCalledTimes(1);

    unmount();

    expect(unsubscribeMock).toHaveBeenCalledTimes(1);
  });

  it('should maintain performance with frequent store updates', async () => {
    const PerformanceTestComponent = () => {
      const value = useCustomSyncExternalStore(
        testStore.subscribe,
        testStore.getSnapshot
      );
      
      const [renderCount, setRenderCount] = useState(0);
      
      useEffect(() => {
        setRenderCount(prev => prev + 1);
      });
      
      return React.createElement('div', null, [
        React.createElement('div', {
          key: 'value',
          'data-testid': 'perf-value'
        }, `Value: ${value}`),
        React.createElement('div', {
          key: 'renders',
          'data-testid': 'render-count'
        }, `Renders: ${renderCount}`)
      ]);
    };

    render(
      React.createElement(ReactHooksErrorBoundary, null,
        React.createElement(PerformanceTestComponent)
      )
    );

    // Initial render
    expect(screen.getByTestId('perf-value')).toHaveTextContent('Value: initial');

    // Rapid updates
    for (let i = 0; i < 10; i++) {
      testStore.setValue(`update-${i}`);
    }

    await waitFor(() => {
      expect(screen.getByTestId('perf-value')).toHaveTextContent('Value: update-9');
    });

    // Should not have excessive re-renders
    const renderCount = parseInt(screen.getByTestId('render-count').textContent.split(': ')[1]);
    expect(renderCount).toBeLessThan(15); // Allow some tolerance for React's batching
  });
});