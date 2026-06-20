import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useApiQuery, useApiPaginatedQuery } from '../../../hooks/useApiQuery';
import * as dataCache from '../../../services/dataCache';
import React from 'react';

vi.mock('../../../services/dataCache', () => ({
  default: {
    get: vi.fn(),
    set: vi.fn(),
    delete: vi.fn(),
    clear: vi.fn(),
    getMarketData: vi.fn(),
    setMarketData: vi.fn(),
    cleanup: vi.fn(),
    getMetadata: vi.fn(),
  },
  get: vi.fn(),
  set: vi.fn(),
}));

describe('useApiQuery - Response Envelope Validation', () => {
  let queryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: 0 } },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const wrapper = ({ children }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);

  it('should successfully unwrap valid envelope {data: {...}}', async () => {
    const mockPayload = { id: 1, name: 'Test Signal' };
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: mockPayload,
      },
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeDefined();
    expect(result.current.data.id).toBe(1);
    expect(result.current.data.name).toBe('Test Signal');
    expect(result.current.error).toBeNull();
  });

  it('should throw error when envelope.data is null', async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: null, // Problem: API returned {data: null}
      },
    });

    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-null-data'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(result.current.error.message).toContain('Invalid response envelope');
    expect(result.current.error.message).toContain('null data field');
    expect(result.current.data).toBeUndefined();
  });

  it('should warn but allow empty object {}', async () => {
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: {}, // Empty object
      },
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-empty-obj'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Data should contain empty object fields plus metadata
    expect(result.current.data).toHaveProperty('_fetchedAt');
    expect(result.current.data).toHaveProperty('_age');
    expect(consoleWarnSpy).toHaveBeenCalledWith(
      expect.stringContaining('empty object'),
      expect.anything()
    );

    consoleWarnSpy.mockRestore();
  });

  it('should throw error when envelope.data is not an object', async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: 'string-value', // Problem: data is a string
      },
    });

    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-string-data'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(result.current.error.message).toContain('Invalid response envelope');
  });

  it('should throw error when envelope.data is a number', async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: 42, // Problem: data is a number
      },
    });

    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-number-data'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(result.current.error.message).toContain('Invalid response envelope');
  });

  it('should pass through paginated response without unwrapping', async () => {
    const mockItems = [{ id: 1 }, { id: 2 }];
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        items: mockItems,
        pagination: { total: 2, page: 1, limit: 50 },
      },
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-items'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // For paginated responses, data has items and pagination
    expect(result.current.data).toBeDefined();
    expect(result.current.data.items).toEqual(mockItems);
    expect(result.current.error).toBeNull();
  });

  it('should pass through direct array response', async () => {
    const mockArray = [{ id: 1 }, { id: 2 }];
    const queryFn = vi.fn().mockResolvedValue({
      data: mockArray, // Direct array, not wrapped
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-direct-array'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Direct array response is wrapped in items
    expect(result.current.data.items).toEqual(mockArray);
    expect(result.current.error).toBeNull();
  });

  it('should handle envelope structure variations gracefully', async () => {
    // Test that extractData normalizes arrays in data field
    // (this is tested at extractData level, not useApiQuery)
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: [{ id: 1 }], // extractData converts this to items format
      },
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-array-data'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // extractData already converted array data to items format
    expect(result.current.data).toBeDefined();
    expect(result.current.error).toBeNull();
  });

  it('should handle response without envelope structure (fallback mode)', async () => {
    const mockData = { id: 1, name: 'Fallback' };
    const queryFn = vi.fn().mockResolvedValue({
      data: mockData, // No statusCode/success/data wrapper
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-no-envelope'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Should pass through as-is when no envelope detected
    expect(result.current.data).toBeDefined();
    expect(result.current.error).toBeNull();
  });

  it('should cache unwrapped data correctly', async () => {
    const mockPayload = { id: 1, name: 'Cached Signal' };
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: mockPayload,
      },
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    renderHook(() => useApiQuery(['test-cache'], queryFn), { wrapper });

    await waitFor(() => {
      expect(dataCache.default.set).toHaveBeenCalled();
    });

    // Verify cache received the UNWRAPPED data (not the envelope)
    const cacheCall = dataCache.default.set.mock.calls[0];
    expect(cacheCall[0]).toBe('test-cache'); // Cache key
    // The second argument is the unwrapped payload, but with metadata added
    // So we just check it has the payload fields
    expect(cacheCall[1]).toHaveProperty('id', 1);
  });

  it('should validate metadata fields are added after unwrapping', async () => {
    const mockPayload = { symbol: 'AAPL' };
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        data: mockPayload,
      },
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(['test-metadata'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // Metadata should be added to unwrapped data
    expect(result.current.data).toHaveProperty('symbol', 'AAPL');
    expect(result.current.data).toHaveProperty('_fetchedAt');
    expect(result.current.data).toHaveProperty('_age');
    expect(result.current.data).toHaveProperty('_fromCache', false);
    expect(result.current.data).toHaveProperty('_isStale');
  });
});

describe('useApiPaginatedQuery - Response Envelope Validation', () => {
  let queryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: 0 } },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const wrapper = ({ children }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);

  it('should extract items from paginated response', async () => {
    const mockItems = [{ id: 1, symbol: 'AAPL' }, { id: 2, symbol: 'MSFT' }];
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        items: mockItems,
        pagination: {
          total: 2,
          page: 1,
          limit: 50,
          hasNext: false,
          hasPrev: false,
        },
      },
    });

    dataCache.default.set.mockResolvedValue(undefined);
    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiPaginatedQuery(['test-paginated'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toEqual(mockItems);
    expect(result.current.pagination.total).toBe(2);
    expect(result.current.error).toBeNull();
  });

  it('should return empty array when items is null', async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        items: null,
      },
    });

    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiPaginatedQuery(['test-null-items'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('should return empty array when items is missing', async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: {
        statusCode: 200,
        success: true,
        // No items property
      },
    });

    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiPaginatedQuery(['test-no-items'], queryFn), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.error).toBeNull();
  });
});
