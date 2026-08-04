/**
 * Service Health — patrol findings, loader status, data freshness, schedules.
 * Pure JSX + theme.css classes.
 */

import React, { useState } from "react";
import { useApiQuery } from "../hooks/useApiQuery";
import {
  RefreshCw,
  Inbox,
  CheckCircle,
  AlertTriangle,
  AlertCircle,
  Activity,
  Play,
} from "lucide-react";
import { api } from "../services/api";
import ErrorBoundary from "../components/ErrorBoundary";

const fmtAgo = (ts) => {
  if (!ts) return "—";
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const STATUS_VARIANT = {
  ok: "badge-success",
  stale: "badge-amber",
  error: "badge-danger",
  empty: "badge",
};

function ServiceHealthContent() {
  const [patrolRunning, setPatrolRunning] = useState(false);
  const [patrolMsg, setPatrolMsg] = useState(null);

  const runPatrol = async () => {
    setPatrolRunning(true);
    setPatrolMsg(null);
    try {
      await api.post("/api/algo/patrol", { quick: false });
      setPatrolMsg({
        ok: true,
        text: "Data patrol complete — refresh to see latest findings.",
      });
    } catch (e) {
      console.error("[ServiceHealth] Data patrol failed:", {
        message: e?.message,
        code: e?.code,
        status: e?.response?.status,
        endpoint: "/api/algo/patrol",
      });
      setPatrolMsg({
        ok: false,
        text: `Patrol failed: ${e?.message || "Unknown error"}`,
      });
    }
    setPatrolRunning(false);
  };

  const {
    data: dataStatus,
    loading: dsLoading,
    error: dsError,
    refetch,
  } = useApiQuery(
    ["algo-data-status"],
    () => api.get("/api/algo/data-status"),
    { refetchInterval: 30000 }
  );
  const {
    data: patrolLog,
    loading: plLoading,
    error: plError,
  } = useApiQuery(
    ["algo-patrol-log"],
    () => api.get("/api/algo/patrol-log?limit=50"),
    { refetchInterval: 60000 }
  );
  const { data: status, loading: statusLoading } = useApiQuery(
    ["algo-status"],
    () => api.get("/api/algo/status"),
    { refetchInterval: 30000 }
  );

  const isLoading = dsLoading || plLoading || statusLoading;

  const plAccessDenied =
    plError?.status === 403 ||
    (typeof plError === "string" && plError.includes("Authentication"));

  if (dsError) {
    return (
      <div className="alert alert-danger" style={{ margin: "20px" }}>
        {dsError?.message || "Failed to load service health data"}
      </div>
    );
  }

  const summary = dataStatus?.summary || {
    ok: 0,
    stale: 0,
    empty: 0,
    error: 0,
  };
  const sources = dataStatus?.sources || [];
  const ready = dataStatus?.ready_to_trade;
  const executionHealth = dataStatus?.execution_health;
  const findings = plAccessDenied
    ? []
    : Array.isArray(patrolLog)
      ? patrolLog
      : patrolLog?.items || [];

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Service Health</div>
          <div className="page-head-sub">
            Data freshness · Patrol findings · Algo readiness
          </div>
        </div>
        <div className="page-head-actions">
          <button
            className="btn btn-primary btn-sm"
            onClick={runPatrol}
            disabled={patrolRunning}
          >
            <Play size={14} /> {patrolRunning ? "Running…" : "Run Data Patrol"}
          </button>
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {patrolMsg && (
        <div
          className={`alert ${patrolMsg.ok ? "alert-success" : "alert-danger"}`}
          style={{ marginBottom: "var(--space-4)" }}
        >
          {patrolMsg.ok ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          <span>{patrolMsg.text}</span>
        </div>
      )}

      {/* Top status banner */}
      <div
        className="card"
        style={{
          borderLeft: `3px solid ${ready ? "var(--success)" : "var(--danger)"}`,
          padding: "var(--space-5) var(--space-6)",
        }}
      >
        <div className="grid grid-4 items-center">
          <div className="flex items-center gap-3">
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: "var(--r-md)",
                background: ready
                  ? "var(--success-soft)"
                  : "var(--danger-soft)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: `1px solid ${ready ? "var(--success)" : "var(--danger)"}50`,
              }}
            >
              {ready ? (
                <CheckCircle size={24} color="var(--success)" />
              ) : (
                <AlertCircle size={24} color="var(--danger)" />
              )}
            </div>
            <div>
              <div className="eyebrow">Algo Status</div>
              <div
                className={`mono ${ready ? "up" : "down"}`}
                style={{ fontSize: "var(--t-xl)", fontWeight: "var(--w-bold)" }}
              >
                {ready ? "READY TO TRADE" : "NOT READY"}
              </div>
            </div>
          </div>
          <div className="stile">
            <div className="stile-label">Sources OK</div>
            <div className="stile-value up">{summary.ok}</div>
          </div>
          <div className="stile">
            <div className="stile-label">Stale</div>
            <div className={`stile-value ${summary.stale > 0 ? "down" : ""}`}>
              {summary.stale || 0}
            </div>
          </div>
          <div className="stile">
            <div className="stile-label">Errors</div>
            <div
              className={`stile-value ${(summary.error || 0) + (summary.empty || 0) > 0 ? "down" : ""}`}
            >
              {(summary.error || 0) + (summary.empty || 0)}
            </div>
          </div>
        </div>
        {dataStatus?.critical_stale?.length > 0 && (
          <div
            className="alert alert-danger"
            style={{ marginTop: "var(--space-4)" }}
          >
            <AlertCircle size={16} />
            <div>
              <strong>Critical sources stale:</strong>{" "}
              {dataStatus.critical_stale.join(", ")}
            </div>
          </div>
        )}
      </div>

      {/* Data Sources (narrowed to make room on the right) + Phase Execution */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)",
          gap: "var(--space-4)",
          marginTop: "var(--space-4)",
          alignItems: "start",
        }}
      >
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Data Sources ({sources.length})</div>
            <div className="card-sub">
              Per-table freshness · loader role · age
            </div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {isLoading ? (
            <Empty title="Loading…" />
          ) : sources.length === 0 ? (
            <Empty title="No data" />
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Role</th>
                    <th className="num">Latest</th>
                    <th className="num">Age</th>
                    <th className="num">Rows</th>
                    <th className="num">Duration</th>
                    <th className="num">Fails</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s, i) => {
                    // Loader operational health (consecutive_failures, loader_error,
                    // loader_run_status) is an independent signal from freshness status
                    // (s.status: ok/stale/empty) - a table can be freshness-"ok" (its last
                    // SUCCESSFUL run met the freshness window) while the loader has failed on
                    // every attempt since. Previously this table showed neither Duration nor
                    // failure count at all, so a table with dozens of consecutive failures
                    // rendered identically to one with zero - the whole-table listing gave no
                    // indication anything was wrong.
                    const fails = s.consecutive_failures;
                    const hasFails = typeof fails === "number" && fails > 0;
                    const duration =
                      s.execution_duration_sec != null
                        ? `${Math.round(s.execution_duration_sec)}s`
                        : "—";
                    const failTitle = hasFails
                      ? [
                          s.loader_error,
                          s.last_success_at
                            ? `last success ${String(s.last_success_at).slice(0, 10)}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")
                      : undefined;
                    return (
                      <tr key={i}>
                        <td>
                          <span
                            className="strong"
                            style={{ fontWeight: "var(--w-semibold)" }}
                          >
                            {s.name}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`badge ${s.role === "CRIT" ? "badge-danger" : s.role === "IMP" ? "badge-amber" : "badge"}`}
                            style={{ fontSize: "var(--t-2xs)" }}
                          >
                            {s.role || "NORM"}
                          </span>
                        </td>
                        <td className="num mono t-xs">
                          {s.last_updated
                            ? String(s.last_updated).slice(0, 10)
                            : "—"}
                        </td>
                        <td
                          className={`num mono ${s.age_hours > 168 ? "down" : ""}`}
                        >
                          {s.age_hours != null ? `${s.age_hours}h` : "—"}
                        </td>
                        <td className="num mono t-xs muted">
                          {s.row_count
                            ? Number(s.row_count).toLocaleString("en-US")
                            : "—"}
                        </td>
                        <td className="num mono t-xs muted">{duration}</td>
                        <td
                          className={`num mono t-xs ${hasFails ? "down" : "muted"}`}
                          title={failTitle}
                        >
                          {hasFails ? fails : "—"}
                        </td>
                        <td>
                          <span
                            className={`badge ${STATUS_VARIANT[s.status] || "badge"}`}
                          >
                            {(s.status || "").toUpperCase()}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Phase Execution</div>
            <div className="card-sub">Live per-phase status (P1–P9)</div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          <PhaseExecutionPanel executionHealth={executionHealth} />
        </div>
      </div>
      </div>

      {/* Two-column: patrol findings + orchestrator run status */}
      <div className="grid grid-2" style={{ marginTop: "var(--space-4)" }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Recent Patrol Findings</div>
              <div className="card-sub">
                Last 50 issues across critical/error/warn
              </div>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {plAccessDenied ? (
              <Empty
                title="Admin access required"
                desc="Patrol log requires admin permissions."
                icon={AlertTriangle}
              />
            ) : findings.length === 0 ? (
              <Empty
                title="All clear"
                desc="No recent patrol findings."
                icon={CheckCircle}
              />
            ) : (
              <div style={{ maxHeight: "400px", overflow: "auto" }}>
                {findings.map((f, i) => (
                  <FindingRow key={i} finding={f} />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Last Orchestrator Run</div>
              <div className="card-sub">
                Phase results from the most recent algo workflow execution
              </div>
            </div>
          </div>
          <div className="card-body">
            {status ? (
              <div className="grid grid-2">
                <div className="stile">
                  <div className="stile-label">Last Run</div>
                  <div className="stile-value">
                    {status.last_run ? fmtAgo(status.last_run) : "—"}
                  </div>
                  <div className="stile-sub">{status.run_id || "—"}</div>
                </div>
                <div className="stile">
                  <div className="stile-label">Status</div>
                  <div
                    className={`stile-value ${status.status === "success" ? "up" : "down"}`}
                  >
                    {(status.status || "UNKNOWN").toUpperCase()}
                  </div>
                </div>
                <div className="stile">
                  <div className="stile-label">Current Phase</div>
                  <div className="stile-value">
                    {status.current_phase || "—"}
                  </div>
                </div>
                <div className="stile">
                  <div className="stile-label">Open Positions</div>
                  <div className="stile-value">
                    {status.portfolio?.open_positions ?? "—"}
                  </div>
                </div>
              </div>
            ) : (
              <Empty
                title="No status yet"
                desc="Algo orchestrator hasn't reported a run."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ServiceHealth() {
  return (
    <ErrorBoundary>
      <ServiceHealthContent />
    </ErrorBoundary>
  );
}

function FindingRow({ finding }) {
  const sev = (finding.severity || "").toUpperCase();
  const variant =
    sev === "CRITICAL" || sev === "ERROR"
      ? "badge-danger"
      : sev === "WARN"
        ? "badge-amber"
        : "badge";
  const icon =
    sev === "CRITICAL" || sev === "ERROR" ? (
      <AlertCircle size={14} color="var(--danger)" />
    ) : sev === "WARN" ? (
      <AlertTriangle size={14} color="var(--amber)" />
    ) : (
      <Activity size={14} className="muted" />
    );
  return (
    <div
      style={{
        padding: "var(--space-3) var(--space-4)",
        borderBottom: "1px solid var(--border-soft)",
      }}
    >
      <div className="flex items-center gap-3">
        {icon}
        <span className={`badge ${variant}`}>{sev}</span>
        <span
          className="strong t-sm"
          style={{ fontWeight: "var(--w-semibold)" }}
        >
          {finding.check_name}
        </span>
        {finding.target_table && (
          <span className="muted t-xs">· {finding.target_table}</span>
        )}
        <span className="t-xs faint mono" style={{ marginLeft: "auto" }}>
          {fmtAgo(finding.created_at)}
        </span>
      </div>
      <div className="t-sm" style={{ marginTop: 4, color: "var(--text-2)" }}>
        {finding.message}
      </div>
    </div>
  );
}

function Empty({ title, desc, icon: Icon = Inbox }) {
  return (
    <div className="empty">
      <Icon size={36} />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}

// Mirrors dashboard/panels/health.py's phases_def / execution_health field names —
// keep the two in sync if either changes.
const PHASE_DEFS = [
  { key: "phase_1_data_check", num: 1, label: "Data Freshness" },
  { key: "phase_2_circuit_breakers", num: 2, label: "Circuit Breakers" },
  { key: "phase_3_position_monitor", num: 3, label: "Position Monitor" },
  { key: "phase_4_broker_reconciliation", num: 4, label: "Broker Reconciliation" },
  { key: "phase_5_exposure_policy", num: 5, label: "Exposure Policy" },
  { key: "phase_6_exit_execution", num: 6, label: "Exit Execution" },
  { key: "phase_7_signal_generation", num: 7, label: "Signal Generation" },
  { key: "phase_8_entry_execution", num: 8, label: "Entry Execution" },
  { key: "phase_9_portfolio_snapshot", num: 9, label: "Portfolio Snapshot" },
];

// Live per-phase read (from /api/algo/data-status's execution_health) - not tied to a
// specific orchestrator run, so this shows current state rather than a COMPLETED/HALTED
// run-status badge (that would require phase_results, which this endpoint doesn't carry).
function phaseSummary(num, data) {
  if (!data || typeof data !== "object") return null;
  switch (num) {
    case 1: {
      const { tables_fresh, tables_stale, tables_validated } = data;
      if (tables_validated == null) return null;
      const tone = tables_stale >= 3 ? "down" : tables_stale > 0 ? "" : "up";
      return { text: `${tables_fresh ?? "?"}/${tables_validated} fresh`, tone };
    }
    case 2: {
      const { any_triggered, drawdown_pct, vix_level } = data;
      if (any_triggered == null) return null;
      const parts = [any_triggered ? "TRIGGERED" : "OK"];
      if (drawdown_pct != null) parts.push(`DD ${Number(drawdown_pct).toFixed(1)}%`);
      if (vix_level != null) parts.push(`VIX ${Number(vix_level).toFixed(1)}`);
      return { text: parts.join(" · "), tone: any_triggered ? "down" : "up" };
    }
    case 3: {
      const { open_positions, max_loss_pct } = data;
      if (open_positions == null) return null;
      const parts = [`${open_positions} open`];
      if (max_loss_pct != null) parts.push(`max ${Number(max_loss_pct).toFixed(1)}%`);
      return { text: parts.join(" · "), tone: open_positions > 5 ? "down" : "" };
    }
    case 4: {
      const { sync_count, avg_match_pct } = data;
      if (sync_count == null) return null;
      const parts = [`${sync_count} syncs`];
      if (avg_match_pct != null) parts.push(`${Math.round(avg_match_pct)}% match`);
      return { text: parts.join(" · "), tone: avg_match_pct != null && avg_match_pct < 80 ? "down" : "" };
    }
    case 5: {
      const { market_regime, entry_allowed, halt_active } = data;
      if (entry_allowed == null && !market_regime) return null;
      const parts = [];
      if (market_regime) parts.push(market_regime);
      parts.push(entry_allowed ? "entries allowed" : "entries blocked");
      if (halt_active) parts.push("HALT ACTIVE");
      return { text: parts.join(" · "), tone: halt_active ? "down" : entry_allowed ? "up" : "" };
    }
    case 6: {
      const { exits_executed, success_rate } = data;
      if (exits_executed == null) return null;
      const parts = [`${exits_executed} exits`];
      if (success_rate != null && exits_executed > 0) parts.push(`${Math.round(success_rate)}% success`);
      return {
        text: parts.join(" · "),
        tone: exits_executed > 0 && success_rate != null && success_rate < 50 ? "down" : "",
      };
    }
    case 7: {
      const { signals_generated, avg_strength } = data;
      if (signals_generated == null) return null;
      const parts = [`${signals_generated} signals`];
      if (avg_strength != null) parts.push(`avg ${Number(avg_strength).toFixed(1)}`);
      return { text: parts.join(" · "), tone: "" };
    }
    case 8: {
      const { entries_executed, success_rate } = data;
      if (entries_executed == null) return null;
      const parts = [`${entries_executed} entries`];
      if (success_rate != null && entries_executed > 0) parts.push(`${Math.round(success_rate)}% success`);
      return {
        text: parts.join(" · "),
        tone: entries_executed > 0 && success_rate != null && success_rate < 50 ? "down" : "",
      };
    }
    case 9: {
      const { portfolio_value, total_return_pct } = data;
      if (portfolio_value == null) return null;
      const parts = [`$${Number(portfolio_value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`];
      if (total_return_pct != null) parts.push(`${Number(total_return_pct).toFixed(2)}%`);
      return { text: parts.join(" · "), tone: total_return_pct != null ? (total_return_pct >= 0 ? "up" : "down") : "" };
    }
    default:
      return null;
  }
}

function PhaseExecutionPanel({ executionHealth }) {
  if (!executionHealth || typeof executionHealth !== "object") {
    return (
      <Empty
        title="No phase data"
        desc="Execution health unavailable."
        icon={Activity}
      />
    );
  }
  return (
    <div>
      {PHASE_DEFS.map((p) => {
        const summary = phaseSummary(p.num, executionHealth[p.key]);
        return (
          <div
            key={p.num}
            style={{
              padding: "var(--space-2) var(--space-3)",
              borderBottom: "1px solid var(--border-soft)",
            }}
          >
            <div
              className="t-xs strong"
              style={{ fontWeight: "var(--w-semibold)" }}
            >
              P{p.num} · {p.label}
            </div>
            {summary ? (
              <div className={`t-xs mono ${summary.tone}`} style={{ marginTop: 2 }}>
                {summary.text}
              </div>
            ) : (
              <div className="t-xs faint" style={{ marginTop: 2 }}>
                no data
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
