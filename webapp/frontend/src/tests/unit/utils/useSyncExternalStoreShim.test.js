/**
 * Unit tests for useSyncExternalStore shim
 * 
 * Tests the shim that provides a drop-in replacement for the problematic
 * use-sync-external-store package
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSyncExternalStore, useSyncExternalStoreWithSelector } from '../../../utils/useSyncExternalStoreShim';

describe('useSyncExternalStore shim', () => {
  let mockStore;
  let mockSubscribe;
  let mockGetSnapshot;
  let mockUnsubscribe;
  let subscribers;
  let originalConsole;

  beforeEach(() => {
    subscribers = [];
    mockUnsubscribe = vi.fn();
    mockStore = { value: 'initial', count: 0 };
    
    mockSubscribe = vi.fn((callback) => {
      subscribers.push(callback);
      return mockUnsubscribe;
    });
    
    mockGetSnapshot = vi.fn(() => mockStore.value);
    
    originalConsole = {
      warn: console.warn,
      log: console.log
    };
    
    console.warn = vi.fn();
    console.log = vi.fn();
  });

  afterEach(() => {
    console.warn = originalConsole.warn;
    console.log = originalConsole.log;
    vi.clearAllMocks();
    subscribers = [];
  });

  it('should return initial snapshot value', () => {
    const { result } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(result.current).toBe('initial');
    expect(mockGetSnapshot).toHaveBeenCalled();
    expect(mockSubscribe).toHaveBeenCalledWith(expect.any(Function));
  });

  it('should subscribe to store changes', () => {
    renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(mockSubscribe).toHaveBeenCalledTimes(1);
    expect(subscribers).toHaveLength(1);
    expect(typeof subscribers[0]).toBe('function');
  });

  it('should update when store value changes', () => {
    const { result } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(result.current).toBe('initial');

    // Update store value
    act(() => {
      mockStore.value = 'updated';
      mockGetSnapshot.mockReturnValue('updated');
      subscribers.forEach(callback => callback());
    });

    expect(result.current).toBe('updated');
  });

  it('should unsubscribe when component unmounts', () => {
    const { unmount } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    unmount();

    expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
  });

  it('should handle subscription errors gracefully', () => {
    mockSubscribe.mockImplementation(() => {
      throw new Error('Subscription failed');
    });

    const { result } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(result.current).toBe('initial');
    expect(console.warn).toHaveBeenCalledWith(
      'useSyncExternalStore: Error during subscription:',
      expect.any(Error)
    );
  });

  it('should handle getSnapshot errors gracefully', () => {
    mockGetSnapshot.mockImplementation(() => {
      throw new Error('Snapshot failed');
    });

    const { result } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    expect(result.current).toBeUndefined();
    expect(console.warn).toHaveBeenCalledWith(
      'useSyncExternalStore: Error in initial getSnapshot:',
      expect.any(Error)
    );
  });

  it('should handle unsubscribe errors gracefully', () => {
    mockUnsubscribe.mockImplementation(() => {
      throw new Error('Unsubscribe failed');
    });

    const { unmount } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    unmount();

    expect(console.warn).toHaveBeenCalledWith(
      'useSyncExternalStore: Error during unsubscribe:',
      expect.any(Error)
    );
  });

  it('should handle store change callback errors gracefully', () => {
    const { result } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    // Make getSnapshot fail during store change
    mockGetSnapshot.mockImplementationOnce(() => 'initial')
      .mockImplementationOnce(() => {
        throw new Error('Callback failed');
      });

    act(() => {
      subscribers.forEach(callback => callback());
    });

    expect(console.warn).toHaveBeenCalledWith(
      'useSyncExternalStore: Error in store change handler:',
      expect.any(Error)
    );
  });

  it('should only trigger updates when value actually changes', () => {
    const { result } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot)
    );

    const initialValue = result.current;

    // Trigger change with same value
    act(() => {
      subscribers.forEach(callback => callback());
    });

    expect(result.current).toBe(initialValue);
    expect(mockGetSnapshot).toHaveBeenCalledTimes(2); // Initial + change check
  });

  it('should work with server snapshot parameter', () => {
    const mockGetServerSnapshot = vi.fn(() => 'server-value');

    const { result } = renderHook(() =>
      useSyncExternalStore(mockSubscribe, mockGetSnapshot, mockGetServerSnapshot)
    );

    // In test environment, should use client snapshot
    expect(result.current).toBe('initial');
  });

  it('should maintain stable subscription across re-renders', () => {
    const { rerender } = renderHook((props) =>
      useSyncExternalStore(props.subscribe, props.getSnapshot),
      {
        initialProps: { subscribe: mockSubscribe, getSnapshot: mockGetSnapshot }
      }
    );

    expect(mockSubscribe).toHaveBeenCalledTimes(1);

    // Re-render with same props
    rerender({ subscribe: mockSubscribe, getSnapshot: mockGetSnapshot });

    // Should not re-subscribe
    expect(mockSubscribe).toHaveBeenCalledTimes(1);
  });
});

describe('useSyncExternalStoreWithSelector', () => {
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
    
    console.warn = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should return selected value from snapshot', () => {
    const { result } = renderHook(() =>
      useSyncExternalStoreWithSelector(
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
      useSyncExternalStoreWithSelector(
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

  it('should handle selector that returns different types', () => {
    const stringSelector = vi.fn((state) => state.name);

    const { result } = renderHook(() =>
      useSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        undefined,
        stringSelector
      )
    );

    expect(result.current).toBe('test');
    expect(stringSelector).toHaveBeenCalledWith(mockStore);
  });

  it('should work without selector (pass-through)', () => {
    const { result } = renderHook(() =>
      useSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot
      )
    );

    expect(result.current).toBe(mockStore);
  });

  it('should handle selector errors gracefully', () => {
    const errorSelector = vi.fn(() => {
      throw new Error('Selector failed');
    });

    const { result } = renderHook(() =>
      useSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        undefined,
        errorSelector
      )
    );

    expect(result.current).toBeUndefined();
    expect(console.warn).toHaveBeenCalledWith(
      'useSyncExternalStoreWithSelector: Error in getSnapshot:',
      expect.any(Error)
    );
  });

  it('should handle server snapshot with selector', () => {
    const mockGetServerSnapshot = vi.fn(() => ({ count: 100, name: 'server' }));

    const { result } = renderHook(() =>
      useSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        mockGetServerSnapshot,
        mockSelector
      )
    );

    // In test environment, should use client snapshot
    expect(result.current).toBe(5);
  });

  it('should handle server snapshot selector errors gracefully', () => {
    const mockGetServerSnapshot = vi.fn(() => {
      throw new Error('Server snapshot failed');
    });

    const { result } = renderHook(() =>
      useSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        mockGetServerSnapshot,
        mockSelector
      )
    );

    // Should still work with client snapshot
    expect(result.current).toBe(5);
  });

  it('should optimize re-renders for unchanged selected values', () => {
    let renderCount = 0;
    const countingSelector = vi.fn((state) => {
      renderCount++;
      return state.count;
    });

    const { result } = renderHook(() =>
      useSyncExternalStoreWithSelector(
        mockSubscribe,
        mockGetSnapshot,
        undefined,
        countingSelector
      )
    );

    const initialValue = result.current;
    const initialRenderCount = renderCount;

    // Update store but keep selected value the same
    act(() => {
      mockStore.name = 'changed'; // Change non-selected field
      subscribers.forEach(callback => callback());
    });

    expect(result.current).toBe(initialValue);
    // Selector should be called again but value should remain same
    expect(renderCount).toBeGreaterThan(initialRenderCount);
  });
});