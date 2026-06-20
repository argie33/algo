import { renderHook, act, waitFor } from '@testing-library/react';
import { useFormSubmit } from '../../../hooks/useFormSubmit';

describe('useFormSubmit', () => {
  test('should initialize with correct state', () => {
    const mockSubmit = jest.fn();
    const { result } = renderHook(() => useFormSubmit(mockSubmit));

    expect(result.current.isSubmitting).toBe(false);
    expect(result.current.error).toBe(null);
    expect(result.current.success).toBe(false);
  });

  test('should call submitFn and return success', async () => {
    const mockData = { success: true, data: { id: '123', name: 'Test' } };
    const mockSubmit = jest.fn().mockResolvedValue(mockData);

    const { result } = renderHook(() => useFormSubmit(mockSubmit));

    let submitResult;
    await act(async () => {
      submitResult = await result.current.submit({ name: 'Test' });
    });

    expect(mockSubmit).toHaveBeenCalledWith({ name: 'Test' });
    expect(submitResult.success).toBe(true);
    expect(submitResult.data).toEqual(mockData);
    expect(result.current.success).toBe(true);
    expect(result.current.error).toBe(null);
  });

  test('should handle API errors', async () => {
    const mockError = new Error('API failed');
    const mockSubmit = jest.fn().mockRejectedValue(mockError);

    const { result } = renderHook(() => useFormSubmit(mockSubmit));

    let submitResult;
    await act(async () => {
      submitResult = await result.current.submit({ name: 'Test' });
    });

    expect(submitResult.success).toBe(false);
    expect(submitResult.error).toBe('API failed');
    expect(result.current.error).toBe('API failed');
    expect(result.current.success).toBe(false);
  });

  test('should handle response with error field', async () => {
    const mockData = { error: 'Validation failed' };
    const mockSubmit = jest.fn().mockResolvedValue(mockData);

    const { result } = renderHook(() => useFormSubmit(mockSubmit));

    let submitResult;
    await act(async () => {
      submitResult = await result.current.submit({ name: 'Test' });
    });

    expect(submitResult.success).toBe(false);
    expect(submitResult.error).toBe('Validation failed');
    expect(result.current.error).toBe('Validation failed');
  });

  test('should timeout on slow submissions', async () => {
    const slowSubmit = jest.fn(
      () => new Promise((resolve) => {
        setTimeout(() => resolve({ success: true }), 5000);
      })
    );

    const { result } = renderHook(() => useFormSubmit(slowSubmit, { timeout: 100 }));

    let submitResult;
    await act(async () => {
      submitResult = await result.current.submit({ name: 'Test' });
    });

    expect(submitResult.success).toBe(false);
    expect(submitResult.error).toContain('timeout');
  });

  test('should call onSuccess callback on success', async () => {
    const mockData = { success: true, id: '123' };
    const mockSubmit = jest.fn().mockResolvedValue(mockData);
    const onSuccess = jest.fn();

    renderHook(() => useFormSubmit(mockSubmit, { onSuccess }));

    const { result } = renderHook(() => useFormSubmit(mockSubmit, { onSuccess }));

    await act(async () => {
      await result.current.submit({ name: 'Test' });
    });

    expect(onSuccess).toHaveBeenCalledWith(mockData);
  });

  test('should call onError callback on failure', async () => {
    const mockError = new Error('API failed');
    const mockSubmit = jest.fn().mockRejectedValue(mockError);
    const onError = jest.fn();

    const { result } = renderHook(() => useFormSubmit(mockSubmit, { onError }));

    await act(async () => {
      await result.current.submit({ name: 'Test' });
    });

    expect(onError).toHaveBeenCalledWith(mockError);
  });

  test('should reset error state', async () => {
    const mockSubmit = jest.fn().mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => useFormSubmit(mockSubmit));

    // First submit fails
    await act(async () => {
      await result.current.submit({ name: 'Test' });
    });

    expect(result.current.error).toBe('Failed');

    // Reset error
    act(() => {
      result.current.reset();
    });

    expect(result.current.error).toBe(null);
    expect(result.current.success).toBe(false);
  });

  test('should set isSubmitting during submission', async () => {
    let resolveSubmit;
    const mockSubmit = jest.fn(
      () => new Promise((resolve) => {
        resolveSubmit = resolve;
      })
    );

    const { result } = renderHook(() => useFormSubmit(mockSubmit));

    const submitPromise = act(async () => {
      result.current.submit({ name: 'Test' });
    });

    // During submission, isSubmitting should be true
    await waitFor(() => {
      expect(result.current.isSubmitting).toBe(true);
    });

    // Resolve the submission
    act(() => {
      resolveSubmit({ success: true });
    });

    await submitPromise;

    // After submission, isSubmitting should be false
    expect(result.current.isSubmitting).toBe(false);
  });

  test('should handle null response gracefully', async () => {
    const mockSubmit = jest.fn().mockResolvedValue(null);

    const { result } = renderHook(() => useFormSubmit(mockSubmit));

    let submitResult;
    await act(async () => {
      submitResult = await result.current.submit({ name: 'Test' });
    });

    expect(submitResult.success).toBe(false);
    expect(submitResult.error).toContain('No response');
  });
});
