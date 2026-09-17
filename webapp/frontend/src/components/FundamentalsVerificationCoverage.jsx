/**
 * FundamentalsVerificationCoverage - for every SEC-XBRL-sourced fundamentals line item we
 * cross-check against yfinance (scripts/xbrl_yfinance_crosscheck.py), how many comparisons are
 * confident (match), how many are flagged and still unreviewed, and - of the ones a human has
 * actually looked at - how many turned out to be a legitimate difference vs. a confirmed bug
 * (open or already fixed). Answers "how many of our metrics are we confident are right, which
 * ones we know are still wrong, and which ones we're still uncertain about" so the remaining
 * review effort has a real, shrinking denominator instead of one undifferentiated pile.
 *
 * ADDED 2026-09-16, same session as migration 1302 (review_status column on
 * xbrl_yfinance_line_item_report). Deliberately does NOT claim a "known wrong" count backed by
 * guesswork: `divergent` alone only means SEC and yfinance disagree by more than the field's
 * materiality band - it does NOT mean either source has been confirmed wrong. Conflating the two
 * is what caused the 2026-09-16 corruption incident (scripts/DIVERGENCE_REPAIR_POSTMORTEM.md),
 * where "divergent" got treated as "yfinance must be right" and 1,411 correct records got
 * overwritten with garbage. So "Confirmed wrong" here only counts rows someone has actually
 * marked via scripts/xbrl_line_item_review.py after checking that specific
 * (symbol, table, field, fiscal_year) - everything else flagged-but-unlooked-at is "Unreviewed",
 * not "wrong".
 *
 * Backed by GET /api/data-coverage (lambda/api/routes/data_coverage.py::
 * get_fundamentals_verification_coverage) - same endpoint ScoresDataCoverage's neighbors on this
 * tab do not yet use; this is a new consumer of an existing, previously-unsurfaced section of
 * that response.
 */
import React, { useMemo, useState } from "react";
import { CheckCircle2, HelpCircle, AlertTriangle, Wrench, RefreshCw } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";

const COVERAGE_URL = "/api/data-coverage";

const fmtInt = (n) => Number(n || 0).toLocaleString("en-US");
const fmtPct = (n) => (n == null ? "—" : `${n}%`);

// Order matters - matches the stacked-bar segment order below.
const BUCKETS = [
  { key: "confident", label: "Confident (matches yfinance)", shortLabel: "confident", color: "#22ab84", icon: CheckCircle2 },
  { key: "unreviewed", label: "Flagged, unreviewed", shortLabel: "unreviewed", color: "#7a8aa3", icon: HelpCircle },
  { key: "reviewed_not_error", label: "Reviewed - legitimate difference", shortLabel: "legit diff", color: "#3987e5", icon: CheckCircle2 },
  { key: "reviewed_needs_fix", label: "Reviewed - confirmed wrong, open", shortLabel: "open", color: "#e2645f", icon: AlertTriangle },
  { key: "reviewed_fixed", label: "Reviewed - confirmed wrong, fixed", shortLabel: "fixed", color: "#d1a336", icon: Wrench },
];

function StackedBar({ row, total }) {
  if (!total) return <span className="t-2xs faint">No comparisons</span>;
  return (
    <div
      title={BUCKETS.map((b) => `${b.label}: ${fmtInt(row[b.key])}`).join(" · ")}
      style={{
        display: "flex",
        height: 18,
        borderRadius: "var(--r-xs)",
        overflow: "hidden",
        background: "var(--surface-3)",
      }}
    >
      {BUCKETS.map((b) => {
        const v = row[b.key] || 0;
        if (!v) return null;
        return (
          <div key={b.key} style={{ width: `${(100 * v) / total}%`, background: b.color }} />
        );
      })}
    </div>
  );
}

// Numeric breakdown, always visible under the bar - the bar alone only shows relative widths,
// which makes small-but-nonzero buckets (like a handful of open bugs) invisible against 5,000+
// confident matches. Only prints buckets that are actually nonzero for that row.
function BucketCounts({ row }) {
  const nonzero = BUCKETS.filter((b) => (row[b.key] || 0) > 0);
  if (!nonzero.length) return null;
  return (
    <div className="flex gap-2 t-2xs" style={{ flexWrap: "wrap", marginTop: 4 }}>
      {nonzero.map((b) => (
        <span
          key={b.key}
          className="flex items-center gap-1"
          style={{ color: b.key === "reviewed_needs_fix" ? b.color : "var(--text-muted)" }}
        >
          <span className="dot" style={{ background: b.color, width: 6, height: 6 }} />
          {fmtInt(row[b.key])} {b.shortLabel}
        </span>
      ))}
    </div>
  );
}

function fmtVal(n) {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return `${n}`;
}

const REVIEW_STATUS_LABEL = {
  reviewed_needs_fix: "Open - confirmed wrong",
  unreviewed: "Unreviewed",
  reviewed_not_error: "Legitimate difference",
  reviewed_fixed: "Fixed",
};

// Drill-down for one (table, field): the per-field row only ever showed counts - there was no
// way to see which (symbol, fiscal_year) rows actually make up an "open" or "unreviewed" bucket.
// Backed by GET /api/data-coverage?table=...&field=... (get_fundamentals_verification_field_detail).
function FieldDetailPanel({ table, field }) {
  const { data, loading, error } = useApiQuery(
    ["data-coverage-field-detail", table, field],
    () => api.get(COVERAGE_URL, { params: { table, field } }),
    { timeout: 20000, retry: 1 }
  );

  const detail = data?.data || data;
  const rows = detail?.rows || [];

  if (loading) {
    return (
      <div className="t-2xs muted" style={{ padding: "var(--space-2) var(--space-3)" }}>
        Loading divergent rows for {table}.{field}…
      </div>
    );
  }
  if (error) {
    return (
      <div className="t-2xs" style={{ padding: "var(--space-2) var(--space-3)", color: "var(--danger, #e2645f)" }}>
        Failed to load detail: {error?.message || "unknown error"}
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="t-2xs muted" style={{ padding: "var(--space-2) var(--space-3)" }}>
        No divergent rows recorded for {table}.{field} - every comparison on record matched
        yfinance within the materiality band.
      </div>
    );
  }

  return (
    <div style={{ padding: "var(--space-2) var(--space-3)" }}>
      {detail?.truncated && (
        <div className="t-2xs faint" style={{ marginBottom: 6 }}>
          Showing the first {rows.length} divergent rows (open bugs and unreviewed first) - more
          exist. Use{" "}
          <code className="mono t-2xs">
            python scripts/xbrl_line_item_report.py --divergent-only --unreviewed-only
          </code>{" "}
          for the full list.
        </div>
      )}
      <table className="data-table" style={{ fontSize: "var(--t-2xs)" }}>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Period</th>
            <th>Ours</th>
            <th>yfinance</th>
            <th>Ratio</th>
            <th>Status</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.symbol}-${r.fiscal_year}-${r.fiscal_quarter}-${i}`}>
              <td className="mono">{r.symbol}</td>
              <td className="mono">{r.fiscal_quarter ? `FY${r.fiscal_year}Q${r.fiscal_quarter}` : `FY${r.fiscal_year}`}</td>
              <td className="mono num">{fmtVal(r.our_value)}</td>
              <td className="mono num">{fmtVal(r.yfinance_value)}</td>
              <td className="mono num">{r.ratio != null ? r.ratio.toFixed(3) : "—"}</td>
              <td>
                <span
                  className="t-2xs"
                  style={{
                    color: r.review_status === "reviewed_needs_fix" ? "#e2645f" : "var(--text-muted)",
                    fontWeight: r.review_status === "reviewed_needs_fix" ? 600 : 400,
                  }}
                >
                  {REVIEW_STATUS_LABEL[r.review_status] || r.review_status}
                </span>
              </td>
              <td className="t-2xs faint">{r.review_note || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FundamentalsVerificationCoverage({ active }) {
  const { data, loading, error, isFetching, refetch } = useApiQuery(
    ["data-coverage", "fundamentals-verification"],
    () => api.get(COVERAGE_URL),
    { enabled: active, timeout: 30000, retry: 1 }
  );

  const [sortMode, setSortMode] = useState("unreviewed_desc");
  const [expandedField, setExpandedField] = useState(null); // `${table}.${field}` or null

  if (!active) return null;

  if (error) {
    return (
      <div className="alert alert-danger" style={{ margin: "20px 0" }}>
        {error?.message || "Failed to load fundamentals verification coverage"}
      </div>
    );
  }

  // get_fundamentals_verification_coverage wraps its own payload in a second
  // {statusCode, data} envelope (via success_response) before it's embedded under
  // data.fundamentals_verification in the outer /api/data-coverage response - useApiQuery only
  // unwraps the outer one.
  const fv = data?.fundamentals_verification?.data;
  const matrix = fv?.line_item_matrix;
  const perField = matrix?.per_field || [];

  const totals = useMemo(() => {
    if (!matrix) return null;
    return {
      confident: matrix.comparisons_confident || 0,
      unreviewed: matrix.comparisons_unreviewed || 0,
      reviewed_not_error: matrix.comparisons_reviewed_not_error || 0,
      reviewed_needs_fix: matrix.comparisons_reviewed_needs_fix || 0,
      reviewed_fixed: matrix.comparisons_reviewed_fixed || 0,
      total: matrix.comparisons_total || 0,
    };
  }, [matrix]);

  const rows = useMemo(() => {
    const out = perField.slice();
    out.sort((a, b) => {
      if (sortMode === "unreviewed_desc") return (b.unreviewed || 0) - (a.unreviewed || 0);
      if (sortMode === "needs_fix_desc") return (b.reviewed_needs_fix || 0) - (a.reviewed_needs_fix || 0);
      if (sortMode === "checked_desc") return (b.checked || 0) - (a.checked || 0);
      if (sortMode === "name") return `${a.table}.${a.field}`.localeCompare(`${b.table}.${b.field}`);
      return 0;
    });
    return out;
  }, [perField, sortMode]);

  return (
    <div style={{ marginTop: "var(--space-5)" }}>
      <div className="flex items-center gap-3" style={{ marginBottom: "var(--space-4)" }}>
        <div style={{ flex: 1 }}>
          <div className="t-sm muted">
            For every SEC-XBRL fundamentals line item cross-checked against Yahoo Finance
            (<code className="mono t-2xs">scripts/xbrl_yfinance_crosscheck.py</code>): how many
            comparisons are confident matches, how many are flagged and still unreviewed, and -
            of the ones actually reviewed - how many turned out to be a legitimate difference vs.
            a confirmed bug (open or fixed). This is the real scope of remaining review work, not
            a raw divergence count.
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
          <div className="empty-title">Loading fundamentals verification coverage…</div>
        </div>
      ) : !matrix || !totals?.total ? (
        <div className="empty">
          <div className="empty-title">No comparisons recorded yet</div>
          <div className="empty-desc">
            Run <code className="mono t-2xs">python scripts/xbrl_yfinance_crosscheck.py --sweep</code>{" "}
            to start building this matrix.
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-4" style={{ marginBottom: "var(--space-3)" }}>
            <div className="stile">
              <div className="stile-label">Symbols Checked</div>
              <div className="stile-value">
                {fmtInt(matrix.symbols_checked)}/{fmtInt(matrix.universe_size)}
              </div>
              <div className="stile-sub">{fmtPct(matrix.coverage_pct)} of eligible universe</div>
            </div>
            <div className="stile">
              <div className="stile-label">Confident</div>
              <div className="stile-value up">{fmtInt(totals.confident)}</div>
              <div className="stile-sub">
                {fmtInt(totals.total)} total comparisons,{" "}
                {totals.total ? Math.round((1000 * totals.confident) / totals.total) / 10 : 0}%
              </div>
            </div>
            <div className="stile">
              <div className="stile-label">Unreviewed</div>
              <div className={`stile-value ${totals.unreviewed > 0 ? "down" : "up"}`}>
                {fmtInt(totals.unreviewed)}
              </div>
              <div className="stile-sub">flagged, nobody's looked yet - the real remaining scope</div>
            </div>
            <div className="stile">
              <div className="stile-label">Confirmed Wrong</div>
              <div className={`stile-value ${totals.reviewed_needs_fix > 0 ? "down" : "up"}`}>
                {fmtInt(totals.reviewed_needs_fix)}
              </div>
              <div className="stile-sub">
                open{totals.reviewed_fixed > 0 ? ` · ${fmtInt(totals.reviewed_fixed)} already fixed` : ""}
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: "var(--space-3)" }}>
            <div className="card-body" style={{ padding: "var(--space-3)" }}>
              <StackedBar row={totals} total={totals.total} />
              <div className="flex gap-3 t-xs muted" style={{ flexWrap: "wrap", marginTop: 8 }}>
                {BUCKETS.map((b) => (
                  <span key={b.key} className="flex items-center gap-2">
                    <span className="dot" style={{ background: b.color }} />
                    {b.label} ({fmtInt(totals[b.key])})
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div
            className="card-pad-sm flex gap-3 items-center"
            style={{ flexWrap: "wrap", marginBottom: "var(--space-2)" }}
          >
            <select
              className="select"
              style={{ width: 220 }}
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value)}
            >
              <option value="unreviewed_desc">Sort: most unreviewed first</option>
              <option value="needs_fix_desc">Sort: most confirmed-wrong (open) first</option>
              <option value="checked_desc">Sort: most comparisons</option>
              <option value="name">Sort: field name</option>
            </select>
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0, overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th style={{ width: 100 }}>Checked</th>
                    <th>Breakdown</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const key = `${r.table}.${r.field}`;
                    const isOpen = expandedField === key;
                    return (
                      <React.Fragment key={key}>
                        <tr
                          onClick={() => setExpandedField(isOpen ? null : key)}
                          style={{ cursor: "pointer" }}
                          title="Click to see the underlying divergent rows"
                        >
                          <td>
                            <div className="dbl">
                              <span className="dbl-main mono t-sm">
                                {isOpen ? "▾" : "▸"} {r.field}
                              </span>
                              <span className="dbl-sub mono t-2xs faint">{r.table}</span>
                            </div>
                          </td>
                          <td className="mono t-sm num">{fmtInt(r.checked)}</td>
                          <td>
                            <StackedBar row={r} total={r.checked} />
                            <BucketCounts row={r} />
                          </td>
                        </tr>
                        {isOpen && (
                          <tr>
                            <td colSpan={3} style={{ padding: 0, background: "var(--surface-2)" }}>
                              <FieldDetailPanel table={r.table} field={r.field} />
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
            "Confident" means SEC and yfinance agree within the field's materiality band this run
            - it doesn't require a human to have looked. "Unreviewed" means the two sources
            disagree and nobody has checked which one (if either) is actually wrong yet - this is
            the honest measure of remaining review effort, not a bug count. Only rows someone has
            explicitly marked via{" "}
            <code className="mono t-2xs">scripts/xbrl_line_item_review.py</code> after checking
            that specific symbol/field/year move into "Reviewed - legitimate difference" or
            "Confirmed wrong" - there is no bulk/automatic way to mark a row reviewed, on purpose:
            treating a whole class of flagged rows as "confirmed wrong" without checking each one
            is what caused the 2026-09-16 corruption incident (see{" "}
            <code className="mono t-2xs">scripts/DIVERGENCE_REPAIR_POSTMORTEM.md</code>). Drill
            into a specific field with{" "}
            <code className="mono t-2xs">
              python scripts/xbrl_line_item_report.py --divergent-only --unreviewed-only
            </code>
            .
          </div>
        </>
      )}
    </div>
  );
}
