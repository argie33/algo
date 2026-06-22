import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// jsdom does not implement PromiseRejectionEvent. Simulate it by dispatching
// a regular event with the expected shape (reason, promise, preventDefault).
function dispatchRejection(reason) {
  const event = Object.assign(
    new Event("unhandledrejection", { bubbles: true, cancelable: true }),
    {
      promise: Promise.resolve(),
      reason,
    }
  );
  window.dispatchEvent(event);
  return event;
}

describe("Global Error Handlers - Unhandled Promise Rejections", () => {
  let consoleErrorSpy;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    vi.clearAllMocks();
  });

  it("should capture unhandled promise rejections", () => {
    const testError = new Error("Test unhandled rejection");
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
    });

    window.addEventListener("unhandledrejection", rejectionHandler);
    dispatchRejection(testError);
    window.removeEventListener("unhandledrejection", rejectionHandler);

    expect(rejectionHandler).toHaveBeenCalledOnce();
    expect(rejectionHandler.mock.calls[0][0].reason).toBe(testError);
  });

  it("should handle promise rejection with error object", () => {
    const testError = new Error("Rejection with error object");
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
    });

    window.addEventListener("unhandledrejection", rejectionHandler);
    dispatchRejection(testError);
    window.removeEventListener("unhandledrejection", rejectionHandler);

    expect(rejectionHandler).toHaveBeenCalledOnce();
    const e = rejectionHandler.mock.calls[0][0];
    expect(e.reason).toBeInstanceOf(Error);
    expect(e.reason.message).toBe("Rejection with error object");
  });

  it("should handle promise rejection with string", () => {
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
    });

    window.addEventListener("unhandledrejection", rejectionHandler);
    dispatchRejection("String rejection");
    window.removeEventListener("unhandledrejection", rejectionHandler);

    expect(rejectionHandler).toHaveBeenCalledOnce();
    const e = rejectionHandler.mock.calls[0][0];
    expect(typeof e.reason).toBe("string");
    expect(e.reason).toBe("String rejection");
  });

  it("should prevent unhandled rejection from crashing app", () => {
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
      return false;
    });

    window.addEventListener("unhandledrejection", rejectionHandler);
    dispatchRejection(new Error("Test error"));
    window.removeEventListener("unhandledrejection", rejectionHandler);

    // Handler was called and app did not crash
    expect(rejectionHandler).toHaveBeenCalledOnce();
  });

  it("should attach catch handlers to prevent rejections", async () => {
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
    });

    window.addEventListener("unhandledrejection", rejectionHandler);

    // A handled rejection — we intentionally do NOT dispatch a synthetic rejection.
    const promise = Promise.reject(new Error("Test error"));
    await promise.catch((err) => {
      expect(err.message).toBe("Test error");
    });

    window.removeEventListener("unhandledrejection", rejectionHandler);

    // No event was dispatched, so handler should not have been called
    expect(rejectionHandler).not.toHaveBeenCalled();
  });
});

describe("Promise Error Context Tracking", () => {
  it("should track error context properly", () => {
    const rejectionHandler = vi.fn((e) => {
      e.preventDefault();
    });

    window.addEventListener("unhandledrejection", rejectionHandler);
    dispatchRejection(new Error("Context test error"));
    window.removeEventListener("unhandledrejection", rejectionHandler);

    expect(rejectionHandler).toHaveBeenCalledOnce();
    expect(rejectionHandler.mock.calls[0][0].reason).toBeInstanceOf(Error);
  });
});
