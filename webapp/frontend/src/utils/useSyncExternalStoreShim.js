/**
 * ARCHITECTURAL FIX: useSyncExternalStore Shim
 * 
 * This shim forces all dependencies to use React 18's built-in useSyncExternalStore
 * instead of the separate use-sync-external-store package that causes conflicts.
 * 
 * React 18.3.1 has useSyncExternalStore built-in, so we use that directly.
 */

import { useSyncExternalStore } from 'react';

// Export React 18's built-in useSyncExternalStore
export { useSyncExternalStore };

// For compatibility with libraries expecting the separate package structure
export const useSyncExternalStoreWithSelector = (
  subscribe,
  getSnapshot,
  getServerSnapshot,
  selector,
  isEqual
) => {
  // Use React's built-in hook
  const value = useSyncExternalStore(
    subscribe,
    selector ? () => selector(getSnapshot()) : getSnapshot,
    getServerSnapshot ? () => selector ? selector(getServerSnapshot()) : getServerSnapshot() : undefined
  );
  
  return value;
};

// Default export for direct imports
export default useSyncExternalStore;

// Also export the shim functions for compatibility
export const shim = () => {
  console.log('✅ Using React 18 built-in useSyncExternalStore');
  return { useSyncExternalStore };
};

console.log('🚀 useSyncExternalStore shim loaded - using React 18 built-in implementation');