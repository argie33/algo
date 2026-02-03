import ReactDOM from "react-dom/client";
// Fresh deployment to clear CloudFront cache and ensure correct config (2025-08-21)
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
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

// RESTORED: Professional error service integration for window errors
window.addEventListener(
  "error",
  function (e) {
    const errorContext = {
      filename: e.filename,
      lineno: e.lineno,
      colno: e.colno,
      userAgent: navigator.userAgent,
      url: window.location.href,
      timestamp: new Date().toISOString(),
    };

    // Log detailed error for .type access issues
    if (e.message && e.message.includes("Cannot read properties of undefined (reading 'type')")) {
      console.error("🔴 CRITICAL: .type access on undefined detected!");
      console.error("Stack:", e.error?.stack);
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

// Aggressively clear all Service Workers and caches to fix old API URL caching
if ("serviceWorker" in navigator) {
  // Unregister all service workers
  navigator.serviceWorker
    .getRegistrations()
    .then(function (registrations) {
      // Found Service Worker registrations
      for (let registration of registrations) {
        registration.unregister().then(function (_boolean) {
          // Service Worker unregistered
        });
      }
    })
    .catch(function (error) {
      console.error("Service Worker unregistration failed:", error);
    });
}

// Clear all caches to ensure fresh configuration loading
if ("caches" in window) {
  caches
    .keys()
    .then(function (cacheNames) {
      // Found cache stores
      return Promise.all(
        (cacheNames || []).map(function (cacheName) {
          // Deleting cache
          return caches.delete(cacheName);
        })
      );
    })
    .then(function () {
      // All caches cleared
    })
    .catch(function (error) {
      console.error("Cache clearing failed:", error);
    });
}

// Check if config is already loaded by index.html, don't force reload
if (window.__CONFIG__) {
  // Config already loaded by index.html
} else {
  // Waiting for config.js to load from index.html
  // Wait a bit for config to load naturally from index.html
  setTimeout(() => {
    if (window.__CONFIG__) {
      // Config loaded after waiting
    } else {
      if (import.meta.env && import.meta.env.DEV) {
        console.warn("⚠️ Config not loaded yet, check index.html script tag");
      }
    }
  }, 1000);
}

// Configure Amplify
configureAmplify();

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0, // Always fresh - NO caching
      gcTime: 0, // Disable garbage collection cache
      refetchOnWindowFocus: true, // Refetch when window regains focus
      retry: (failureCount, error) => {
        if (error.status === 404) return false;
        return failureCount < 3;
      },
    },
  },
});

// Clear cache immediately - no stale data before render
queryClient.clear();

// Theme and QueryClient created, looking for root element

const rootElement = document.getElementById("root");
if (!rootElement) {
  console.error("❌ Root element not found!");
  alert("Root element not found!");
} else {
  // Root element found
}

// Creating React root and rendering app

try {
  logger.info("React application initialization starting");

  const rootElement = document.getElementById("root");
  if (!rootElement) {
    throw new Error("Root element not found in DOM");
  }

  const root = ReactDOM.createRoot(rootElement);
  logger.info("React root created successfully");

  root.render(
    <ErrorBoundary>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <QueryClientProvider client={queryClient}>
          <ThemeProvider theme={modernTheme}>
            <CssBaseline />
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
