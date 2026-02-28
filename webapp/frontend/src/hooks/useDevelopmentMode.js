// Development mode detection and API availability checking
import { useState, useEffect } from "react";

export function useDevelopmentMode() {
  const [isDevelopment, setIsDevelopment] = useState(false);
  const [apiAvailable, setApiAvailable] = useState(false);

  useEffect(() => {
    // Check if we're in development mode
    const isDevMode =
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1" ||
      window.location.port === "5173";

    setIsDevelopment(isDevMode);

    // In development mode, quickly check if API is available
    if (isDevMode) {
      const checkApiAvailability = async () => {
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 1000); // 1 second timeout

          // Get API URL from configuration or environment
          const apiUrl = (() => {
            if (window.__CONFIG__?.API_URL) return window.__CONFIG__.API_URL;
            if (import.meta.env?.VITE_API_URL) return import.meta.env.VITE_API_URL;
            // Only use localhost as last resort during local development
            return window.location.hostname === 'localhost'
              ? 'http://localhost:3000'
              : window.location.origin.replace(/:\d+$/, ':3000');
          })();
          const response = await fetch(`${apiUrl}/api/health?quick=true`, {
            signal: controller.signal,
            headers: { Accept: "application/json" },
          });

          clearTimeout(timeoutId);
          const available = response.ok;
          // API availability check
          setApiAvailable(available);
        } catch (error) {
          // API not available, suppress the error
          // API unavailable
          setApiAvailable(false);
        }
      };

      checkApiAvailability();
    } else {
      // In production, assume API is available
      setApiAvailable(true);
    }
  }, []);

  const shouldEnableQueries = !isDevelopment || apiAvailable;

  // Development mode debugging available

  return {
    isDevelopment,
    apiAvailable,
    // Helper to determine if queries should be enabled
    shouldEnableQueries,
  };
}

export default useDevelopmentMode;
