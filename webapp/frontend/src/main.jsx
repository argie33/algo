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
import { modernTheme } from "./theme/modernTheme";

// Initialize comprehensive error logging service
const logger = createComponentLogger("Main");

// RESTORED: Professional error logging service integration
const _originalConsoleError = console.error;
const _originalConsoleWarn = console.warn;

// Filter out non-critical warnings and errors
console.warn = function (...args) {
  const msg = String(args[0] || '');
  // Suppress recharts dimension warnings (non-critical, charts render fine)
  if (msg.includes('width(-1)') || msg.includes('height(-1)')) {
    return;
  }
  _originalConsoleWarn.apply(console, args);
};

// Suppress expected CORS/network errors that occur during initial data load
// These are transient and resolve after auth initialization/retries
console.error = function (...args) {
  const msg = String(args[0] || '');
  // Suppress CORS errors in development - they're expected during initial data fetch
  // The requests retry and eventually succeed with proper auth
  if (import.meta.env.DEV && (
    msg.includes('Access to XMLHttpRequest') ||
    msg.includes('Failed to load resource: net::ERR_FAILED') ||
    msg.includes('net::ERR_FAILED')
  )) {
    return;
  }
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
  };

  logger.error("UnhandledPromiseRejection", e.reason, errorContext);

  // Let all errors through for debugging
  return false;
});


// Application initialization

// Smart service worker and cache management
// Only clear stale caches on deploy version change, not on every load
const checkAndClearStaleCache = async () => {
  const CACHE_VERSION_KEY = 'app-cache-version';
  const CURRENT_VERSION = import.meta.env.VITE_BUILD_TIME || new Date().toISOString().split('T')[0];

  try {
    // Check if we have a cached version stored
    const storedVersion = localStorage.getItem(CACHE_VERSION_KEY);

    if (storedVersion && storedVersion !== CURRENT_VERSION) {
      logger.info(`Cache version changed (${storedVersion} → ${CURRENT_VERSION}), clearing stale caches`);

      // Only clear old caches on version change, not every load
      if ("caches" in window) {
        try {
          const cacheNames = await caches.keys();
          // Delete API response caches that may have stale endpoints
          const cacheNamesToDelete = cacheNames.filter(name =>
            name.startsWith('api-') || name.includes('http') || name === 'v1'
          );

          await Promise.all(cacheNamesToDelete.map(name => caches.delete(name)));
          logger.info(`Cleared ${cacheNamesToDelete.length} stale cache stores`);
        } catch (error) {
          logger.warn("Failed to clear caches on version change", error);
        }
      }
    }

    // Update stored version
    localStorage.setItem(CACHE_VERSION_KEY, CURRENT_VERSION);

    // Unregister old service workers on deploy (one-time on version change)
    if (storedVersion && storedVersion !== CURRENT_VERSION && "serviceWorker" in navigator) {
      try {
        const registrations = await navigator.serviceWorker.getRegistrations();
        for (let registration of registrations) {
          // Unregister old service worker versions
          await registration.unregister();
        }
        logger.info(`Unregistered ${registrations.length} old service worker(s)`);
      } catch (error) {
        logger.warn("Failed to unregister service workers", error);
      }
    }
  } catch (error) {
    logger.warn("Cache version check failed (non-critical)", error);
  }
};

// Run cache check asynchronously (non-blocking)
checkAndClearStaleCache().catch(() => {});


// Wait for config.js to load before configuring Amplify
// Ensures window.__CONFIG__ is available when AuthContext initializes
const waitForConfig = async () => {
  let attempts = 0;
  const maxAttempts = 200; // 200 * 50ms = 10 seconds max wait (increased from 5s)

  while (!window.__CONFIG__ && attempts < maxAttempts) {
    await new Promise(resolve => setTimeout(resolve, 50));
    attempts++;
  }

  if (!window.__CONFIG__) {
    logger.error(`Config not loaded after ${(attempts * 50) / 1000}s. Check index.html script load order.`);
    // Still proceed to prevent app hang
  }

  // Configure Amplify after config is available (or timeout)
  configureAmplify();
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

  // Ensure config is loaded before rendering app
  configPromise.then(() => {
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

