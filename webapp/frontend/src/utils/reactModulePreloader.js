/**
 * React Module Preloader
 * Ensures React is properly loaded before any external store synchronization libraries
 * FIXES: use-sync-external-store TypeError: Cannot read properties of undefined (reading 'useState')
 */

// Import React first and ensure it's available
import React from 'react';
import ReactDOM from 'react-dom/client';

// CRITICAL FIX: Ensure React.useState is explicitly available
if (!React.useState) {
  console.error('❌ CRITICAL: React.useState is not available in imported React');
  throw new Error('React hooks not available - React import failed');
}

// CRITICAL FIX: Ensure all React hooks are properly available
const ReactWithHooks = {
  ...React,
  // Explicitly ensure all hooks are available
  useState: React.useState,
  useEffect: React.useEffect,
  useLayoutEffect: React.useLayoutEffect,
  useCallback: React.useCallback,
  useMemo: React.useMemo,
  useRef: React.useRef,
  useContext: React.useContext,
  useReducer: React.useReducer,
  useDebugValue: React.useDebugValue,
  useSyncExternalStore: React.useSyncExternalStore,
  // Add any missing React 18 hooks
  useId: React.useId || (() => Math.random().toString(36)),
  useDeferredValue: React.useDeferredValue || ((value) => value),
  useTransition: React.useTransition || (() => [false, (fn) => fn()]),
  useInsertionEffect: React.useInsertionEffect || React.useLayoutEffect
};

// CRITICAL: Verify all hooks are actually functions before proceeding
const missingHooks = Object.entries(ReactWithHooks)
  .filter(([name, hook]) => name.startsWith('use') && typeof hook !== 'function')
  .map(([name]) => name);

if (missingHooks.length > 0) {
  console.error('❌ CRITICAL: Missing React hooks detected:', missingHooks);
  throw new Error(`React hooks not available: ${missingHooks.join(', ')}`);
}

// Set React globally with multiple fallback mechanisms
if (typeof window !== 'undefined') {
  window.React = ReactWithHooks;
  window.ReactDOM = ReactDOM;
  // CRITICAL: Set F for MUI/bundled library compatibility
  window.F = ReactWithHooks;
  
  // Additional protection - ensure F is never undefined
  Object.defineProperty(window, 'F', {
    get() { return ReactWithHooks; },
    set(value) { /* Prevent F from being overwritten */ },
    configurable: false,
    enumerable: true
  });
}

if (typeof globalThis !== 'undefined') {
  globalThis.React = ReactWithHooks;
  globalThis.ReactDOM = ReactDOM;
  globalThis.F = ReactWithHooks;
  
  // Protection for globalThis.F
  try {
    Object.defineProperty(globalThis, 'F', {
      get() { return ReactWithHooks; },
      set(value) { /* Prevent F from being overwritten */ },
      configurable: false,
      enumerable: true
    });
  } catch (e) {
    // Fallback if defineProperty fails
    globalThis.F = ReactWithHooks;
  }
}

if (typeof global !== 'undefined') {
  global.React = ReactWithHooks;
  global.ReactDOM = ReactDOM;
  global.F = ReactWithHooks;
}

// Polyfill for require() calls that might need React
if (typeof require !== 'undefined' && typeof require.cache !== 'undefined') {
  // Force React to be available for CommonJS requires
  require.cache['react'] = {
    exports: ReactWithHooks,
    loaded: true,
    id: 'react'
  };
}

// Create a module mock for environments that might call require("react")
const createRequireMock = () => {
  const requireMock = (moduleName) => {
    if (moduleName === 'react') {
      return ReactWithHooks;
    }
    if (moduleName === 'react-dom/client') {
      return ReactDOM;
    }
    // Fallback to original require if available
    if (typeof originalRequire !== 'undefined') {
      return originalRequire(moduleName);
    }
    throw new Error(`Module ${moduleName} not found`);
  };
  
  requireMock.cache = {};
  requireMock.resolve = (moduleName) => moduleName;
  
  return requireMock;
};

// Store original require if it exists
let originalRequire;
if (typeof require !== 'undefined') {
  originalRequire = require;
}

// Override global require for React modules
if (typeof global !== 'undefined') {
  global.require = createRequireMock();
}

if (typeof window !== 'undefined') {
  window.require = createRequireMock();
}

// Ensure React hooks are available
export const ensureReactHooks = () => {
  const hooks = {
    useState: ReactWithHooks.useState,
    useEffect: ReactWithHooks.useEffect,
    useLayoutEffect: ReactWithHooks.useLayoutEffect,
    useDebugValue: ReactWithHooks.useDebugValue,
    useSyncExternalStore: ReactWithHooks.useSyncExternalStore,
    useCallback: ReactWithHooks.useCallback,
    useMemo: ReactWithHooks.useMemo,
    useRef: ReactWithHooks.useRef,
    useContext: ReactWithHooks.useContext,
    useReducer: ReactWithHooks.useReducer
  };

  // Verify all hooks are available
  const missingHooks = Object.entries(hooks)
    .filter(([name, hook]) => typeof hook !== 'function')
    .map(([name]) => name);

  if (missingHooks.length > 0) {
    console.error('❌ Missing React hooks:', missingHooks);
    throw new Error(`React hooks not available: ${missingHooks.join(', ')}`);
  }

  console.log('✅ All React hooks verified and available');
  return hooks;
};

// Pre-initialize React hooks
try {
  ensureReactHooks();
  console.log('✅ React module preloader initialized successfully');
} catch (error) {
  console.error('❌ React module preloader failed:', error);
}

// CRITICAL: Runtime monitoring to prevent F from becoming undefined
if (typeof window !== 'undefined') {
  // Monitor F and restore it if it becomes undefined
  const monitorF = () => {
    if (typeof window.F === 'undefined' || !window.F.useLayoutEffect) {
      console.warn('⚠️ CRITICAL: window.F became undefined, restoring...');
      window.F = ReactWithHooks;
      
      // Also ensure React is still available
      if (typeof window.React === 'undefined' || !window.React.useLayoutEffect) {
        window.React = ReactWithHooks;
      }
    }
  };
  
  // Check every 100ms during initial load
  const monitorInterval = setInterval(monitorF, 100);
  
  // Stop monitoring after 10 seconds
  setTimeout(() => {
    clearInterval(monitorInterval);
    // Do one final check
    monitorF();
    console.log('✅ F monitoring completed');
  }, 10000);
  
  // Also monitor on errors
  window.addEventListener('error', (event) => {
    if (event.message.includes('useLayoutEffect') || event.message.includes('undefined')) {
      console.warn('⚠️ CRITICAL: Error detected, checking F...');
      monitorF();
    }
  });
}

export { ReactWithHooks as React, ReactDOM };
export default ReactWithHooks;