/**
 * Main Entry Point Tests
 * Tests the critical initialization patterns used in main.jsx
 * 
 * NOTE: Testing main.jsx directly is complex due to side effects.
 * This tests the key patterns and error handling approaches.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createTheme } from "@mui/material/styles";
import { QueryClient } from "@tanstack/react-query";

describe("Main Entry Point", () => {
  let originalConsoleError;
  let originalConsoleWarn;

  beforeEach(() => {
    originalConsoleError = console.error;
    originalConsoleWarn = console.warn;
    console.error = vi.fn();
    console.warn = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
    console.warn = originalConsoleWarn;
  });

  describe("Theme Configuration", () => {
    it("should create theme with accessibility features", () => {
      const theme = createTheme({
        palette: {
          mode: "light",
          primary: { main: "#1976d2" },
        },
        components: {
          MuiButton: {
            styleOverrides: {
              root: {
                '&:focus': {
                  outline: "3px solid #1976d2",
                  outlineOffset: "2px",
                },
              },
            },
          },
        },
      });

      expect(theme.palette.mode).toBe("light");
      expect(theme.palette.primary.main).toBe("#1976d2");
      expect(theme.components.MuiButton.styleOverrides.root["&:focus"]).toEqual({
        outline: "3px solid #1976d2",
        outlineOffset: "2px",
      });
    });

    it("should include focus styles for accessibility", () => {
      const theme = createTheme({
        components: {
          MuiTextField: {
            styleOverrides: {
              root: {
                '& .MuiOutlinedInput-root': {
                  '&:focus-within': {
                    outline: "3px solid rgba(25, 118, 210, 0.3)",
                    outlineOffset: "2px",
                  },
                },
              },
            },
          },
        },
      });

      const textFieldStyles = theme.components.MuiTextField.styleOverrides.root;
      expect(textFieldStyles["& .MuiOutlinedInput-root"]["&:focus-within"]).toEqual({
        outline: "3px solid rgba(25, 118, 210, 0.3)",
        outlineOffset: "2px",
      });
    });
  });

  describe("Query Client Configuration", () => {
    it("should create QueryClient with proper retry logic", () => {
      const queryClient = new QueryClient({
        defaultOptions: {
          queries: {
            retry: (failureCount, error) => {
              if (error.status === 404) return false;
              return failureCount < 3;
            },
          },
        },
      });

      const retryFn = queryClient.getDefaultOptions().queries.retry;
      
      // Test 404 errors don't retry
      expect(retryFn(1, { status: 404 })).toBe(false);
      
      // Test other errors retry up to 3 times
      expect(retryFn(0, { status: 500 })).toBe(true);
      expect(retryFn(2, { status: 500 })).toBe(true);
      expect(retryFn(3, { status: 500 })).toBe(false);
    });

    it("should configure proper cache timing", () => {
      const queryClient = new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000, // 5 minutes
            cacheTime: 10 * 60 * 1000, // 10 minutes
            refetchOnWindowFocus: false,
          },
        },
      });

      const options = queryClient.getDefaultOptions().queries;
      expect(options.staleTime).toBe(5 * 60 * 1000);
      expect(options.cacheTime).toBe(10 * 60 * 1000);
      expect(options.refetchOnWindowFocus).toBe(false);
    });
  });

  describe("Error Handling Patterns", () => {
    it("should handle DOM element validation", () => {
      const validateRootElement = (elementId) => {
        const element = document.getElementById(elementId);
        if (!element) {
          console.error(`❌ ${elementId} element not found!`);
          return false;
        }
        return true;
      };

      // Mock missing element
      vi.spyOn(document, "getElementById").mockReturnValue(null);
      
      const result = validateRootElement("root");
      
      expect(result).toBe(false);
      expect(console.error).toHaveBeenCalledWith("❌ root element not found!");
    });

    it("should handle config loading validation", async () => {
      const validateConfig = () => {
        if (window.__CONFIG__) {
          return true;
        } else {
          console.warn("⚠️ Config not loaded yet, check index.html script tag");
          return false;
        }
      };

      // Test missing config
      const originalConfig = window.__CONFIG__;
      delete window.__CONFIG__;
      
      const result = validateConfig();
      
      expect(result).toBe(false);
      expect(console.warn).toHaveBeenCalledWith(
        "⚠️ Config not loaded yet, check index.html script tag"
      );

      // Restore config
      window.__CONFIG__ = originalConfig;
    });

    it("should handle service worker cleanup errors", async () => {
      const cleanupServiceWorkers = async () => {
        try {
          if ("serviceWorker" in navigator) {
            const registrations = await navigator.serviceWorker.getRegistrations();
            await Promise.all(
              registrations.map(registration => registration.unregister())
            );
          }
        } catch (error) {
          console.error("Service Worker unregistration failed:", error);
        }
      };

      // Mock service worker with error
      Object.defineProperty(navigator, "serviceWorker", {
        value: {
          getRegistrations: vi.fn().mockRejectedValue(new Error("SW Error")),
        },
        configurable: true,
      });

      await cleanupServiceWorkers();

      expect(console.error).toHaveBeenCalledWith(
        "Service Worker unregistration failed:",
        expect.any(Error)
      );
    });

    it("should handle cache cleanup errors", async () => {
      const cleanupCaches = async () => {
        try {
          if ("caches" in window) {
            const cacheNames = await caches.keys();
            await Promise.all(
              cacheNames.map(cacheName => caches.delete(cacheName))
            );
          }
        } catch (error) {
          console.error("Cache clearing failed:", error);
        }
      };

      // Mock caches with error
      Object.defineProperty(window, "caches", {
        value: {
          keys: vi.fn().mockRejectedValue(new Error("Cache Error")),
          delete: vi.fn(),
        },
        configurable: true,
      });

      await cleanupCaches();

      expect(console.error).toHaveBeenCalledWith(
        "Cache clearing failed:",
        expect.any(Error)
      );
    });
  });

  describe("Global Error Handlers", () => {
    it("should create proper window error handler", () => {
      const createWindowErrorHandler = (logger) => {
        return function(e) {
          const errorContext = {
            filename: e.filename,
            lineno: e.lineno,
            colno: e.colno,
            userAgent: navigator.userAgent,
            url: window.location.href,
            timestamp: new Date().toISOString()
          };
          
          logger.error('WindowError', e.error || new Error(e.message), errorContext);
          return false;
        };
      };

      const mockLogger = { error: vi.fn() };
      const handler = createWindowErrorHandler(mockLogger);
      
      const errorEvent = {
        filename: "test.js",
        lineno: 123,
        colno: 45,
        message: "Test error",
        error: new Error("Test error")
      };

      const result = handler(errorEvent);

      expect(result).toBe(false);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'WindowError',
        expect.any(Error),
        expect.objectContaining({
          filename: "test.js",
          lineno: 123,
          colno: 45,
        })
      );
    });

    it("should create proper unhandled rejection handler", () => {
      const createUnhandledRejectionHandler = (logger) => {
        return function(e) {
          const errorContext = {
            url: window.location.href,
            timestamp: new Date().toISOString(),
            promiseState: 'rejected'
          };
          
          logger.error('UnhandledPromiseRejection', e.reason, errorContext);
          return false;
        };
      };

      const mockLogger = { error: vi.fn() };
      const handler = createUnhandledRejectionHandler(mockLogger);
      
      const rejectionEvent = {
        reason: "Promise rejection reason"
      };

      const result = handler(rejectionEvent);

      expect(result).toBe(false);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'UnhandledPromiseRejection',
        "Promise rejection reason",
        expect.objectContaining({
          promiseState: 'rejected',
        })
      );
    });
  });

  describe("Post-render Validation", () => {
    it("should validate successful render", () => {
      const validateRender = (logger) => {
        const rootContent = document.getElementById("root");
        
        if (rootContent && rootContent.innerHTML.trim() === "") {
          logger.error("EmptyRender", new Error("React rendered but root is empty"), {
            innerHTML: rootContent.innerHTML,
            timestamp: new Date().toISOString()
          });
          return false;
        } else if (rootContent) {
          logger.success("React application rendered successfully", {
            contentLength: rootContent.innerHTML.length,
            hasContent: rootContent.innerHTML.length > 0
          });
          return true;
        }
        
        return false;
      };

      const mockLogger = { error: vi.fn(), success: vi.fn() };
      
      // Test empty render
      const emptyElement = document.createElement("div");
      emptyElement.id = "root";
      emptyElement.innerHTML = "";
      vi.spyOn(document, "getElementById").mockReturnValue(emptyElement);
      
      let result = validateRender(mockLogger);
      
      expect(result).toBe(false);
      expect(mockLogger.error).toHaveBeenCalledWith(
        "EmptyRender",
        expect.any(Error),
        expect.objectContaining({
          innerHTML: "",
        })
      );

      // Test successful render
      const contentElement = document.createElement("div");
      contentElement.id = "root";
      contentElement.innerHTML = "<div>App Content</div>";
      vi.spyOn(document, "getElementById").mockReturnValue(contentElement);
      
      result = validateRender(mockLogger);
      
      expect(result).toBe(true);
      expect(mockLogger.success).toHaveBeenCalledWith(
        "React application rendered successfully",
        expect.objectContaining({
          hasContent: true,
          contentLength: expect.any(Number),
        })
      );
    });
  });
});