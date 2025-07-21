/**
 * PERMANENT FIX: Custom useSyncExternalStore implementation that bypasses the problematic shim
 * This ensures we never hit the useState undefined error in production
 * Updated: 2025-07-21 - Added comprehensive React safety checks and logging
 */

import React from 'react';

// Check if React 18+ native useSyncExternalStore is available
const hasNativeUseSyncExternalStore = typeof React.useSyncExternalStore === 'function';

// Debug logging for production troubleshooting (only logs once)
if (typeof window !== 'undefined' && !window.__USE_SYNC_EXTERNAL_STORE_FIX_LOADED) {
  console.log('🔧 useSyncExternalStoreFix loaded - React hooks safety enabled');
  console.log('🔧 Native useSyncExternalStore available:', hasNativeUseSyncExternalStore);
  window.__USE_SYNC_EXTERNAL_STORE_FIX_LOADED = true;
}

/**
 * Safe implementation of useSyncExternalStore that works in all environments
 */
export function useSyncExternalStoreSafe(subscribe, getSnapshot, getServerSnapshot) {
  // If React 18+ native implementation is available, use it
  if (hasNativeUseSyncExternalStore) {
    return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  }

  // Fallback implementation for older React versions or when shim fails
  const [{ inst }, forceUpdate] = React.useState({
    inst: { value: getSnapshot(), getSnapshot }
  });

  React.useLayoutEffect(() => {
    inst.value = getSnapshot();
    inst.getSnapshot = getSnapshot;
    
    // Check if snapshot changed
    if (checkIfSnapshotChanged(inst)) {
      forceUpdate({ inst });
    }
  }, [subscribe, getSnapshot]);

  React.useEffect(() => {
    if (checkIfSnapshotChanged(inst)) {
      forceUpdate({ inst });
    }
    
    return subscribe(() => {
      if (checkIfSnapshotChanged(inst)) {
        forceUpdate({ inst });
      }
    });
  }, [subscribe]);

  return inst.value;
}

function checkIfSnapshotChanged(inst) {
  const latestGetSnapshot = inst.getSnapshot;
  const value = inst.value;
  
  try {
    const nextValue = latestGetSnapshot();
    return !Object.is(value, nextValue);
  } catch (error) {
    return true;
  }
}

/**
 * Export in the format expected by use-sync-external-store/shim
 */
export const useSyncExternalStore = useSyncExternalStoreSafe;
export default { useSyncExternalStore: useSyncExternalStoreSafe };