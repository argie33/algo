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
    mode: "dark",
    primary: {
      main: "#3b82f6",
      light: "#60a5fa",
      dark: "#1e40af",
      contrastText: "#ffffff",
    },
    secondary: {
      main: "#8b5cf6",
      light: "#a78bfa",
      dark: "#6d28d9",
      contrastText: "#ffffff",
    },
    background: {
      default: "#0f172a",
      paper: "#1e293b",
    },
    divider: "rgba(148, 163, 184, 0.12)",
    success: {
      main: "#10b981",
      light: "#34d399",
      dark: "#059669",
    },
    error: {
      main: "#ef4444",
      light: "#f87171",
      dark: "#dc2626",
    },
    warning: {
      main: "#f59e0b",
      light: "#fbbf24",
      dark: "#d97706",
    },
    info: {
      main: "#06b6d4",
      light: "#22d3ee",
      dark: "#0891b2",
    },
    text: {
      primary: "#f1f5f9",
      secondary: "#cbd5e1",
    },
    action: {
      hover: "rgba(59, 130, 246, 0.08)",
      selected: "rgba(59, 130, 246, 0.12)",
      disabled: "rgba(148, 163, 184, 0.38)",
    },
  },
  typography: {
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',
    h1: {
      fontWeight: 700,
      fontSize: "2.25rem",
      letterSpacing: "-0.02em",
    },
    h2: {
      fontWeight: 700,
      fontSize: "1.875rem",
      letterSpacing: "-0.01em",
    },
    h3: {
      fontWeight: 600,
      fontSize: "1.5rem",
    },
    h4: {
      fontWeight: 600,
      fontSize: "1.25rem",
    },
    h5: {
      fontWeight: 600,
      fontSize: "1.125rem",
    },
    h6: {
      fontWeight: 600,
      fontSize: "1rem",
    },
    body1: {
      fontSize: "0.95rem",
      lineHeight: 1.6,
    },
    body2: {
      fontSize: "0.875rem",
      lineHeight: 1.5,
    },
  },
  shape: {
    borderRadius: 10,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 600,
          minWidth: "44px",
          minHeight: "44px",
          borderRadius: 8,
          transition: "all 0.2s ease-in-out",
          "&:hover": {
            transform: "translateY(-1px)",
            boxShadow: "0 8px 16px rgba(0,0,0,0.3)",
          },
          "&:focus": {
            outline: "2px solid #3b82f6",
            outlineOffset: "2px",
          },
          "&:focus-visible": {
            outline: "2px solid #3b82f6",
            outlineOffset: "2px",
          },
        },
        contained: {
          backgroundColor: "#3b82f6",
          color: "#ffffff",
          "&:hover": {
            backgroundColor: "#2563eb",
          },
        },
        outlined: {
          borderColor: "rgba(148, 163, 184, 0.3)",
          color: "#3b82f6",
          "&:hover": {
            backgroundColor: "rgba(59, 130, 246, 0.08)",
            borderColor: "#3b82f6",
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          minWidth: "44px",
          minHeight: "44px",
          borderRadius: 8,
          transition: "all 0.2s ease-in-out",
          color: "#cbd5e1",
          "&:hover": {
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            color: "#3b82f6",
          },
          "&:focus": {
            outline: "2px solid #3b82f6",
            outlineOffset: "2px",
          },
          "&:focus-visible": {
            outline: "2px solid #3b82f6",
            outlineOffset: "2px",
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            backgroundColor: "rgba(30, 41, 59, 0.8)",
            borderColor: "rgba(148, 163, 184, 0.2)",
            color: "#f1f5f9",
            transition: "all 0.2s ease-in-out",
            "&:hover": {
              borderColor: "rgba(148, 163, 184, 0.4)",
              backgroundColor: "rgba(30, 41, 59, 1)",
            },
            "&.Mui-focused": {
              backgroundColor: "rgba(30, 41, 59, 1)",
              "& .MuiOutlinedInput-notchedOutline": {
                borderColor: "#3b82f6",
                borderWidth: "2px",
              },
            },
            "&:focus-within": {
              borderColor: "#3b82f6",
            },
          },
          "& .MuiInputBase-input::placeholder": {
            color: "rgba(148, 163, 184, 0.5)",
            opacity: 1,
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: "#1e293b",
          backgroundImage:
            "linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(139, 92, 246, 0.05) 100%)",
          boxShadow:
            "0 4px 20px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
          borderRadius: 10,
          border: "1px solid rgba(148, 163, 184, 0.12)",
          transition: "all 0.3s ease-in-out",
          "&:hover": {
            boxShadow:
              "0 12px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
            borderColor: "rgba(148, 163, 184, 0.2)",
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundColor: "#1e293b",
          backgroundImage:
            "linear-gradient(135deg, rgba(59, 130, 246, 0.03) 0%, rgba(139, 92, 246, 0.03) 100%)",
          borderRadius: 10,
          border: "1px solid rgba(148, 163, 184, 0.12)",
        },
        elevation1: {
          boxShadow:
            "0 2px 8px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
        },
        elevation4: {
          boxShadow:
            "0 4px 20px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          minHeight: "32px",
          backgroundColor: "rgba(59, 130, 246, 0.15)",
          color: "#3b82f6",
          border: "1px solid rgba(59, 130, 246, 0.3)",
          "& .MuiChip-label": {
            paddingLeft: "12px",
            paddingRight: "12px",
            fontWeight: 500,
          },
          "&:hover": {
            backgroundColor: "rgba(59, 130, 246, 0.25)",
          },
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "#0f172a",
          backgroundImage:
            "linear-gradient(180deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 1) 100%)",
          boxShadow:
            "0 4px 12px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
          borderBottom: "1px solid rgba(148, 163, 184, 0.1)",
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        root: {
          "& .MuiDrawer-paper": {
            backgroundColor: "#0f172a",
            backgroundImage:
              "linear-gradient(180deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 1) 100%)",
            borderRight: "1px solid rgba(148, 163, 184, 0.1)",
          },
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          margin: "0 8px 4px 8px",
          color: "#cbd5e1",
          transition: "all 0.2s ease-in-out",
          "&:hover": {
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            color: "#3b82f6",
          },
          "&.Mui-selected": {
            backgroundColor: "rgba(59, 130, 246, 0.2)",
            color: "#3b82f6",
            fontWeight: 600,
            "&:hover": {
              backgroundColor: "rgba(59, 130, 246, 0.3)",
            },
          },
        },
      },
    },
    MuiTable: {
      styleOverrides: {
        root: {
          backgroundColor: "transparent",
          "& .MuiTableCell-head": {
            backgroundColor: "rgba(30, 41, 59, 0.6)",
            borderColor: "rgba(148, 163, 184, 0.12)",
            color: "#f1f5f9",
            fontWeight: 700,
            fontSize: "0.875rem",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          },
          "& .MuiTableCell-body": {
            borderColor: "rgba(148, 163, 184, 0.08)",
            color: "#cbd5e1",
          },
          "& tbody tr:hover": {
            backgroundColor: "rgba(59, 130, 246, 0.05)",
          },
        },
      },
    },
    MuiInputBase: {
      styleOverrides: {
        root: {
          color: "#f1f5f9",
        },
      },
    },
  },
});

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      cacheTime: 10 * 60 * 1000, // 10 minutes
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error.status === 404) return false;
        return failureCount < 3;
      },
    },
  },
});

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
