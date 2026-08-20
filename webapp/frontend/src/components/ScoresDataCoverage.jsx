/**
 * ScoresDataCoverage — "which scoring factors are missing data, how much, and why"
 * Powers the ServiceHealth "Scores Data Coverage" tab. Pure JSX + theme.css classes,
 * matching ServiceHealth's own convention.
 *
 * Backed by GET /api/algo/scores/coverage (lambda/api/routes/scores.py::_get_scores_coverage),
 * which aggregates every *_unavailable_reason column in the schema (~100+ small grouped-count
 * queries, ~15-20s). Manual-refresh only - not polled on an interval.
 */
import React, { useMemo, useState } from "react";
import { RefreshCw, ChevronRight, Search } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";

// Fixed color per root-cause category - order must match the backend's category_order
// (lambda/api/routes/scores.py::_COVERAGE_CATEGORY_ORDER). Neutral gray for "legitimate /
// not applicable" deliberately, since it isn't a real data gap.
const CAT_COLORS = [
  "#3987e5", // Missing SEC/XBRL data
  "#e2883f", // Insufficient history
  "#22ab84", // No analyst coverage
  "#d1a336", // Stale fiscal data
  "#9085e9", // Ownership data unresolved
  "#d9679a", // Implausible / rejected value
  "#e2645f", // Other (errors / excluded)
  "#5b6478", // Legitimate / not applicable
];

const fmtInt = (n) => Number(n || 0).toLocaleString("en-US");

export default function ScoresDataCoverage({ active }) {
  const { data, loading, error, isFetching, refetch } = useApiQuery(
    ["scores-coverage"],
    () => api.get("/api/algo/scores/coverage"),
    { enabled: active, timeout: 45000, retry: 1 }
  );

  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("All");
  const [sortMode, setSortMode] = useState("pct_desc");
  const [hideLegit, setHideLegit] = useState(false);
  const [expanded, setExpanded] = useState(() => new Set());

  const factors = data?.factors || [];
  const summary = data?.summary;
  const catOrder = summary?.category_order || [];
  const catColor = (cat) =>
    CAT_COLORS[catOrder.indexOf(cat)] || "var(--text-faint)";

  const groups = useMemo(
    () => Array.from(new Set(factors.map((f) => f.group))).sort(),
    [factors]
  );

  const kpis = useMemo(() => {
    if (!summary) return null;
    const over50 = factors.filter((f) => (f.pct_missing ?? 0) >= 50).length;
    const over20 = factors.filter((f) => (f.pct_missing ?? 0) >= 20).length;
    const gapTotal = Object.entries(summary.category_totals || {})
      .filter(([c]) => c !== "Legitimate / not applicable")
      .reduce((s, [, v]) => s + v, 0);
    const topCause = Object.entries(summary.category_totals || {})
      .filter(([c]) => c !== "Legitimate / not applicable")
      .sort((a, b) => b[1] - a[1])[0];
    return { over50, over20, gapTotal, topCause };
  }, [summary, factors]);

  const rows = useMemo(() => {
    let out = factors.filter((f) => {
      if (group !== "All" && f.group !== group) return false;
      if (
        search &&
        !(
          f.factor.toLowerCase().includes(search.toLowerCase()) ||
          f.table.toLowerCase().includes(search.toLowerCase())
        )
      )
        return false;
      if (hideLegit) {
        const nonLegit = Object.entries(f.categories || {})
          .filter(([c]) => c !== "Legitimate / not applicable")
          .reduce((s, [, v]) => s + v, 0);
        if (nonLegit === 0) return false;
      }
      return true;
    });
    out = out.slice().sort((a, b) => {
      if (sortMode === "pct_desc")
        return (b.pct_missing ?? -1) - (a.pct_missing ?? -1);
      if (sortMode === "pct_asc")
        return (a.pct_missing ?? 999) - (b.pct_missing ?? 999);
      if (sortMode === "count_desc") return b.total_missing - a.total_missing;
      if (sortMode === "name") return a.factor.localeCompare(b.factor);
      return 0;
    });
    return out;
  }, [factors, group, search, hideLegit, sortMode]);

  const toggleExpanded = (key) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (!active) return null;

  if (error) {
    return (
      <div className="alert alert-danger" style={{ margin: "20px 0" }}>
        {error?.message || "Failed to load scores data coverage"}
      </div>
    );
  }

  return (
    <div>
      <div
        className="flex items-center gap-3"
        style={{ marginBottom: "var(--space-4)" }}
      >
        <div style={{ flex: 1 }}>
          <div className="t-sm muted">
            Which scoring factors are missing data across the universe, and why
            — aggregated by root cause from every{" "}
            <code className="mono t-2xs">*_unavailable_reason</code> column in
            the schema.
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
        <Empty
          title="Loading coverage report…"
          desc="Scanning ~100+ factor columns, this can take 15–20s."
        />
      ) : !summary ? (
        <Empty title="No coverage data" />
      ) : (
        <>
          {/* KPI row */}
          <div
            className="grid grid-4"
            style={{ marginBottom: "var(--space-4)" }}
          >
            <div className="stile">
              <div className="stile-label">Factors Tracked</div>
              <div className="stile-value">{summary.factor_count}</div>
              <div className="stile-sub">across {groups.length} categories</div>
            </div>
            <div className="stile">
              <div className="stile-label">≥50% Missing</div>
              <div className={`stile-value ${kpis.over50 > 0 ? "down" : "up"}`}>
                {kpis.over50}
              </div>
              <div className="stile-sub">
                {kpis.over20} factors ≥ 20% missing
              </div>
            </div>
            <div className="stile">
              <div className="stile-label">Real Gap Instances</div>
              <div className="stile-value">{fmtInt(kpis.gapTotal)}</div>
              <div className="stile-sub">excludes legitimate / N/A</div>
            </div>
            <div className="stile">
              <div className="stile-label">Biggest Cause</div>
              <div className="stile-value" style={{ fontSize: "var(--t-lg)" }}>
                {kpis.topCause?.[0] || "—"}
              </div>
              <div className="stile-sub">
                {kpis.topCause
                  ? `${fmtInt(kpis.topCause[1])} symbol-factor gaps`
                  : ""}
              </div>
            </div>
          </div>

          {/* Top causes bar chart */}
          <div className="card" style={{ marginBottom: "var(--space-4)" }}>
            <div className="card-head">
              <div>
                <div className="card-title">Top Causes of Missing Data</div>
                <div className="card-sub">
                  Total symbol-factor gaps attributed to each root cause, summed
                  across all tracked factors
                </div>
              </div>
            </div>
            <div className="card-body">
              {Object.entries(summary.category_totals || {})
                .sort((a, b) => b[1] - a[1])
                .map(([cat, val], i, arr) => {
                  const max = arr[0][1] || 1;
                  return (
                    <div
                      key={cat}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "220px 1fr 90px",
                        alignItems: "center",
                        gap: "var(--space-3)",
                        padding: "6px 0",
                      }}
                    >
                      <div className="flex items-center gap-2 t-sm">
                        <span
                          className="dot"
                          style={{ background: catColor(cat) }}
                        />
                        {cat}
                      </div>
                      <div className="bar" style={{ height: 10 }}>
                        <div
                          className="bar-fill"
                          style={{
                            width: `${(100 * val) / max}%`,
                            background: catColor(cat),
                          }}
                        />
                      </div>
                      <div className="mono t-sm num muted">{fmtInt(val)}</div>
                    </div>
                  );
                })}
            </div>
          </div>

          {/* Controls */}
          <div
            className="card-pad-sm flex gap-3 items-center"
            style={{ flexWrap: "wrap", marginBottom: "var(--space-2)" }}
          >
            <div style={{ position: "relative", minWidth: 200 }}>
              <Search
                size={14}
                style={{
                  position: "absolute",
                  left: 10,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "var(--text-faint)",
                }}
              />
              <input
                className="input"
                placeholder="Search factor or table…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ paddingLeft: 32 }}
              />
            </div>
            <select
              className="select"
              style={{ width: 160 }}
              value={group}
              onChange={(e) => setGroup(e.target.value)}
            >
              <option value="All">All groups</option>
              {groups.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
            <select
              className="select"
              style={{ width: 220 }}
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value)}
            >
              <option value="pct_desc">Sort: % missing (worst first)</option>
              <option value="pct_asc">Sort: % missing (best first)</option>
              <option value="count_desc">Sort: symbol count</option>
              <option value="name">Sort: factor name</option>
            </select>
            <label
              className="flex items-center gap-2 t-sm muted"
              style={{ marginLeft: "auto", cursor: "pointer" }}
            >
              <input
                type="checkbox"
                checked={hideLegit}
                onChange={(e) => setHideLegit(e.target.checked)}
              />
              Hide legitimate-only rows
            </label>
          </div>

          {/* Legend */}
          <div
            className="flex gap-3 t-xs muted"
            style={{
              flexWrap: "wrap",
              padding: "0 var(--space-2) var(--space-3)",
            }}
          >
            {catOrder.map((cat) => (
              <span key={cat} className="flex items-center gap-2">
                <span className="dot" style={{ background: catColor(cat) }} />
                {cat}
              </span>
            ))}
          </div>

          <div
            className="t-xs faint"
            style={{ padding: "0 var(--space-2) var(--space-2)" }}
          >
            {rows.length} of {factors.length} factors
          </div>

          {/* Coverage table */}
          <div className="card">
            <div
              className="card-body"
              style={{ padding: 0, overflowX: "auto" }}
            >
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 24 }}></th>
                    <th>Factor</th>
                    <th style={{ width: 160 }}>Missing</th>
                    <th>Reason composition</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((f) => {
                    const key = `${f.table}.${f.column}`;
                    const isOpen = expanded.has(key);
                    return (
                      <React.Fragment key={key}>
                        <tr onClick={() => toggleExpanded(key)}>
                          <td>
                            <ChevronRight
                              size={14}
                              style={{
                                transform: isOpen ? "rotate(90deg)" : "none",
                                transition: "transform 140ms",
                                color: isOpen
                                  ? "var(--brand-2)"
                                  : "var(--text-faint)",
                              }}
                            />
                          </td>
                          <td>
                            <div className="dbl">
                              <span className="dbl-main mono t-sm">
                                {f.factor}
                              </span>
                              <span className="dbl-sub">
                                <span
                                  className="badge badge-neutral"
                                  style={{ fontSize: "var(--t-2xs)" }}
                                >
                                  {f.group}
                                </span>
                              </span>
                            </div>
                          </td>
                          <td>
                            <div className="dbl">
                              <span className="dbl-main mono">
                                {f.pct_missing != null
                                  ? `${f.pct_missing}%`
                                  : "—"}
                              </span>
                              <span className="dbl-sub mono">
                                {f.pct_missing != null
                                  ? `${fmtInt(f.total_missing)}/${fmtInt(f.denom)}`
                                  : `${fmtInt(f.total_missing)} rows`}
                              </span>
                            </div>
                            <div className="bar" style={{ marginTop: 4 }}>
                              <div
                                className="bar-fill"
                                style={{
                                  width: `${f.pct_missing != null ? f.pct_missing : Math.min(100, f.total_missing / 20)}%`,
                                }}
                              />
                            </div>
                          </td>
                          <td>
                            <div
                              style={{
                                display: "flex",
                                height: 18,
                                borderRadius: "var(--r-xs)",
                                overflow: "hidden",
                                background: "var(--surface-3)",
                              }}
                            >
                              {catOrder.map((cat) => {
                                const v = f.categories?.[cat];
                                if (!v) return null;
                                return (
                                  <div
                                    key={cat}
                                    title={`${cat}: ${fmtInt(v)}`}
                                    style={{
                                      width: `${(100 * v) / f.total_missing}%`,
                                      background: catColor(cat),
                                    }}
                                  />
                                );
                              })}
                            </div>
                          </td>
                        </tr>
                        {isOpen && (
                          <tr>
                            <td
                              colSpan={4}
                              style={{
                                background: "var(--bg-2)",
                                cursor: "default",
                              }}
                            >
                              {f.reasons.map((r, i) => (
                                <div
                                  key={i}
                                  className="flex items-center gap-3 t-sm"
                                  style={{
                                    padding: "5px 0 5px 34px",
                                    borderBottom:
                                      i < f.reasons.length - 1
                                        ? "1px dashed var(--border-soft)"
                                        : "none",
                                  }}
                                >
                                  <span
                                    className="dot"
                                    style={{ background: catColor(r.category) }}
                                  />
                                  <span
                                    className="mono strong"
                                    style={{ minWidth: 56, textAlign: "right" }}
                                  >
                                    {fmtInt(r.count)}
                                  </span>
                                  <span style={{ flex: 1 }}>{r.reason}</span>
                                  {f.denom && (
                                    <span className="t-2xs faint">
                                      {((100 * r.count) / f.denom).toFixed(1)}%
                                      of table
                                    </span>
                                  )}
                                </div>
                              ))}
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

          <div
            className="t-2xs faint"
            style={{ marginTop: "var(--space-3)", lineHeight: 1.6 }}
          >
            "% missing" is count / distinct symbols in that factor's own table —
            tables have slightly different populations, so this is coverage
            within each factor's table, not always the full universe. Rows with
            no denominator (market-wide tables) show a raw row count instead.
            Source:{" "}
            <code className="mono t-2xs">
              scripts/audit_unavailable_reasons.py
            </code>{" "}
            methodology, served live via{" "}
            <code className="mono t-2xs">/api/algo/scores/coverage</code>.
          </div>
        </>
      )}
    </div>
  );
}

function Empty({ title, desc }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}
