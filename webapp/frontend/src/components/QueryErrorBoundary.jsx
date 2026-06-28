import React from "react";
import { AlertTriangle } from "lucide-react";

/**
 * Display for failed API queries within a page section
 * Shows visible error message instead of silent failure
 */
export const QueryError = ({ error, section, onRetry }) => {
  const message = error?.message || "Unknown error";
  const status = error?.status ? ` (${error.status})` : "";

  return (
    <div
      className="card"
      style={{ borderColor: "var(--danger)", borderWidth: "1px" }}
    >
      <div className="card-body">
        <div className="flex gap-3 items-start">
          <AlertTriangle
            size={18}
            style={{ color: "var(--danger)", flexShrink: 0, marginTop: 2 }}
          />
          <div style={{ flex: 1 }}>
            <div
              className="t-sm strong"
              style={{ color: "var(--danger)", marginBottom: 4 }}
            >
              {section || "Data"} failed to load{status}
            </div>
            <div className="t-xs muted" style={{ marginBottom: 8 }}>
              {message.length > 100
                ? message.substring(0, 100) + "..."
                : message}
            </div>
            {onRetry && (
              <button
                className="btn btn-sm btn-outline"
                onClick={onRetry}
                style={{ marginTop: 8 }}
              >
                Retry
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Wrapper component to handle query errors in a page section
 * Shows error UI if query failed, content otherwise
 */
export const QuerySection = ({
  loading,
  error,
  isEmpty,
  children,
  section,
  onRetry,
}) => {
  if (error) {
    return <QueryError error={error} section={section} onRetry={onRetry} />;
  }

  if (loading) {
    return (
      <div className="card">
        <div className="card-body">
          <div className="t-xs muted">
            Loading {section?.toLowerCase() || "data"}…
          </div>
        </div>
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="card">
        <div className="card-body">
          <div className="t-xs muted">
            No {section?.toLowerCase() || "data"} available
          </div>
        </div>
      </div>
    );
  }

  return children;
};

export default { QueryError, QuerySection };
