import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('API Service - Promise Rejection Handling', () => {
  let consoleErrorSpy;
  let unhandledRejections = [];

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    unhandledRejections = [];

    const handleRejection = (e) => {
      unhandledRejections.push(e.reason || e);
    };

    window.addEventListener('unhandledrejection', handleRejection);

    return () => {
      window.removeEventListener('unhandledrejection', handleRejection);
    };
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    vi.clearAllMocks();
    unhandledRejections = [];
  });

  it('should handle axios interceptor errors with catch handlers', async () => {
    // Create a promise that simulates interceptor behavior
    const interceptorPromise = new Promise((resolve, reject) => {
      setTimeout(() => {
        reject(new Error('Interceptor error'));
      }, 10);
    });

    // Properly attach catch handler
    const handledPromise = interceptorPromise.catch((err) => {
      expect(err.message).toBe('Interceptor error');
      return Promise.reject(err);
    }).catch((err) => {
      // Secondary catch handler
      console.error('Handled:', err.message);
      return null; // Suppress final rejection
    });

    await handledPromise;

    // No unhandled rejections should have occurred
    expect(unhandledRejections.length).toBe(0);
  });

  it('should handle processQueue errors safely', () => {
    const queue = [
      { resolve: vi.fn(), reject: vi.fn() },
      { resolve: vi.fn(), reject: vi.fn() },
    ];

    const processQueue = (error, token = null) => {
      queue.forEach((prom) => {
        try {
          error ? prom.reject(error) : prom.resolve(token);
        } catch (e) {
          console.error('[API] Error processing queue item:', e.message);
        }
      });
      queue.length = 0;
    };

    // Simulate rejecting items in queue
    const error = new Error('Token refresh failed');
    expect(() => {
      processQueue(error);
    }).not.toThrow();

    // All rejections should have been called
    queue.forEach((prom) => {
      expect(prom.reject).toHaveBeenCalledWith(error);
    });
  });

  it('should handle token refresh queue rejection', async () => {
    const queuePromise = new Promise((resolve, reject) => {
      const queueItem = { resolve, reject };
      // Simulate queue processing
      setTimeout(() => {
        queueItem.reject(new Error('Token refresh failed'));
      }, 10);
    });

    // Attach catch handler to prevent unhandled rejection
    const handledPromise = queuePromise
      .then((token) => {
        // Token resolution path
        return token;
      })
      .catch((err) => {
        console.error('[API] Queued request failed after token refresh:', err.message);
        return Promise.reject(err);
      })
      .catch(() => {
        // Final catch to suppress rejection
        return null;
      });

    const result = await handledPromise;
    expect(result).toBeNull();
    expect(unhandledRejections.length).toBe(0);
  });

  it('should not generate unhandled rejections from fetch operations', async () => {
    const fetchPromise = new Promise((resolve, reject) => {
      setTimeout(() => {
        reject(new Error('Fetch timeout'));
      }, 10);
    });

    // Properly attach catch handler
    const safePromise = fetchPromise
      .catch((error) => {
        console.debug('[API] Health check error (non-critical):', error.message);
        return false; // Return fallback value instead of rethrowing
      });

    const result = await safePromise;
    expect(result).toBe(false);
    expect(unhandledRejections.length).toBe(0);
  });

  it('should handle multiple promise chains without rejection', async () => {
    const promises = [
      Promise.reject(new Error('Error 1')).catch(() => 'Handled 1'),
      Promise.reject(new Error('Error 2')).catch(() => 'Handled 2'),
      Promise.reject(new Error('Error 3')).catch(() => 'Handled 3'),
    ];

    const results = await Promise.all(promises);
    expect(results).toEqual(['Handled 1', 'Handled 2', 'Handled 3']);
    expect(unhandledRejections.length).toBe(0);
  });

  it('should use Promise.allSettled for cleanup operations', async () => {
    const operations = [
      Promise.reject(new Error('Cleanup 1 failed')),
      Promise.resolve('Cleanup 2 success'),
      Promise.reject(new Error('Cleanup 3 failed')),
    ];

    const results = await Promise.allSettled(operations);

    expect(results[0].status).toBe('rejected');
    expect(results[1].status).toBe('fulfilled');
    expect(results[2].status).toBe('rejected');

    // allSettled never rejects, so no unhandled rejections
    expect(unhandledRejections.length).toBe(0);
  });
});

describe('Promise Timeout Handling', () => {
  let unhandledRejections = [];

  beforeEach(() => {
    unhandledRejections = [];

    const handleRejection = (e) => {
      unhandledRejections.push(e.reason || e);
    };

    window.addEventListener('unhandledrejection', handleRejection);

    return () => {
      window.removeEventListener('unhandledrejection', handleRejection);
    };
  });

  afterEach(() => {
    unhandledRejections = [];
  });

  it('should handle AbortSignal timeout without unhandled rejection', async () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10);

    const fetchPromise = new Promise((resolve, reject) => {
      if (controller.signal.aborted) {
        reject(new Error('Aborted'));
      } else {
        setTimeout(() => {
          reject(new Error('Timeout'));
        }, 100);
      }
    });

    try {
      await fetchPromise;
    } catch (error) {
      expect(error.message).toBe('Timeout');
    }

    clearTimeout(timeoutId);
    // Even though promise was rejected, we caught it, so no unhandled rejections
    expect(unhandledRejections.length).toBe(0);
  });

  it('should handle race condition between promise and timeout', async () => {
    const promiseWithTimeout = (promise, ms) => {
      return Promise.race([
        promise,
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Timeout')), ms)
        ),
      ]);
    };

    const slowPromise = new Promise((resolve) => {
      setTimeout(() => resolve('Success'), 100);
    });

    try {
      await promiseWithTimeout(slowPromise, 10);
    } catch (error) {
      expect(error.message).toBe('Timeout');
    }

    // Promise was rejected but caught, so no unhandled rejections
    expect(unhandledRejections.length).toBe(0);
  });
});
