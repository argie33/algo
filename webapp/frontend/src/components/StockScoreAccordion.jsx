import React, { useState, useEffect } from "react";
import {
  Star,
  Activity,
  DollarSign,
  TrendingUp,
  Shield,
  Inbox,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { formatNumber, formatPercentageChange } from "../utils/formatters";
import { api } from "../services/api";

const num = (v, dp = 1) => formatNumber(v, dp);
const pct = (v, dp = 2) => formatPercentageChange(v, dp);

const scoreClass = (v) => {
  if (v == null || isNaN(Number(v))) return "badge";
  const n = Number(v);
  if (n >= 80) return "badge-success";
  if (n >= 60) return "badge-cyan";
  if (n >= 40) return "badge-amber";
  return "badge-danger";
};

// Sub-factor scores use a looser band than composite scores (matches the CLI
// dashboard's _score_cell 70/50/30 vs _composite_score_color 80/60/40 split —
// composite is a weighted aggregate that clusters higher, individual factors
// vary more).
const scoreColor = (v) => {
  if (v == null || isNaN(Number(v))) return "var(--text-faint)";
  const n = Number(v);
  if (n >= 70) return "var(--success)";
  if (n >= 50) return "var(--cyan)";
  if (n >= 30) return "var(--amber)";
  return "var(--danger)";
};

const grade = (v) => {
  if (v == null) return "—";
  const n = Number(v);
  if (n >= 90) return "A+";
  if (n >= 85) return "A";
  if (n >= 80) return "A-";
  if (n >= 75) return "B+";
  if (n >= 70) return "B";
  if (n >= 65) return "B-";
  if (n >= 60) return "C+";
  if (n >= 55) return "C";
  if (n >= 50) return "C-";
  if (n >= 45) return "D+";
  if (n >= 40) return "D";
  return "F";
};

const formatReasonDisplay = (reason) => {
  if (!reason) return null;
  const reasonMap = {
    missing_sec_data: "SEC data not available",
    insufficient_history: "Insufficient history",
    insufficient_year_over_year_quarterly_history:
      "Needs 2 years of quarterly filings (year-over-year comparison)",
    no_analyst_estimates: "Analyst estimates unavailable",
    analyst_estimates_not_in_sec_filings: "Analyst data not in SEC",
    ebitda_not_extracted: "EBITDA not extracted",
    depreciation_amortization_not_loaded:
      "Depreciation/amortization not loaded",
    non_dividend_paying_stock: "Non-dividend payer",
    api_error: "Data fetch error",
    unprofitable_stock: "Company unprofitable",
    missing_price_or_shares: "Missing price/shares",
    missing_finra_data: "FINRA data unavailable",
    missing_price_data: "Price data unavailable",
    institutional_data_not_available: "Institutional data not available",
    no_resolved_13f_holdings: "No 13F filer reported holding this stock",
    shares_outstanding_unavailable: "Shares outstanding unavailable",
    not_found_in_institutional_holdings_13f: "Not found in 13F filings",
    short_float_data_not_calculated: "Short float metrics not calculated",
    ad_rating_not_available: "A/D rating not available",
    no_dividend_paying_stock: "Non-dividend payer",
    reit_special_entity: "REIT/bank/insurer - different accounting",
    interest_expense_not_itemized: "Interest expense not itemized",
    total_debt_not_itemized: "No debt reported (or not itemized)",
    no_revenue_reported: "Pre-revenue company",
    stockholders_equity_not_reported: "Shareholders' equity not reported",
    foreign_20f_filer: "Foreign 20-F filer - XBRL data limited",
    bank_special_reporting: "Financial institution - alternative metrics",
    insufficient_prior_year_data: "Prior fiscal year data unavailable",
    no_segment_disclosure: "Single-segment filer",
    insufficient_quarterly_history: "Fewer than 4 quarters of history",
    insufficient_quarterly_data: "Quarterly data unavailable",
    insufficient_eps_data: "EPS data missing for recent quarters",
    insufficient_revenue_data: "Revenue data missing for recent quarters",
    insufficient_eps_growth_datapoints:
      "Not enough EPS comparisons for a trend",
    growth_undefined_sign_change: "Growth undefined (profit/loss swing)",
    implausible_ratio: "Value excluded as implausible",
    negative_free_cash_flow: "Company burned cash (negative FCF)",
    missing_cash_flow_data: "Cash flow data unavailable",
    implausible_dcf_result: "Value excluded as implausible",
    negative_earnings_growth: "Earnings growth declining or negative",
    negative_book_value: "Negative shareholders' equity",
    negative_invested_capital: "Negative invested capital",
    stale_fiscal_data: "Latest SEC filing too old",
  };
  return reasonMap[reason] || reason;
};

// Detailed reason tooltips (hover text)
const reasonTooltips = {
  missing_sec_data:
    "This metric requires SEC filing data that is not available for this company type",
  non_dividend_paying_stock: "This company does not pay dividends",
  insufficient_history:
    "Requires historical data for calculation (typically 2+ years)",
  insufficient_year_over_year_quarterly_history:
    "This metric compares each of the last 4 quarters to the same quarter a year ago (to avoid seasonal noise), which needs 8 quarters of filing history - fewer quarters, or a gap in the filing history, leaves no matched pair to compare",
  no_analyst_estimates:
    "External analyst estimates not loaded from data providers",
  unprofitable_stock: "Metric is undefined when company has negative earnings",
  missing_price_data: "Historical price data not yet available",
  institutional_data_not_available:
    "Institutional holding data not available for this stock",
  no_resolved_13f_holdings:
    "No institutional 13F filer currently reports holding this stock - either genuinely low institutional ownership, or the filer's CUSIP hasn't been matched to this ticker yet",
  shares_outstanding_unavailable:
    "Institutional ownership percentage requires shares outstanding, which isn't available for this stock",
  not_found_in_institutional_holdings_13f:
    "This stock hasn't been processed by the 13F institutional-ownership pipeline yet",
  reit_special_entity:
    "REITs, banks, and insurers report an unclassified balance sheet (no current/non-current split) or omit gross profit as a permanent feature of their accounting model, not a data gap - traditional ratio metrics don't apply",
  interest_expense_not_itemized:
    "This company hasn't reported interest expense as its own line item in its 3 most recent fiscal years - either it carries no debt, or it nets interest into other income/expense instead of breaking it out, not a data extraction gap",
  total_debt_not_itemized:
    "This company hasn't reported any debt line item (long-term debt, short-term debt, or lease liabilities) in its 3 most recent fiscal years - most likely it simply carries no debt, not a data extraction gap",
  no_revenue_reported:
    "This company hasn't reported revenue in its 3 most recent fiscal years - typically a SPAC or a pre-revenue clinical-stage company, not a data extraction gap",
  stockholders_equity_not_reported:
    "This company hasn't reported shareholders' equity as its own line item in its 3 most recent fiscal years, not a data extraction gap",
  foreign_20f_filer:
    "Foreign companies filing 20-F use different XBRL data structure; full metrics extraction limited",
  bank_special_reporting:
    "Banks and financial institutions use specialized accounting; different metrics apply",
  insufficient_prior_year_data:
    "This company's prior fiscal year filing doesn't report the comparison figure needed for this trend/growth calculation",
  growth_undefined_sign_change:
    "This company's earnings switched between profit and loss across the comparison period - a compound annual growth rate is not mathematically meaningful across a sign change, regardless of how much history is available",
  implausible_ratio:
    "The underlying data is present but produces a ratio far outside plausible bounds (e.g. a near-zero denominator or reporting inconsistency), so it was excluded rather than shown as a misleading number",
  negative_free_cash_flow:
    "This company had negative free cash flow (operating cash flow minus capital expenditures) in its most recent fiscal year - a discounted cash flow valuation isn't meaningful for a company burning cash, so no intrinsic value is shown rather than a misleading negative one",
  missing_cash_flow_data:
    "Operating cash flow or capital expenditure data required for this calculation is not available in SEC filings for this company",
  implausible_dcf_result:
    "The discounted cash flow model produced a per-share value far outside plausible bounds, so it was excluded rather than shown as a misleading number",
  negative_earnings_growth:
    "This company's earnings declined or went negative year-over-year, so a PEG ratio (which divides by earnings growth) is not meaningful",
  negative_book_value:
    "This company reports negative shareholders' equity (liabilities exceed assets - common after heavy share buybacks or an accumulated deficit), so price-to-book is not meaningful",
  negative_invested_capital:
    "This company's invested capital (equity plus debt minus cash) is zero or negative, so return on invested capital is not meaningful",
  stale_fiscal_data:
    "This company's most recent balance sheet on file is more than 3 years old (it may have stopped filing, been acquired, or gone private) - the underlying figures may be real but are too outdated to trust for a current ratio, so they're excluded rather than shown as current",
};

const FACTORS = [
  { key: "quality", label: "Quality", scoreKey: "quality_score", icon: Star },
  {
    key: "momentum",
    label: "Momentum",
    scoreKey: "momentum_score",
    icon: Activity,
  },
  { key: "value", label: "Value", scoreKey: "value_score", icon: DollarSign },
  {
    key: "growth",
    label: "Growth",
    scoreKey: "growth_score",
    icon: TrendingUp,
  },
  {
    key: "risk",
    // LABEL RENAMED 2026-08-28 (user directive): "Risk" -> "Safety". This score is
    // higher-is-better (low volatility/beta-near-1/shallow drawdowns = high score), so
    // "Risk" reads backwards to anyone scanning the page ("high Risk" sounds bad, but here
    // it means the opposite - low actual risk). This is the second naming flip on this
    // pillar: it was originally "Stability" (also higher-is-better, also intuitive) until a
    // 2026-08-26 user directive renamed it to "Risk" - see _score_risk's docstring in
    // loaders/load_stock_scores.py. Display label only: `key`/`scoreKey` below are
    // unchanged (still "risk"/"risk_score", matching the live risk_score DB column, the
    // risk_inputs API payload key, and _score_risk in the loader) - renaming those would be
    // a much larger, higher-risk cascade (migrations, API contract, loader, every test/
    // memory reference to "risk_score") for what was asked as a display-naming fix.
    label: "Safety",
    scoreKey: "risk_score",
    icon: Shield,
  },
];

// Composite pillar weights - single source of truth for the top-level composite_score mix.
// MUST match loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS exactly -
// tests/unit/test_scores_frontend_weight_badges_match_backend.py verifies this. Positioning
// and Size are retired composite pillars (informational-only tabs below, not part of
// composite_score) and have no entry here.
const PILLAR_COMPOSITE_WEIGHTS = {
  quality: 0.2,
  growth: 0.24,
  value: 0.27,
  risk: 0.19,
  momentum: 0.1,
};

// ─── Empty state ────────────────────────────────────────────────────────────
function Empty({ title, desc }) {
  return (
    <div className="empty">
      <Inbox size={24} />
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}

// ─── recent trading signals for a stock ────────────────────────────────────
const SignalsForStock = ({ symbol }) => {
  const [signals, setSignals] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .get(`/api/signals/stocks?symbol=${symbol}&limit=10&timeframe=daily`)
      .then((res) => {
        setSignals(res.data?.items || []);
      })
      .catch((err) => {
        setError(err?.message || "Failed to load signals");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [symbol]);

  return (
    <div className="card">
      <div className="card-body" style={{ padding: 0 }}>
        {loading ? (
          <Empty title="Loading signals…" />
        ) : error ? (
          <div
            className="t-xs"
            style={{ color: "var(--danger)", padding: "var(--space-3)" }}
          >
            {error}
          </div>
        ) : !signals || signals.length === 0 ? (
          <Empty title="No recent trading signals" />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Date</th>
                  <th style={{ width: 60 }}>Signal</th>
                  <th className="num" style={{ width: 70 }}>
                    Score
                  </th>
                  <th style={{ width: 60 }}>Grade</th>
                  <th style={{ width: 100 }}>Gates</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, idx) => (
                  <tr key={`${sig.symbol}-${sig.date}-${idx}`}>
                    <td className="t-xs muted">
                      {sig.date ? new Date(sig.date).toLocaleDateString() : "—"}
                    </td>
                    <td>
                      <span
                        className={`badge ${sig.signal === "BUY" ? "badge-success" : "badge-danger"}`}
                      >
                        {sig.signal || "—"}
                      </span>
                    </td>
                    <td className="num t-xs">
                      {sig.entry_quality_score != null
                        ? formatNumber(sig.entry_quality_score, 1)
                        : "—"}
                    </td>
                    <td className="t-xs">{sig.grade || "—"}</td>
                    <td className="t-xs">
                      {sig.pass_gates ? (
                        <span className="badge badge-success">Pass</span>
                      ) : (
                        <span className="badge badge-danger">Fail</span>
                      )}
                    </td>
                    <td className="t-xs muted">{sig.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── composite score / rank history (stock_scores_history, one snapshot per
// trading day - see loaders/load_stock_scores.py's snapshot_score_history()) ──
const ScoreHistoryForStock = ({ symbol }) => {
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api
      .get(`/api/scores/history/${symbol}?days=90`)
      .then((res) => {
        setHistory(res.data || null);
      })
      .catch(() => {
        setHistory(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [symbol]);

  // Fewer than 2 snapshots means there's nothing to plot a trend from yet
  // (a stock new to scoring, or the feature's first day) - omit rather than
  // show an empty/misleading chart.
  if (
    loading ||
    !history ||
    !Array.isArray(history.points) ||
    history.points.length < 2
  ) {
    return null;
  }

  const chartData = history.points.map((p) => ({
    date: p.score_date,
    score: p.composite_score != null ? Number(p.composite_score) : null,
    rank: p.composite_rank,
  }));

  const { movement } = history;
  const scoreUp = movement.score_change != null && movement.score_change > 0;
  const rankImproved = movement.rank_change != null && movement.rank_change > 0;

  return (
    <div className="card" style={{ marginBottom: "var(--space-5)" }}>
      <div className="card-head flex items-center gap-2">
        <div
          className="card-title"
          style={{
            fontSize: "var(--t-xs)",
            textTransform: "uppercase",
            letterSpacing: "0.3px",
          }}
        >
          Score &amp; Rank History
        </div>
        <span className="t-2xs muted">since {movement.start_date || "—"}</span>
        <div className="flex gap-2" style={{ marginLeft: "auto" }}>
          {movement.score_change != null && (
            <span
              className={`badge ${scoreUp ? "badge-success" : movement.score_change < 0 ? "badge-danger" : ""}`}
            >
              Score {scoreUp ? "+" : ""}
              {num(movement.score_change, 1)}
            </span>
          )}
          {movement.rank_change != null && movement.rank_change !== 0 && (
            <span
              className={`badge ${rankImproved ? "badge-success" : "badge-danger"}`}
            >
              Rank {rankImproved ? "▲" : "▼"} {Math.abs(movement.rank_change)}
            </span>
          )}
        </div>
      </div>
      <div className="card-body" style={{ padding: "var(--space-3)" }}>
        <ResponsiveContainer width="100%" height={140}>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 10, left: 0, bottom: 0 }}
          >
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis domain={[0, 100]} width={30} tick={{ fontSize: 10 }} />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(0,0,0,0.9)",
                border: "1px solid #666",
                borderRadius: 4,
                color: "#fff",
              }}
              labelStyle={{ color: "#fff" }}
              formatter={(value) => [value, "Composite Score"]}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="#4FC3F7"
              strokeWidth={2}
              dot={false}
              name="Composite Score"
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// ─── factor score summary card ─────────────────────────────────────────────
function FactorCard({ factor, stock, sectorAvg, marketAvg }) {
  const Icon = factor.icon;
  const score = stock[factor.scoreKey];
  const diff = (avg) => {
    if (score == null || avg == null) return null;
    const d = Number(score) - Number(avg);
    return `${d >= 0 ? "+" : ""}${num(d, 1)}`;
  };

  return (
    <div className="card" style={{ background: "var(--surface-2)" }}>
      <div className="card-body">
        <div
          className="flex items-center gap-2"
          style={{ marginBottom: "var(--space-3)" }}
        >
          <Icon size={15} style={{ color: scoreColor(score) }} />
          <span
            style={{
              fontWeight: "var(--w-semibold)",
              fontSize: "var(--t-xs)",
              textTransform: "uppercase",
              letterSpacing: "0.3px",
            }}
          >
            {factor.label}
          </span>
          <span
            className={`badge ${scoreClass(score)}`}
            style={{ marginLeft: "auto" }}
          >
            {num(score, 1)}
          </span>
        </div>
        <div className="flex flex-col" style={{ gap: 4 }}>
          <div className="flex" style={{ fontSize: "var(--t-2xs)" }}>
            <span className="muted" style={{ minWidth: 80 }}>
              Sector avg
            </span>
            <span className="mono tnum" style={{ flex: 1, textAlign: "right" }}>
              {sectorAvg != null
                ? `${num(sectorAvg, 1)} (${diff(sectorAvg)})`
                : "—"}
            </span>
          </div>
          <div className="flex" style={{ fontSize: "var(--t-2xs)" }}>
            <span className="muted" style={{ minWidth: 80 }}>
              Market avg
            </span>
            <span className="mono tnum" style={{ flex: 1, textAlign: "right" }}>
              {marketAvg != null
                ? `${num(marketAvg, 1)} (${diff(marketAvg)})`
                : "—"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Parses the leading "NN%" or "NN.N%" out of a within-pillar weight display string (e.g.
// "~11%", "37% avg", "45%") - returns null if the string has no parseable percentage (e.g. a
// non-numeric badge like "fallback"). Used only to DERIVE the composite-level contribution,
// never to re-store a duplicate literal - the pillar-level % stays single-sourced in each
// SCHEMA array above, exactly as it always has.
function _parsePctWeight(weight) {
  const m = typeof weight === "string" ? weight.match(/(\d+(?:\.\d+)?)%/) : null;
  return m ? parseFloat(m[1]) : null;
}

// ─── one row of a factor-inputs table ──────────────────────────────────────
// tier: "used" (feeds the score formula), "tracked" (collected, not scored)
// weight: display string for "used" rows, e.g. "35%", "avg", "fallback"
// collected: false means this column is essentially never populated system-wide
//   (verified against live DB, not just this stock) — rendered as "Not yet available"
//   rather than the ambiguous "No data" used for a per-stock null.
// compositePct: this row's share of the FULL composite_score (pillarWeight * within-pillar
//   weight), e.g. Quality's ROE at ~11% inside a 20%-weighted Quality pillar = ~2.2% of the
//   composite - only set (by InputsCard below) for pillars that actually feed the composite.
function InputRow({ row }) {
  const hasValue = row.value != null;
  const reason = row.reason;
  const reasonDisplay = formatReasonDisplay(reason);

  // DIAGNOSTIC: Log when reason field doesn't display but should
  if (!hasValue && !reason && typeof reason !== "string" && reason !== false) {
    if (
      row.key &&
      row.key !== "consecutive_positive_quarters" &&
      row.key !== "price_vs_52w_high"
    ) {
      // Only log once per unique key to avoid spam
      const logKey = `no_reason_${row.key}`;
      if (!window._inputRowLogCache) window._inputRowLogCache = {};
      if (!window._inputRowLogCache[logKey]) {
        window._inputRowLogCache[logKey] = true;
        console.debug(
          `[InputRow] No value/reason for ${row.key}, reason=${reason}, collected=${row.collected}`
        );
      }
    }
  }

  return (
    <tr>
      <td className="t-xs" title={row.note || undefined}>
        {row.label}
        {row.weight && (
          <span
            className="badge badge-cyan"
            style={{ marginLeft: 6, fontSize: "0.62rem", padding: "1px 5px" }}
            title="Weight within this factor score"
          >
            {row.weight}
          </span>
        )}
        {row.compositePct != null && (
          <span
            className="badge"
            style={{
              marginLeft: 4,
              fontSize: "0.62rem",
              padding: "1px 5px",
              color: "var(--text-faint)",
              border: "1px solid var(--border)",
            }}
            title="Effective share of the full composite score (factor weight x this factor's own weight)"
          >
            {row.compositePct}% of composite
          </span>
        )}
      </td>
      <td className="num mono tnum t-xs">
        {hasValue ? (
          row.fmt(row.value)
        ) : reasonDisplay ? (
          <span className="muted" title={reasonTooltips[reason] || reason}>
            {reasonDisplay}
          </span>
        ) : row.collected === false ? (
          <span className="badge badge-amber" style={{ fontSize: "0.65rem" }}>
            Not yet available
          </span>
        ) : (
          <span
            className="muted"
            title="Data tracked but missing for this stock"
          >
            No data
          </span>
        )}
      </td>
    </tr>
  );
}

// ─── factor inputs card — every remaining field is a real weighted score
// input (20260816 second pass removed all unweighted reference-only fields) ─
// pillarWeight: this factor's own share of composite_score (PILLAR_COMPOSITE_WEIGHTS[key]),
//   e.g. 0.20 for Quality - omitted for Positioning/Size, which are informational-only tabs
//   with no composite_score contribution at all, so no "% of composite" badge is shown there.
function InputsCard({ title, stock, schema, inputsKey = null, pillarWeight = null }) {
  const inputsObj = inputsKey ? stock?.[inputsKey] : stock;

  // DIAGNOSTIC: Log if inputsObj is missing (helps debug "No data" issues)
  if (!inputsObj && inputsKey) {
    console.warn(
      `[InputsCard] Missing factor inputs for ${inputsKey} on ${stock?.symbol || "unknown"}. Stock keys: ${stock ? Object.keys(stock).slice(0, 10).join(", ") : "N/A"}`
    );
  }

  const rows = schema.map((s) => {
    const value = inputsObj?.[s.key];
    const reason = inputsObj?.[s.key + "_unavailable_reason"];
    // DIAGNOSTIC: Log missing reason fields that have null values
    if (!value && !reason && inputsObj) {
      console.debug(
        `[InputsCard] No reason for ${s.key} on ${stock?.symbol || "unknown"}`
      );
    }
    const withinPillarPct = s.used ? _parsePctWeight(s.weight) : null;
    const compositePct =
      pillarWeight != null && withinPillarPct != null
        ? Math.round(withinPillarPct * pillarWeight * 10) / 10
        : null;
    return { ...s, value, reason, compositePct };
  });

  return (
    <div className="card">
      <div className="card-head">
        <div
          className="card-title"
          style={{
            fontSize: "var(--t-xs)",
            textTransform: "uppercase",
            letterSpacing: "0.3px",
          }}
        >
          {title}
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <table className="data-table">
          <tbody>
            {rows.map((r) => (
              <InputRow key={r.key} row={r} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── single stock detail (matches TradingSignals' SignalDetail styling) ────
function StockDetail({ stock, marketAvgs, sectorAvgs }) {
  return (
    <div>
      {/* Overview / meta bar */}
      <div
        className="flex gap-3 items-center"
        style={{ marginBottom: "var(--space-4)", flexWrap: "wrap" }}
      >
        <span className={`badge badge-lg ${scoreClass(stock.composite_score)}`}>
          Grade {grade(stock.composite_score)}
        </span>
        {stock.industry && <span className="t-xs muted">{stock.industry}</span>}
        {stock.data_completeness != null && (
          <span className="t-xs muted">
            Data completeness {num(stock.data_completeness, 0)}%
          </span>
        )}
        {stock.rs_percentile != null && (
          <span className="t-xs muted">
            RS percentile {num(stock.rs_percentile, 0)}
          </span>
        )}
        {stock.last_updated && (
          <span className="t-xs muted" style={{ marginLeft: "auto" }}>
            Updated {new Date(stock.last_updated).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Composite score / rank trend */}
      <ScoreHistoryForStock symbol={stock.symbol} />

      {/* Factor scores vs sector/market */}
      <div className="eyebrow" style={{ marginBottom: "var(--space-2)" }}>
        Factor Scores vs Sector &amp; Market
      </div>
      <div
        className="grid grid-3 gap-3"
        style={{ marginBottom: "var(--space-5)" }}
      >
        {FACTORS.map((f) => (
          <FactorCard
            key={f.key}
            factor={f}
            stock={stock}
            sectorAvg={sectorAvgs?.[f.key]}
            marketAvg={marketAvgs?.[f.key]}
          />
        ))}
      </div>

      {/* Detailed factor inputs */}
      <div className="eyebrow" style={{ marginBottom: "var(--space-1)" }}>
        Detailed Factor Inputs
      </div>
      <div className="t-2xs muted" style={{ marginBottom: "var(--space-2)" }}>
        <div style={{ marginBottom: "var(--space-1)" }}>
          <strong>Legend:</strong>
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong>Cyan tag</strong> = weight within this factor's own score
          (e.g. Quality, Value)
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong>Outlined tag</strong> = that input's effective share of
          the full composite score (factor weight × its weight within the
          factor) - Positioning and Size don't feed the composite, so they
          have no outlined tag
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong style={{ color: "var(--success)" }}>Value</strong> = data
          available for this stock
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong style={{ color: "var(--text-faint)" }}>No SEC data</strong>{" "}
          = SEC doesn't require this disclosure for all company types
        </div>
        <div style={{ marginBottom: "4px" }}>
          •{" "}
          <strong style={{ color: "var(--text-faint)" }}>
            Non-dividend payer
          </strong>{" "}
          = stock characteristic, not a data gap
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong style={{ color: "var(--text-faint)" }}>No data</strong> =
          metric tracked but missing for this stock
        </div>
        <div>
          •{" "}
          <strong
            className="badge badge-amber"
            style={{ fontSize: "0.65rem", padding: "1px 3px" }}
          >
            Not yet available
          </strong>{" "}
          = system-wide gap (no stock has this yet)
        </div>
      </div>
      <div
        className="grid grid-3 gap-3"
        style={{ marginBottom: "var(--space-5)" }}
      >
        <InputsCard
          title="Quality & Fundamentals"
          stock={stock}
          schema={QUALITY_SCHEMA}
          inputsKey="quality_inputs"
          pillarWeight={PILLAR_COMPOSITE_WEIGHTS.quality}
        />
        <InputsCard
          title="Momentum"
          stock={stock}
          schema={MOMENTUM_SCHEMA}
          inputsKey="momentum_inputs"
          pillarWeight={PILLAR_COMPOSITE_WEIGHTS.momentum}
        />
        <InputsCard
          title="Value"
          stock={stock}
          schema={VALUE_SCHEMA}
          inputsKey="value_inputs"
          pillarWeight={PILLAR_COMPOSITE_WEIGHTS.value}
        />
        <InputsCard
          title="Growth"
          stock={stock}
          schema={GROWTH_SCHEMA}
          inputsKey="growth_inputs"
          pillarWeight={PILLAR_COMPOSITE_WEIGHTS.growth}
        />
        <InputsCard
          title="Positioning (informational)"
          stock={stock}
          schema={POSITIONING_SCHEMA}
          inputsKey="positioning_inputs"
        />
        <InputsCard
          title="Safety"
          stock={stock}
          schema={RISK_SCHEMA}
          inputsKey="risk_inputs"
          pillarWeight={PILLAR_COMPOSITE_WEIGHTS.risk}
        />
      </div>

      {/* Recent trading signals */}
      <div className="eyebrow" style={{ marginBottom: "var(--space-2)" }}>
        Recent Trading Signals
      </div>
      <SignalsForStock symbol={stock.symbol} />
    </div>
  );
}

const StockScoreAccordion = ({
  stocks = [],
  marketAvgs = {},
  sectorAvgs = {},
}) => {
  if (!stocks || stocks.length === 0) {
    return <Empty title="No stock scores data found" />;
  }

  return (
    <div className="flex flex-col" style={{ gap: "var(--space-6)" }}>
      {stocks.map((stock, index) => (
        <StockDetail
          key={`${stock.symbol}-${index}`}
          stock={stock}
          marketAvgs={marketAvgs}
          sectorAvgs={sectorAvgs}
        />
      ))}
    </div>
  );
};

export default StockScoreAccordion;
export { QUALITY_SCHEMA, RISK_SCHEMA, PILLAR_COMPOSITE_WEIGHTS };

// ─── Input Schemas ──────────────────────────────────────────────────────────
// Ground-truthed against loaders/load_stock_scores.py and
// loaders/load_value_quality_growth_metrics.py (the actual scoring formulas),
// plus a live-DB column-population audit (2026-07-20, refreshed 2026-08-03) to
// flag fields that are queried/displayed but essentially never populated for
// any stock ("not yet available" rather than an ordinary per-stock null).
// 2026-08-03: wired forward_pe/ev_ebitda/ev_revenue (value), net_income_growth_yoy/
// operating_income_growth_yoy/sustainable_growth_rate/fcf_growth_yoy/ocf_growth_yoy
// (growth), short_interest_trend (positioning), and downside_volatility_252d/
// max_drawdown_1y (stability) into their respective _score_* formulas in
// load_stock_scores.py - flipped from used:false to used:true here to match.
// 2026-08-03 (later same day): gross_margin_trend/operating_margin_trend/net_margin_trend/
// roe_trend/asset_growth_yoy flipped to used:true too - the "structurally always NULL" premise
// above was wrong, traced to a local-DB schema bug (stockholders_equity/cash_and_equivalents
// columns renamed out from under the loader) that crashed fetch_incremental() before these
// fields could ever be computed; once fixed, live-verified real non-NULL values. Wired into
// _score_growth in load_stock_scores.py.
// CORRECTED 2026-08-27: the line above used to claim quarterly_growth_momentum "has no
// computation logic anywhere... genuinely, permanently dead" - false, live-verified against
// loaders/load_value_quality_growth_metrics.py's _compute_quarterly_metrics() (computed from
// quarterly_income_statement, 79.5% coverage). Isolated FM-tested along with 3 siblings
// (consecutive_positive_quarters, earnings_growth_4q_avg, eps_growth_stability) via
// algo/research/growth_quarterly_earnings_quality_candidates.py: quarterly_growth_momentum and
// consecutive_positive_quarters are clean nulls (t=-1.41/0.96 full sample, weak both halves) -
// correctly excluded. earnings_growth_4q_avg (t=4.47) and eps_growth_stability (t=-5.00) are
// strong full-sample but fail this project's own era-robustness bar (first half t=1.42/-1.38,
// well under |t|>2, despite a much stronger second half t=4.45/-5.18 - same sign both halves,
// not a flip, but not independently significant early on either). earnings_growth_4q_avg
// shipped anyway 2026-08-31 on industry-alignment grounds (IBD CAN SLIM "C" criterion).
// eps_growth_stability ALSO shipped 2026-08-31 (later, separate /goal session, explicit user
// directive to add earnings variability as a Growth input) - same "explicit user override of
// the era-robustness bar" footing as this pillar's own standing multi-input restore, not a
// reversal of the FM-test finding above (still true, just not the deciding factor here).
//
// used: true  -> this field is a genuine input to the score formula
// weight: display string for the "Used in Score" badge
// collected: false -> live-DB audit found ~0% population across the whole
//   universe (i.e. this isn't a per-stock gap, the pipeline doesn't produce it)

// REDESIGNED 2026-08-26 (Quality literature audit: Novy-Marx 2013, Fama-French 2015 RMW,
// Sloan 1996, QMJ 2013, Altman 1995 - see loaders/load_stock_scores.py's _score_quality
// docstring and algo/research/fama_macbeth_quality_factors.py's EXTENDED_CANDIDATE_COLS/
// ALTMAN_CANDIDATE_COLS for the full evidence). quality_score is 10 weighted signals: an
// equity-profitability cluster (ROE + Operating Profitability, 10% combined, ~5% each), an
// asset-profitability cluster (ROA + Gross Profitability, 25% combined, ~12.5% each), ROIC
// (10%), Accruals Ratio (10%), Debt-to-Assets (15%), Interest Coverage (5%), Margin
// Volatility (5%), Payout Ratio (10%), Altman Z''-Score (10%).
// TWO REWEIGHTS same day, both evidence-driven (see loaders/load_value_quality_growth_metrics.py's
// weighted_score comments for the full t-stats): (1) margin_volatility held 20% - the LARGEST
// weight in the composite - despite t=-1.28/-1.51, below this repo's own |t|>2 bar; cut to 5%,
// freed 15% went to Debt-to-Assets (10%->15%, t=2.11/2.18) and the asset cluster (15%->25%,
// carried by ROA's t=2.16/1.95). (2) Altman Z''-Score added (t=3.49 on the full
// retained_earnings-backfilled sample - the single strongest-evidenced component in this whole
// composite), funded by cutting Interest Coverage (10%->5%: sign-flips between univariate
// +0.16 and multivariate -1.47, the least stable component here) and Accruals Ratio (15%->10%:
// consistently negative-signed but t=-1.84/-1.49, doesn't clear the bar either). ROIC's own
// t=0.45 near-zero check was NOT acted on - that check used an approximate invested-capital
// formula, less trustworthy than the exact-formula checks behind the other two reweights.
// This REPLACES the old ±adjustment layer entirely (EBITDA Margin/FCF-NI/OCF-NI/
// Debt-to-Equity rows below are GONE - none of them influence quality_score anymore, so
// displaying them would be actively wrong, not just stale) - see _score_quality's docstring
// for why splitting one score across a base formula + a bump layer was real architectural
// debt independent of the literature findings.
//
// REBUILT 2026-08-26 (Quality pillar exhaustive-input review, user-directed). ROIC,
// Operating Profitability, Gross Profitability, Accruals Ratio, Margin Volatility, and Debt
// to Assets all removed from scoring (weak/insignificant Fama-MacBeth evidence, or replaced
// by a stronger alternative - see loaders/load_value_quality_growth_metrics.py's
// weighted_score comment for the full evidence). ROCE (replaces ROIC), FCF Margin (replaces
// Accruals), and Debt to Equity (replaces Debt to Assets) added - all three tested with
// meaningfully stronger and more time-stable Fama-MacBeth evidence than what they replaced
// (see that same comment). Current Ratio was proposed and tested too but showed no
// cross-sectional signal (t=-0.30/0.32, sign-flips across a half-split robustness check) -
// deliberately excluded despite being a standard quality-investing checklist item.
//
// margin_volatility RE-ADDED 2026-08-27 (goal: close out the SHAP-interaction sweep's
// flagged lead - see MEMORY.md quality_margin_volatility_3y_revalidated_borderline_20260827).
// A proper multivariate re-test (controlling for the other 7 live components, not the
// pooled-univariate test that got it cut 2026-08-26) found t=-2.42 full-sample, sign-
// consistent across both halves - real, second-tier evidence, same class as asset_turnover.
//
// operating_margin_trend/net_margin_trend/roe_trend MOVED HERE FROM GROWTH 2026-08-27 (goal:
// resolve the pillar-placement question flagged in growth_missing_metrics_swept_20260827) -
// Piotroski (2000 JAR) / QMJ (2019) both place improvement-in-profitability signals in
// Quality, not Growth. Same 3% each weight, just relocated - not a new empirical claim.
//
// asset_turnover ADDED 2026-08-27 (goal: act on the pending candidate flagged by the
// 2026-08-27 missing-metrics sweep - see MEMORY.md
// quality_asset_turnover_piotroski_tested_20260827). Classic DuPont efficiency component
// (Revenue / Total Assets), never previously tested by this pillar. FM-validated: t=3.03 full
// sample/3.00 first half/1.54 second half - same evidentiary tier as margin_volatility,
// weighted the same (7 of 113 nominal).
//
// Weight percentages below are all recomputed against the new 12-component nominal total
// (113 = 90 + margin_volatility's 7 + the 3 trend fields' 3 each + asset_turnover's 7).
//
// TRIMMED TO SCORED-ONLY 2026-08-28 (user directive: "the frontend react scores should
// reflect what is in the scores, we don't need to show what is not part of it" - after this
// same session settled what the right Quality formula actually is, see
// algo/research/quality_industry_leader_formula_comparison_20260828.py and
// loaders/load_value_quality_growth_metrics.py's quality_components comment for the full
// evidence trail). Every informational/unscored row this file had accumulated across prior
// sessions (ROIC, Operating Profitability, Accruals Ratio, Gross/Operating/Net/EBITDA Margin,
// FCF-NI, OCF-NI, Current/Quick Ratio, Interest Coverage, Debt to Assets, Payout Ratio,
// Earnings Surprise/Beat Rate, Consecutive Positive Quarters) is a field this repo's own
// isolated Fama-MacBeth testing already confirmed either genuinely dead, redundant with an
// already-scored input, or blocked on data depth (not a scoring decision) - see MEMORY.md's
// stock_scores_pillar_formulas section for the per-field evidence. Raw values remain
// computed/persisted in quality_metrics and in the API's quality_inputs payload for anyone
// who needs them - this is a display-only trim, not a data or scoring change.
//
// SECTOR-CONDITIONAL FORMULA (same session): Financial Services and Real Estate symbols use
// a 7-input, two-cluster (profitability + safety) construction that drops Asset Turnover -
// confirmed via isolated testing to be the one input structurally mismatched for a bank's
// loan book or a REIT's real estate portfolio (see _get_symbol_sector's docstring in
// loaders/load_value_quality_growth_metrics.py for the full evidence). This schema is static
// across all sectors - Asset Turnover's "~7%" badge below is accurate for the universal case
// but does not apply to Financial Services/Real Estate symbols specifically. Not worth a
// dynamic per-sector schema for one row; flagged here so it isn't mistaken for an oversight.
const QUALITY_SCHEMA = [
  {
    key: "return_on_equity_pct",
    label: "ROE",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~11%",
  },
  {
    key: "return_on_assets_pct",
    label: "ROA",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~17%",
  },
  {
    key: "return_on_capital_employed_pct",
    label: "ROCE",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~17%",
  },
  {
    key: "fcf_margin_pct",
    label: "FCF Margin",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~14%",
  },
  {
    key: "debt_to_equity",
    label: "Debt to Equity",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "~17%",
  },
  {
    key: "margin_volatility",
    label: "Margin Volatility (3Y)",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "~7%",
  },
  {
    key: "asset_turnover_pct",
    label: "Asset Turnover",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~7%",
  },
  {
    key: "gross_profitability_pct",
    label: "Gross Profitability",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "~7%",
  },
  // Every other Quality field this pipeline computes (ROIC, Operating Profitability, Accruals
  // Ratio, Gross/Operating/Net/EBITDA Margin, FCF-NI, OCF-NI, Current/Quick Ratio, Interest
  // Coverage, Debt to Assets, Payout Ratio, Earnings Surprise/Beat Rate, Consecutive Positive
  // Quarters, Altman Z-Score, the 3 margin/ROE trend fields) is intentionally NOT listed here
  // - each was isolated-Fama-MacBeth-tested and confirmed either genuinely dead, redundant
  // with an already-scored input, or blocked on data depth rather than a scoring choice (see
  // this file's REDESIGNED/REBUILT comments above and MEMORY.md's stock_scores_pillar_formulas
  // section for the per-field evidence). Raw values remain computed/persisted in
  // quality_metrics and in the API's quality_inputs payload - this tab shows only what
  // actually drives quality_score, per user directive 2026-08-28.
];

// REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): momentum_1m removed
// entirely - standard academic 12-1 momentum construction (Jegadeesh 1990) deliberately
// excludes the most recent month; our own panel confirmed why (trailing-1m return vs
// forward-1m return: Spearman=-0.031, p=4.2e-97 short-term reversal, concentrated in
// low-momentum names specifically). The ROC composite (roc_20d/60d/120d/252d) was also
// removed - it restated the same `close.pct_change()` computation as momentum_3m/6m/12m
// over near-identical trading-day windows, not a diversifying signal. Freed weight moved
// to RSI/MACD (genuinely distinct technical signals) and the remaining return windows.
//
// RSI/MACD CONSOLIDATED 2026-08-28 (goal: momentum/risk factor-interaction review): the two
// were correlated (r=0.70 in the 2026-08-25 FM panel, r=0.58 live-reverified 2026-08-28) and
// their multivariate coefficients flip sign against each other - the same redundancy
// symptom that already got SMA-50/200 averaged into one slot below and Risk's volatility
// windows collapsed from 6 to 2. Averaged into one "technical trend confirmation" slot,
// combined weight unchanged (21%+16%=37%) - see load_stock_scores.py's _score_momentum
// docstring (CONSOLIDATED 2026-08-28 note) for the full evidence. Both rows below still
// display their own raw value (RSI and MACD read differently even though they're now
// scored together), same "N% avg" convention as price_vs_sma_50/200's shared 8% slot.
//
// momentum_6m and raw momentum_12m (momentum_12_3) REPLACED 2026-08-25 (same-day
// follow-up, goal: act on this pillar's own named consolidation plan) by a derived 12-1
// skip-month construction - momentum_6m was the most redundant "middle" window (r=0.69
// with 3m, r=0.83 with 12m per algo/research/fama_macbeth_momentum_factors.py) and raw
// momentum_12m carried the same recency-reversal contamination this pillar's own 1m
// removal above was designed to avoid. See lambda/api/routes/scores.py's
// _derive_mom_12_1 and loaders/load_stock_scores.py's _score_momentum docstring
// (RESOLVED note) for the full evidence - this shows the actual number the score now
// uses (35% weight = the exact combined 6m(20%)+12m(15%) it replaced), not a stale
// predecessor value.
const MOMENTUM_SCHEMA = [
  {
    key: "momentum_3m",
    label: "Momentum (3M)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "20%",
  },
  {
    key: "momentum_12_1",
    label: "Momentum (12-1, skip-month)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "35%",
  },
  {
    key: "rsi",
    label: "RSI (14)",
    fmt: (v) => num(v, 1),
    used: true,
    weight: "37% avg",
  },
  {
    key: "macd",
    label: "MACD Line",
    fmt: (v) => num(v, 3),
    used: true,
    weight: "37% avg",
  },
  {
    key: "price_vs_sma_50",
    label: "Price vs 50-SMA",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "8% avg",
  },
  {
    key: "price_vs_sma_200",
    label: "Price vs 200-SMA",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "8% avg",
  },
  // TRIMMED BACK 2026-08-28 (user directive: this tab should show ONLY what's actually in
  // the scoring formula, not every computed field - reversing the same-day earlier
  // "restore to display" pass below). Before cutting each field, checked whether it
  // deserved to be a REAL scored input instead of just hidden - the standard the user asked
  // for ("if we need more in the scoring logic to get it right, keep working on it").
  // - current_price: not a signal, a display-only fact. Never a scoring candidate.
  // - momentum_1m/momentum_6m/momentum_12_3 (raw 12m): already tested and excluded from
  //   scoring on real evidence (Jegadeesh 1990 short-term reversal for 1m; redundancy with
  //   3m/12-1 for 6m/12m - see this pillar's own docstring above). Confirmed rejects, not
  //   gaps - the 12-1 skip-month row above IS the properly-constructed use of this same
  //   underlying data.
  // - roc_20d/60d/120d/252d: same `close.pct_change()` computation as the momentum windows
  //   over near-identical trading-day windows - proven duplicate data, not a distinct signal.
  // - price_vs_52w_high: the one candidate that hadn't actually been tested for this pillar
  //   before today, despite being a real, separate, published anomaly (George & Hwang 2004,
  //   JoF, "52-Week High and Momentum Investing"). Tested properly just now - monthly
  //   cross-sectional panel, 37 months, 52,152 symbol-months, same Fama-MacBeth-style
  //   methodology as every other factor in this file: mean_corr=0.0092, t=0.308 (no signal),
  //   and unstable across sub-periods (first half t=0.92, second half t=-0.43, sign flip).
  //   The naive pooled Spearman looked significant (r=-0.031, p=1.8e-12) but that's the same
  //   inflated-significance artifact this file already warns about elsewhere (pooled panels
  //   understate within-month correlation). Genuinely tested and rejected, not overlooked.
];

// FIXED 2026-08-04: value_score (load_stock_scores.py::_score_value) weight badges were
// stale here vs. the code's actual constants (P/E 45% not 20%, P/B 20% not 15%, FCF
// Yield 12% not 20%), and dividend_yield (8% weight, a real input since migration 1146)
// was displayed as a plain unweighted number despite being scored.
// market_cap cut 20260816 (second pass) - unweighted reference field, doesn't feed value_score.
// CLEANUP 2026-08-18: margin_of_safety_pct's 20% Value weight removed per user request -
// it doesn't belong in the Value factor score. Dropped the separate raw-dollar
// "Intrinsic Value (DCF)" row too (stock_intrinsic_value isn't comparable across symbols,
// and was already used:false / display-only) - stock_margin_of_safety (the DCF % discount
// to intrinsic value, which *is* comparable across symbols) is now the single informational
// read for this signal, kept visible but unweighted.
// REINSTATED 2026-08-24 (user-directed): margin_of_safety_pct is back in the Value factor
// score at its original 20% weight (load_stock_scores.py::_score_value) - same curve as the
// original 2026-08-17 add. stock_margin_of_safety is used:true again below.
// RENAMED 2026-08-19 (user-reported confusion): "Intrinsic Value (DCF)" -> "Margin of
// Safety (DCF)". The 2026-08-18 rename above swapped in "Intrinsic Value (DCF)" as the
// label for this same %, reasoning the % discount to intrinsic value IS the margin of
// safety - true, but "Intrinsic Value" on its own reads as a dollar figure (what a share
// is worth), not a percentage - live example that surfaced the confusion: this row
// rendering "Intrinsic Value (DCF)  -186.3%", which looks like intrinsic value itself
// cratered 186%, not "price sits 186% above the DCF fair value." "Margin of Safety" is
// the standard term (Graham) for exactly this %-based comparison and doesn't collide with
// the dollar-valued reading "Intrinsic Value" implies.
// REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): P/E was 45% (more than
// double every other input) despite being the empirically WEAKER of the three traditional
// value multiples in our own forward-1y-return panel (PE Spearman=-0.091, PB=-0.137,
// PS=-0.146) - consistent with Fama-French value work centering on book-to-market, not
// P/E. Shifted weight toward P/B/P/S accordingly. Forward P/E removed entirely -
// analyst_earnings_estimates has zero historical depth (every row fell within a single
// 3-week window as of this audit), so it could never be validated, and it shares trailing
// P/E's weaker standing plus analyst-forecast optimism bias on top. Dividend yield cut to
// a token weight - tested inconclusive (marginal p=0.036 full-sample, vanished to p=0.542
// in the best-covered recent sub-period). Margin-of-safety's weight reduced (not removed)
// to reflect its already-documented DCF growth-cap bias.
//
// EV/EBITDA and EV/Revenue REMOVED 2026-08-25 (same-day follow-up, goal: re-audit ALL
// stock_scores inputs) - measured directly (150mo pooled, n=45,806): ps_ratio/ev_revenue
// correlate r=1.00 (literally the same signal), pe_ratio/ev_ebitda r=0.93 (near-duplicate) -
// same "counted twice" bug class already fixed for Momentum's ROC and Quality's
// debt_to_assets. Their combined 16pts initially moved to P/B (+6, "most genuinely
// distinct multiple" per the same correlation pass), FCF Yield (+6, real near-uncorrelated
// diversifier), and Dividend Yield/Margin of Safety (+2 each). Both removed fields stay
// fetched/displayed elsewhere on this page, just no longer weighted here.
//
// PE/PB/PS reweighted AGAIN same day (later pass) - a sub-period-robust Fama-MacBeth
// re-test found PB is the WEAKEST of the three multiples and PE/PS are comparably strong
// (the opposite ranking from the pooled-Spearman claim that originally justified cutting
// PE from 45% to 18%) - see loaders/load_stock_scores.py's _score_value docstring
// ("PE-vs-PB/PS RANKING DISPUTE - RESOLVED") for the full evidence.
// SUPERSEDED 2026-08-26: that whole prior ranking chain, including the "independent
// re-verification" pass, shared one selection-bias flaw (requiring PE alongside PB/PS
// requires positive earnings, excluding unprofitable/small firms). Bias-corrected re-test
// REVERSES it: PB is now the STRONGEST of the three (univariate t=-9.34), PE the
// weakest/near-null (t=-4.11 univariate, -0.96 multivariate). See loaders/load_stock_scores.py's
// _score_value docstring ("PE-vs-PB/PS RANKING - REVERSED") for the full evidence.
//
// PE/PB/PS REVERSED AGAIN 2026-08-25 (later same day, follow-up pass): every prior PE/PB/PS
// verdict above (both the original ranking and the "PB weakest" re-verification) used a test
// script requiring all 6 value inputs simultaneously non-null, which implicitly required
// positive earnings (PE undefined for eps<=0) - systematically excluding unprofitable/small/
// distressed firms, exactly where these effects concentrate. A selection-bias-corrected
// rerun (only forward return mandatory, missing inputs imputed rather than dropped)
// completely inverts the ranking: PB is now the STRONGEST of the three (robust across
// univariate/multivariate specs and 2 independent sub-periods), PE the weakest/null. FCF
// yield also flipped sign vs the old test and is now treated as a fragile null. See
// loaders/load_stock_scores.py's _score_value docstring ("PE-vs-PB/PS RANKING - REVERSED")
// for the full evidence.
//
// SIZE (market_cap) MOVED OUT 2026-08-26 - promoted to its own top-level "Size" pillar/tab,
// removed from scoring the same day on a UX/product objection, RE-PROMOTED 2026-08-27 on new
// era-robust half-split evidence, then RETIRED ENTIRELY 2026-08-28 (see
// loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS for the full history), and its last
// informational-only display (a "Size (informational)" card / SIZE_SCHEMA) removed 2026-08-31.
// market_cap never moved back into this schema. The 7 inputs below stay at the x1.25-rescaled
// weights that restored their pre-Size 100% (unaffected by any of Size's later moves, since
// Value never absorbed market_cap back).
// AMIHUD ILLIQUIDITY added 2026-08-26, REMOVED same day (user directive - see
// loaders/load_stock_scores.py's _score_value docstring "AMIHUD ILLIQUIDITY" note for why:
// real academic signal, but scored favoring harder-to-trade micro-caps in a way that's
// hard to trust given this system's flat, likely-understated slippage assumption). The
// other 7 inputs below are back at their pre-Amihud weights.
// P/E, P/B, and P/S SCORING METHOD CHANGED 2026-08-28 (goal: "what does IBD/the best and
// brightest do" - see loaders/load_stock_scores.py's update_value_multiples_percentiles()
// docstring for the full evidence trail, citations, and validation). These 3 raw ratios
// (still shown below as-is) are no longer scored against a fixed absolute threshold curve -
// they're now a CROSS-SECTIONAL PERCENTILE RANK against the current run's universe (the same
// "rank against peers, not a fixed cutoff" convention this pillar's own PEG/margin-of-safety
// don't use, but IBD's every SmartSelect rating and MSCI's factor construction both do).
// Weights themselves (12%/30%/27%) are unchanged - only how a given raw ratio maps to a 0-100
// sub-score changed.
const VALUE_SCHEMA = [
  {
    key: "stock_pe",
    label: "P/E",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "12%",
  },
  {
    key: "stock_pb",
    label: "P/B",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "39%",
  },
  {
    key: "stock_ps",
    label: "P/S",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "34%",
  },
  // Forward P/E PROMOTED to a scored input 2026-08-28 (user directive - MSCI's Value index
  // uses 12-month forward Earnings/Price as one of its three core descriptors; explicitly a
  // judgment call, not evidence-based - analyst_earnings_estimates only has ~22 trading days
  // of history and can't be backtested yet).
  {
    key: "stock_forward_pe",
    label: "Forward P/E",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "4%",
  },
  // "Net Payout Yield (Div + Buybacks)" (net_payout_yield) REVERTED 2026-08-28 back to plain
  // Dividend Yield on explicit user directive ("we want the dividend yield instead of that
  // payout shit") - see loaders/load_stock_scores.py's _score_value docstring for the full
  // history. Weight 11% (2026-08-28, later same day: +3 from PEG's removal below).
  {
    key: "stock_dividend_yield",
    label: "Dividend Yield",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "11%",
  },
  // market_cap moved to the Size pillar 2026-08-26, since retired entirely (see comment above).
  // amihud_illiquidity NOT added below - value_inputs (lambda/api/routes/scores.py) doesn't
  // carry it at all (it lives in technical_data_daily, a different query entirely); adding it
  // would need a real backend SQL/join change, out of scope for this display-only pass.
  //
  // FULLY REMOVED FROM DISPLAY 2026-08-28 (user directive: "if we not scoring it we dont want
  // to display it" - overrides the prior "keep unscored fields visible for transparency"
  // convention this tab used to follow). This is a Value-tab-specific display rule, not a
  // data change - every field below stays fully computed/stored/API-served, just not rendered
  // on THIS tab:
  //   - PEG (peg_ratio): REMOVED FROM SCORING 2026-08-28 - a growth-ADJUSTED earnings multiple
  //     (PE / growth rate) is, by design, a Value/Growth hybrid; no mainstream systematic
  //     Value methodology (MSCI Enhanced Value/World Value, Russell, S&P Style, Barra,
  //     Fama-French/AQR) includes one - institutional practice keeps Value and Growth as
  //     separate, independently-measurable factors on purpose. This repo's own 15-pair
  //     pillar-interaction sweep (algo/research/cross_pillar_interaction_sweep_20260828.py)
  //     confirms Growth x Value specifically isn't era-robust either (only Value x Risk is -
  //     see load_stock_scores.py's `_value_risk_adjusted_weights`). See _score_value's
  //     "PEG - REMOVED FROM SCORING 2026-08-28" docstring note. Freed 3% went to Dividend
  //     Yield above.
  //   - FCF Yield (fcf_yield): REMOVED FROM SCORING 2026-08-25 - independently re-verified
  //     robustly wrong-signed (t=-2.43/-0.91/-2.17 full/half/half). Checked 2026-08-28
  //     specifically for the same missing-data selection bias that flipped the PE-vs-PB/PS
  //     ranking dispute - does NOT apply here (fcf_yield is computed unconditionally, correctly
  //     negative for cash-burning companies, not gated to positive-only like pe_ratio was) -
  //     see "FCF YIELD - RESOLVED 2026-08-28" docstring note.
  //   - EV/EBITDA (stock_ev_ebitda) / EV/Revenue (stock_ev_revenue): excluded as near-literal
  //     duplicates of P/E (r=0.93) and P/S (r=1.00) respectively - would double-weight a signal
  //     already scored, not add information.
  //   - Margin of Safety (stock_margin_of_safety) / Intrinsic Value (stock_intrinsic_value):
  //     REMOVED FROM SCORING 2026-08-28 - DCF-based intrinsic-value estimates are an
  //     industry-standard deep-value screening/decision tool (Graham/Klarman), not a
  //     systematic Value-factor ranking input - see "MARGIN OF SAFETY - REMOVED FROM SCORING
  //     2026-08-28" docstring note. Both are the Deep Value Picks page's (DeepValueStocks.jsx)
  //     primary metrics instead - their natural home, and where a viewer should look for them.
  //   - net_payout_yield: was already fully hidden here on an earlier explicit user directive
  //     ("make sure this one is gone") - unaffected by this pass, still gone.
  //   - market_cap (Size, formerly shown informationally via a separate "Size (informational)"
  //     card below Safety): REMOVED FROM DISPLAY 2026-08-31 (user directive) - Size was already
  //     retired as a scored pillar 2026-08-28 (see BASE_PILLAR_WEIGHTS history above); this
  //     removes its last informational-only display too. No backend/scoring change.
];

// RESTORED TO MULTI-INPUT 2026-08-28 (user directive, /goal session: "get the rest of the
// growth inputs back in there the ones that are in the react" + explicit pushback that
// revenue_growth_1y's "inverted - lower is better" framing "shouldn't be inverted"). This tab
// had drifted out of sync with a backend that was rebuilt 3 times in 48h into an increasingly
// narrow single-input, sign-flipped formula while this schema kept displaying a dozen
// "computed but unscored" rows next to a "sole input" weight badge on just one of them -
// looked multi-factor, wasn't, and the one scored row's label told users the opposite of what
// a plain reading of "Growth" would suggest. loaders/load_stock_scores.py's _score_growth is
// now a genuine multi-input blend (GROWTH_SCORE_FIELDS) - every row below is a real, scored
// input, equal-weighted (partial-availability renormalized - a symbol missing some of these
// still gets scored off whichever are present) and NOT sign-flipped (higher growth = higher
// score for every field here, per the user's explicit direction - overriding this file's own
// prior growth-reversal research, see _score_growth's docstring for the full evidence-vs-
// override history). Equal-weighted across whatever GROWTH_SCORE_FIELDS currently holds (14
// as of 2026-08-31's eps_growth_stability addition, so "7%" below is 1/14 rounded) - not a
// separately-tuned per-field weight; update this comment's count/pct if the field list changes
// again rather than letting it drift stale (see the 11/"9%" figure this replaced, which had
// gone stale across 2 intervening field-count changes without being updated).
//
// ocf_growth_yoy/asset_growth_yoy REMOVED 2026-08-28 (user directive, /goal session: "remove
// these two from growth score and from react") - dropped from both GROWTH_SCORE_FIELDS
// (loaders/load_stock_scores.py) and this schema. Raw values remain in growth_metrics/the API
// for reference, just no longer scored or shown on this tab.
//
// book_value_growth_pct REMOVED 2026-08-28 (user directive, /goal session: live-observed
// persistent "No data" on this row) - dropped from both GROWTH_SCORE_FIELDS and this schema.
// Raw value remains in growth_metrics (migration 1242) for reference, just no longer scored
// or shown here.
//
// operating_income_growth_yoy REMOVED 2026-08-28 (user directive, /goal session: "remove this
// Operating Income Growth (YoY) ... from growth from the score and the react") - dropped from
// both GROWTH_SCORE_FIELDS and this schema. Raw value remains in growth_metrics/the API for
// reference, just no longer scored or shown on this tab.
//
// gross_margin_trend/operating_margin_trend/net_margin_trend/roe_trend are NOT in this schema
// (and never were, since 2026-08-28's earlier removal) - _score_growth's own docstring states
// they remain a Quality-origin concept (relocated there 2026-08-27, removed from Quality
// scoring the same day on their own isolated re-test) and are absent from GROWTH_SCORE_FIELDS.
// Raw values remain computed/persisted in both quality_metrics and growth_metrics for
// reference, just not displayed on this tab.
//
// eps_growth_stability ADDED 2026-08-31 (/goal session, explicit user directive: "add earnings
// variability as additional input to growth score") - now scored (used:true) via a dedicated
// inverted curve (_score_eps_growth_stability in loaders/load_stock_scores.py's _score_growth,
// NOT the shared _score_single_growth every other row here uses, since this field is a
// dispersion metric - always >=0, lower=more consistent - not a signed growth rate). Real,
// live-computed data: 79.8% coverage, comparable to fcf_growth_yoy's 72.1%. GROWTH_SCORE_FIELDS
// is now 14 fields, so every badge below (including this one) is ~1/14 - "7%", not "8%".
//
// REVISED 2026-08-31 (industry-alignment review - see GROWTH_SCORE_FIELDS's docstring in
// loaders/load_stock_scores.py for the full rationale/evidence): net_income_growth_yoy is no
// longer a scored input (raw net income growth isn't how MSCI/Russell/S&P/Zacks/IBD define
// the "earnings growth" component of a Growth factor - they all use per-share EPS growth
// specifically because it's buyback/dilution-adjusted) - still shown below for reference, same
// still-computed/no-longer-scored treatment as ocf_growth_yoy/asset_growth_yoy/
// operating_income_growth_yoy above. forward_eps_growth_current_fy/forward_eps_growth_next_fy/
// forward_revenue_growth_next_fy are RESTORED and now scored (used:true) - forward/analyst-
// consensus EPS growth is the headline Growth descriptor in MSCI/Russell/S&P's own
// methodologies, and this pillar had no forward-looking input at all before this pass. Their
// brief 2026-08-31 same-day removal-from-display was a display-only declutter reacting to one
// stock's legitimate no-analyst-coverage gap, not a rejection of the fields themselves - see
// loaders/load_value_quality_growth_metrics.py's _get_analyst_forward_growth_estimates
// docstring for the live coverage numbers (73-77%, comparable to fcf_growth_yoy's 72%) that
// motivated bringing them back. Values are raw fractions in the API's growth_inputs (0.18 =
// 18%) - same *100 formatter this file already uses elsewhere for fraction-scaled fields (see
// RISK_SCHEMA's volatility_60d). eps_estimate_revision_90d_pct restored informationally only
// (unscored, no weight badge) - an estimate-REVISION-momentum signal is a distinct factor
// style from a growth-rate level, not folded into this blend; already percentage-point scaled
// (no *100 needed).
const GROWTH_SCHEMA = [
  {
    key: "revenue_growth_1y_pct",
    label: "Revenue Growth (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "eps_growth_1y_pct",
    label: "EPS Growth (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "revenue_growth_3y_cagr",
    label: "Revenue Growth (3Y CAGR)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "eps_growth_3y_cagr",
    label: "EPS Growth (3Y CAGR)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "revenue_growth_5y_cagr",
    label: "Revenue Growth (5Y CAGR)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "eps_growth_5y_cagr",
    label: "EPS Growth (5Y CAGR)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "forward_eps_growth_current_fy",
    label: "Forward EPS Growth (Current FY, analyst consensus)",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "forward_eps_growth_next_fy",
    label: "Forward EPS Growth (Next FY, analyst consensus)",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "forward_revenue_growth_next_fy",
    label: "Forward Revenue Growth (Next FY, analyst consensus)",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "sustainable_growth_rate",
    label: "Sustainable Growth Rate",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "quarterly_growth_momentum",
    label: "QoQ Growth Momentum",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "earnings_growth_4q_avg",
    label: "Earnings Growth (4Q Avg)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "fcf_growth_yoy",
    label: "FCF Growth (YoY)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "eps_growth_stability",
    label: "EPS Growth Stability (variability, lower = more consistent)",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "7%",
  },
  {
    key: "net_income_growth_yoy",
    label: "Net Income Growth (YoY)",
    fmt: (v) => pct(v, 2),
  },
  {
    key: "eps_estimate_revision_90d_pct",
    label: "EPS Estimate Revision (90D)",
    fmt: (v) => pct(v, 2),
  },
];

// POSITIONING RETIRED AS A SCORED PILLAR 2026-08-27 (evidence-driven - see
// loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS for the full trail): A/D rating showed no
// forward-return signal by any methodology tried, including a full 2000-2026 price-history
// re-test (t=1.05); institutional ownership and short interest have never had real historical
// depth in this database to test at all. None of the fields below feed composite_score or any
// pillar score anymore - this tab is informational only (no weight badges), sourced directly
// from positioning_metrics via the scores API's positioning_inputs field.
const POSITIONING_SCHEMA = [
  {
    key: "ad_rating",
    label: "A/D Rating",
    fmt: (v) => num(v, 1),
  },
  {
    key: "institutional_ownership_pct",
    label: "Institutional Own %",
    fmt: (v) => pct(v, 1),
  },
  {
    key: "short_interest_pct",
    label: "Short Interest %",
    fmt: (v) => pct(v, 2),
  },
  // short_percent_of_float removed 20260816: loaders/load_positioning_metrics.py computes
  // it as short_shares / shares_outstanding, the same FINRA short_shares numerator and
  // (per that loader's own comment) "same denominator" short_interest_pct already uses -
  // a near-duplicate restatement of the field above it, not an independent signal.
  {
    key: "short_interest_pct_change",
    label: "Short Interest % Chg (MoM)",
    fmt: (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${num(v, 1)}%`),
  },
  // RESTORED TO DISPLAY 2026-08-28 (user-directed: wants full visibility into every computed
  // input). top_10_institutions_pct/institutional_holders_count/shares_short_prior_month/
  // short_ratio were cut 20260816 (second pass) as unweighted reference fields - API still
  // returns all of them.
  {
    key: "top_10_institutions_pct",
    label: "Top 10 Institutions %",
    fmt: (v) => pct(v, 1),
  },
  {
    key: "institutional_holders_count",
    label: "Institutional Holders (Count)",
    fmt: (v) => num(v, 0),
  },
  {
    key: "shares_short_prior_month",
    label: "Shares Short (Prior Month)",
    fmt: (v) => (v == null ? "—" : `${(v / 1e6).toFixed(2)}M`),
  },
  {
    key: "short_ratio",
    label: "Short Ratio (Days to Cover)",
    fmt: (v) => num(v, 2),
  },
];

// CONSOLIDATED 2026-08-25 (goal: full scoring-architecture audit): this tab previously
// scored volatility_12m/60d/30d AND downside_volatility_252d/60d/30d as 6 separate inputs.
// Measured directly on a 400-symbol sample (20,904 observations): the three symmetric
// windows correlate 0.69-0.89 with each other, the three downside windows correlate
// 0.78-0.92 with each other, and even cross-flavor correlations run 0.52-0.83 - all six
// were essentially the same "how choppy is this stock" signal at different smoothing
// windows (volatility clustering - Engle 1982, Bollerslev 1986 GARCH literature), while
// beta and max drawdown - the two genuinely distinct signals - carried the smallest
// weights. Collapsed to one symmetric + one downside window (60d) and redistributed the
// freed weight to beta and max_drawdown.
// volatility_60d and downside_volatility_60d are raw fractions in the DB
// (load_risk_metrics_daily.py's _calculate_volatility/_calculate_downside_volatility return
// daily_std * sqrt(252), e.g. 0.15 for 15% - _score_risk's own 0.15/0.30/0.60 thresholds
// in load_stock_scores.py confirm this), same convention as debt_to_assets above, so they need
// the same *100 scaling pct() doesn't do itself. max_drawdown_1y is the odd one out here -
// _calculate_max_drawdown already multiplies by 100 (returns e.g. -25.5), so it's passed
// through as-is like the loader-pre-scaled *_pct fields in QUALITY_SCHEMA.
// REWORKED 2026-08-30 (later same day, user directive: full delegation to figure out the
// best combination - see _score_risk's docstring in load_stock_scores.py for the per-input
// reasoning). Volatility 60D 45% + Volatility 252D 20% + Beta 20% + Max Drawdown 1Y 15%.
// Volatility 30D dropped (most redundant of the three windows). Downside volatility and
// Debt-to-Assets stay out - both have clean, confirmed reasons (pure redundancy with
// volatility_60d; balance-sheet metric scored under Quality's base quality_score instead).
// Note: the API's "volatility_12m" key actually carries volatility_252d (a legacy naming
// quirk in lambda/api/routes/scores.py, not a real 12-month window).
const RISK_SCHEMA = [
  {
    key: "volatility_60d",
    label: "Volatility (60D)",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "45%",
  },
  {
    key: "volatility_12m",
    label: "Volatility (252D)",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "20%",
  },
  {
    key: "beta",
    label: "Beta vs Market",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "20%",
  },
  {
    key: "max_drawdown_1y",
    label: "Max Drawdown (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "15%",
  },
  // Volatility 30D and downside volatility (252d/60d/30d) are NOT part of the current
  // 4-input formula - still fetched/persisted for reference. Debt-to-Assets is scored under
  // Quality instead, not this price-volatility/risk-of-loss pillar.
  // segment_count/largest_segment_revenue_pct/is_diversified also stay off this tab - the
  // underlying XBRL segment-dimension extraction always comes back empty.
];
