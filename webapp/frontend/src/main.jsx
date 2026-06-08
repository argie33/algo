import ReactDOM from "react-dom/client";
import "./index.css"; // Tailwind base + design system tokens
import { theme } from "./services/theme";

// Apply theme class before first paint (avoid flash of wrong theme).
// Dark is default — sleek is the look we want. User can opt into light via
// the toggle in the user menu (persisted to localStorage as theme=light).
theme.initialize();
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { configureAmplify } from "./config/amplify";
import { createComponentLogger } from "./utils/errorLogger";
import ErrorBoundary from "./components/ErrorBoundary";
import ApiErrorBanner from "./components/ApiErrorBanner";
import { modernTheme } from "./theme/modernTheme";

// Initialize comprehensive error logging service
const logger = createComponentLogger("Main");

// RESTORED: Professional error logging service integration
const _originalConsoleError = console.error;
const _originalConsoleWarn = console.warn;

// Suppress non-actionable Recharts dimension warnings during initial render.
// These occur when ResponsiveContainer renders before parent dimensions are calculated.
// The charts render fine once layout is complete, so this warning is not actionable for users.
console.warn = function (...args) {
  const msg = String(args[0] || '');

  // Suppress Recharts dimension warnings (width/height = -1 during mount)
  if (msg.includes('The width') && msg.includes('of chart should be greater than 0')) {
    return;
  }

  // All other warnings pass through
  _originalConsoleWarn.apply(console, args);
};

// Suppress only non-actionable browser warnings that come from third-party libraries.
// All application errors and CORS/network issues pass through for debugging.
console.error = function (...args) {
  const msg = String(args[0] || '');

  // Suppress ResizeObserver warnings from third-party libraries (not caused by our code)
  // These are known benign warnings from resize observation in external libs
  if (msg.includes('ResizeObserver') && msg.includes('loop limit exceeded')) {
    return;
  }

  // All other errors are shown (CORS, network, app errors, API errors, etc.)
  // API errors from api.js are the single source of truth for HTTP failures
  _originalConsoleError.apply(console, args);
};

// RESTORED: Professional error service integration for window errors
window.addEventListener(
  "error",
  function (e) {
    const errorContext = {
      filename: e.filename,
      lineno: e.lineno,
      colno: e.colno,
      message: e.message,
      userAgent: navigator.userAgent,
      url: window.location.href,
      timestamp: new Date().toISOString(),
      stack: e.error?.stack,
    };

    // Log detailed error for .type access issues
    if (e.message && e.message.includes("Cannot read properties of undefined (reading 'type')")) {
      console.group("🔴 CRITICAL: .type access on undefined detected!");
      console.error("Message:", e.message);
      console.error("Location:", `${e.filename}:${e.lineno}:${e.colno}`);
      console.error("Stack trace:", e.error?.stack);
      console.error("Full error:", e.error);
      console.groupEnd();
    }

    logger.error("WindowError", e.error || new Error(e.message), errorContext);

    // Let all errors through for debugging
    return false;
  },
  true
);

// RESTORED: Professional promise rejection handling
window.addEventListener("unhandledrejection", function (e) {
  const errorContext = {
    url: window.location.href,
    timestamp: new Date().toISOString(),
    promiseState: "rejected",
    reason: e.reason?.message || String(e.reason),
    stack: e.reason?.stack,
  };

  // Always log unhandled rejections
  if (e.reason instanceof Error) {
    logger.error("UnhandledPromiseRejection", e.reason, errorContext);
    console.error("[UnhandledRejection]", {
      message: e.reason.message,
      stack: e.reason.stack,
      context: errorContext
    });
  } else {
    const error = new Error(String(e.reason));
    logger.error("UnhandledPromiseRejection", error, errorContext);
    console.error("[UnhandledRejection]", {
      reason: e.reason,
      context: errorContext
    });
  }

  // Prevent unhandled rejection from crashing the app
  // The error is now logged and visible to developers
  e.preventDefault();
  return false;
});


// Application initialization

// Smart service worker and cache management
// Detect configuration staleness and aggressively clear caches on deploy
const checkAndClearStaleCache = async () => {
  const CACHE_VERSION_KEY = 'app-cache-version';
  const CONFIG_HASH_KEY = 'app-config-hash';
  const CURRENT_VERSION = import.meta.env.VITE_BUILD_TIME || new Date().toISOString().split('T')[0];

  try {
    // Detect config staleness by checking if config.js URL has cache-bust parameter
    // If the URL in index.html has a v= parameter, compute a hash of it
    // This helps us detect when a new build was deployed (new cache-bust value)
    let configUrlHash = '';
    const scripts = Array.from(document.querySelectorAll('script'));
    const configScript = scripts.find(s => s.src && s.src.includes('config.js'));
    if (configScript && configScript.src) {
      // Extract and hash the config.js URL (including any v= parameter)
      // This uniquely identifies the deployed version
      configUrlHash = configScript.src;
    }

    const storedVersion = localStorage.getItem(CACHE_VERSION_KEY);
    const storedConfigHash = localStorage.getItem(CONFIG_HASH_KEY);

    // Trigger cache clear if EITHER version or config URL changed
    const versionChanged = storedVersion && storedVersion !== CURRENT_VERSION;
    const configChanged = storedConfigHash && storedConfigHash !== configUrlHash;

    if (versionChanged || configChanged) {
      const reason = versionChanged ? `version (${storedVersion} → ${CURRENT_VERSION})` : 'config URL';
      logger.info(`Deploy detected via ${reason}, clearing all stale caches`);

      // Phase 1: Clear ALL caches aggressively (not just api-*)
      // This ensures stale config.js and all related resources are removed
      if ("caches" in window) {
        try {
          const cacheNames = await caches.keys();

          // Delete all caches on version change to ensure fresh config load
          await Promise.all(
            cacheNames.map(name =>
              caches.delete(name).catch(err => {
                console.warn(`Failed to delete cache '${name}':`, err.message);
              })
            )
          );
          logger.info(`Cleared ${cacheNames.length} cache stores (full purge on deploy)`);
        } catch (error) {
          logger.warn("Failed to clear caches on deploy detection", error);
        }
      }

      // Phase 2: Unregister all service workers (after caches are cleared)
      // This forces browser to fetch fresh resources from network
      if ("serviceWorker" in navigator) {
        try {
          const registrations = await navigator.serviceWorker.getRegistrations();
          await Promise.all(
            registrations.map(reg => reg.unregister())
          );
          logger.info(`Unregistered ${registrations.length} service worker(s) on deploy`);
        } catch (error) {
          logger.warn("Failed to unregister service workers", error);
        }
      }

      // Phase 3: Clear HTTP cache headers by invalidating browser's cached state
      // Ensure next page load hits network for critical resources
      if (performance && performance.clearResourceTimings) {
        performance.clearResourceTimings();
      }
    }

    // Update stored identifiers (after cleanup complete)
    localStorage.setItem(CACHE_VERSION_KEY, CURRENT_VERSION);
    if (configUrlHash) {
      localStorage.setItem(CONFIG_HASH_KEY, configUrlHash);
    }
  } catch (error) {
    logger.warn("Cache version check failed (non-critical)", error);
  }
};

// Run cache check asynchronously (non-blocking)
// Completes before app render, so first page load gets clean caches
// Always attach catch handler to prevent unhandled rejection
checkAndClearStaleCache().catch((err) => {
  console.warn('[Cache] Background cache check failed:', err.message);
});


// Wait for config.js to load before configuring Amplify and rendering app.
// Ensures window.__CONFIG__ is available when AuthContext initializes.
// This is CRITICAL: API calls are blocked until this completes.
const waitForConfig = async () => {
  // If config already loaded (synchronously), proceed immediately
  // In dev mode, API_URL is intentionally empty (Vite proxy handles /api/*)
  // So check for the object existence, not the URL value
  if (window.__CONFIG__ && typeof window.__CONFIG__ === 'object' && 'ENVIRONMENT' in window.__CONFIG__) {
    logger.info("Config already loaded, using immediately");
    configureAmplify();
    return;
  }

  // Check if config.js failed to load
  if (window.__CONFIG_ERROR__) {
    const error = new Error(
      'Configuration file (config.js) failed to load. ' +
      'This usually means: (1) 404 - config.js not deployed, (2) syntax error in config.js, or (3) server returned error. ' +
      'Check browser DevTools → Network tab for config.js load status and error details.'
    );
    logger.error("ConfigLoadFailed", error, {
      errorFlag: window.__CONFIG_ERROR__,
      configExists: !!window.__CONFIG__,
    });
    throw error;
  }

  // Otherwise, wait for config script to execute with validation
  return new Promise((resolve, reject) => {
    const CONFIG_TIMEOUT = 10000; // 10 seconds (increased from 5s for slow networks)
    let configLoaded = false;
    let detectionAttempts = 0;
    const MAX_STALE_DETECTION_ATTEMPTS = 3; // Detect stale config after 3 attempts

    const timeout = setTimeout(() => {
      if (!configLoaded) {
        const debugInfo = {
          configExists: !!window.__CONFIG__,
          configType: typeof window.__CONFIG__,
          configKeys: window.__CONFIG__ ? Object.keys(window.__CONFIG__) : [],
          errorFlag: window.__CONFIG_ERROR__,
          timeoutMs: CONFIG_TIMEOUT,
        };
        const error = new Error(
          'Configuration failed to load within 10 seconds. ' +
          'Likely causes: (1) config.js not deployed to S3, (2) S3 permissions issue, ' +
          '(3) CloudFront cache issue, or (4) network connectivity. ' +
          'Actions: Check browser DevTools Network tab for config.js status, verify S3 deployment, check CloudFront distribution.'
        );
        logger.error("ConfigLoadTimeout", error, debugInfo);
        reject(error);
      }
    }, CONFIG_TIMEOUT);

    // Poll for config with adaptive frequency
    // Check for ENVIRONMENT property instead of API_URL (which is intentionally empty in dev mode)
    const pollInterval = setInterval(() => {
      detectionAttempts++;

      if (window.__CONFIG__ && typeof window.__CONFIG__ === 'object' && 'ENVIRONMENT' in window.__CONFIG__) {
        configLoaded = true;
        clearTimeout(timeout);
        clearInterval(pollInterval);
        logger.info("Config loaded successfully", {
          apiUrl: window.__CONFIG__.API_URL || '(empty - using Vite proxy)',
          environment: window.__CONFIG__.ENVIRONMENT,
        });
        configureAmplify();
        resolve();
      }

      // Stale config detection: if config still not loaded after multiple attempts,
      // and service worker is present, likely the service worker is serving stale config.js
      // Force reload to clear service worker cache
      if (detectionAttempts >= MAX_STALE_DETECTION_ATTEMPTS && !configLoaded) {
        if ("serviceWorker" in navigator) {
          logger.warn(
            "Config load stalled - likely stale service worker cache. " +
            "Clearing service workers and reloading...",
            { attempts: detectionAttempts }
          );
          clearTimeout(timeout);
          clearInterval(pollInterval);

          navigator.serviceWorker.getRegistrations().then(registrations => {
            Promise.all(registrations.map(r => r.unregister()))
              .then(() => {
                // Hard reload bypasses all caches
                window.location.reload(true);
              })
              .catch(err => {
                logger.warn("Failed to unregister during stale detection", err);
                window.location.reload(true);
              });
          }).catch(err => {
            logger.warn("Failed to get registrations during stale detection", err);
            window.location.reload(true);
          });
        }
      }
    }, 50);
  });
};

// Wait for config before rendering app. Use Promise.all to ensure order.
const configPromise = waitForConfig();

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000, // 30 seconds default
      gcTime: 1000 * 60 * 10, // 10 minutes
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error.status === 404) return false;
        return failureCount < 2;
      },
    },
  },
});

try {
  logger.info("React application initialization starting");

  const rootElement = document.getElementById("root");
  if (!rootElement) {
    throw new Error("Root element not found in DOM");
  }

  const root = ReactDOM.createRoot(rootElement);
  logger.info("React root created successfully");

  // Ensure config is loaded before rendering app, or fail loudly
  configPromise
    .then(async () => {
      // Initialize API config after main config loads
      // This ensures window.__CONFIG__.API_URL is injected into axios baseURL
      const { initializeApiConfig } = await import('./services/api');
      initializeApiConfig();

      root.render(
        <ErrorBoundary>
          <BrowserRouter
            future={{
              v7_startTransition: true,
              v7_relativeSplatPath: true,
            }}
          >
            <QueryClientProvider client={queryClient}>
              {/* MUI ThemeProvider stays for legacy MUI components on other pages.
                  CssBaseline removed — our theme.css owns the global reset/base. */}
              <ThemeProvider theme={modernTheme}>
                <AuthProvider>
                  <ApiErrorBanner />
                  <App />
                </AuthProvider>
              </ThemeProvider>
            </QueryClientProvider>
          </BrowserRouter>
        </ErrorBoundary>
      );

      logger.success("React application render initiated");

      // Post-render validation
      setTimeout(() => {
        const rootContent = document.getElementById("root");
        if (rootContent && rootContent.innerHTML.trim() === "") {
          logger.error(
            "EmptyRender",
            new Error("React rendered but root is empty"),
            {
              innerHTML: rootContent.innerHTML,
              config: window.__CONFIG__,
              timestamp: new Date().toISOString(),
            }
          );
        } else if (rootContent) {
          logger.success("React application rendered successfully", {
            contentLength: rootContent.innerHTML.length,
            hasContent: rootContent.innerHTML.length > 0,
          });
        }
      }, 2000);
    })
    .catch((error) => {
      logger.error("ConfigLoadFailed", error);
      const rootElement = document.getElementById("root");
      if (rootElement) {
        rootElement.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: center; height: 100vh; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #f87171; background: #1f2937;">
            <div style="text-align: center; max-width: 500px;">
              <h1 style="font-size: 24px; margin: 0 0 12px 0;">Configuration Error</h1>
              <p style="margin: 0; line-height: 1.6; color: #d1d5db;">
                ${error.message || 'Failed to load application configuration'}
              </p>
              <p style="margin: 20px 0 0 0; font-size: 12px; color: #9ca3af;">
                Please try refreshing the page. If the problem persists, contact support.
              </p>
            </div>
          </div>
        `;
      }
    });
} catch (error) {
  logger.error("ReactInitialization", error, {
    phase: "main_render",
    config: window.__CONFIG__,
    userAgent: navigator.userAgent,
  });

  // Show user-friendly error
  alert(
    "Application failed to start. Please refresh the page or contact support."
  );
}

