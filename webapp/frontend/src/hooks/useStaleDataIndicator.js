/**
 * Hook to show stale data indicator when data comes from cache
 * Usage: const { StaleDataBanner } = useStaleDataIndicator(data);
 */
import React from "react";
import { AlertCircle } from "lucide-react";

export const useStaleDataIndicator = (data) => {
  const isStale = data?._fromCache === true;

  const StaleDataBanner = () => {
    if (!isStale) return null;

    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "8px 12px",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          color: "var(--amber)",
          fontSize: "12px",
          marginBottom: "8px",
        }}
      >
        <AlertCircle size={14} />
        <span>Showing cached data — live updates temporarily unavailable</span>
      </div>
    );
  };

  return {
    isStale,
    StaleDataBanner,
  };
};

export default useStaleDataIndicator;
