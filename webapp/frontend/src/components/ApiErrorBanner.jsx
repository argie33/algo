import React, { useState, useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";

/**
 * Global API Error Banner
 * Shows when the API is returning errors or when network issues occur
 * Tracks failed API requests and displays a dismissible warning
 */
export default function ApiErrorBanner() {
  const [showBanner, setShowBanner] = useState(false);
  const [errorCount, setErrorCount] = useState(0);
  const [_lastError, setLastError] = useState(null);

  useEffect(() => {
    const handleConsoleError = (message) => {
      if (
        message.includes("[API]") ||
        message.includes("401") ||
        message.includes("5xx")
      ) {
        setErrorCount((prev) => prev + 1);
        setLastError(message);
        setShowBanner(true);
      }
    };

    // Intercept console errors
    const originalError = console.error;
    console.error = function (...args) {
      const message = String(args[0] || "");
      handleConsoleError(message);
      originalError.apply(console, args);
    };

    return () => {
      console.error = originalError;
    };
  }, []);

  // Auto-hide banner after 30 seconds if no new errors
  useEffect(() => {
    if (showBanner && errorCount > 0) {
      const timer = setTimeout(() => {
        if (errorCount < 3) {
          setShowBanner(false);
        }
      }, 30000);
      return () => clearTimeout(timer);
    }
  }, [showBanner, errorCount]);

  if (!showBanner) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red-900 border-b-2 border-red-700 px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3 flex-1">
        <AlertTriangle size={20} className="text-red-200 flex-shrink-0" />
        <div>
          <div className="font-semibold text-red-100">API Connection Issue</div>
          <div className="text-sm text-red-200 mt-1">
            {errorCount === 1
              ? "The API is having trouble responding. Some data may be unavailable."
              : errorCount < 5
                ? `Multiple API errors detected (${errorCount}). Trying to recover...`
                : `Persistent API issues (${errorCount}+ errors). Please check your connection or refresh the page.`}
          </div>
        </div>
      </div>
      <button
        onClick={() => setShowBanner(false)}
        className="flex-shrink-0 text-red-200 hover:text-red-100 ml-4"
        aria-label="Dismiss"
      >
        <X size={20} />
      </button>
    </div>
  );
}
