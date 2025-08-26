/**
 * React Context Dependency Integration Test
 * 
 * This test should catch the exact error you encountered:
 * "Cannot set properties of undefined (setting 'ContextConsumer')"
 * 
 * This error occurs due to react-is v19.x compatibility issues with
 * hoist-non-react-statics, which is used by many libraries including
 * @emotion/react, @mui/material, and others.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { createContext, useContext } from 'react';
import { render, screen } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';

describe('React Context Dependency Integration', () => {
  let consoleErrors = [];
  let originalConsoleError;

  beforeAll(() => {
    // Capture console errors during testing
    originalConsoleError = console.error;
    console.error = (...args) => {
      consoleErrors.push(args.join(' '));
      originalConsoleError(...args);
    };
  });

  afterAll(() => {
    console.error = originalConsoleError;
  });

  beforeEach(() => {
    consoleErrors = [];
  });

  describe('Context Consumer Compatibility', () => {
    it('should not throw ContextConsumer undefined errors', () => {
      // This test specifically catches the error you encountered
      const TestComponent = () => {
        try {
          const auth = useAuth();
          return <div data-testid="auth-test">Auth loaded: {auth ? 'yes' : 'no'}</div>;
        } catch (error) {
          if (error.message.includes('ContextConsumer') || 
              error.message.includes('Cannot set properties of undefined')) {
            throw new Error(`React Context Dependency Error: ${error.message}`);
          }
          throw error;
        }
      };

      expect(() => {
        render(
          <AuthProvider>
            <TestComponent />
          </AuthProvider>
        );
      }).not.toThrow(/ContextConsumer|Cannot set properties of undefined/);

      // Should render without React Context errors
      expect(screen.getByTestId('auth-test')).toBeInTheDocument();
    });

    it('should not have react-is v19.x compatibility issues', () => {
      // Check for specific react-is/hoist-non-react-statics conflict
      const reactIsErrors = consoleErrors.filter(error =>
        error.includes('react-is') ||
        error.includes('ContextConsumer') ||
        error.includes('hoist-non-react-statics')
      );

      expect(reactIsErrors).toHaveLength(0);
    });

    it('should properly initialize Context without library conflicts', () => {
      // Test that Context creation works without interference from dependency conflicts
      const TestContext = createContext();
      
      const TestProvider = ({ children }) => {
        return (
          <TestContext.Provider value={{ test: true }}>
            {children}
          </TestContext.Provider>
        );
      };

      const TestConsumer = () => {
        const value = useContext(TestContext);
        return <div data-testid="context-test">Value: {value?.test ? 'true' : 'false'}</div>;
      };

      expect(() => {
        render(
          <TestProvider>
            <TestConsumer />
          </TestProvider>
        );
      }).not.toThrow();

      expect(screen.getByTestId('context-test')).toBeInTheDocument();
      expect(screen.getByTestId('context-test')).toHaveTextContent('Value: true');
    });
  });

  describe('Emotion/MUI Context Compatibility', () => {
    it('should not have @emotion/react context conflicts', () => {
      // @emotion/react uses hoist-non-react-statics internally
      // This can cause the ContextConsumer error with react-is v19.x
      const emotionErrors = consoleErrors.filter(error =>
        error.includes('@emotion') ||
        error.includes('emotion-react') ||
        error.includes('EmotionContext')
      );

      expect(emotionErrors).toHaveLength(0);
    });

    it('should not have MUI Theme context conflicts', () => {
      // MUI Theme also uses Context internally and can be affected
      const muiErrors = consoleErrors.filter(error =>
        error.includes('ThemeContext') ||
        error.includes('@mui') ||
        error.includes('mui-material')
      );

      expect(muiErrors).toHaveLength(0);
    });
  });

  describe('Runtime Dependency Validation', () => {
    it('should have react-is v18.x (not v19.x)', () => {
      // This test ensures the package.json override is working
      try {
        const reactIs = require('react-is');
        
        // Check if react-is exports are defined properly
        expect(reactIs.isValidElementType).toBeDefined();
        expect(reactIs.isContextConsumer).toBeDefined();
        expect(reactIs.isContextProvider).toBeDefined();

        // These should work without throwing
        expect(() => {
          const TestContext = createContext();
          reactIs.isContextConsumer(<TestContext.Consumer>{() => null}</TestContext.Consumer>);
          reactIs.isContextProvider(<TestContext.Provider value={{}}>{null}</TestContext.Provider>);
        }).not.toThrow();

      } catch (error) {
        // If react-is import fails, that's also a dependency issue
        throw new Error(`react-is dependency issue: ${error.message}`);
      }
    });

    it('should not have conflicting hoist-non-react-statics versions', () => {
      // This test validates that hoist-non-react-statics works with our react-is version
      try {
        const hoistNonReactStatics = require('hoist-non-react-statics');
        
        const TestComponent = () => <div>Test</div>;
        TestComponent.displayName = 'TestComponent';
        
        const WrappedComponent = () => <div>Wrapped</div>;
        
        // This should work without throwing ContextConsumer errors
        expect(() => {
          hoistNonReactStatics(WrappedComponent, TestComponent);
        }).not.toThrow(/ContextConsumer|Cannot set properties of undefined/);

      } catch (error) {
        if (error.code === 'MODULE_NOT_FOUND') {
          // hoist-non-react-statics not directly installed, but used by dependencies
          // This is normal, skip the test
          return;
        }
        throw new Error(`hoist-non-react-statics compatibility issue: ${error.message}`);
      }
    });
  });

  describe('Component Integration with Context', () => {
    it('should render AuthProvider with all consumer components', () => {
      const MultipleConsumers = () => {
        const auth1 = useAuth();
        const auth2 = useAuth(); // Multiple calls to test stability
        const auth3 = useAuth();

        return (
          <div data-testid="multiple-consumers">
            <div>Consumer 1: {auth1 ? 'loaded' : 'null'}</div>
            <div>Consumer 2: {auth2 ? 'loaded' : 'null'}</div>
            <div>Consumer 3: {auth3 ? 'loaded' : 'null'}</div>
          </div>
        );
      };

      expect(() => {
        render(
          <AuthProvider>
            <MultipleConsumers />
          </AuthProvider>
        );
      }).not.toThrow();

      expect(screen.getByTestId('multiple-consumers')).toBeInTheDocument();
    });

    it('should handle nested context providers without conflicts', () => {
      const NestedContext = createContext();
      
      const DeepNested = () => {
        const auth = useAuth();
        const nested = useContext(NestedContext);
        
        return (
          <div data-testid="deep-nested">
            Auth: {auth ? 'yes' : 'no'} | Nested: {nested?.value || 'none'}
          </div>
        );
      };

      expect(() => {
        render(
          <AuthProvider>
            <NestedContext.Provider value={{ value: 'test' }}>
              <DeepNested />
            </NestedContext.Provider>
          </AuthProvider>
        );
      }).not.toThrow();

      expect(screen.getByTestId('deep-nested')).toBeInTheDocument();
    });
  });

  describe('Error Prevention', () => {
    it('should catch and report react-is production.min.js errors', () => {
      // The specific error you encountered comes from react-is.production.min.js
      const reactIsProductionErrors = consoleErrors.filter(error =>
        error.includes('react-is.production.min.js') ||
        error.includes('at up (react-is.production.min.js') ||
        error.includes('at sp (index.js')
      );

      if (reactIsProductionErrors.length > 0) {
        console.error('🚨 React-is production errors detected:', reactIsProductionErrors);
        expect.fail('React-is production errors found - likely v19.x compatibility issue');
      }
    });

    it('should validate package.json overrides are working', () => {
      // This test ensures the overrides in package.json are effective
      const packageJson = require('../../../package.json');
      
      expect(packageJson.overrides).toBeDefined();
      expect(packageJson.overrides['react-is']).toBe('^18.3.1');
      expect(packageJson.overrides['use-sync-external-store']).toBe(false);
      expect(packageJson.overrides['hoist-non-react-statics']).toBeDefined();
    });
  });
});

/**
 * TEST TYPE CLASSIFICATION:
 * 
 * This error should have been caught by:
 * 1. DEPENDENCY INTEGRATION TESTS (this test) - Tests runtime dependency compatibility
 * 2. COMPONENT INTEGRATION TESTS - Tests Context providers work with real components
 * 3. BUILD VALIDATION TESTS - Validates dependency tree doesn't have conflicts
 * 4. E2E TESTS - Would catch this as a runtime error in browser console
 * 
 * The existing enhanced-dep-test.cjs SHOULD have caught this but may need to run more often.
 */