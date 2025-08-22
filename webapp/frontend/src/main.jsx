import React from "react";
import ReactDOM from "react-dom/client";
// Fresh deployment to clear CloudFront cache and ensure correct config (2025-08-21)
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { configureAmplify } from "./config/amplify";

console.log("🚀 main.jsx loaded - starting React app");

// Unregister any existing Service Workers to clear old cached API URLs
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(function(registrations) {
    for(let registration of registrations) {
      registration.unregister().then(function(boolean) {
        console.log('🧹 Service Worker unregistered:', boolean);
      });
    }
  }).catch(function(error) {
    console.log('Service Worker unregistration failed:', error);
  });
}

// Force reload config.js with cache busting to get latest API URL configuration
const forceReloadConfig = () => {
  try {
    // Remove existing config script if it exists
    const existingScript = document.querySelector('script[src*="config.js"]');
    if (existingScript) {
      existingScript.remove();
      console.log('🗑️ Removed existing config script');
    }
    
    // Add new config script with cache busting
    const script = document.createElement('script');
    script.src = `/config.js?t=${Date.now()}`;
    script.onload = () => {
      console.log('✅ Config reloaded with latest values:', window.__CONFIG__);
    };
    script.onerror = () => {
      console.error('❌ Failed to reload config.js');
    };
    document.head.appendChild(script);
  } catch (error) {
    console.error('❌ Error forcing config reload:', error);
  }
};

forceReloadConfig();

// Configure Amplify
configureAmplify();

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 5 * 60 * 1000, // 5 minutes
      cacheTime: 10 * 60 * 1000, // 10 minutes
    },
  },
});

console.log("✅ QueryClient created");

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

console.log("✅ Theme created");
console.log("🔍 Looking for root element...");

const rootElement = document.getElementById("root");
if (!rootElement) {
  console.error("❌ Root element not found!");
  alert("Root element not found!");
} else {
  console.log("✅ Root element found:", rootElement);
}

console.log("🚀 Creating React root and rendering app...");

try {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <BrowserRouter>
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
  console.log("✅ React app rendered successfully");
} catch (error) {
  console.error("❌ Error rendering React app:", error);
  alert("Error rendering React app: " + error.message);
}
