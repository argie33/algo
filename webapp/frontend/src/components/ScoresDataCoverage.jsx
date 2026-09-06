/**
 * ScoresDataCoverage — "which scoring factors are missing data, how much and why, and which
 * upstream source (SEC/Yahoo Finance/FINRA/etc) their data actually comes from"
 * Powers the ServiceHealth "Scores Data Coverage" tab. Pure JSX + theme.css classes,
 * matching ServiceHealth's own convention.
 *
 * Backed by GET /api/algo/scores/coverage (lambda/api/routes/scores.py::_get_scores_coverage),
 * which aggregates every *_unavailable_reason column in the schema (~100+ small grouped-count
 * queries) plus each table's `data_source`/`source_tracking` columns for the source breakdown.
 *
 * FIXED 2026-09-01 (goal session: "this one timing out"): the whole ~100+ query aggregation
 * used to run as one HTTP call, taking 15-20s+ end to end - close enough to api.js's 28s
 * client-side timeout (itself set below API Gateway/Lambda's 30s hard cutoff) that it timed
 * out in practice, even though a one-off script run of the same queries "worked" outside that
 * window. Raising the client timeout doesn't fix this: production Lambda kills the function at
 * 30s regardless of what the client is willing to wait. Fetched here in chunks instead - one
 * cheap `?meta=1` call for the group list, then one `?group=<name>` call per group (bounded
 * concurrency), merged client-side - so every individual request stays well under both limits.
 * Manual-refresh only - not polled on an interval.
 *
 * ADDED 2026-09-02 (goal session: "is this classifying things right, especially for
 * valuation stuff"): each factor now also carries a `scored` flag (scores.py's
 * _UNSCORED_FACTORS) - some tracked fields (EV/EBITDA, PEG, margin of safety, several
 * growth trend/YoY siblings, a couple of stability variants) are computed/stored for
 * display elsewhere but excluded from the live composite formula entirely, so a 100%
 * gap on one of them can never move a stock's score. Surfaced as a "not scored" badge
 * plus a "Hide display-only (unscored) factors" filter, same pattern as the existing
 * "Hide legitimate-only rows" toggle for "Legitimate / not applicable" reasons.
 */
import React, { useMemo, useState } from "react";
import { RefreshCw, ChevronRight, Search } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";
import { extractData } from "../utils/responseNormalizer";

const COVERAGE_URL = "/api/algo/scores/coverage";
const COVERAGE_FETCH_CONCURRENCY = 4;

// Merges the per-group {summary, factors} responses fetched by fetchScoresCoverageChunked
// below into the same single-response shape the rest of this component (and the schema this
// endpoint used to return in one call) expects.
function mergeCoverageChunks(chunks) {
  const factors = [];
  const category_totals = {};
  const source_totals = {};
  const source_labels = {};
  let category_order = [];
  let universe_estimate = 0;

  for (const chunk of chunks) {
    if (!chunk) continue; // a failed group is skipped, not fatal to the whole report
    factors.push(...(chunk.factors || []));
    const s = chunk.summary || {};
    if (s.category_order?.length) category_order = s.category_order;
    for (const [cat, v] of Object.entries(s.category_totals || {})) {
      category_totals[cat] = (category_totals[cat] || 0) + v;
    }
    for (const [label, v] of Object.entries(s.source_totals || {})) {
      source_totals[label] = (source_totals[label] || 0) + v;
    }
    Object.assign(source_labels, s.source_labels || {});
    if (s.universe_estimate) {
      universe_estimate = Math.max(universe_estimate, s.universe_estimate);
    }
  }

  factors.sort((a, b) => (b.pct_missing ?? -1) - (a.pct_missing ?? -1));
  const source_order = Object.keys(source_totals).sort(
    (a, b) => source_totals[b] - source_totals[a]
  );

  return {
    summary: {
      universe_estimate,
      factor_count: factors.length,
      category_order,
      category_totals,
      source_order,
      source_totals,
      source_labels,
    },
    factors,
  };
}

// Fetches the coverage report in per-group chunks instead of one long-running call - see the
// file header comment for why. A bounded worker pool (not Promise.all over every group at
// once) caps how many concurrent connections this puts on the DB.
async function fetchScoresCoverageChunked() {
  const metaResp = await api.get(COVERAGE_URL, { params: { meta: "1" } });
  const { groups = [] } = extractData(metaResp).data || {};
  if (groups.length === 0)
    return { statusCode: 200, summary: null, factors: [] };

  const chunks = new Array(groups.length);
  let next = 0;
  const worker = async () => {
    while (next < groups.length) {
      const i = next++;
      const group = groups[i];
      try {
        const resp = await api.get(COVERAGE_URL, { params: { group } });
        chunks[i] = extractData(resp).data;
      } catch (err) {
        console.warn(
          `[ScoresDataCoverage] group "${group}" failed:`,
          err.message
        );
        chunks[i] = null;
      }
    }
  };
  await Promise.all(
    Array.from(
      { length: Math.min(COVERAGE_FETCH_CONCURRENCY, groups.length) },
      worker
    )
  );

  return { statusCode: 200, ...mergeCoverageChunks(chunks) };
}

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

// Source palette - unlike categories, the set of raw `data_source` strings isn't fixed at the
// frontend (loaders can add new ones; see scores.py::_prettify_source's own "unknown value"
// fallback for the same reasoning on the backend). Colors are assigned by hashing the raw
// source string instead of by position, so a given source always gets the same color
// everywhere on the page without the frontend needing its own copy of every source name.
const SOURCE_PALETTE = [
  "#3987e5",
  "#22ab84",
  "#e2883f",
  "#9085e9",
  "#d9679a",
  "#4fb3bf",
  "#d1a336",
  "#6c9c3f",
  "#e2645f",
  "#7a8aa3",
];
const hashStr = (s) => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
};
// Accepts both raw data_source strings (per-factor breakdowns, e.g. "unavailable") and
// pretty labels (the table-wide summary chart now keys by label - see scores.py's
// 2026-08-23 source_totals fix) so the "no source" bucket stays gray either way.
const sourceColor = (source) => {
  const s = String(source || "").toLowerCase();
  return s === "not_recorded" ||
    s === "none" ||
    s === "unavailable" ||
    s === "not recorded"
    ? "#5b6478"
    : SOURCE_PALETTE[hashStr(source || "") % SOURCE_PALETTE.length];
};

const fmtInt = (n) => Number(n || 0).toLocaleString("en-US");

export default function ScoresDataCoverage({ active }) {
  const { data, loading, error, isFetching, refetch } = useApiQuery(
    ["scores-coverage"],
    fetchScoresCoverageChunked,
    { enabled: active, timeout: 60000, retry: 1 }
  );

  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("All");
  const [sourceFilter, setSourceFilter] = useState("All");
  const [sortMode, setSortMode] = useState("pct_desc");
  const [hideLegit, setHideLegit] = useState(false);
  const [hideUnscored, setHideUnscored] = useState(false);
  const [expanded, setExpanded] = useState(() => new Set());

  const factors = data?.factors || [];
  const summary = data?.summary;
  const catOrder = summary?.category_order || [];
  const catColor = (cat) =>
    CAT_COLORS[catOrder.indexOf(cat)] || "var(--text-faint)";
  const sourceLabels = summary?.source_labels || {};

  const groups = useMemo(
    () => Array.from(new Set(factors.map((f) => f.group))).sort(),
    [factors]
  );

  // Dominant (largest-share) source per factor - used for the filter dropdown and as a quick
  // at-a-glance label; the full per-factor breakdown (all sources, not just the dominant one)
  // is still shown in the table's Sources column and expanded detail.
  const dominantSource = (f) =>
    (f.sources || []).reduce(
      (best, s) => (!best || s.count > best.count ? s : best),
      null
    );

  const sourceOptions = useMemo(
    () =>
      Array.from(
        new Set(factors.map((f) => dominantSource(f)?.label).filter(Boolean))
      ).sort(),
    [factors]
  );

  // A factor's own `scored` flag is missing (older cached response, or a group that
  // hasn't reported yet) means "assume scored" - don't silently mislabel a factor as
  // display-only just because its flag hasn't loaded.
  const isScored = (f) => f.scored !== false;
  const nonLegitCount = (f) =>
    Object.entries(f.categories || {})
      .filter(([c]) => c !== "Legitimate / not applicable")
      .reduce((s, [, v]) => s + v, 0);
  // The number this whole page leads with, per factor: how many symbols have a GENUINE
  // gap, excluding "Legitimate / not applicable" (data known, ratio doesn't apply - e.g.
  // no P/E for a loss-making stock, no PEG for shrinking earnings) from both the count and
  // the percentage entirely. User directive (2026-09-02, the "PEG 78% missing, I'm
  // freaking out" conversation): a row must never LOOK like a big gap when most of it is
  // actually "we know, it just doesn't apply" - that story stays available on expand (the
  // full reasons list below still itemizes every legitimate-N/A reason with its own %), it
  // just isn't allowed to inflate the headline number anymore.
  const realGapCount = (f) => nonLegitCount(f);
  const realGapPct = (f) =>
    f.denom ? Math.round((1000 * realGapCount(f)) / f.denom) / 10 : null;

  // Category totals recomputed here from the merged per-factor `factors` array, scoped to
  // SCORED factors only - deliberately NOT the backend's summary.category_totals, which
  // rolls up every tracked factor regardless of scoring role. A gap on a display-only field
  // (EV/EBITDA, PEG, margin of safety, several growth trend/YoY siblings, a couple of
  // volatility variants - see scores.py's _UNSCORED_FACTORS) can never move a stock's score,
  // so it's excluded from "Real Gap Instances" / "Top Causes" / the ≥50%/≥20% counts the
  // same way "Legitimate / not applicable" already is - otherwise the headline numbers on a
  // tab titled "Scores Data Coverage" keep looking alarming for reasons that have zero
  // scoring impact, which is exactly the "so many missing, is this misleading" confusion
  // this addition exists to fix.
  const scoredCategoryTotals = useMemo(() => {
    const totals = {};
    for (const f of factors) {
      if (!isScored(f)) continue;
      for (const [cat, v] of Object.entries(f.categories || {})) {
        totals[cat] = (totals[cat] || 0) + v;
      }
    }
    return totals;
  }, [factors]);

  const kpis = useMemo(() => {
    if (!summary) return null;
    const over50 = factors.filter(
      (f) => isScored(f) && (realGapPct(f) ?? 0) >= 50
    ).length;
    const over20 = factors.filter(
      (f) => isScored(f) && (realGapPct(f) ?? 0) >= 20
    ).length;
    const gapTotal = Object.entries(scoredCategoryTotals)
      .filter(([c]) => c !== "Legitimate / not applicable")
      .reduce((s, [, v]) => s + v, 0);
    const topCause = Object.entries(scoredCategoryTotals)
      .filter(([c]) => c !== "Legitimate / not applicable")
      .sort((a, b) => b[1] - a[1])[0];
    // How many display-only (unscored) factors ALSO cross the same thresholds, and how
    // much of the full (scored + unscored) universe of gaps they carry - shown as
    // supplementary context, not folded into the headline numbers above.
    const unscoredOver50 = factors.filter(
      (f) => !isScored(f) && (realGapPct(f) ?? 0) >= 50
    ).length;
    const unscoredGapTotal = factors
      .filter((f) => !isScored(f))
      .reduce((s, f) => s + nonLegitCount(f), 0);
    return {
      over50,
      over20,
      gapTotal,
      topCause,
      unscoredGapTotal,
      unscoredOver50,
    };
  }, [summary, factors, scoredCategoryTotals]);

  const rows = useMemo(() => {
    let out = factors.filter((f) => {
      if (group !== "All" && f.group !== group) return false;
      if (
        sourceFilter !== "All" &&
        !(f.sources || []).some((s) => s.label === sourceFilter)
      )
        return false;
      if (
        search &&
        !(
          f.factor.toLowerCase().includes(search.toLowerCase()) ||
          f.table.toLowerCase().includes(search.toLowerCase())
        )
      )
        return false;
      if (hideLegit && nonLegitCount(f) === 0) return false;
      if (hideUnscored && !isScored(f)) return false;
      return true;
    });
    out = out.slice().sort((a, b) => {
      if (sortMode === "pct_desc")
        return (realGapPct(b) ?? -1) - (realGapPct(a) ?? -1);
      if (sortMode === "pct_asc")
        return (realGapPct(a) ?? 999) - (realGapPct(b) ?? 999);
      if (sortMode === "count_desc") return realGapCount(b) - realGapCount(a);
      if (sortMode === "name") return a.factor.localeCompare(b.factor);
      return 0;
    });
    return out;
  }, [factors, group, sourceFilter, search, hideLegit, hideUnscored, sortMode]);

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
            Which scoring factors are missing data across the universe, why —
            aggregated by root cause from every{" "}
            <code className="mono t-2xs">*_unavailable_reason</code> column in
            the schema — and which upstream source (SEC, Yahoo Finance, FINRA,
            ...) each factor's data actually comes from.
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
          desc="Fetching ~100+ factor columns in per-group chunks."
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
              <div className="stile-label">≥50% Data Gap (scored factors)</div>
              <div className={`stile-value ${kpis.over50 > 0 ? "down" : "up"}`}>
                {kpis.over50}
              </div>
              <div className="stile-sub">
                {kpis.over20} factors ≥ 20% data gap
                {kpis.unscoredOver50 > 0 &&
                  ` · +${kpis.unscoredOver50} unscored`}
              </div>
            </div>
            <div className="stile">
              <div className="stile-label">Real Gap Instances</div>
              <div className="stile-value">{fmtInt(kpis.gapTotal)}</div>
              <div className="stile-sub">
                scored factors, excludes legitimate / N/A
                {kpis.unscoredGapTotal > 0 &&
                  ` · ${fmtInt(kpis.unscoredGapTotal)} more on display-only (unscored) factors, not counted here`}
              </div>
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
                  across scored factors only (excludes display-only/unscored
                  fields - see the "not scored" badge below)
                </div>
              </div>
            </div>
            <div className="card-body">
              {Object.entries(scoredCategoryTotals)
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

          {/* Data sources bar chart - which upstream source (SEC, Yahoo Finance, FINRA, ...)
              the tracked factors' data actually comes from, and how much from each. Same
              shape as the Top Causes chart above, over summary.source_totals instead of
              category_totals. */}
          {summary.source_order?.length > 0 && (
            <div className="card" style={{ marginBottom: "var(--space-4)" }}>
              <div className="card-head">
                <div>
                  <div className="card-title">Data Sources</div>
                  <div className="card-sub">
                    Which upstream source each tracked factor's data comes from,
                    summed across all tracked factors (latest row per symbol)
                  </div>
                </div>
              </div>
              <div className="card-body">
                {summary.source_order.map((src, i, arr) => {
                  const val = summary.source_totals[src];
                  const max = summary.source_totals[arr[0]] || 1;
                  return (
                    <div
                      key={src}
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
                          style={{ background: sourceColor(src) }}
                        />
                        {sourceLabels[src] || src}
                      </div>
                      <div className="bar" style={{ height: 10 }}>
                        <div
                          className="bar-fill"
                          style={{
                            width: `${(100 * val) / max}%`,
                            background: sourceColor(src),
                          }}
                        />
                      </div>
                      <div className="mono t-sm num muted">{fmtInt(val)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

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
              style={{ width: 190 }}
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
            >
              <option value="All">All sources</option>
              {sourceOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className="select"
              style={{ width: 220 }}
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value)}
            >
              <option value="pct_desc">Sort: data gap % (worst first)</option>
              <option value="pct_asc">Sort: data gap % (best first)</option>
              <option value="count_desc">Sort: symbol count</option>
              <option value="name">Sort: factor name</option>
            </select>
            <label
              className="flex items-center gap-2 t-sm muted"
              style={{ marginLeft: "auto", cursor: "pointer" }}
            >
              <input
                type="checkbox"
                checked={hideUnscored}
                onChange={(e) => setHideUnscored(e.target.checked)}
              />
              Hide display-only (unscored) factors
            </label>
            <label
              className="flex items-center gap-2 t-sm muted"
              style={{ cursor: "pointer" }}
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
          {summary.source_order?.length > 0 && (
            <div
              className="flex gap-3 t-xs muted"
              style={{
                flexWrap: "wrap",
                padding: "0 var(--space-2) var(--space-3)",
              }}
            >
              <span className="t-2xs faint">Sources:</span>
              {summary.source_order.map((src) => (
                <span key={src} className="flex items-center gap-2">
                  <span
                    className="dot"
                    style={{ background: sourceColor(src) }}
                  />
                  {sourceLabels[src] || src}
                </span>
              ))}
            </div>
          )}

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
                    <th style={{ width: 160 }}>Data Gap</th>
                    <th style={{ width: 160 }}>Sources</th>
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
                                {!isScored(f) && (
                                  <span
                                    className="badge"
                                    title="Computed and displayed elsewhere (e.g. Deep Value page) but not read by the live composite scoring formula - a gap here can't move a stock's score."
                                    style={{
                                      fontSize: "var(--t-2xs)",
                                      marginLeft: 4,
                                      color: "var(--text-faint)",
                                      border: "1px solid var(--border-soft)",
                                    }}
                                  >
                                    not scored
                                  </span>
                                )}
                              </span>
                            </div>
                          </td>
                          <td>
                            <div className="dbl">
                              <span className="dbl-main mono">
                                {realGapPct(f) != null
                                  ? `${realGapPct(f)}%`
                                  : "—"}
                              </span>
                              <span className="dbl-sub mono">
                                {realGapPct(f) != null
                                  ? `${fmtInt(realGapCount(f))}/${fmtInt(f.denom)}`
                                  : `${fmtInt(realGapCount(f))} rows`}
                              </span>
                            </div>
                            <div className="bar" style={{ marginTop: 4 }}>
                              <div
                                className="bar-fill"
                                style={{
                                  width: `${realGapPct(f) != null ? realGapPct(f) : Math.min(100, realGapCount(f) / 20)}%`,
                                }}
                              />
                            </div>
                          </td>
                          <td>
                            {f.sources?.length ? (
                              <div
                                title={f.sources
                                  .map((s) => `${s.label}: ${s.pct}%`)
                                  .join(" · ")}
                                style={{
                                  display: "flex",
                                  height: 18,
                                  borderRadius: "var(--r-xs)",
                                  overflow: "hidden",
                                  background: "var(--surface-3)",
                                }}
                              >
                                {f.sources.map((s) => (
                                  <div
                                    key={s.source}
                                    style={{
                                      width: `${s.pct}%`,
                                      background: sourceColor(s.source),
                                    }}
                                  />
                                ))}
                              </div>
                            ) : (
                              <span className="t-2xs faint">Not tracked</span>
                            )}
                          </td>
                          <td>
                            {realGapCount(f) > 0 ? (
                              <div
                                style={{
                                  display: "flex",
                                  height: 18,
                                  borderRadius: "var(--r-xs)",
                                  overflow: "hidden",
                                  background: "var(--surface-3)",
                                }}
                              >
                                {catOrder
                                  .filter(
                                    (cat) =>
                                      cat !== "Legitimate / not applicable"
                                  )
                                  .map((cat) => {
                                    const v = f.categories?.[cat];
                                    if (!v) return null;
                                    return (
                                      <div
                                        key={cat}
                                        title={`${cat}: ${fmtInt(v)}`}
                                        style={{
                                          width: `${(100 * v) / realGapCount(f)}%`,
                                          background: catColor(cat),
                                        }}
                                      />
                                    );
                                  })}
                              </div>
                            ) : (
                              <span className="t-2xs faint">
                                {(f.categories?.[
                                  "Legitimate / not applicable"
                                ] ?? 0) > 0
                                  ? "N/A only (see expand)"
                                  : "—"}
                              </span>
                            )}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr>
                            <td
                              colSpan={5}
                              style={{
                                background: "var(--bg-2)",
                                cursor: "default",
                              }}
                            >
                              {f.sources?.length > 0 && (
                                <div
                                  style={{
                                    padding: "8px 0 8px 34px",
                                    borderBottom:
                                      "1px solid var(--border-soft)",
                                  }}
                                >
                                  <div
                                    className="t-2xs faint"
                                    style={{ marginBottom: 4 }}
                                  >
                                    Data sources
                                  </div>
                                  {f.sources.map((s) => (
                                    <div
                                      key={s.source}
                                      className="flex items-center gap-3 t-sm"
                                      style={{ padding: "3px 0" }}
                                    >
                                      <span
                                        className="dot"
                                        style={{
                                          background: sourceColor(s.source),
                                        }}
                                      />
                                      <span
                                        className="mono strong"
                                        style={{
                                          minWidth: 56,
                                          textAlign: "right",
                                        }}
                                      >
                                        {fmtInt(s.count)}
                                      </span>
                                      <span style={{ flex: 1 }}>{s.label}</span>
                                      <span className="t-2xs faint">
                                        {s.pct}%
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              )}
                              <div
                                style={{
                                  paddingTop: f.sources?.length ? 4 : 0,
                                }}
                              >
                                {f.sources?.length > 0 && (
                                  <div
                                    className="t-2xs faint"
                                    style={{ padding: "4px 0 4px 34px" }}
                                  >
                                    Issues
                                  </div>
                                )}
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
                                      style={{
                                        background: catColor(r.category),
                                      }}
                                    />
                                    <span
                                      className="mono strong"
                                      style={{
                                        minWidth: 56,
                                        textAlign: "right",
                                      }}
                                    >
                                      {fmtInt(r.count)}
                                    </span>
                                    <span style={{ flex: 1 }}>{r.reason}</span>
                                    {f.denom && (
                                      <span className="t-2xs faint">
                                        {((100 * r.count) / f.denom).toFixed(1)}
                                        % of table
                                      </span>
                                    )}
                                  </div>
                                ))}
                              </div>
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
            "Data Gap %" is genuinely-missing count / distinct symbols in that
            factor's own table — it deliberately EXCLUDES "Legitimate / not
            applicable" cases (the underlying data is known and real, e.g. a
            company's actual negative EPS, but the ratio itself doesn't exist
            for that company - same idea as a stock having no dividend yield
            because it pays no dividend). Those aren't a gap in what we know, so
            they no longer count toward this number or the reason composition
            bar — expand a row to see them itemized in the full reasons list,
            each with its own share of the table. Tables have slightly different
            populations, so this is coverage within each factor's own table, not
            always the full universe; rows with no denominator (market-wide
            tables) show a raw row count instead. A "not scored" badge means the
            field is computed and shown elsewhere (e.g. the Deep Value page) but
            the live composite scoring formula doesn't read it — closing that
            gap can't move a stock's score. The Sources column reads each
            table's own <code className="mono t-2xs">data_source</code>
            {" / "}
            <code className="mono t-2xs">source_tracking</code> column where
            present — "Not tracked" means the table doesn't record per-row
            provenance, not that the data is missing. Source:{" "}
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
