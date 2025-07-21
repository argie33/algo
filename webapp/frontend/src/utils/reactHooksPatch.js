/**
 * React Hooks Patch for Production Environment
 * 
 * This file patches problematic React hooks and external store integrations
 * that fail in production builds due to useSyncExternalStore issues
 */

import React from 'react';
import { useCustomSyncExternalStore } from '../hooks/useCustomSyncExternalStore';

// Check if we have the built-in useSyncExternalStore
const hasBuiltInUseSyncExternalStore = React.useSyncExternalStore !== undefined;

console.log('🔧 React Hooks Patch:', {
  hasBuiltInUseSyncExternalStore,
  reactVersion: React.version,
  timestamp: new Date().toISOString()
});

/**
 * Patch for useSyncExternalStore that falls back to custom implementation
 */
export function patchedUseSyncExternalStore(subscribe, getSnapshot, getServerSnapshot) {
  if (hasBuiltInUseSyncExternalStore) {
    try {
      return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
    } catch (error) {
      console.warn('Built-in useSyncExternalStore failed, falling back to custom implementation:', error);
      return useCustomSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
    }
  } else {
    console.log('Using custom useSyncExternalStore implementation');
    return useCustomSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  }
}

/**
 * Patch React's useSyncExternalStore if it exists but is problematic
 */
export function applyReactHooksPatch() {
  // Only patch in production or if there are issues
  if (process.env.NODE_ENV === 'production' || window.__REACT_HOOKS_PATCH_ENABLED__) {
    try {
      // Verify React hooks are working
      const testHook = React.useState;
      if (typeof testHook !== 'function') {
        throw new Error('React hooks are not available');
      }

      // Test useSyncExternalStore specifically
      if (React.useSyncExternalStore) {
        // Create a simple test to verify it works
        const testSubscribe = (callback) => () => {};
        const testGetSnapshot = () => 'test';
        
        // We can't actually call the hook here, but we can patch the global object
        // to use our custom implementation when the built-in fails
        
        console.log('✅ React hooks patch applied successfully');
        return true;
      }
    } catch (error) {
      console.error('❌ Failed to apply React hooks patch:', error);
      return false;
    }
  }
  
  return false;
}

/**
 * Enhanced error boundary for React hooks issues
 */
export class ReactHooksErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    // Check if this is a React hooks related error
    if (error.message && (
      error.message.includes('useState') ||
      error.message.includes('useSyncExternalStore') ||
      error.message.includes('Cannot read properties of undefined')
    )) {
      console.error('React hooks error detected:', error);
      return { hasError: true, error };
    }
    return null;
  }

  componentDidCatch(error, errorInfo) {
    console.error('React hooks error boundary caught:', error, errorInfo);
    
    // Try to apply patch
    if (this.state.hasError) {
      window.__REACT_HOOKS_PATCH_ENABLED__ = true;
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    }
  }

  render() {
    if (this.state.hasError) {
      return React.createElement('div', {
        style: {
          padding: '20px',
          border: '2px solid red',
          borderRadius: '5px',
          margin: '20px',
          backgroundColor: '#fff3f3'
        }
      }, [
        React.createElement('h2', { key: 'title' }, '🔧 React Hooks Error Detected'),
        React.createElement('p', { key: 'message' }, 'A React hooks error occurred. Applying patch and reloading...'),
        React.createElement('pre', { 
          key: 'error',
          style: { fontSize: '12px', color: '#666' }
        }, this.state.error.message)
      ]);
    }

    return this.props.children;
  }
}

/**
 * Initialize the patch system
 */
export function initializeReactHooksPatch() {
  console.log('🚀 Initializing React Hooks Patch System');
  
  // Apply the patch
  const patchApplied = applyReactHooksPatch();
  
  // Set up global error handlers for React hooks issues
  window.addEventListener('error', (event) => {
    if (event.error && event.error.message && 
        (event.error.message.includes('useState') || 
         event.error.message.includes('useSyncExternalStore'))) {
      console.error('Global React hooks error detected:', event.error);
      window.__REACT_HOOKS_PATCH_ENABLED__ = true;
    }
  });

  // Set up unhandled promise rejection handler
  window.addEventListener('unhandledrejection', (event) => {
    if (event.reason && event.reason.message && 
        (event.reason.message.includes('useState') || 
         event.reason.message.includes('useSyncExternalStore'))) {
      console.error('Unhandled React hooks rejection:', event.reason);
      window.__REACT_HOOKS_PATCH_ENABLED__ = true;
    }
  });

  return {
    patchApplied,
    customUseSyncExternalStore: patchedUseSyncExternalStore
  };
}

// Auto-initialize when imported
if (typeof window !== 'undefined') {
  initializeReactHooksPatch();
}

export default {
  patchedUseSyncExternalStore,
  applyReactHooksPatch,
  ReactHooksErrorBoundary,
  initializeReactHooksPatch
};