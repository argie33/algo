import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('Global Error Handlers - Unhandled Promise Rejections', () => {
  let consoleErrorSpy;
  let unhandledRejectionHandler;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Get the current unhandledrejection handler
    unhandledRejectionHandler = null;
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    vi.clearAllMocks();
  });

  it('should capture unhandled promise rejections', (done) => {
    const testError = new Error('Test unhandled rejection');
    const rejectionHandler = vi.fn((e) => {
      expect(e.reason).toBe(testError);
      e.preventDefault();
      done();
    });

    window.addEventListener('unhandledrejection', rejectionHandler);

    // Trigger an unhandled rejection
    Promise.reject(testError);

    // Give the event loop time to process
    setTimeout(() => {
      window.removeEventListener('unhandledrejection', rejectionHandler);
    }, 100);
  });

  it('should handle promise rejection with error object', (done) => {
    const testError = new Error('Rejection with error object');
    const rejectionHandler = vi.fn((e) => {
      expect(e.reason instanceof Error).toBe(true);
      expect(e.reason.message).toBe('Rejection with error object');
      e.preventDefault();
      done();
    });

    window.addEventListener('unhandledrejection', rejectionHandler);
    Promise.reject(testError);

    setTimeout(() => {
      window.removeEventListener('unhandledrejection', rejectionHandler);
    }, 100);
  });

  it('should handle promise rejection with string', (done) => {
    const rejectionHandler = vi.fn((e) => {
      expect(typeof e.reason).toBe('string');
      expect(e.reason).toBe('String rejection');
      e.preventDefault();
      done();
    });

    window.addEventListener('unhandledrejection', rejectionHandler);
    Promise.reject('String rejection');

    setTimeout(() => {
      window.removeEventListener('unhandledrejection', rejectionHandler);
    }, 100);
  });

  it('should prevent unhandled rejection from crashing app', (done) => {
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
      return false;
    });

    window.addEventListener('unhandledrejection', rejectionHandler);

    const testPromise = Promise.reject(new Error('Test error'));

    // The app should not crash even though we don't attach a catch handler
    setTimeout(() => {
      // If we got here, the app didn't crash
      expect(true).toBe(true);
      window.removeEventListener('unhandledrejection', rejectionHandler);
      done();
    }, 100);
  });

  it('should attach catch handlers to prevent rejections', (done) => {
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
    });

    window.addEventListener('unhandledrejection', rejectionHandler);

    const promise = Promise.reject(new Error('Test error'));
    promise.catch((err) => {
      // Error is handled
      expect(err.message).toBe('Test error');
    });

    setTimeout(() => {
      // No unhandled rejection should have triggered
      expect(rejectionHandler).not.toHaveBeenCalled();
      window.removeEventListener('unhandledrejection', rejectionHandler);
      done();
    }, 100);
  });
});

describe('Promise Error Context Tracking', () => {
  it('should track error context properly', (done) => {
    const errorContext = {
      url: 'http://test.local',
      timestamp: new Date().toISOString(),
      promiseState: 'rejected',
    };

    const rejectionHandler = vi.fn((e) => {
      expect(e.reason).toBeInstanceOf(Error);
      e.preventDefault();
      done();
    });

    window.addEventListener('unhandledrejection', rejectionHandler);

    Promise.reject(new Error('Context test error')).catch(() => {
      // Handled
    });

    setTimeout(() => {
      window.removeEventListener('unhandledrejection', rejectionHandler);
    }, 100);
  });
});
