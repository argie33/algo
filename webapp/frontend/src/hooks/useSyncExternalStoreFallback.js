/**
 * Complete replacement for use-sync-external-store package
 * This file should be aliased in Vite config to replace any imports
 */

import React from 'react';

// Use React 18's built-in useSyncExternalStore
export default function useSyncExternalStoreShim(subscribe, getSnapshot, getServerSnapshot) {
  // Ensure React is available
  if (!React || !React.useSyncExternalStore) {
    console.error('React 18 useSyncExternalStore not available - this should not happen');
    
    // Emergency fallback
    const [state, setState] = React.useState(getSnapshot);
    
    React.useEffect(() => {
      const unsubscribe = subscribe(() => {
        setState(getSnapshot());
      });
      return unsubscribe;
    }, [subscribe, getSnapshot]);

    return state;
  }

  // Use React 18's native implementation
  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

// Export both named and default to match all import patterns
export { useSyncExternalStoreShim as useSyncExternalStore };
export { default as useSyncExternalStoreWithSelector } from './useSyncExternalStoreFallback.js';