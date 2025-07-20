/**
 * React Module Preloader
 * Ensures React is properly loaded before any external store synchronization libraries
 */

// Import React first and ensure it's available
import React from 'react';
import ReactDOM from 'react-dom/client';

// Set React globally in all possible scopes
if (typeof window !== 'undefined') {
  window.React = React;
  window.ReactDOM = ReactDOM;
}

if (typeof globalThis !== 'undefined') {
  globalThis.React = React;
  globalThis.ReactDOM = ReactDOM;
}

if (typeof global !== 'undefined') {
  global.React = React;
  global.ReactDOM = ReactDOM;
}

// Polyfill for require() calls that might need React
if (typeof require !== 'undefined' && typeof require.cache !== 'undefined') {
  // Force React to be available for CommonJS requires
  require.cache['react'] = {
    exports: React,
    loaded: true,
    id: 'react'
  };
}

// Create a module mock for environments that might call require("react")
const createRequireMock = () => {
  const requireMock = (moduleName) => {
    if (moduleName === 'react') {
      return React;
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
    useState: React.useState,
    useEffect: React.useEffect,
    useLayoutEffect: React.useLayoutEffect,
    useDebugValue: React.useDebugValue,
    useSyncExternalStore: React.useSyncExternalStore,
    useCallback: React.useCallback,
    useMemo: React.useMemo,
    useRef: React.useRef,
    useContext: React.useContext,
    useReducer: React.useReducer
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

export { React, ReactDOM };
export default React;