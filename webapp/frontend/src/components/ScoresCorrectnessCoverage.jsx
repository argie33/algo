/**
 * ScoresCorrectnessCoverage — for every pillar-input table, has DataPatrol actually ever run
 * and found (or not found) anything, and what did it say. Rendered directly below
 * ScoresDataCoverage on the ServiceHealth "Scores Data Coverage" tab: that panel answers "is
 * the value present" (completeness); this one answers "has anything ever actually checked it"
 * (correctness monitoring).
 *
 * REWRITTEN FROM SCRATCH 2026-09-13 (user directive - the prior version, which showed whether
 * a DataPatrol check MODULE'S SOURCE TEXT happened to mention a field name, was rejected
 * outright: "it tells us nothing, gives us nothing, worthless"). That was a guess about what a
 * check could theoretically do; it never asked whether DataPatrol had actually run against a
 * table and what it found. This version is sourced entirely from GET
 * /api/algo/scores/correctness-coverage (lambda/api/routes/scores_handlers/
 * coverage_correctness.py), which reads `data_patrol_log` directly - the table every check's
 * own `self.log(...)` call writes to - so every number and message here reflects something
 * that actually ran, not source code that could in principle run.
 *
 * Table-level, not per-field (data_patrol_log's target_table is a real DB table name for most
 * checks, but doesn't carry per-column detail) - coarser than the old per-factor claim, but
 * everything shown is real execution history instead of a text-match guess.
 */
import React, { useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, HelpCircle, RefreshCw } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";

const CORRECTNESS_URL = "/api/algo/scores/correctness-coverage";

const STATUS_META = {
  never_logged: {
    label: "Never checked",
    color: "var(--danger, #e2645f)",
    icon: HelpCircle,
    blurb: "DataPatrol has never logged a single finding against this table.",
  },
  active_findings: {
    label: "Findings open",
    color: "var(--danger, #e2645f)",
    icon: AlertTriangle,
    blurb: "Checked recently, and it found something worth a look.",
  },
  stale: {
    label: "Stale",
    color: "var(--warning, #d99a2b)",
    icon: Clock,
    blurb: "Has real check history, but nothing logged inside the lookback window.",
  },
  active_clean: {
    label: "Clean",
    color: "var(--success, #22ab84)",
    icon: CheckCircle2,
    blurb: "Checked recently, nothing above informational.",
  },
};

// A finding's `details.examples` entry shape varies per check (whatever that check's own
// self.log(...) call happened to build) - usually {"symbol": "...", <flagged fields>} but
// sometimes a bare string/number. Split into a Symbol cell and a Value cell so each example
// lands in the table's own columns as a real line item, instead of one formatted blob.
function exampleSymbol(ex) {
  if (ex === null || typeof ex !== "object") return "—";
  return ex.symbol ?? "—";
}

function exampleValue(ex) {
  if (ex === null || typeof ex !== "object") return String(ex);
  const { symbol, ...rest } = ex;
  const restStr = Object.entries(rest)
    .map(([k, v]) => `${k}=${typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 4 }) : v}`)
    .join(", ");
  return restStr || "—";
}

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.stale;
  const Icon = meta.icon;
  return (
    <span
      className="flex items-center gap-1 t-xs"
      style={{ color: meta.color, fontWeight: 600 }}
      title={meta.blurb}
    >
      <Icon size={13} /> {meta.label}
    </span>
  );
}

// How many days is normal to go between checks for a table with this cadence - lets a reader
// tell "28d ago" apart for a monthly-cadence table (fine) vs a daily one (a real gap), without
// having to already know each check's own schedule.
const CADENCE_HINT = { daily: "~1d", weekly: "~7d", monthly: "~30d", quarterly: "~90d" };

export default function ScoresCorrectnessCoverage({ active }) {
  const { data, loading, error, isFetching, refetch } = useApiQuery(
    ["scores-correctness-coverage"],
    () => api.get(CORRECTNESS_URL),
    { enabled: active, timeout: 30000, retry: 1 }
  );

  const [pillarFilter, setPillarFilter] = useState(null);

  if (!active) return null;

  if (error) {
    return (
      <div className="alert alert-danger" style={{ margin: "20px 0" }}>
        {error?.message || "Failed to load correctness check coverage"}
      </div>
    );
  }

  const tables = data?.tables || [];
  const pillarSummary = data?.pillar_summary || [];
  const totals = data?.totals || {
    total_tables: 0,
    never_logged: 0,
    stale: 0,
    active_findings: 0,
    active_clean: 0,
    open_quarantine_count: 0,
  };
  const visibleTables = pillarFilter ? tables.filter((t) => t.group === pillarFilter) : tables;

  return (
    <div style={{ marginTop: "var(--space-5)" }}>
      <div className="flex items-center gap-3" style={{ marginBottom: "var(--space-4)" }}>
        <div style={{ flex: 1 }}>
          <div className="t-sm muted">
            For every pillar-input table, whether DataPatrol has actually ever logged a finding
            against it — sourced live from <code className="mono t-2xs">data_patrol_log</code>,
            not from guessing what a check's source code could do. A table can look fine in
            ScoresDataCoverage above (values present) and still never have been validated for
            plausibility at all.
          </div>
        </div>
        <button
          className="btn btn-outline btn-sm"
          onClick={() => refetch()}
          disabled={loading || isFetching}
        >
          <RefreshCw size={14} className={isFetching ? "spin" : ""} />{" "}
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {loading ? (
        <div className="empty">
          <div className="empty-title">Loading correctness check coverage…</div>
        </div>
      ) : !data ? (
        <div className="empty">
          <div className="empty-title">No correctness coverage data</div>
        </div>
      ) : (
        <>
          <div className="grid grid-4" style={{ marginBottom: "var(--space-4)" }}>
            <div className="stile">
              <div className="stile-label">Never Checked</div>
              <div className={`stile-value ${totals.never_logged > 0 ? "down" : "up"}`}>
                {totals.never_logged}
              </div>
              <div className="stile-sub">of {totals.total_tables} pillar-input tables</div>
            </div>
            <div className="stile">
              <div className="stile-label">Findings Open</div>
              <div className={`stile-value ${totals.active_findings > 0 ? "down" : "up"}`}>
                {totals.active_findings}
              </div>
              <div className="stile-sub">
                checked in the last {data.window_days}d, something to review
              </div>
            </div>
            <div className="stile">
              <div className="stile-label">Stale</div>
              <div className="stile-value">{totals.stale}</div>
              <div className="stile-sub">has check history, none in the last {data.window_days}d</div>
            </div>
            <div className="stile">
              <div className="stile-label">Clean</div>
              <div className="stile-value">{totals.active_clean}</div>
              <div className="stile-sub">checked recently, nothing found</div>
            </div>
          </div>

          {pillarSummary.length > 0 && (
            <div className="card" style={{ marginBottom: "var(--space-4)" }}>
              <div className="card-body" style={{ padding: "var(--space-3)" }}>
                <div className="flex items-center gap-3" style={{ marginBottom: "var(--space-2)" }}>
                  <div className="t-xs faint" style={{ flex: 1 }}>
                    By pillar — click to filter the table below
                  </div>
                  {pillarFilter && (
                    <button
                      className="btn btn-ghost btn-sm t-2xs"
                      onClick={() => setPillarFilter(null)}
                    >
                      Clear filter ({pillarFilter})
                    </button>
                  )}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {pillarSummary.map((p) => {
                    const needsAttention = p.never_logged + p.active_findings;
                    return (
                      <div
                        key={p.pillar}
                        className="flex items-center gap-3"
                        style={{
                          cursor: "pointer",
                          opacity: pillarFilter && pillarFilter !== p.pillar ? 0.45 : 1,
                        }}
                        onClick={() => setPillarFilter(pillarFilter === p.pillar ? null : p.pillar)}
                      >
                        <div className="t-sm" style={{ width: 90, flexShrink: 0 }}>
                          {p.pillar}
                        </div>
                        <div
                          className="flex"
                          style={{
                            flex: 1,
                            height: 10,
                            borderRadius: 4,
                            overflow: "hidden",
                            background: "var(--border-soft)",
                          }}
                        >
                          {p.never_logged > 0 && (
                            <div
                              style={{
                                width: `${(100 * p.never_logged) / p.total}%`,
                                background: STATUS_META.never_logged.color,
                              }}
                              title={`${p.never_logged} never checked`}
                            />
                          )}
                          {p.active_findings > 0 && (
                            <div
                              style={{
                                width: `${(100 * p.active_findings) / p.total}%`,
                                background: STATUS_META.active_findings.color,
                                opacity: 0.7,
                              }}
                              title={`${p.active_findings} findings open`}
                            />
                          )}
                          {p.stale > 0 && (
                            <div
                              style={{
                                width: `${(100 * p.stale) / p.total}%`,
                                background: STATUS_META.stale.color,
                              }}
                              title={`${p.stale} stale`}
                            />
                          )}
                          {p.active_clean > 0 && (
                            <div
                              style={{
                                width: `${(100 * p.active_clean) / p.total}%`,
                                background: STATUS_META.active_clean.color,
                              }}
                              title={`${p.active_clean} clean`}
                            />
                          )}
                        </div>
                        <div
                          className="t-xs faint mono"
                          style={{ width: 100, textAlign: "right", flexShrink: 0 }}
                        >
                          {needsAttention}/{p.total} need attention
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-body" style={{ padding: 0, overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Status</th>
                    <th>Last Checked</th>
                    <th>Recent ({data.window_days}d)</th>
                    <th>Latest Finding</th>
                    <th>Symbol</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTables.map((t) => {
                    const top = t.recent_findings?.[0];
                    const examples = Array.isArray(top?.details?.examples) ? top.details.examples.slice(0, 5) : [];
                    const count = top?.details?.count;
                    const moreCount = typeof count === "number" ? count - examples.length : 0;
                    // Every flagged symbol/value gets its own <tr> with its own Symbol/Value
                    // cells - a real line item in this same table, not text packed into the
                    // Latest Finding cell and not a nested table/box inside one cell. The
                    // columns shared across every example (Table/Status/Last Checked/Recent/
                    // Latest Finding) are rowSpan'd across all of that finding's line-item rows.
                    const lineRows = examples.length > 0 ? examples.length : 1;
                    const rowSpan = lineRows + (moreCount > 0 ? 1 : 0);
                    const firstExample = examples[0];
                    return (
                      <React.Fragment key={t.table}>
                        <tr>
                          <td rowSpan={rowSpan}>
                            <div className="dbl">
                              <span className="dbl-main mono t-sm">{t.table}</span>
                              <span className="dbl-sub">
                                <span className="badge badge-neutral" style={{ fontSize: "var(--t-2xs)" }}>
                                  {t.group}
                                </span>
                              </span>
                            </div>
                          </td>
                          <td rowSpan={rowSpan}>
                            <div className="flex items-center gap-2">
                              <StatusBadge status={t.status} />
                              {t.open_quarantine_count > 0 && (
                                <span
                                  className="badge badge-danger"
                                  style={{ fontSize: "var(--t-2xs)" }}
                                  title={`${t.open_quarantine_count} symbol(s) currently quarantined by a check that targets this table`}
                                >
                                  {t.open_quarantine_count} quarantined
                                </span>
                              )}
                            </div>
                          </td>
                          <td rowSpan={rowSpan} className="t-xs">
                            {t.last_seen_at ? (
                              <span title={t.last_seen_at}>
                                {t.days_since_last_seen < 1
                                  ? "< 1d ago"
                                  : `${Math.round(t.days_since_last_seen)}d ago`}
                              </span>
                            ) : (
                              <span className="faint">never</span>
                            )}
                            {t.cadence && (
                              <span className="faint" style={{ marginLeft: 4 }} title={`Expected cadence: ${t.cadence}`}>
                                ({CADENCE_HINT[t.cadence] || t.cadence})
                              </span>
                            )}
                          </td>
                          <td rowSpan={rowSpan} className="t-xs mono">
                            {t.recent.critical ? `${t.recent.critical} crit ` : ""}
                            {t.recent.error ? `${t.recent.error} err ` : ""}
                            {t.recent.warn ? `${t.recent.warn} warn ` : ""}
                            {!t.recent.critical && !t.recent.error && !t.recent.warn
                              ? t.recent.info
                                ? `${t.recent.info} info`
                                : "—"
                              : ""}
                          </td>
                          <td rowSpan={rowSpan} className="t-2xs" style={{ maxWidth: 360 }}>
                            {top ? (
                              <span title={(t.recent_findings || []).map((f) => f.message).join("\n")}>
                                <span className="mono faint">[{top.check}]</span> {top.message}
                              </span>
                            ) : (
                              <span className="faint">
                                {t.status === "never_logged"
                                  ? "No check has ever targeted this table"
                                  : "No finding in the lookback window"}
                              </span>
                            )}
                          </td>
                          <td className="t-xs mono">
                            {firstExample ? exampleSymbol(firstExample) : <span className="faint">—</span>}
                          </td>
                          <td className="t-xs mono faint">
                            {firstExample ? exampleValue(firstExample) : <span className="faint">—</span>}
                          </td>
                        </tr>
                        {examples.slice(1).map((ex, i) => (
                          <tr key={`${t.table}-ex-${i + 1}`}>
                            <td className="t-xs mono">{exampleSymbol(ex)}</td>
                            <td className="t-xs mono faint">{exampleValue(ex)}</td>
                          </tr>
                        ))}
                        {moreCount > 0 && (
                          <tr key={`${t.table}-more`}>
                            <td colSpan={2} className="t-xs faint">
                              +{moreCount} more
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="t-2xs faint" style={{ marginTop: "var(--space-3)", lineHeight: 1.6 }}>
            Table-level, not per-field — a "Clean" table has had at least one recent DataPatrol
            finding of any severity logged against it, which doesn't guarantee every column on
            it is validated. "Never checked" and "Findings open" are the two statuses worth
            acting on first: the former means literally nothing has ever run against this table;
            the latter means something ran recently and flagged a real issue still open. The
            "(~Nd)" hint next to Last Checked is that table's own expected check cadence (from
            the same thresholds StalenessChecker enforces) — a table with no hint has no
            staleness entry at all, a separate gap from whether it's ever been checked for
            correctness. A "quarantined" badge means real symbols are currently sitting in
            <code className="mono t-2xs"> symbol_quarantine</code> because of a check that
            targets this table, not just a logged message.
          </div>
        </>
      )}
    </div>
  );
}
