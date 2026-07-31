/**
 * LoaderHealthPanel - Comprehensive table and loader health display
 *
 * Mirrors Python dashboard/panels/health.py:_format_comprehensive_table_loader_health()
 * Shows all tables with their loader status, grouped by health category:
 * - CRITICAL: tables that require immediate attention
 * - FAILED: loader errors
 * - STALE: aged but not critical yet
 * - EMPTY: tables with no data
 * - HEALTHY: all systems normal
 */

import React, { useMemo } from "react";
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  Zap,
  AlertCircle,
  Loader,
} from "lucide-react";

// Color palette - matches Python dashboard
const COLORS = {
  GREEN: "var(--success)",
  YELLOW: "var(--amber)",
  RED: "var(--danger)",
  CYAN: "var(--brand)",
  DIM: "var(--text-faint)",
  TEXT: "var(--text)",
};

const STATUS_CONFIG = {
  healthy: { color: COLORS.GREEN, icon: "✓", label: "HEALTHY" },
  stale: { color: COLORS.YELLOW, icon: "~", label: "STALE" },
  critical: { color: COLORS.RED, icon: "!", label: "CRITICAL" },
  empty: { color: COLORS.DIM, icon: "○", label: "EMPTY" },
  error: { color: COLORS.RED, icon: "✗", label: "ERROR" },
  failed: { color: COLORS.RED, icon: "✗", label: "FAILED" },
};

const LOADER_BADGES = {
  running: { icon: "●", color: COLORS.CYAN, text: "RUNNING" },
  loading: { icon: "●", color: COLORS.CYAN, text: "LOADING" },
  completed: { icon: "✓", color: COLORS.GREEN, text: "OK" },
  ok: { icon: "✓", color: COLORS.GREEN, text: "OK" },
  failed: { icon: "✗", color: COLORS.RED, text: "FAILED" },
  error: { icon: "✗", color: COLORS.RED, text: "ERROR" },
  timeout: { icon: "⏱", color: COLORS.YELLOW, text: "TIMEOUT" },
  not_started: { icon: "∘", color: COLORS.DIM, text: "NOT_STARTED" },
  unknown: { icon: "?", color: COLORS.DIM, text: "UNKNOWN" },
};

/**
 * Format age from hours or days
 */
function formatAge(ageHours, ageDays) {
  if (ageHours !== null && ageHours !== undefined) {
    const h = parseFloat(ageHours);
    return h < 24 ? `${Math.round(h)}h` : `${(h / 24).toFixed(1)}d`;
  }
  if (ageDays !== null && ageDays !== undefined) {
    return `${parseFloat(ageDays).toFixed(1)}d`;
  }
  return "—";
}

/**
 * Format row count with commas
 */
function formatRowCount(count) {
  if (count === null || count === undefined) return "—";
  try {
    return parseInt(count).toLocaleString();
  } catch {
    return "—";
  }
}

/**
 * Single table row with loader status and details
 */
function TableRow({ tableName, health, loader, statusColor }) {
  const loaderStatus = loader?.status?.toLowerCase?.() || "";
  const loaderBadge = LOADER_BADGES[loaderStatus] || LOADER_BADGES.unknown;

  const ageHours = health?.age_hours;
  const ageDays = health?.age;
  const rowCount = health?.row_count || loader?.row_count;
  const errorMsg = loader?.error_message;
  const consecutiveFails = loader?.consecutive_failures;

  const completion = loader?.completion_pct;
  const completionText =
    completion !== null && completion !== undefined ? `${Math.round(completion)}%` : "";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-2)",
        fontSize: "var(--t-sm)",
        borderBottom: "1px solid var(--border-soft)",
      }}
    >
      {/* Loader Status Badge */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 24,
          height: 24,
          color: loaderBadge.color,
          fontWeight: "bold",
          title: loaderBadge.text,
        }}
      >
        {loaderBadge.icon}
      </div>

      {/* Table Name */}
      <div
        style={{
          flex: "0 0 160px",
          color: statusColor,
          fontWeight: "500",
          fontFamily: "var(--font-mono)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={tableName}
      >
        {tableName}
      </div>

      {/* Age */}
      <div
        style={{
          flex: "0 0 50px",
          color: statusColor === COLORS.GREEN ? COLORS.DIM : statusColor,
          fontSize: "var(--t-xs)",
          fontFamily: "var(--font-mono)",
        }}
      >
        {formatAge(ageHours, ageDays)}
      </div>

      {/* Row Count */}
      <div
        style={{
          flex: "0 0 80px",
          color: COLORS.DIM,
          fontSize: "var(--t-xs)",
          fontFamily: "var(--font-mono)",
          textAlign: "right",
        }}
      >
        {rowCount ? `n=${formatRowCount(rowCount)}` : "—"}
      </div>

      {/* Loader Completion/Status */}
      {completionText && (
        <div
          style={{
            flex: "0 0 50px",
            color: COLORS.CYAN,
            fontSize: "var(--t-xs)",
            fontFamily: "var(--font-mono)",
            fontWeight: "500",
          }}
        >
          {completionText}
        </div>
      )}

      {/* Error Details */}
      {errorMsg && (
        <div
          style={{
            flex: "1",
            color: COLORS.DIM,
            fontSize: "var(--t-xs)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={errorMsg}
        >
          {errorMsg.substring(0, 40)}
          {errorMsg.length > 40 ? "..." : ""}
        </div>
      )}

      {/* Consecutive Failures */}
      {consecutiveFails && consecutiveFails > 1 && (
        <div
          style={{
            flex: "0 0 100px",
            color: COLORS.YELLOW,
            fontSize: "var(--t-xs)",
            fontWeight: "500",
          }}
        >
          ({consecutiveFails} failures)
        </div>
      )}
    </div>
  );
}

/**
 * Category section with tables
 */
function CategorySection({ category, tables, statusColor, maxDisplay = 5 }) {
  const displayTables = tables.slice(0, maxDisplay);
  const hasMore = tables.length > maxDisplay;

  return (
    <div style={{ marginBottom: "var(--space-3)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          padding: "var(--space-2) 0",
          borderTop: "1px solid var(--border-soft)",
          color: statusColor,
          fontWeight: "600",
          fontSize: "var(--t-sm)",
        }}
      >
        <span>{STATUS_CONFIG[category].icon}</span>
        <span>
          {STATUS_CONFIG[category].label} ({tables.length})
          {hasMore && ` — showing ${maxDisplay}/${tables.length}`}
        </span>
      </div>
      <div
        style={{
          borderLeft: `3px solid ${statusColor}`,
          paddingLeft: "var(--space-2)",
        }}
      >
        {displayTables.map((table, idx) => (
          <TableRow
            key={`${table.tbl}-${idx}`}
            tableName={table.tbl}
            health={table.hlth}
            loader={table.load}
            statusColor={statusColor}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * LoaderHealthPanel component
 */
export function LoaderHealthPanel({ healthData, loading = false, error = null }) {
  const categorized = useMemo(() => {
    const categories = {
      healthy: [],
      critical: [],
      stale: [],
      error: [],
      empty: [],
    };

    if (!Array.isArray(healthData)) {
      return categories;
    }

    const healthDict = {};
    const loaderDict = {};

    // Parse health items (table freshness data)
    healthData.forEach((item) => {
      if (item && typeof item === "object") {
        const tblName = item.tbl;
        if (tblName) {
          healthDict[tblName] = item;
        }
      }
    });

    // Parse loader status (would come from separate API endpoint)
    // For now, we extract it from health items if available
    healthData.forEach((item) => {
      if (item && typeof item === "object" && item.loader_status) {
        const tblName = item.tbl;
        if (tblName) {
          loaderDict[tblName] = item.loader_status;
        }
      }
    });

    // Categorize tables
    Object.keys(healthDict).forEach((tbl) => {
      const hlth = healthDict[tbl];
      const load = loaderDict[tbl] || {};
      const status = hlth.st || "unknown";

      const tableData = { tbl, hlth, load };

      if (status === "ok") {
        categories.healthy.push(tableData);
      } else if (status === "critical") {
        categories.critical.push(tableData);
      } else if (status === "stale") {
        categories.stale.push(tableData);
      } else if (status === "empty") {
        categories.empty.push(tableData);
      } else {
        // Check loader status if health status unclear
        const loaderStatus = load.status?.toLowerCase?.() || "";
        if (loaderStatus === "error" || loaderStatus === "failed") {
          categories.error.push(tableData);
        } else if (
          loaderStatus === "running" ||
          loaderStatus === "loading" ||
          loaderStatus === "not_started"
        ) {
          categories.stale.push(tableData);
        } else {
          categories.healthy.push(tableData);
        }
      }
    });

    return categories;
  }, [healthData]);

  const totalTables = Object.values(categorized).reduce((sum, cat) => sum + cat.length, 0);

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "var(--space-6)",
          color: COLORS.DIM,
        }}
      >
        <Loader size={20} style={{ marginRight: "var(--space-2)", animation: "spin 1s linear infinite" }} />
        Loading loader health data...
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: "var(--space-4)",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          border: `1px solid ${COLORS.RED}`,
          borderRadius: "var(--r-sm)",
          color: COLORS.RED,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <XCircle size={16} />
          <span>Failed to load health data: {error}</span>
        </div>
      </div>
    );
  }

  if (totalTables === 0) {
    return (
      <div
        style={{
          padding: "var(--space-4)",
          color: COLORS.DIM,
          textAlign: "center",
        }}
      >
        No table data available
      </div>
    );
  }

  // Summary badges
  const summaryBadges = [];
  if (categorized.healthy.length > 0) {
    summaryBadges.push(
      `${categorized.healthy.length}${STATUS_CONFIG.healthy.icon}`
    );
  }
  if (categorized.stale.length > 0) {
    summaryBadges.push(`${categorized.stale.length}${STATUS_CONFIG.stale.icon}`);
  }
  if (categorized.critical.length > 0) {
    summaryBadges.push(
      `${categorized.critical.length}${STATUS_CONFIG.critical.icon}`
    );
  }
  if (categorized.empty.length > 0) {
    summaryBadges.push(`${categorized.empty.length}${STATUS_CONFIG.empty.icon}`);
  }
  if (categorized.error.length > 0) {
    summaryBadges.push(`${categorized.error.length}${STATUS_CONFIG.error.icon}`);
  }

  return (
    <div style={{ padding: "var(--space-4)" }}>
      {/* Summary Line */}
      {summaryBadges.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: "var(--space-3)",
            marginBottom: "var(--space-4)",
            fontSize: "var(--t-sm)",
            fontWeight: "500",
          }}
        >
          {summaryBadges.map((badge, idx) => (
            <span key={idx} style={{ fontFamily: "var(--font-mono)" }}>
              {badge}
            </span>
          ))}
        </div>
      )}

      {/* CRITICAL Section - highest priority */}
      {categorized.critical.length > 0 && (
        <CategorySection
          category="critical"
          tables={categorized.critical}
          statusColor={STATUS_CONFIG.critical.color}
          maxDisplay={5}
        />
      )}

      {/* ERROR Loaders Section - real failures */}
      {categorized.error.length > 0 && (
        <CategorySection
          category="error"
          tables={categorized.error}
          statusColor={STATUS_CONFIG.error.color}
          maxDisplay={5}
        />
      )}

      {/* STALE Section - aged but not critical */}
      {categorized.stale.length > 0 && (
        <CategorySection
          category="stale"
          tables={categorized.stale}
          statusColor={STATUS_CONFIG.stale.color}
          maxDisplay={4}
        />
      )}

      {/* EMPTY Section - no data yet */}
      {categorized.empty.length > 0 && (
        <CategorySection
          category="empty"
          tables={categorized.empty}
          statusColor={STATUS_CONFIG.empty.color}
          maxDisplay={3}
        />
      )}

      {/* HEALTHY Section - all systems normal (collapsed by default) */}
      {categorized.healthy.length > 0 && (
        <div style={{ marginTop: "var(--space-4)", opacity: 0.7 }}>
          <details>
            <summary
              style={{
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                padding: "var(--space-2) 0",
                color: STATUS_CONFIG.healthy.color,
                fontWeight: "600",
                fontSize: "var(--t-sm)",
                userSelect: "none",
              }}
            >
              <span>{STATUS_CONFIG.healthy.icon}</span>
              <span>
                {STATUS_CONFIG.healthy.label} ({categorized.healthy.length})
              </span>
            </summary>
            <div
              style={{
                borderLeft: `3px solid ${STATUS_CONFIG.healthy.color}`,
                paddingLeft: "var(--space-2)",
                marginTop: "var(--space-2)",
              }}
            >
              {categorized.healthy.map((table, idx) => (
                <TableRow
                  key={`${table.tbl}-${idx}`}
                  tableName={table.tbl}
                  health={table.hlth}
                  loader={table.load}
                  statusColor={STATUS_CONFIG.healthy.color}
                />
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

export default LoaderHealthPanel;
