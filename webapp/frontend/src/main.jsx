import ReactDOM from "react-dom/client";
// Fresh deployment to clear CloudFront cache and ensure correct config (2025-08-21)
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { configureAmplify } from "./config/amplify";

console.log("🚀 main.jsx loaded - starting React app");

// Aggressively clear all Service Workers and caches to fix old API URL caching
if ("serviceWorker" in navigator) {
  // Unregister all service workers
  navigator.serviceWorker
    .getRegistrations()
    .then(function (registrations) {
      console.log(
        `🧹 Found ${registrations.length} Service Worker registrations`
      );
      for (let registration of registrations) {
        registration.unregister().then(function (boolean) {
          console.log("🧹 Service Worker unregistered:", boolean);
        });
      }
    })
    .catch(function (error) {
      console.log("Service Worker unregistration failed:", error);
    });
}

// Clear all caches to ensure fresh configuration loading
if ("caches" in window) {
  caches
    .keys()
    .then(function (cacheNames) {
      console.log(`🗑️ Found ${cacheNames.length} cache stores`);
      return Promise.all(
        cacheNames.map(function (cacheName) {
          console.log("🗑️ Deleting cache:", cacheName);
          return caches.delete(cacheName);
        })
      );
    })
    .then(function () {
      console.log("✅ All caches cleared");
    })
    .catch(function (error) {
      console.log("Cache clearing failed:", error);
    });
}

// Force reload config.js with cache busting to get latest API URL configuration
const forceReloadConfig = () => {
  try {
    // Remove existing config script if it exists
    const existingScript = document.querySelector('script[src*="config.js"]');
    if (existingScript) {
      existingScript.remove();
      console.log("🗑️ Removed existing config script");
    }

    // Add new config script with cache busting
    const script = document.createElement("script");
    script.src = `/config.js?t=${Date.now()}`;
    script.onload = () => {
      console.log("✅ Config reloaded with latest values:", window.__CONFIG__);
    };
    script.onerror = () => {
      console.error("❌ Failed to reload config.js");
    };
    document.head.appendChild(script);
  } catch (error) {
    console.error("❌ Error forcing config reload:", error);
  }
};

forceReloadConfig();

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
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <App />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
  console.log("✅ React app rendered successfully");
} catch (error) {
  console.error("❌ Error rendering React app:", error);
  alert("Error rendering React app: " + error.message);
}
