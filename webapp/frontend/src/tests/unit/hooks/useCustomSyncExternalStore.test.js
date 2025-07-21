/**
 * Unit tests for useCustomSyncExternalStore hook
 * 
 * Tests the custom implementation that replaces the problematic 
 * use-sync-external-store package in production
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCustomSyncExternalStore, useCustomSyncExternalStoreWithSelector } from '../../../hooks/useCustomSyncExternalStore';

describe('useCustomSyncExternalStore', () => {
  let mockStore;
  let mockSubscribe;
  let mockGetSnapshot;
  let mockUnsubscribe;
  let subscribers;

  beforeEach(() => {
    subscribers = [];
    mockUnsubscribe = vi.fn();
    mockStore = { value: 'initial' };
    
    mockSubscribe = vi.fn((callback) => {
      subscribers.push(callback);
      return mockUnsubscribe;
    });
    
    mockGetSnapshot = vi.fn(() => mockStore.value);
  });

  afterEach(() => {
    vi.clearAllMocks();
    subscribers = [];
  });

  it('should return initial snapshot value', () => {
    const { result } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(result.current).toBe('initial');
    expect(mockGetSnapshot).toHaveBeenCalled();
    expect(mockSubscribe).toHaveBeenCalledTimes(1);
  });

  it('should subscribe to store changes', () => {
    const { result } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(mockSubscribe).toHaveBeenCalledWith(expect.any(Function));
    expect(subscribers).toHaveLength(1);
  });

  it('should update when store value changes', () => {
    const { result } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(result.current).toBe('initial');

    // Simulate store change
    act(() => {
      mockStore.value = 'updated';
      mockGetSnapshot.mockReturnValue('updated');
      subscribers.forEach(callback => callback());
    });

    expect(result.current).toBe('updated');
  });

  it('should unsubscribe on unmount', () => {
    const { unmount } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    unmount();

    expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
  });

  it('should handle subscription errors gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    mockSubscribe.mockImplementation(() => {
      throw new Error('Subscription failed');
    });

    const { result } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(result.current).toBe('initial');
    // Our implementation logs warnings, but doesn't throw
    expect(consoleSpy).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  it('should handle getSnapshot errors gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    mockGetSnapshot.mockImplementation(() => {
      throw new Error('Snapshot failed');
    });

    const { result } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    // Our implementation returns undefined on error
    expect(result.current).toBeUndefined();
    expect(consoleSpy).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  it('should handle store change callback errors gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    const { result } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    // Cause getSnapshot to fail during store change
    mockGetSnapshot.mockImplementation(() => {
      throw new Error('Store change failed');
    });

    act(() => {
      subscribers.forEach(callback => callback());
    });

    expect(consoleSpy).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  it('should only update when value actually changes', () => {
    const { result, rerender } = renderHook(() =>
      useCustomSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    const initialValue = result.current;

    // Trigger change with same value
    act(() => {
      // Value stays the same
      subscribers.forEach(callback => callback());
    });

    expect(result.current).toBe(initialValue);
    expect(mockGetSnapshot).toHaveBeenCalledTimes(3); // Initial + useEffect + change check
  });
});

describe('useCustomSyncExternalStoreWithSelector', () => {
  let mockStore;
  let mockSubscribe;
  let mockGetSnapshot;
  let mockSelector;
  let subscribers;

  beforeEach(() => {
    subscribers = [];
    mockStore = { count: 5, name: 'test' };
    
    mockSubscribe = vi.fn((callback) => {
      subscribers.push(callback);
      return vi.fn(); // unsubscribe
    });
    
    mockGetSnapshot = vi.fn(() => mockStore);
    mockSelector = vi.fn((state) => state.count);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should return selected value from snapshot', () => {
    const { result } = renderHook(() =>
      useCustomSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        undefined,
        mockSelector
      )
    );

    expect(result.current).toBe(5);
    expect(mockSelector).toHaveBeenCalledWith(mockStore);
  });

  it('should update when selected value changes', () => {
    const { result } = renderHook(() =>
      useCustomSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        undefined,
        mockSelector
      )
    );

    expect(result.current).toBe(5);

    // Update store
    act(() => {
      mockStore.count = 10;
      subscribers.forEach(callback => callback());
    });

    expect(result.current).toBe(10);
  });

  it('should handle selector errors gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    mockSelector.mockImplementation(() => {
      throw new Error('Selector failed');
    });

    const { result } = renderHook(() =>
      useCustomSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        undefined,
        mockSelector
      )
    );

    // Our implementation returns undefined on error
    expect(result.current).toBeUndefined();
    expect(consoleSpy).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  it('should work without selector (pass-through)', () => {
    const { result } = renderHook(() =>
      useCustomSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot
      )
    );

    expect(result.current).toBe(mockStore);
  });

  it('should handle server snapshot with selector', () => {
    const mockGetServerSnapshot = vi.fn(() => ({ count: 100, name: 'server' }));

    const { result } = renderHook(() =>
      useCustomSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        mockGetServerSnapshot,
        mockSelector
      )
    );

    expect(result.current).toBe(5); // Client snapshot should be used in test environment
  });

  it('should handle server snapshot selector errors gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    const mockGetServerSnapshot = vi.fn(() => {
      throw new Error('Server snapshot failed');
    });

    const { result } = renderHook(() =>
      useCustomSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        mockGetServerSnapshot,
        mockSelector
      )
    );

    // Should still work with client snapshot
    expect(result.current).toBe(5);

    consoleSpy.mockRestore();
  });
});