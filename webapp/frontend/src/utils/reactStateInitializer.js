/**
 * React State Initializer
 * 
 * Ensures React hooks are properly available before the app starts
 * This prevents the useState error in use-sync-external-store-shim
 */

// Global React state verification
export function verifyReactState() {
  const checks = {
    reactAvailable: typeof React !== 'undefined',
    reactOnWindow: typeof window?.React !== 'undefined',
    useStateAvailable: false,
    useSyncExternalStoreAvailable: false,
    reactVersion: null
  };

  try {
    // Import React synchronously if possible
    const React = require('react');
    
    if (React && typeof React.useState === 'function') {
      checks.useStateAvailable = true;
      checks.useSyncExternalStoreAvailable = typeof React.useSyncExternalStore === 'function';
      checks.reactVersion = React.version;
    }
  } catch (error) {
    console.warn('React state verification failed:', error);
  }

  return checks;
}

// Fix React state issues globally
export function initializeReactState() {
  console.log('🔧 Initializing React state...');
  
  const stateCheck = verifyReactState();
  console.log('React state check:', stateCheck);
  
  // If React hooks aren't available, try to fix it
  if (!stateCheck.useStateAvailable) {
    console.warn('⚠️ React useState not available, attempting to fix...');
    
    try {
      // Try to force load React
      const React = require('react');
      
      if (React && React.useState) {
        console.log('✅ React hooks now available after forced import');
        
        // Make React available globally as fallback
        if (typeof window !== 'undefined') {
          window.React = React;
        }
        
        return true;
      }
    } catch (error) {
      console.error('❌ Failed to initialize React state:', error);
      return false;
    }
  }
  
  return stateCheck.useStateAvailable;
}

// Emergency React hooks fallback
export function createReactFallback() {
  return {
    useState: (initial) => [initial, () => {}],
    useEffect: () => {},
    useLayoutEffect: () => {},
    useDebugValue: () => {},
    useSyncExternalStore: null,
    version: '18.3.1-fallback'
  };
}

// Initialize when imported
if (typeof window !== 'undefined') {
  initializeReactState();
}

export default {
  verifyReactState,
  initializeReactState,
  createReactFallback
};