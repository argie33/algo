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

// Set React globally in all possible scopes with full hooks
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

if (typeof window !== 'undefined') {
  window.React = ReactWithHooks;
  window.ReactDOM = ReactDOM;
}

if (typeof globalThis !== 'undefined') {
  globalThis.React = ReactWithHooks;
  globalThis.ReactDOM = ReactDOM;
}

if (typeof global !== 'undefined') {
  global.React = ReactWithHooks;
  global.ReactDOM = ReactDOM;
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

export { ReactWithHooks as React, ReactDOM };
export default ReactWithHooks;