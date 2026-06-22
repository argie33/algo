import React, { useState, useEffect } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";

const LOAD_TIMEOUT_MS = 15000; // 15 seconds before showing timeout message

export function LoadingFallback() {
  const [showTimeout, setShowTimeout] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setShowTimeout(true);
    }, LOAD_TIMEOUT_MS);

    return () => clearTimeout(timer);
  }, []);

  if (showTimeout) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "var(--bg)",
          color: "var(--text)",
          padding: "20px",
        }}
      >
        <div
          style={{
            textAlign: "center",
            maxWidth: "400px",
          }}
        >
          <div
            style={{
              marginBottom: "16px",
              color: "var(--danger)",
            }}
          >
            <AlertTriangle size={48} strokeWidth={2} />
          </div>
          <h2
            style={{
              fontSize: "18px",
              fontWeight: 600,
              margin: "0 0 8px 0",
              color: "var(--text)",
            }}
          >
            Page Loading Timeout
          </h2>
          <p
            style={{
              margin: "0 0 16px 0",
              color: "var(--text-muted)",
              fontSize: "14px",
              lineHeight: 1.5,
            }}
          >
            The page took too long to load. This usually means the API server is
            down or unreachable.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "10px 16px",
              background: "var(--brand)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--r-sm)",
              fontWeight: 500,
              cursor: "pointer",
              fontSize: "14px",
              transition: "background 0.2s",
            }}
            onMouseEnter={(e) => (e.target.style.background = "var(--brand-2)")}
            onMouseLeave={(e) => (e.target.style.background = "var(--brand)")}
          >
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        fontFamily: "system-ui, -apple-system, sans-serif",
        background: "var(--bg)",
        color: "var(--text)",
      }}
    >
      <div
        style={{
          textAlign: "center",
        }}
      >
        <div
          style={{
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              animation: "spin 1s linear infinite",
              display: "flex",
            }}
          >
            <RefreshCw size={32} strokeWidth={2} />
          </div>
        </div>
        <p
          style={{
            margin: 0,
            fontSize: "14px",
            color: "var(--text-muted)",
          }}
        >
          Loading...
        </p>
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    </div>
  );
}
