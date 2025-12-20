import ReactDOM from "react-dom/client";
// Fresh deployment to clear CloudFront cache and ensure correct config (2025-08-21)
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { configureAmplify } from "./config/amplify";
import { createComponentLogger } from "./utils/errorLogger";
import ErrorBoundary from "./components/ErrorBoundary";

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

// Create theme
const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#1976d2",
      light: "#42a5f5",
      dark: "#1565c0",
    },
    secondary: {
      main: "#dc004e",
      light: "#ff5983",
      dark: "#9a0036",
    },
    background: {
      default: "#f5f5f5",
      paper: "#ffffff",
    },
    success: {
      main: "#2e7d32",
      light: "#4caf50",
      dark: "#1b5e20",
    },
    error: {
      main: "#d32f2f",
      light: "#ef5350",
      dark: "#c62828",
    },
    warning: {
      main: "#b7700d",
      light: "#d4951a",
      dark: "#8a5409",
    },
    info: {
      main: "#0277bd",
      light: "#29b6f6",
      dark: "#01579b",
    },
  },
  typography: {
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',
    h1: {
      fontWeight: 600,
    },
    h2: {
      fontWeight: 600,
    },
    h3: {
      fontWeight: 600,
    },
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 500,
          minWidth: "44px",
          minHeight: "44px",
          "&:focus": {
            outline: "3px solid #1976d2",
            outlineOffset: "2px",
            boxShadow: "0 0 0 3px rgba(25, 118, 210, 0.3)",
          },
          "&:focus-visible": {
            outline: "3px solid #1976d2",
            outlineOffset: "2px",
            boxShadow: "0 0 0 3px rgba(25, 118, 210, 0.3)",
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          minWidth: "44px",
          minHeight: "44px",
          "&:focus": {
            outline: "3px solid #1976d2",
            outlineOffset: "2px",
            boxShadow: "0 0 0 3px rgba(25, 118, 210, 0.3)",
          },
          "&:focus-visible": {
            outline: "3px solid #1976d2",
            outlineOffset: "2px",
            boxShadow: "0 0 0 3px rgba(25, 118, 210, 0.3)",
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            "&.Mui-focused": {
              "& .MuiOutlinedInput-notchedOutline": {
                borderColor: "#1976d2",
                borderWidth: "2px",
              },
            },
            "&:focus-within": {
              outline: "3px solid rgba(25, 118, 210, 0.3)",
              outlineOffset: "2px",
            },
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
          borderRadius: 12,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          minHeight: "32px",
          "& .MuiChip-label": {
            paddingLeft: "12px",
            paddingRight: "12px",
          },
        },
      },
    },
  },
});

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
          <ThemeProvider theme={theme}>
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
