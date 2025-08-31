import ReactDOM from "react-dom/client";
// Fresh deployment to clear CloudFront cache and ensure correct config (2025-08-21)
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { configureAmplify } from "./config/amplify";

// RESTORED: Enhanced error logging with ZERO suppression - let all errors through
const _originalConsoleError = console.error;
const _originalConsoleWarn = console.warn;

// Enhanced error logging that PRESERVES all errors while adding context
const _safeStringify = (obj, depth = 0, maxDepth = 3) => {
  if (depth > maxDepth) return '[Max Depth Reached]';
  if (obj === null) return 'null';
  if (obj === undefined) return 'undefined';
  
  if (typeof obj === 'object') {
    if (obj instanceof Error) {
      return `Error: ${obj.message} (${obj.name})`;
    }
    
    // Handle circular references and deep objects safely
    try {
      const seen = new WeakSet();
      return JSON.stringify(obj, function(key, val) {
        if (val != null && typeof val === 'object') {
          if (seen.has(val)) return '[Circular]';
          seen.add(val);
        }
        return val;
      }, 2);
    } catch (e) {
      return `[Object: ${obj.constructor?.name || 'Unknown'}]`;
    }
  }
  
  return String(obj);
};

// ENHANCED console.error that PRESERVES all errors while adding debugging context
console.error = function(...args) {
  try {
    // Add timestamp and enhanced context to all error messages
    const timestamp = new Date().toISOString();
    const enhanced = [`[${timestamp}] ENHANCED ERROR LOG:`];
    
    const safeArgs = (args || []).map(arg => {
      if (typeof arg === 'object' && arg !== null) {
        try {
          return _safeStringify(arg);
        } catch (e) {
          return `[Unsafe Object: ${arg.constructor?.name || 'Unknown'}]`;
        }
      }
      return arg;
    });
    
    enhanced.push(...safeArgs);
    
    // ALWAYS call original console.error - ZERO SUPPRESSION
    return _originalConsoleError.apply(console, enhanced);
  } catch (error) {
    // Fallback to original error logging if enhancement fails
    _originalConsoleError.call(console, '[Error Enhancement Failed]', error.message);
    return _originalConsoleError.apply(console, args);
  }
};

// ENHANCED console.warn with context preservation
console.warn = function(...args) {
  try {
    const timestamp = new Date().toISOString();
    const enhanced = [`[${timestamp}] ENHANCED WARN:`];
    
    const safeArgs = (args || []).map(arg => {
      if (typeof arg === 'object' && arg !== null) {
        try {
          return _safeStringify(arg);
        } catch (e) {
          return `[Unsafe Object: ${arg.constructor?.name || 'Unknown'}]`;
        }
      }
      return arg;
    });
    
    enhanced.push(...safeArgs);
    
    // ALWAYS call original console.warn - ZERO SUPPRESSION
    return _originalConsoleWarn.apply(console, enhanced);
  } catch (error) {
    _originalConsoleWarn.call(console, '[Warn Enhancement Failed]', error.message);
    return _originalConsoleWarn.apply(console, args);
  }
};

// ENHANCED window error handling - capture ALL errors with context
window.addEventListener('error', function(e) {
  const timestamp = new Date().toISOString();
  const errorDetails = {
    message: e.message,
    filename: e.filename,
    lineno: e.lineno,
    colno: e.colno,
    error: e.error ? {
      name: e.error.name,
      message: e.error.message,
      stack: e.error.stack
    } : null,
    timestamp: timestamp,
    userAgent: navigator.userAgent,
    url: window.location.href
  };
  
  console.error('[ENHANCED WINDOW ERROR]', errorDetails);
  
  // DO NOT prevent default - let all errors through
  return false;
}, true);

// ENHANCED unhandled promise rejection handling
window.addEventListener('unhandledrejection', function(e) {
  const timestamp = new Date().toISOString();
  const rejectionDetails = {
    reason: e.reason,
    promise: e.promise,
    timestamp: timestamp,
    url: window.location.href
  };
  
  console.error('[ENHANCED UNHANDLED REJECTION]', rejectionDetails);
  
  // DO NOT prevent default - let all errors through
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
      console.warn("⚠️ Config not loaded yet, check index.html script tag");
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
          '&:focus': {
            outline: "3px solid #1976d2",
            outlineOffset: "2px",
            boxShadow: "0 0 0 3px rgba(25, 118, 210, 0.3)",
          },
          '&:focus-visible': {
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
          '&:focus': {
            outline: "3px solid #1976d2",
            outlineOffset: "2px",
            boxShadow: "0 0 0 3px rgba(25, 118, 210, 0.3)",
          },
          '&:focus-visible': {
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
          '& .MuiOutlinedInput-root': {
            '&.Mui-focused': {
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: '#1976d2',
                borderWidth: '2px',
              },
            },
            '&:focus-within': {
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
  ReactDOM.createRoot(document.getElementById("root")).render(
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
  );
  // React app rendered successfully
} catch (error) {
  console.error("❌ Error rendering React app:", error);
  alert("Error rendering React app: " + error.message);
}
