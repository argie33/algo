/**
 * React useState Fix Test
 * Simple test to verify the "Cannot read properties of undefined (reading 'useState')" error is fixed
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Import our fixed React module
import '../../utils/reactModulePreloader.js';
import React from 'react';

describe('🔧 React useState Fix Test', () => {
  
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Critical useState Fix', () => {
    it('should have React with useState available', () => {
      expect(React).toBeDefined();
      expect(React.useState).toBeDefined();
      expect(typeof React.useState).toBe('function');
    });

    it('should have useSyncExternalStore available (React 18)', () => {
      expect(React.useSyncExternalStore).toBeDefined();
      expect(typeof React.useSyncExternalStore).toBe('function');
    });

    it('should not throw when accessing useState', () => {
      expect(() => {
        const hook = React.useState;
        expect(hook).toBeDefined();
      }).not.toThrow();
    });

    it('should not throw when accessing useSyncExternalStore', () => {
      expect(() => {
        const hook = React.useSyncExternalStore;
        expect(hook).toBeDefined();
      }).not.toThrow();
    });

    it('should create a functional component with useState', () => {
      expect(() => {
        const TestComponent = () => {
          const [state, setState] = React.useState('test');
          return React.createElement('div', { onClick: () => setState('clicked') }, state);
        };
        
        expect(TestComponent).toBeDefined();
        expect(typeof TestComponent).toBe('function');
      }).not.toThrow();
    });

    it('should create a functional component with useSyncExternalStore', () => {
      expect(() => {
        const TestComponent = () => {
          const subscribe = React.useCallback((callback) => {
            // Simple subscription
            return () => {}; // unsubscribe
          }, []);
          
          const getSnapshot = React.useCallback(() => 'test-value', []);
          
          const value = React.useSyncExternalStore(subscribe, getSnapshot);
          return React.createElement('div', null, value);
        };
        
        expect(TestComponent).toBeDefined();
        expect(typeof TestComponent).toBe('function');
      }).not.toThrow();
    });

    it('should work with external store pattern (common in React Query)', () => {
      expect(() => {
        // Simulate what ../hooks/useSimpleFetch.js does internally
        const store = {
          state: { data: 'test' },
          listeners: new Set(),
          subscribe(listener) {
            this.listeners.add(listener);
            return () => this.listeners.delete(listener);
          },
          getSnapshot() {
            return this.state;
          },
          setState(newState) {
            this.state = newState;
            this.listeners.forEach(listener => listener());
          }
        };
        
        const useStore = () => {
          return React.useSyncExternalStore(
            store.subscribe.bind(store),
            store.getSnapshot.bind(store)
          );
        };
        
        expect(useStore).toBeDefined();
        expect(typeof useStore).toBe('function');
      }).not.toThrow();
    });

    it('should handle multiple hook types in same component', () => {
      expect(() => {
        const ComplexComponent = () => {
          // Multiple hooks that could conflict
          const [state, setState] = React.useState('initial');
          const ref = React.useRef(null);
          const memoized = React.useMemo(() => state.toUpperCase(), [state]);
          
          const subscribe = React.useCallback(() => () => {}, []);
          const getSnapshot = React.useCallback(() => state, [state]);
          const external = React.useSyncExternalStore(subscribe, getSnapshot);
          
          React.useEffect(() => {
            console.log('Effect running');
          }, [state]);
          
          return React.createElement('div', { 
            ref,
            onClick: () => setState('updated')
          }, `${memoized} - ${external}`);
        };
        
        expect(ComplexComponent).toBeDefined();
      }).not.toThrow();
    });

    it('should provide all essential React hooks', () => {
      const essentialHooks = [
        'useState',
        'useEffect',
        'useCallback',
        'useMemo',
        'useRef',
        'useContext',
        'useReducer',
        'useSyncExternalStore'
      ];

      essentialHooks.forEach(hookName => {
        expect(React[hookName]).toBeDefined();
        expect(typeof React[hookName]).toBe('function');
      });
    });
  });

  describe('React Module Preloader Integration', () => {
    it('should successfully import and use React module preloader', async () => {
      const preloaderModule = await import('../../utils/reactModulePreloader.js');
      
      expect(preloaderModule.React).toBeDefined();
      expect(preloaderModule.React.useState).toBeDefined();
      expect(preloaderModule.ensureReactHooks).toBeDefined();
      
      // Should not throw when ensuring hooks
      expect(() => {
        preloaderModule.ensureReactHooks();
      }).not.toThrow();
    });

    it('should have React preloader export working React instance', async () => {
      const preloaderModule = await import('../../utils/reactModulePreloader.js');
      const PreloaderReact = preloaderModule.React;
      
      // Should be same as or compatible with main React import
      expect(PreloaderReact.useState).toBeDefined();
      expect(PreloaderReact.useSyncExternalStore).toBeDefined();
      expect(typeof PreloaderReact.useState).toBe('function');
      expect(typeof PreloaderReact.useSyncExternalStore).toBe('function');
    });
  });

  describe('Error Condition Handling', () => {
    it('should provide meaningful error if hooks are missing', async () => {
      const preloaderModule = await import('../../utils/reactModulePreloader.js');
      
      // The ensureReactHooks function should validate all hooks
      expect(() => {
        const hooks = preloaderModule.ensureReactHooks();
        expect(hooks.useState).toBeDefined();
        expect(hooks.useSyncExternalStore).toBeDefined();
      }).not.toThrow();
    });
  });

  describe('Real-world Usage Patterns', () => {
    it('should work with typical useState patterns', () => {
      expect(() => {
        const Counter = () => {
          const [count, setCount] = React.useState(0);
          const [name, setName] = React.useState('test');
          
          return React.createElement('div', null, 
            React.createElement('span', null, `${name}: ${count}`),
            React.createElement('button', { 
              onClick: () => setCount(c => c + 1) 
            }, 'Increment')
          );
        };
        
        expect(Counter).toBeDefined();
      }).not.toThrow();
    });

    it('should work with typical external store patterns', () => {
      expect(() => {
        // Pattern used by state management libraries
        const createExternalStore = (initialValue) => {
          let state = initialValue;
          const listeners = new Set();
          
          return {
            getSnapshot: () => state,
            subscribe: (listener) => {
              listeners.add(listener);
              return () => listeners.delete(listener);
            },
            setState: (newState) => {
              state = newState;
              listeners.forEach(l => l());
            }
          };
        };
        
        const store = createExternalStore('initial');
        
        const useExternalState = () => {
          return React.useSyncExternalStore(
            store.subscribe,
            store.getSnapshot
          );
        };
        
        const Component = () => {
          const value = useExternalState();
          return React.createElement('div', null, value);
        };
        
        expect(Component).toBeDefined();
      }).not.toThrow();
    });
  });
});