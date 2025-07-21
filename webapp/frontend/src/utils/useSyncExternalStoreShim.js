/**
 * Use Sync External Store Shim
 * Forces all libraries to use React 18's built-in useSyncExternalStore
 * This replaces the external use-sync-external-store package entirely
 */

import React from 'react';

// Ensure React is available and has the built-in hook
if (!React || !React.useSyncExternalStore) {
  console.error('🚨 CRITICAL: React 18 with useSyncExternalStore is required');
  throw new Error('React 18 with built-in useSyncExternalStore is required but not available');
}

console.log('✅ useSyncExternalStore shim loaded - using React 18 built-in implementation');

// Export React's built-in useSyncExternalStore directly
export const useSyncExternalStore = React.useSyncExternalStore;

// Create a simple selector wrapper for libraries that expect with-selector
export const useSyncExternalStoreWithSelector = (store, selector, getServerSnapshot, isEqual) => {
  const state = React.useSyncExternalStore(store, () => selector(store.getSnapshot()), getServerSnapshot);
  return state;
};

// Export default for libraries that import the whole module
export default {
  useSyncExternalStore: React.useSyncExternalStore,
  useSyncExternalStoreWithSelector
};

// Log successful shim activation
console.log('🔄 All use-sync-external-store imports now redirected to React 18 built-in hook');