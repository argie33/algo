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
  ChevronDown,
  ChevronRight,
  XCircle,
  MinusCircle,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
  CartesianGrid,
} from "recharts";
import { api } from "../services/api";
import ErrorBoundary from "../components/ErrorBoundary";
import ScoresDataCoverage from "../components/ScoresDataCoverage";
import ScoresCorrectnessCoverage from "../components/ScoresCorrectnessCoverage";
import SymbolQuarantinePanel from "../components/SymbolQuarantinePanel";
import FindingExamples from "../components/DataPatrolFindingExamples";

const CHART_TOOLTIP_STYLE = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)",
  fontSize: "var(--t-xs)",
  padding: "var(--space-2) var(--space-3)",
};

// overall_status values actually written by save_execution_log() (see
// utils/logging/execution_tracker.py): success, ok, degraded, halted, error, skipped.
const RUN_STATUS_COLORS = {
  success: "var(--success)",
  ok: "var(--success)",
  degraded: "var(--amber)",
  halted: "var(--amber)",
  skipped: "var(--text-faint)",
  error: "var(--danger)",
  running: "var(--brand)",
};

const RUN_STATUS_BADGE = {
  success: "badge-success",
  ok: "badge-success",
  degraded: "badge-warning",
  halted: "badge-amber",
  skipped: "badge-neutral",
  error: "badge-danger",
  running: "badge-indigo",
  no_runs_yet: "badge",
};

const RUN_STATUS_ICON = {
  success: <CheckCircle size={14} />,
  ok: <CheckCircle size={14} />,
  degraded: <AlertTriangle size={14} />,
  halted: <AlertTriangle size={14} />,
  skipped: <MinusCircle size={14} />,
  error: <XCircle size={14} />,
  running: <Activity size={14} />,
};

const fmtDuration = (start, end) => {
  if (!start || !end) return "—";
  const s = Math.round((new Date(end) - new Date(start)) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
};

const fmtRunTime = (ts) => {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
};

const fmtRunDate = (ts) => {
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

// All 9 orchestrator phases (see algo/orchestration/orchestrator.py).
function PhaseChips({ phasesCompleted, phasesHalted, phasesErrored }) {
  const phases = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"];
  const halted = toPhaseSet(phasesHalted);
  const errored = toPhaseSet(phasesErrored);
  const completed = toPhaseSet(phasesCompleted);

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {phases.map((p) => {
        const label = p.replace("P", "Phase ");
        let color = "var(--surface-2)";
        let text = "var(--text-faint)";
        let title = "Not run";

        if (errored.has(p) || errored.has(label)) {
          color = "var(--danger)";
          text = "#fff";
          title = "Phase errored or has warnings";
        } else if (halted.has(p) || halted.has(label)) {
          color = "var(--amber)";
          text = "#000";
          title = "Phase halted";
        } else if (completed.has(p) || completed.has(label)) {
          color = "var(--success)";
          text = "#fff";
          title = "Phase completed";
        }

        return (
          <span
            key={p}
            title={title}
            style={{
              padding: "2px 6px",
              borderRadius: "var(--r-sm)",
              fontSize: "var(--t-2xs)",
              fontWeight: "var(--w-semibold)",
              background: color,
              color: text,
              fontFamily: "var(--font-mono)",
              cursor: "help",
            }}
          >
            {p}
          </span>
        );
      })}
    </div>
  );
}

function ExecutionRunRow({ run }) {
  const [expanded, setExpanded] = useState(false);
  const statusCls = RUN_STATUS_BADGE[run.overall_status] || "badge";
  const icon = RUN_STATUS_ICON[run.overall_status];

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
          {fmtRunDate(run.run_date)}
        </td>
        <td className="mono tnum" style={{ fontSize: "var(--t-xs)" }}>
          {fmtRunTime(run.started_at)}
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

function ExecutionHistoryTab() {
  const [days, setDays] = useState(7);

  const { data: execStats, loading: statsLoading } = useApiQuery(
    ["exec-stats", days],
    () => api.get(`/api/algo/execution/stats?days=${days}`),
    { refetchInterval: 60000 }
  );

  const {
    data: recentRuns,
    loading: runsLoading,
    error: runsError,
  } = useApiQuery(
    ["exec-recent", days],
    () => api.get(`/api/algo/execution/recent?days=${days}&limit=30`),
    { refetchInterval: 60000 }
  );

  const runs = Array.isArray(recentRuns) ? recentRuns : recentRuns?.items || [];
  const stats = execStats || {};
  const byStatus = stats.by_status || {};
  const chartData = Object.entries(byStatus).map(([status, count]) => ({
    status,
    count,
    fill: RUN_STATUS_COLORS[status] || "var(--text-faint)",
  }));

  return (
    <>
      <div
        className="page-head-actions"
        style={{ justifyContent: "flex-end", marginBottom: "var(--space-4)" }}
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
      </div>

      <div className="card" style={{ marginBottom: "var(--space-4)" }}>
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
                <RechartsTooltip contentStyle={CHART_TOOLTIP_STYLE} />
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
                  <ExecutionRunRow key={run.run_id || i} run={run} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}

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
  const [tab, setTab] = useState("overview");
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
  // ready_to_trade only reflects data freshness + halt-flag state (see market.py's
  // ready_to_trade = data_fresh_enough and not trading_halted) - it never looks at the
  // quality/coverage checks below, so it can render as an all-clear right next to a real
  // NULL-rate or coverage problem this same page lists per-source. Caveat it instead of
  // letting the two disagree silently (mirrors the TUI fix, 2026-08-21).
  const qualityIssueCount = sources.filter(
    (s) => s.quality_status === "warning" || s.quality_status === "error"
  ).length;
  const coverageIssueCount = sources.filter(
    (s) => s.coverage_status === "partial" || s.coverage_status === "sparse"
  ).length;
  const executionHealth = dataStatus?.execution_health;
  const allFindings = plAccessDenied
    ? []
    : Array.isArray(patrolLog)
      ? patrolLog
      : patrolLog?.items || [];
  // INFO-severity rows are health CONFIRMATIONS ("price_daily fresh", "loader_contract OK"),
  // not findings to triage - re-logged as "open" every run whether or not anything is wrong.
  // Counting them here would make this panel disagree with its own "critical/error/warn"
  // subtitle and with scripts/data_patrol_backlog_report.py's identical split (the CLI tool
  // this same session used to answer "how many data issues do we still have") - see
  // _get_patrol_log's 2026-09-13 fix docstring for why the two now share one query shape.
  const findings = allFindings.filter((f) => f.severity !== "info");
  const patrolReviewSummary = {
    acceptable: findings.filter((f) => f.review_status === "acceptable").length,
    needsFix: findings.filter((f) => f.review_status === "needs_fix").length,
    unreviewed: findings.filter((f) => !f.review_status).length,
  };

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

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--border)",
          marginBottom: "var(--space-4)",
        }}
      >
        {[
          ["overview", "Overview"],
          ["execution", "Execution History"],
          ["coverage", "Data Coverage"],
        ].map(([v, lbl]) => (
          <button
            key={v}
            type="button"
            onClick={() => setTab(v)}
            style={{
              background: "transparent",
              border: "none",
              borderBottom: `2px solid ${tab === v ? "var(--brand)" : "transparent"}`,
              color: tab === v ? "var(--brand-2)" : "var(--text-muted)",
              fontWeight: tab === v ? "var(--w-semibold)" : "var(--w-medium)",
              fontSize: "var(--t-sm)",
              padding: "12px 16px",
              cursor: "pointer",
              marginBottom: -1,
            }}
          >
            {lbl}
          </button>
        ))}
      </div>

      {tab === "coverage" && (
        <>
          {/* Data Coverage tab (renamed from "Scores Data Coverage" 2026-09-13, broadened to
              be the single home for every "is our data right / do we know what's wrong with
              it" surface instead of splitting them across tabs): raw patrol findings first
              (what checks found), then quarantine (which symbols got isolated because of
              it), then completeness, then correctness - each section builds on the one
              before it. */}
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Recent Patrol Findings</div>
                <div className="card-sub">
                  {findings.length === 0
                    ? "Currently open, critical/error/warn only"
                    : `${findings.length} open (critical/error/warn) — ` +
                      `${patrolReviewSummary.acceptable} reviewed-acceptable, ` +
                      `${patrolReviewSummary.needsFix} needs fix, ` +
                      `${patrolReviewSummary.unreviewed} never reviewed`}
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
                  desc="No open patrol findings."
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

          <SymbolQuarantinePanel active={tab === "coverage"} />
          <ScoresDataCoverage active={tab === "coverage"} />
          <ScoresCorrectnessCoverage active={tab === "coverage"} />
        </>
      )}

      {tab === "execution" && <ExecutionHistoryTab />}

      {tab === "overview" && (
        <>
          {patrolMsg && (
            <div
              className={`alert ${patrolMsg.ok ? "alert-success" : "alert-danger"}`}
              style={{ marginBottom: "var(--space-4)" }}
            >
              {patrolMsg.ok ? (
                <CheckCircle size={16} />
              ) : (
                <AlertCircle size={16} />
              )}
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
                    style={{
                      fontSize: "var(--t-xl)",
                      fontWeight: "var(--w-bold)",
                    }}
                  >
                    {ready ? "READY TO TRADE" : "NOT READY"}
                  </div>
                  {ready &&
                    (qualityIssueCount > 0 || coverageIssueCount > 0) && (
                      <div className="t-xs" style={{ color: "var(--amber)" }}>
                        {[
                          qualityIssueCount > 0
                            ? `${qualityIssueCount} quality issue(s)`
                            : null,
                          coverageIssueCount > 0
                            ? `${coverageIssueCount} coverage gap(s)`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(", ")}{" "}
                        below
                      </div>
                    )}
                </div>
              </div>
              <div className="stile">
                <div className="stile-label">Sources OK</div>
                <div className="stile-value up">{summary.ok}</div>
              </div>
              <div className="stile">
                <div className="stile-label">Stale</div>
                <div
                  className={`stile-value ${summary.stale > 0 ? "down" : ""}`}
                >
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
                  <div className="card-title">
                    Data Sources ({sources.length})
                  </div>
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
                          const hasFails =
                            typeof fails === "number" && fails > 0;
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
                          // A table can be freshness-"ok" (fresh run) while
                          // freshness_enhancements.py's separate NULL-ratio/coverage
                          // checks found a real problem in it - quality_status/
                          // coverage_status are populated independently of s.status.
                          // Without this, this exact row showed a bare green "OK" badge
                          // right next to a real data-quality gap (mirrors the same fix
                          // in dashboard/panels/health.py's TUI table, 2026-08-21).
                          const hasQualityIssue =
                            s.status === "ok" &&
                            (s.quality_status === "warning" ||
                              s.quality_status === "error");
                          const hasCoverageIssue =
                            s.status === "ok" &&
                            (s.coverage_status === "partial" ||
                              s.coverage_status === "sparse");
                          const flagQA = hasQualityIssue || hasCoverageIssue;
                          const qaTitle = flagQA
                            ? [
                                ...(s.data_quality_issues || []),
                                s.coverage_status
                                  ? `coverage: ${s.coverage_status}`
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
                              <td className="num mono t-xs muted">
                                {duration}
                              </td>
                              <td
                                className={`num mono t-xs ${hasFails ? "down" : "muted"}`}
                                title={failTitle}
                              >
                                {hasFails ? fails : "—"}
                              </td>
                              <td>
                                <span
                                  className={`badge ${flagQA ? "badge-amber" : STATUS_VARIANT[s.status] || "badge"}`}
                                  title={qaTitle}
                                >
                                  {flagQA
                                    ? "QA"
                                    : (s.status || "").toUpperCase()}
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

          {/* Orchestrator run status - "Recent Patrol Findings" moved to the Data Coverage
              tab (2026-09-13) alongside quarantine/coverage/correctness, so all "what's
              wrong with our data right now" surfaces live together instead of findings
              being split across two tabs from their own downstream effects. */}
          <div className="card" style={{ marginTop: "var(--space-4)" }}>
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
        </>
      )}
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
        {finding.review_status && (
          <span
            className="badge"
            title={finding.review_note || ""}
            style={{
              fontSize: "var(--t-2xs)",
              color: "var(--text-faint)",
              border: "1px solid var(--border-soft)",
            }}
          >
            {finding.review_status === "acceptable"
              ? "reviewed: acceptable"
              : "reviewed: needs fix"}
          </span>
        )}
        <span className="t-xs faint mono" style={{ marginLeft: "auto" }}>
          {fmtAgo(finding.created_at)}
        </span>
      </div>
      <div className="t-sm" style={{ marginTop: 4, color: "var(--text-2)" }}>
        {finding.message}
      </div>
      <FindingExamples details={finding.details} />
      {finding.review_status && finding.review_note && (
        <div
          className="t-xs faint"
          style={{ marginTop: 4, fontStyle: "italic" }}
        >
          {finding.review_note}
        </div>
      )}
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
  {
    key: "phase_4_broker_reconciliation",
    num: 4,
    label: "Broker Reconciliation",
  },
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
      if (drawdown_pct != null)
        parts.push(`DD ${Number(drawdown_pct).toFixed(1)}%`);
      if (vix_level != null) parts.push(`VIX ${Number(vix_level).toFixed(1)}`);
      return { text: parts.join(" · "), tone: any_triggered ? "down" : "up" };
    }
    case 3: {
      const { open_positions, max_loss_pct } = data;
      if (open_positions == null) return null;
      const parts = [`${open_positions} open`];
      if (max_loss_pct != null)
        parts.push(`max ${Number(max_loss_pct).toFixed(1)}%`);
      return {
        text: parts.join(" · "),
        tone: open_positions > 5 ? "down" : "",
      };
    }
    case 4: {
      const { sync_count, avg_match_pct } = data;
      if (sync_count == null) return null;
      const parts = [`${sync_count} syncs`];
      if (avg_match_pct != null)
        parts.push(`${Math.round(avg_match_pct)}% match`);
      return {
        text: parts.join(" · "),
        tone: avg_match_pct != null && avg_match_pct < 80 ? "down" : "",
      };
    }
    case 5: {
      const { market_regime, entry_allowed, halt_active } = data;
      if (entry_allowed == null && !market_regime) return null;
      const parts = [];
      if (market_regime) parts.push(market_regime);
      parts.push(entry_allowed ? "entries allowed" : "entries blocked");
      if (halt_active) parts.push("HALT ACTIVE");
      return {
        text: parts.join(" · "),
        tone: halt_active ? "down" : entry_allowed ? "up" : "",
      };
    }
    case 6: {
      const { exits_executed, success_rate } = data;
      if (exits_executed == null) return null;
      const parts = [`${exits_executed} exits`];
      if (success_rate != null && exits_executed > 0)
        parts.push(`${Math.round(success_rate)}% success`);
      return {
        text: parts.join(" · "),
        tone:
          exits_executed > 0 && success_rate != null && success_rate < 50
            ? "down"
            : "",
      };
    }
    case 7: {
      const { signals_generated, avg_strength } = data;
      if (signals_generated == null) return null;
      const parts = [`${signals_generated} signals`];
      if (avg_strength != null)
        parts.push(`avg ${Number(avg_strength).toFixed(1)}`);
      return { text: parts.join(" · "), tone: "" };
    }
    case 8: {
      const { entries_executed, success_rate } = data;
      if (entries_executed == null) return null;
      const parts = [`${entries_executed} entries`];
      if (success_rate != null && entries_executed > 0)
        parts.push(`${Math.round(success_rate)}% success`);
      return {
        text: parts.join(" · "),
        tone:
          entries_executed > 0 && success_rate != null && success_rate < 50
            ? "down"
            : "",
      };
    }
    case 9: {
      const { portfolio_value, total_return_pct } = data;
      if (portfolio_value == null) return null;
      const parts = [
        `$${Number(portfolio_value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`,
      ];
      if (total_return_pct != null)
        parts.push(`${Number(total_return_pct).toFixed(2)}%`);
      return {
        text: parts.join(" · "),
        tone:
          total_return_pct != null
            ? total_return_pct >= 0
              ? "up"
              : "down"
            : "",
      };
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
              <div
                className={`t-xs mono ${summary.tone}`}
                style={{ marginTop: 2 }}
              >
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
