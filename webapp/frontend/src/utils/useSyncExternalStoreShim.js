/**
 * Shim for useSyncExternalStore to fix production useState errors
 */

import { useState, useEffect, useCallback, useRef } from 'react';

function useSyncExternalStoreFallback(subscribe, getSnapshot, getServerSnapshot) {
  const [state, setState] = useState(() => {
    try {
      return getSnapshot();
    } catch (error) {
      console.warn('useSyncExternalStore: Error in initial getSnapshot:', error);
      return undefined;
    }
  });

  const lastSnapshotRef = useRef(state);
  const getSnapshotRef = useRef(getSnapshot);
  const subscribeRef = useRef(subscribe);

  getSnapshotRef.current = getSnapshot;
  subscribeRef.current = subscribe;

  const handleStoreChange = useCallback(() => {
    try {
      const newSnapshot = getSnapshotRef.current();
      if (newSnapshot !== lastSnapshotRef.current) {
        lastSnapshotRef.current = newSnapshot;
        setState(newSnapshot);
      }
    } catch (error) {
      console.warn('useSyncExternalStore: Error in store change handler:', error);
    }
  }, []);

  useEffect(() => {
    let unsubscribe;
    
    try {
      const currentSnapshot = getSnapshotRef.current();
      if (currentSnapshot !== lastSnapshotRef.current) {
        lastSnapshotRef.current = currentSnapshot;
        setState(currentSnapshot);
      }

      unsubscribe = subscribeRef.current(handleStoreChange);
    } catch (error) {
      console.warn('useSyncExternalStore: Error during subscription:', error);
    }

    return () => {
      if (unsubscribe && typeof unsubscribe === 'function') {
        try {
          unsubscribe();
        } catch (error) {
          console.warn('useSyncExternalStore: Error during unsubscribe:', error);
        }
      }
    };
  }, [handleStoreChange]);

  return state;
}

export function useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot) {
  return useSyncExternalStoreFallback(subscribe, getSnapshot, getServerSnapshot);
}

export function useSyncExternalStoreWithSelector(
  subscribe,
  getSnapshot,
  getServerSnapshot,
  selector,
  isEqual
) {
  const wrappedGetSnapshot = useCallback(() => {
    try {
      const snapshot = getSnapshot();
      return selector ? selector(snapshot) : snapshot;
    } catch (error) {
      console.warn('useSyncExternalStoreWithSelector: Error in getSnapshot:', error);
      return undefined;
    }
  }, [getSnapshot, selector]);

  const wrappedGetServerSnapshot = useCallback(() => {
    if (!getServerSnapshot) return undefined;
    try {
      const serverSnapshot = getServerSnapshot();
      return selector ? selector(serverSnapshot) : serverSnapshot;
    } catch (error) {
      console.warn('useSyncExternalStoreWithSelector: Error in getServerSnapshot:', error);
      return undefined;
    }
  }, [getServerSnapshot, selector]);

  return useSyncExternalStore(subscribe, wrappedGetSnapshot, wrappedGetServerSnapshot);
}

console.log('🔧 useSyncExternalStore shim loaded for production useState fix');

export default {
  useSyncExternalStore,
  useSyncExternalStoreWithSelector
};