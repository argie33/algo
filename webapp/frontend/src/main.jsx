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
import cloudWatchLogger from "./utils/cloudWatchLogger";

// Initialize comprehensive error logging service
const logger = createComponentLogger("Main");

// Initialize CloudWatch error logging for production visibility
try {
  // This sends all unhandled errors to CloudWatch for monitoring
  logger.info("CloudWatch logger initialized");
} catch (e) {
  console.warn("CloudWatch logger initialization failed:", e);
}

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

    // Also log to CloudWatch for production monitoring
    cloudWatchLogger.logError("WindowError", "uncaught_exception", e.error || new Error(e.message), errorContext);

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
    cloudWatchLogger.logError("PromiseRejection", "unhandled_rejection", e.reason, errorContext);
    console.error("[UnhandledRejection]", {
      message: e.reason.message,
      stack: e.reason.stack,
      context: errorContext
    });
  } else {
    const error = new Error(String(e.reason));
    logger.error("UnhandledPromiseRejection", error, errorContext);
    cloudWatchLogger.logError("PromiseRejection", "unhandled_rejection", error, errorContext);
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

// Fetch config.js explicitly to bypass service worker cache
// This ensures config.js is always fresh from the network, preventing stale API_URL issues
const fetchConfigExplicitly = async () => {
  const CONFIG_HASH_KEY = 'app-config-hash';

  try {
    // Build cache-bust parameter (same as in index.html script tag)
    // This forces a fresh fetch even if browser has cached the response
    const configUrl = `/config.js?v=${Date.now().toString(36)}&bypass=${Math.random()}`;

    // Fetch with explicit no-cache directive to bypass all caches (service worker, browser, CDN)
    const response = await fetch(configUrl, {
      cache: 'no-store',  // Bypass all caches - force network fetch
      headers: {
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache, no-store, must-revalidate'
      }
    });

    if (!response.ok) {
      // Log fetch error but don't throw - fall back to script-tag loaded config
      logger.warn(`Explicit config.js fetch returned ${response.status}`, {
        status: response.status,
        statusText: response.statusText,
        url: configUrl
      });
      return; // Fall back to window.__CONFIG__ from script tag
    }

    const configText = await response.text();

    // Evaluate the config (it sets window.__CONFIG__ globally)
    // Use Function() instead of eval() for slightly better scoping
    try {
      new Function(configText)();

      // Verify config was loaded
      if (window.__CONFIG__ && typeof window.__CONFIG__ === 'object' && 'ENVIRONMENT' in window.__CONFIG__) {
        logger.info("Explicit config.js fetch succeeded, using fresh config", {
          apiUrl: window.__CONFIG__.API_URL || '(empty - using Vite proxy)',
          buildTime: window.__CONFIG__.BUILD_TIME
        });

        // Store the BUILD_TIME to detect future deploys (simpler than hashing URLs)
        localStorage.setItem(CONFIG_HASH_KEY, window.__CONFIG__.BUILD_TIME || 'unknown');
      } else {
        logger.warn("Fetched config.js but window.__CONFIG__ not properly set after evaluation");
      }
    } catch (evalError) {
      logger.warn("Failed to evaluate fetched config.js", evalError);
    }
  } catch (error) {
    // Network error or timeout - this is ok, we'll use script-tag loaded config
    logger.info("Explicit config.js fetch failed (expected in offline mode)", {
      error: error.message
    });
  }
};

// Fetch config explicitly to bypass service worker cache
// Run before app initialization to ensure fresh config
const configFetchPromise = fetchConfigExplicitly().catch((err) => {
  logger.warn('[Config] Explicit fetch failed (non-critical)', err.message);
});


// Wait for config.js to load before configuring Amplify and rendering app.
// Ensures window.__CONFIG__ is available when AuthContext initializes.
// The explicit fetch above should provide a fresh copy, but we also wait for the script-tag fallback.
const waitForConfig = async () => {
  // If config already loaded (synchronously from script tag), proceed immediately
  // In dev mode, API_URL is intentionally empty (Vite proxy handles /api/*)
  // So check for the object existence, not the URL value
  if (window.__CONFIG__ && typeof window.__CONFIG__ === 'object' && 'ENVIRONMENT' in window.__CONFIG__) {
    logger.info("Config already loaded", {
      apiUrl: window.__CONFIG__.API_URL || '(empty - using Vite proxy)',
      environment: window.__CONFIG__.ENVIRONMENT,
    });
    configureAmplify();
    return;
  }

  // Check if config.js script tag failed to load
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

  // Otherwise, wait for config script tag to execute with validation
  // (The explicit fetch above should have already provided a fresh copy)
  return new Promise((resolve, reject) => {
    const CONFIG_TIMEOUT = 5000; // 5 seconds - config should be available quickly now that we're fetching it explicitly
    let configLoaded = false;

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
          'Configuration failed to load within 5 seconds. ' +
          'Actions: (1) Check browser DevTools Network tab for config.js request status, ' +
          '(2) Verify config.js is deployed to S3, (3) Check S3 bucket permissions, (4) Verify CloudFront distribution is active.'
        );
        logger.error("ConfigLoadTimeout", error, debugInfo);
        reject(error);
      }
    }, CONFIG_TIMEOUT);

    // Poll for config loading (check every 100ms since we're now fetching explicitly)
    const pollInterval = setInterval(() => {
      if (window.__CONFIG__ && typeof window.__CONFIG__ === 'object' && 'ENVIRONMENT' in window.__CONFIG__) {
        configLoaded = true;
        clearTimeout(timeout);
        clearInterval(pollInterval);
        logger.info("Config loaded successfully (from script tag fallback)");
        configureAmplify();
        resolve();
      }
    }, 100);
  });
};

// Wait for both explicit fetch and config loading before rendering app
const configPromise = configFetchPromise.then(() => waitForConfig());

// Add global timeout for initial app load (30 seconds)
const APP_INIT_TIMEOUT = 30000;
const initTimeoutPromise = new Promise((_, reject) =>
  setTimeout(
    () => reject(new Error('Application initialization timeout - API server may be down')),
    APP_INIT_TIMEOUT
  )
);

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

  // Ensure config is loaded before rendering app with timeout, or fail loudly
  Promise.race([configPromise, initTimeoutPromise])
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
        const isTimeout = error.message && error.message.includes('timeout');
        const title = isTimeout ? 'Loading Timeout' : 'Configuration Error';
        const message = isTimeout
          ? 'The application took too long to start. This usually means the API server is down or unreachable.'
          : (error.message || 'Failed to load application configuration');

        rootElement.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: center; height: 100vh; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #f87171; background: #1f2937;">
            <div style="text-align: center; max-width: 500px;">
              <h1 style="font-size: 24px; margin: 0 0 12px 0;">${title}</h1>
              <p style="margin: 0; line-height: 1.6; color: #d1d5db;">
                ${message}
              </p>
              <button onclick="location.reload()" style="margin: 20px 0 0 0; padding: 10px 16px; background: #6366f1; color: white; border: none; border-radius: 4px; font-weight: 500; cursor: pointer; font-size: 14px;">
                Retry
              </button>
              <p style="margin: 20px 0 0 0; font-size: 12px; color: #9ca3af;">
                ${isTimeout ? 'Please try refreshing the page.' : 'If the problem persists, contact support.'}
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

