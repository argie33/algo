/**
 * Hook to safely handle data freshness metadata from API responses.
 * Provides warnings for stale data and allows users to manually refresh.
 */
import { useState, useEffect } from "react";

export const useDataFreshness = (response, options = {}) => {
  const { staleDays = 2, onStale = null } = options;

  const [freshness, setFreshness] = useState(null);
  const [isStale, setIsStale] = useState(false);

  useEffect(() => {
    if (!response) {
      setFreshness(null);
      setIsStale(false);
      return;
    }

    // Extract freshness data from response
    const freshData =
      response.data_freshness || response?.items?.data_freshness;

    if (!freshData) {
      setFreshness(null);
      setIsStale(false);
      return;
    }

    const { data_age_days, is_stale, max_date, warning } = freshData;

    setFreshness({
      age_days: data_age_days,
      max_date,
      warning,
      is_explicitly_stale: is_stale,
    });

    // Check if data exceeds staleDays threshold
    const stale = data_age_days !== null && data_age_days > staleDays;
    setIsStale(stale);

    // Call optional callback when data becomes stale
    if (stale && onStale) {
      onStale({
        age_days: data_age_days,
        threshold: staleDays,
        max_date,
      });
    }
  }, [response, staleDays, onStale]);

  return {
    freshness,
    isStale,
    shouldWarnUser: isStale || freshness?.is_explicitly_stale,
    freshnessBadgeProps: freshness
      ? {
          age_days: freshness.age_days,
          is_stale: freshness.is_explicitly_stale || isStale,
          max_date: freshness.max_date,
          warning: freshness.warning,
        }
      : null,
  };
};

/**
 * Component to display data freshness warning banner
 */
export const DataFreshnessWarning = ({ freshness, onDismiss = null }) => {
  const [dismissed, setDismissed] = useState(false);

  if (!freshness || dismissed) return null;

  const age = freshness.age_days;
  const isDaysOld = age !== null && age > 0;

  return (
    <div
      className="alert alert-warning"
      style={{
        marginBottom: "var(--space-3)",
        padding: "var(--space-2) var(--space-3)",
        border: "1px solid var(--warning)",
        borderRadius: "var(--r-sm)",
        background: "var(--warning-light)",
      }}
    >
      <div className="flex gap-2" style={{ alignItems: "flex-start" }}>
        <div style={{ fontSize: "var(--t-sm)" }}>
          {freshness.is_explicitly_stale && (
            <>
              ⚠️ <strong>Data is stale</strong>
              {isDaysOld && ` (${age} day${age > 1 ? "s" : ""} old)`}
            </>
          )}
          {!freshness.is_explicitly_stale && isDaysOld && (
            <>
              ℹ️ <strong>Data updated</strong> {age} day{age > 1 ? "s" : ""} ago
            </>
          )}
          {freshness.warning && (
            <div
              style={{
                fontSize: "var(--t-xs)",
                color: "var(--text-muted)",
                marginTop: "var(--space-1)",
              }}
            >
              {freshness.warning}
            </div>
          )}
        </div>
        {onDismiss && (
          <button
            onClick={() => {
              setDismissed(true);
              onDismiss();
            }}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: "var(--text-muted)",
              fontSize: "var(--t-lg)",
              padding: "0",
              lineHeight: "1",
            }}
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
};

export default {
  useDataFreshness,
  DataFreshnessWarning,
};
