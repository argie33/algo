/**
 * Algo Orchestrator Dashboard
 *
 * Shows real-time orchestrator execution history, phase results,
 * circuit breaker status, and system health metrics.
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Activity,
  ChevronDown,
  ChevronRight,
  Inbox,
  Shield,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  CartesianGrid,
} from "recharts";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";
import ErrorBoundary from "../components/ErrorBoundary";

const TOOLTIP_STYLE = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)",
  fontSize: "var(--t-xs)",
  padding: "var(--space-2) var(--space-3)",
};

const STATUS_COLORS = {
  success: "var(--success)",
  halted: "var(--amber)",
  error: "var(--danger)",
  running: "var(--brand)",
};

const STATUS_BADGE = {
  success: "badge-success",
  halted: "badge-amber",
  error: "badge-danger",
  running: "badge-indigo",
  no_runs_yet: "badge",
};

const STATUS_ICON = {
  success: <CheckCircle size={14} />,
  halted: <AlertTriangle size={14} />,
  error: <XCircle size={14} />,
  running: <Activity size={14} />,
};

const fmtAgo = (ts) => {
  if (!ts) return "—";
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const fmtDuration = (start, end) => {
  if (!start || !end) return "—";
  const s = Math.round((new Date(end) - new Date(start)) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
};

const fmtTime = (ts) => {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
};

const fmtDate = (ts) => {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
};

function toPhaseSet(val) {
  if (!val) return new Set();
  if (Array.isArray(val))
    return new Set(val.map((s) => String(s).trim()).filter(Boolean));
  if (typeof val === "number") return new Set(); // API returns count, not phase names
  return new Set(
    String(val)
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
  );
}

function PhaseChips({ phasesCompleted, phasesHalted, phasesErrored }) {
  const phases = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"];
  const halted = toPhaseSet(phasesHalted);
  const errored = toPhaseSet(phasesErrored);
  const completed = toPhaseSet(phasesCompleted);

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {phases.map((p) => {
        const label = p.replace("P", "Phase ");
        let color = "var(--surface-2)";
        let text = "var(--text-faint)";
        if (errored.has(p) || errored.has(label)) {
          color = "var(--danger)";
          text = "#fff";
        } else if (halted.has(p) || halted.has(label)) {
          color = "var(--amber)";
          text = "#000";
        } else if (completed.has(p) || completed.has(label)) {
          color = "var(--success)";
          text = "#fff";
        }
        return (
          <span
            key={p}
            style={{
              padding: "2px 6px",
              borderRadius: "var(--r-sm)",
              fontSize: "var(--t-2xs)",
              fontWeight: "var(--w-semibold)",
              background: color,
              color: text,
              fontFamily: "var(--font-mono)",
            }}
          >
            {p}
          </span>
        );
      })}
    </div>
  );
}

function RunRow({ run }) {
  const [expanded, setExpanded] = useState(false);
  const statusCls = STATUS_BADGE[run.overall_status] || "badge";
  const icon = STATUS_ICON[run.overall_status];

  return (
    <>
      <tr
        onClick={() => setExpanded((e) => !e)}
        style={{ cursor: "pointer" }}
        className="table-row-hover"
      >
        <td style={{ paddingLeft: "var(--space-2)" }}>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </td>
        <td className="mono tnum" style={{ fontSize: "var(--t-xs)" }}>
          {fmtDate(run.run_date)}
        </td>
        <td className="mono tnum" style={{ fontSize: "var(--t-xs)" }}>
          {fmtTime(run.started_at)}
        </td>
        <td
          className="mono tnum"
          style={{ fontSize: "var(--t-xs)", color: "var(--text-muted)" }}
        >
          {fmtDuration(run.started_at, run.completed_at)}
        </td>
        <td>
          <span
            className={`badge ${statusCls}`}
            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
          >
            {icon} {run.overall_status || "—"}
          </span>
        </td>
        <td
          style={{
            fontSize: "var(--t-xs)",
            color: "var(--text-muted)",
            maxWidth: 300,
          }}
        >
          <PhaseChips
            phasesCompleted={run.phases_completed}
            phasesHalted={run.phases_halted}
            phasesErrored={run.phases_errored}
          />
        </td>
      </tr>
      {expanded && (
        <tr>
          <td
            colSpan={6}
            style={{
              padding: "var(--space-3) var(--space-4)",
              background: "var(--surface-2)",
              borderBottom: "1px solid var(--border)",
            }}
          >
            {run.summary && (
              <p
                style={{
                  fontSize: "var(--t-xs)",
                  color: "var(--text-muted)",
                  margin: "0 0 var(--space-2)",
                }}
              >
                <strong>Summary:</strong> {run.summary}
              </p>
            )}
            {run.halt_reason && (
              <p
                style={{
                  fontSize: "var(--t-xs)",
                  color: "var(--amber)",
                  margin: 0,
                }}
              >
                <strong>Halt reason:</strong> {run.halt_reason}
              </p>
            )}
            {!run.summary && !run.halt_reason && (
              <p
                style={{
                  fontSize: "var(--t-xs)",
                  color: "var(--text-faint)",
                  margin: 0,
                }}
              >
                No details available
              </p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function AlgoTradingDashboardContent() {
  const navigate = useNavigate();
  const [days, setDays] = useState(7);

  const {
    data: status,
    loading: statusLoading,
    error: statusError,
    refetch: refetchStatus,
  } = useApiQuery(["algo-status"], () => api.get("/api/algo/status"), {
    refetchInterval: 30000,
  });

  const {
    data: execStats,
    loading: statsLoading,
    refetch: refetchStats,
  } = useApiQuery(
    ["exec-stats", days],
    () => api.get(`/api/algo/execution/stats?days=${days}`),
    { refetchInterval: 60000 }
  );

  const {
    data: recentRuns,
    loading: runsLoading,
    error: runsError,
    refetch: refetchRuns,
  } = useApiQuery(
    ["exec-recent", days],
    () => api.get(`/api/algo/execution/recent?days=${days}&limit=30`),
    { refetchInterval: 60000 }
  );

  const {
    data: breakers,
    loading: breakersLoading,
    refetch: refetchBreakers,
  } = useApiQuery(
    ["circuit-breakers"],
    () => api.get("/api/algo/circuit-breakers"),
    { refetchInterval: 60000 }
  );

  const isLoading =
    statusLoading || statsLoading || runsLoading || breakersLoading;

  const refetchAll = () => {
    refetchStatus();
    refetchStats();
    refetchRuns();
    refetchBreakers();
  };

  const runs = Array.isArray(recentRuns) ? recentRuns : recentRuns?.items || [];
  const breakerList = Array.isArray(breakers)
    ? breakers
    : breakers?.breakers || breakers?.items || [];
  const stats = execStats || {};

  const byStatus = stats.by_status || {};
  const chartData = Object.entries(byStatus).map(([status, count]) => ({
    status,
    count,
    fill: STATUS_COLORS[status] || "var(--text-faint)",
  }));

  const triggeredBreakers = breakerList.filter(
    (b) => b.triggered || b.is_triggered
  );
  const totalBreakers = breakerList.length;

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Algo Orchestrator</div>
          <div className="page-head-sub">
            7-phase execution monitor · Circuit breakers · Run history
          </div>
        </div>
        <div
          className="page-head-actions"
          style={{
            display: "flex",
            gap: "var(--space-2)",
            alignItems: "center",
          }}
        >
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="select select-sm"
            style={{ width: 120 }}
          >
            <option value={3}>Last 3 days</option>
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
          </select>
          <button
            className="btn btn-outline btn-sm"
            onClick={refetchAll}
            disabled={isLoading}
          >
            <RefreshCw size={14} className={isLoading ? "spin" : ""} />
            {isLoading ? "Loading…" : "Refresh"}
          </button>
          <button
            className="btn btn-outline btn-sm"
            onClick={() => navigate("/app/portfolio")}
          >
            Portfolio View
          </button>
          <button
            className="btn btn-outline btn-sm"
            onClick={() => navigate("/app/health")}
          >
            System Health
          </button>
        </div>
      </div>

      {statusError && (
        <div
          className="alert alert-danger"
          style={{ margin: "0 0 var(--space-4)" }}
        >
          Failed to load algo status: {statusError?.message || "Unknown error"}
        </div>
      )}

      {/* KPI Strip */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "var(--space-4)",
          marginBottom: "var(--space-6)",
        }}
      >
        <div className="card">
          <div className="card-body" style={{ padding: "var(--space-4)" }}>
            <div className="kpi-label">Last Run</div>
            {statusLoading ? (
              <div className="skeleton" style={{ height: 28 }} />
            ) : (
              <div className="kpi-value" style={{ fontSize: "var(--t-xl)" }}>
                {status?.status === "no_runs_yet"
                  ? "—"
                  : fmtAgo(status?.last_run)}
              </div>
            )}
            <div className="kpi-sub">{status?.current_phase || "—"}</div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{ padding: "var(--space-4)" }}>
            <div className="kpi-label">Status</div>
            {statusLoading ? (
              <div className="skeleton" style={{ height: 28 }} />
            ) : (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  marginTop: 4,
                }}
              >
                <span
                  className={`badge ${STATUS_BADGE[status?.status] || "badge"}`}
                  style={{ fontSize: "var(--t-sm)", padding: "4px 10px" }}
                >
                  {STATUS_ICON[status?.status]} {status?.status || "—"}
                </span>
              </div>
            )}
            <div className="kpi-sub" style={{ marginTop: 6 }}>
              {status?.message ? status.message.slice(0, 60) : "No recent run"}
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{ padding: "var(--space-4)" }}>
            <div className="kpi-label">Runs ({days}d)</div>
            {statsLoading ? (
              <div className="skeleton" style={{ height: 28 }} />
            ) : (
              <div className="kpi-value" style={{ fontSize: "var(--t-xl)" }}>
                {stats.total_runs ?? "—"}
              </div>
            )}
            <div className="kpi-sub">
              {stats.success_rate
                ? `${stats.success_rate} success`
                : "No data yet"}
              {stats.halt_rate && stats.halt_rate !== "0.0%"
                ? ` · ${stats.halt_rate} halted`
                : ""}
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{ padding: "var(--space-4)" }}>
            <div className="kpi-label">Circuit Breakers</div>
            {breakersLoading ? (
              <div className="skeleton" style={{ height: 28 }} />
            ) : (
              <div
                className="kpi-value"
                style={{
                  fontSize: "var(--t-xl)",
                  color:
                    triggeredBreakers.length > 0
                      ? "var(--danger)"
                      : "var(--success)",
                }}
              >
                {triggeredBreakers.length > 0
                  ? `${triggeredBreakers.length} triggered`
                  : totalBreakers > 0
                    ? "All clear"
                    : "—"}
              </div>
            )}
            <div className="kpi-sub">
              {totalBreakers > 0
                ? `${totalBreakers} breakers monitored`
                : "No breaker data"}
            </div>
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-6)",
          marginBottom: "var(--space-6)",
        }}
      >
        {/* Run Status Chart */}
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Run Outcomes</div>
              <div className="card-sub">Last {days} days by status</div>
            </div>
          </div>
          <div className="card-body">
            {statsLoading ? (
              <div className="skeleton" style={{ height: 160 }} />
            ) : chartData.length === 0 ? (
              <div className="empty-state">
                <Inbox size={32} className="empty-icon" />
                <p>No execution data yet</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart
                  data={chartData}
                  margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--border)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="status"
                    tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                    allowDecimals={false}
                  />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Circuit Breakers */}
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title flex items-center gap-2">
                <Shield size={16} /> Circuit Breakers
              </div>
              <div className="card-sub">
                Trading halt conditions · current vs threshold
              </div>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {breakersLoading ? (
              <div style={{ padding: "var(--space-4)" }}>
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="skeleton"
                    style={{ height: 44, marginBottom: 8 }}
                  />
                ))}
              </div>
            ) : breakerList.length === 0 ? (
              <div className="empty-state">
                <Inbox size={32} className="empty-icon" />
                <p>No circuit breaker data</p>
                <p className="empty-sub">
                  Run the circuit breakers loader to populate
                </p>
              </div>
            ) : (
              <div style={{ overflowY: "auto", maxHeight: 260 }}>
                {breakerList.map((b, i) => {
                  const cur = b.current != null ? Number(b.current) : null;
                  const thr = b.threshold != null ? Number(b.threshold) : null;
                  const barPct = b.triggered
                    ? 100
                    : cur != null && thr != null && thr !== 0
                      ? Math.min(
                          100,
                          Math.max(0, (Math.abs(cur) / Math.abs(thr)) * 100)
                        )
                      : 0;
                  const barTone = b.triggered
                    ? "danger"
                    : barPct >= 80
                      ? "warn"
                      : "success";
                  return (
                    <div
                      key={i}
                      style={{
                        padding: "var(--space-2) var(--space-4)",
                        borderBottom:
                          i < breakerList.length - 1
                            ? "1px solid var(--border-soft)"
                            : "none",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          marginBottom: 4,
                        }}
                      >
                        <span
                          style={{
                            fontSize: "var(--t-xs)",
                            fontWeight: "var(--w-medium)",
                            color: b.triggered
                              ? "var(--danger)"
                              : "var(--text)",
                          }}
                        >
                          {b.label || b.id || `Breaker ${i + 1}`}
                        </span>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "var(--space-2)",
                          }}
                        >
                          <span
                            style={{
                              fontSize: "var(--t-2xs)",
                              color: "var(--text-faint)",
                              fontFamily: "var(--font-mono)",
                            }}
                          >
                            {cur != null
                              ? `${cur.toFixed(1)}${b.unit || ""}`
                              : "—"}
                            {thr != null
                              ? ` / ${thr.toFixed(1)}${b.unit || ""}`
                              : ""}
                          </span>
                          <span
                            className={`badge ${b.triggered ? "badge-danger" : "badge-success"}`}
                          >
                            {b.triggered ? "HALT" : "OK"}
                          </span>
                        </div>
                      </div>
                      <div className="bar">
                        <div
                          className={`bar-fill ${barTone}`}
                          style={{ width: `${barPct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Execution History */}
      <div className="card">
        <div className="card-head">
          <div>
            <div className="card-title">Execution History</div>
            <div className="card-sub">
              Recent orchestrator runs — click a row for details
            </div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0, overflowX: "auto" }}>
          {runsLoading ? (
            <div style={{ padding: "var(--space-4)" }}>
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="skeleton"
                  style={{ height: 40, marginBottom: 8 }}
                />
              ))}
            </div>
          ) : runsError ? (
            <div
              className="alert alert-danger"
              style={{ margin: "var(--space-4)" }}
            >
              Failed to load execution history: {runsError?.message}
            </div>
          ) : runs.length === 0 ? (
            <div className="empty-state">
              <Inbox size={40} className="empty-icon" />
              <p>No execution runs found</p>
              <p className="empty-sub">
                The orchestrator logs runs to the orchestrator_execution_log
                table after each execution.
              </p>
            </div>
          ) : (
            <table className="data-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ width: 24 }}></th>
                  <th>Date</th>
                  <th>Start Time</th>
                  <th>Duration</th>
                  <th>Status</th>
                  <th>Phases</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run, i) => (
                  <RunRow key={run.run_id || i} run={run} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  );
}

export default function AlgoTradingDashboard() {
  return (
    <ErrorBoundary>
      <AlgoTradingDashboardContent />
    </ErrorBoundary>
  );
}
