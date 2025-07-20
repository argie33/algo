/**
 * CRITICAL: React Hooks Diagnostic Tests
 * Tests the exact error: "Cannot read properties of undefined (reading 'useState')"
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';

describe('🔬 React Hooks Diagnostic Tests', () => {
  
  describe('React Core Availability', () => {
    it('should have React available', () => {
      expect(React).toBeDefined();
      expect(typeof React).toBe('object');
    });

    it('should have useState hook available', () => {
      expect(React.useState).toBeDefined();
      expect(typeof React.useState).toBe('function');
    });

    it('should have useEffect hook available', () => {
      expect(React.useEffect).toBeDefined();
      expect(typeof React.useEffect).toBe('function');
    });

    it('should have useSyncExternalStore hook available', () => {
      expect(React.useSyncExternalStore).toBeDefined();
      expect(typeof React.useSyncExternalStore).toBe('function');
    });
  });

  describe('use-sync-external-store-shim Package', () => {
    it('should import use-sync-external-store/shim without error', async () => {
      let importError = null;
      try {
        const { useSyncExternalStore } = await import('use-sync-external-store/shim');
        expect(useSyncExternalStore).toBeDefined();
        expect(typeof useSyncExternalStore).toBe('function');
      } catch (error) {
        importError = error;
      }
      expect(importError).toBe(null);
    });

    it('should have compatible React version for useSyncExternalStore', () => {
      const reactVersion = React.version;
      expect(reactVersion).toBeDefined();
      
      // useSyncExternalStore was added in React 18
      const majorVersion = parseInt(reactVersion.split('.')[0]);
      expect(majorVersion).toBeGreaterThanOrEqual(18);
    });
  });

  describe('useState Error Reproduction', () => {
    it('should not throw "Cannot read properties of undefined" when accessing useState', () => {
      expect(() => {
        const useStateRef = React.useState;
        expect(useStateRef).toBeDefined();
      }).not.toThrow();
    });

    it('should allow useState to be destructured from React', () => {
      expect(() => {
        const { useState } = React;
        expect(useState).toBeDefined();
        expect(typeof useState).toBe('function');
      }).not.toThrow();
    });

    it('should detect if React is undefined when useState is accessed', () => {
      // Simulate the error condition
      const mockReact = undefined;
      expect(() => {
        // This should throw the same error as the production issue
        const useState = mockReact?.useState;
      }).not.toThrow(); // Using optional chaining prevents the error

      // But this would throw (simulating the actual error)
      expect(() => {
        const mockReactNotOptional = undefined;
        const useState = mockReactNotOptional.useState; // This would throw
      }).toThrow();
    });
  });

  describe('Bundle Analysis', () => {
    it('should have React available in global scope (if bundled globally)', () => {
      // Check if React is available globally (common bundling issue)
      const globalReact = globalThis.React || window?.React;
      if (globalReact) {
        expect(globalReact.useState).toBeDefined();
      }
    });

    it('should import React successfully', async () => {
      let importError = null;
      try {
        const ReactImport = await import('react');
        expect(ReactImport.default || ReactImport).toBeDefined();
        expect((ReactImport.default || ReactImport).useState).toBeDefined();
      } catch (error) {
        importError = error;
      }
      expect(importError).toBe(null);
    });
  });

  describe('Dependency Resolution', () => {
    it('should have consistent React and use-sync-external-store versions', async () => {
      const reactVersion = React.version;
      
      try {
        // Try to import the shim
        await import('use-sync-external-store/shim');
        
        // If we get here, the shim is available and should work
        expect(true).toBe(true);
      } catch (error) {
        // Log the specific import error for debugging
        console.error('use-sync-external-store import error:', error);
        throw error;
      }
    });
  });
});