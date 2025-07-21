/**
 * Custom implementation of useSyncExternalStore that doesn't depend on 
 * the problematic use-sync-external-store package
 * 
 * This is a fallback implementation that uses useState and useEffect
 * to provide similar functionality without the production issues
 */
import { useState, useEffect, useCallback, useRef } from 'react';

export function useCustomSyncExternalStore(subscribe, getSnapshot, getServerSnapshot) {
  // Initialize state with current snapshot
  const [state, setState] = useState(() => {
    try {
      return getSnapshot();
    } catch (error) {
      console.warn('useSyncExternalStore: Error in initial getSnapshot:', error);
      return undefined;
    }
  });

  // Track if we're currently subscribed
  const subscribedRef = useRef(false);
  const lastSnapshotRef = useRef(state);

  // Create a stable callback for subscription
  const onStoreChange = useCallback(() => {
    try {
      const newSnapshot = getSnapshot();
      
      // Only update if the value actually changed
      if (newSnapshot !== lastSnapshotRef.current) {
        lastSnapshotRef.current = newSnapshot;
        setState(newSnapshot);
      }
    } catch (error) {
      console.warn('useSyncExternalStore: Error in store change handler:', error);
    }
  }, [getSnapshot]);

  // Subscribe to store changes
  useEffect(() => {
    if (subscribedRef.current) {
      return;
    }

    subscribedRef.current = true;
    let unsubscribe;

    try {
      // Get the current snapshot to ensure we're up to date
      const currentSnapshot = getSnapshot();
      if (currentSnapshot !== lastSnapshotRef.current) {
        lastSnapshotRef.current = currentSnapshot;
        setState(currentSnapshot);
      }

      // Subscribe to changes
      unsubscribe = subscribe(onStoreChange);
    } catch (error) {
      console.warn('useSyncExternalStore: Error during subscription:', error);
    }

    return () => {
      subscribedRef.current = false;
      if (unsubscribe && typeof unsubscribe === 'function') {
        try {
          unsubscribe();
        } catch (error) {
          console.error('Error unsubscribing from store:', error);
        }
      }
    };
  }, [subscribe, onStoreChange, getSnapshot]);

  return state;
}

/**
 * Custom implementation with selector support
 */
export function useCustomSyncExternalStoreWithSelector(
  subscribe,
  getSnapshot,
  getServerSnapshot,
  selector,
  isEqual
) {
  // Create wrapped getSnapshot that applies selector
  const getSelectedSnapshot = useCallback(() => {
    try {
      const snapshot = getSnapshot();
      return selector ? selector(snapshot) : snapshot;
    } catch (error) {
      console.warn('useSyncExternalStoreWithSelector: Error in getSnapshot:', error);
      return undefined;
    }
  }, [getSnapshot, selector]);

  const selectedValue = useCustomSyncExternalStore(
    subscribe,
    getSelectedSnapshot,
    getServerSnapshot ? () => {
      try {
        const serverSnapshot = getServerSnapshot();
        return selector ? selector(serverSnapshot) : serverSnapshot;
      } catch (error) {
        console.warn('useSyncExternalStoreWithSelector: Error in getServerSnapshot:', error);
        return undefined;
      }
    } : undefined
  );

  return selectedValue;
}

// Default export for easy import
export default useCustomSyncExternalStore;