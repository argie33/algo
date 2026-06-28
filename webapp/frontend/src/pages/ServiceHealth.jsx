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

      {/* Data Sources — full width so all tables are visible */}
      <div className="card" style={{ marginTop: "var(--space-4)" }}>
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
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s, i) => (
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
                      <td>
                        <span
                          className={`badge ${STATUS_VARIANT[s.status] || "badge"}`}
                        >
                          {(s.status || "").toUpperCase()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
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
