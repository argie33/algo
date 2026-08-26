import React, { useState, useEffect } from "react";
import {
  Star,
  Activity,
  DollarSign,
  TrendingUp,
  Users,
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
    key: "positioning",
    label: "Positioning",
    scoreKey: "positioning_score",
    icon: Users,
  },
  {
    key: "stability",
    label: "Stability",
    scoreKey: "stability_score",
    icon: Shield,
  },
];

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
  if (loading || !history || !Array.isArray(history.points) || history.points.length < 2) {
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
        <span className="t-2xs muted">
          since {movement.start_date || "—"}
        </span>
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
            <span className={`badge ${rankImproved ? "badge-success" : "badge-danger"}`}>
              Rank {rankImproved ? "▲" : "▼"} {Math.abs(movement.rank_change)}
            </span>
          )}
        </div>
      </div>
      <div className="card-body" style={{ padding: "var(--space-3)" }}>
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
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

// ─── one row of a factor-inputs table ──────────────────────────────────────
// tier: "used" (feeds the score formula), "tracked" (collected, not scored)
// weight: display string for "used" rows, e.g. "35%", "avg", "fallback"
// collected: false means this column is essentially never populated system-wide
//   (verified against live DB, not just this stock) — rendered as "Not yet available"
//   rather than the ambiguous "No data" used for a per-stock null.
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
          >
            {row.weight}
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
function InputsCard({ title, stock, schema, inputsKey = null }) {
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
    return { ...s, value, reason };
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
          • <strong>Cyan tag</strong> = weight in the live scoring formula
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
        />
        <InputsCard
          title="Momentum"
          stock={stock}
          schema={MOMENTUM_SCHEMA}
          inputsKey="momentum_inputs"
        />
        <InputsCard
          title="Value"
          stock={stock}
          schema={VALUE_SCHEMA}
          inputsKey="value_inputs"
        />
        <InputsCard
          title="Growth"
          stock={stock}
          schema={GROWTH_SCHEMA}
          inputsKey="growth_inputs"
        />
        <InputsCard
          title="Positioning"
          stock={stock}
          schema={POSITIONING_SCHEMA}
          inputsKey="positioning_inputs"
        />
        <InputsCard
          title="Stability"
          stock={stock}
          schema={STABILITY_SCHEMA}
          inputsKey="stability_inputs"
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
export { QUALITY_SCHEMA, STABILITY_SCHEMA };

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
// _score_growth in load_stock_scores.py. quarterly_growth_momentum remains used:false - unlike
// the other 5, it has no computation logic anywhere (this loader never fetches quarterly data),
// so it's genuinely, permanently dead.
//
// used: true  -> this field is a genuine input to the score formula
// weight: display string for the "Used in Score" badge
// collected: false -> live-DB audit found ~0% population across the whole
//   universe (i.e. this isn't a per-stock gap, the pipeline doesn't produce it)

// FIXED 2026-08-04: quality_score (load_stock_scores.py::_score_quality) is NOT a
// 6-input linear weighting of ROE/ROA/ROIC/Profit Margin/Op Margin/Debt-Equity as this
// schema previously claimed - it's an equal-weighted average of up to 6 DIFFERENT
// components (roe, roa, operating_margin, net_margin, debt_to_assets inverted,
// interest_coverage - each ~17% when all present, self-normalizing over whichever are
// available), then adjusted +/-10 points by _enhance_quality_score using a separate set
// of signals (margins_avg, earnings_growth_yoy, fcf_to_net_income, roic_pct,
// ocf_to_net_income). ROIC/FCF-to-NI/OCF-to-NI are real inputs but are bounded +/- point
// adjustments, not proportional weights, hence the "adj" labels below instead of a %.
//
// CLEANUP 2026-08-16: debt_to_equity/current_ratio/quick_ratio/cash_per_share moved here
// from the Stability tab - they're balance-sheet leverage/liquidity/cash metrics
// (_score_financial_stability), not price-volatility signals, so they belong under
// Quality. They now feed _enhance_quality_score as a bounded +/-3 adjustment (same
// pattern as margins/ROIC/OCF above), not a proportional weight.
// CLEANUP 2026-08-18: gross_margin/current_ratio/quick_ratio/cash_per_share cut entirely
// per user request - none of them belong in the factor scores anymore. gross_margin
// dropped out of _enhance_quality_score's margin-quality average; current_ratio/
// quick_ratio/cash_per_share dropped out of _score_financial_stability. debt_to_equity
// stays (still a real ±3 adj input); debt_to_assets stays (still a real ~17% input).
const QUALITY_SCHEMA = [
  {
    key: "return_on_equity_pct",
    label: "ROE",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~17%",
  },
  {
    key: "return_on_assets_pct",
    label: "ROA",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~17%",
  },
  {
    key: "profit_margin_pct",
    label: "Profit Margin",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~17%",
  },
  {
    key: "operating_margin_pct",
    label: "Operating Margin",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "~17%",
  },
  {
    key: "ebitda_margin_pct",
    label: "EBITDA Margin",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "±3 adj",
  },
  {
    key: "fcf_to_net_income",
    label: "FCF / Net Income",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "±2 adj",
  },
  {
    key: "operating_cf_to_net_income",
    label: "OCF / Net Income",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "±2 adj",
  },
  {
    key: "interest_coverage",
    label: "Interest Coverage",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "~17%",
  },
  {
    key: "debt_to_assets",
    label: "Debt to Assets",
    fmt: (v) => pct(v == null ? null : v * 100, 1),
    used: true,
    weight: "~17%",
  },
  {
    key: "debt_to_equity",
    label: "Debt / Equity",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "±3 adj",
  },
  // RE-ADDED 2026-08-25 (goal: full scoring-architecture audit): eps_growth_stability was
  // cut 20260816 as an unweighted reference field ("no scoring impact") - it's now wired
  // into _enhance_quality_score as a real ±3 adjustment (stddev of trailing 4-quarter EPS
  // growth - lower = more consistent earnings = higher quality, the QMJ "safety" concept).
  // earnings_growth_yoy REMOVED from _enhance_quality_score entirely (it duplicated the
  // entire Growth pillar's purpose) and replaced with this plus the margin/ROE trend
  // fields below, relocated from the Growth tab (they measure quality-of-earnings
  // direction, not growth magnitude).
  {
    key: "eps_growth_stability",
    label: "EPS Growth Stability (lower = more consistent)",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "±3 adj",
  },
  {
    key: "operating_margin_trend",
    label: "Op Margin Trend",
    fmt: (v) => `${num(v, 2)} pp`,
    used: true,
    weight: "±2 adj",
  },
  {
    key: "net_margin_trend",
    label: "Net Margin Trend",
    fmt: (v) => `${num(v, 2)} pp`,
    used: true,
    weight: "±2 adj",
  },
  {
    key: "roe_trend",
    label: "ROE Trend",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "±2 adj",
  },
  // SECOND PASS 20260816: cut every unweighted "Tracked (Not Scored)" field from this
  // tab (earnings_surprise_avg, earnings_beat_rate, consecutive_positive_quarters,
  // free_cashflow, operating_cashflow, total_debt, total_cash, earnings_growth_4q_avg)
  // per user request - none of them feed quality_score, they were reference-only. See
  // MEMORY.md scoresdashboard_too_many_inputs_history_and_collapse_fix_20260816 for why
  // the field count grew in the first place (real weighted inputs restored, not scope
  // creep) and why these specific ones were safe to cut anyway (no scoring impact).
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
    weight: "21%",
  },
  {
    key: "macd",
    label: "MACD Line",
    fmt: (v) => num(v, 3),
    used: true,
    weight: "16%",
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
  // price_vs_52w_high/current_price cut 20260816 (second pass) - unweighted reference
  // fields, don't feed momentum_score.
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
// SIZE (market_cap) ADDED 2026-08-25 (goal: close the highest-confidence gap found in this
// session's full stock_scores re-audit) - Fama-French SMB (Banz 1981) was completely absent
// from all 6 pillars despite market_cap already being available (77.4% coverage on
// value_metrics, no schema/API change needed - already returned by lambda/api/routes/
// scores.py). log(market_cap) vs forward 1-month return tested at t=-5.37 (150 months,
// median 2,601 symbols) - nearly as strong as volatility_60d's t=-6.1, this session's
// single strongest finding. The other 7 inputs below were uniformly scaled x0.8 to free
// 20pts for this, not re-litigating either ranking dispute already resolved above. See
// loaders/load_stock_scores.py's _score_value docstring ("SIZE FACTOR") for the full
// evidence and the log10-bucketed scoring curve.
const VALUE_SCHEMA = [
  {
    key: "stock_pe",
    label: "P/E",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "10%",
  },
  {
    key: "stock_pb",
    label: "P/B",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "22%",
  },
  {
    key: "stock_ps",
    label: "P/S",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "21%",
  },
  {
    key: "peg_ratio",
    label: "PEG",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "8%",
  },
  {
    key: "stock_dividend_yield",
    label: "Dividend Yield",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "3%",
  },
  {
    key: "fcf_yield",
    label: "FCF Yield",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "10%",
  },
  {
    key: "stock_margin_of_safety",
    label: "Margin of Safety (DCF)",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "6%",
  },
  {
    key: "market_cap",
    label: "Market Cap (Size)",
    fmt: (v) => (v == null ? "—" : `$${(v / 1e9).toFixed(2)}B`),
    used: true,
    weight: "20%",
  },
  // stock_forward_pe removed 2026-08-25 - see comment above.
];

// REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): cut from 14 inputs to 4.
// Three composite-level backtests (original 6-window mix, a consolidated version, and an
// asset/cashflow-led version) against forward 1y returns ALL showed no real signal
// (p=0.27, p=0.94, p=0.33) - more inputs weren't buying predictive power, so simplicity
// won over completeness. Kept: EPS 1y (the single conventional growth reference),
// Asset Growth YoY (SIGN-FLIPPED - Cooper/Gulen/Schill 2008 + Fama-French CMA, and our own
// panel replicated it cleanly: Spearman=-0.037, p=8.4e-6, the strongest single empirical
// result of the whole audit), Revenue Growth 1y (kept small - weak/no standalone signal
// per Lakonishok/Shleifer/Vishny 1994), Sustainable Growth Rate (structurally distinct,
// ROE-driven). Dropped: EPS/Revenue 3y/5y CAGRs (redundant windows; 5y also had the worst
// coverage, 38.9%/73.7% of the universe vs 1y's 75.6%/95.2%), NI/OI growth YoY (near-
// duplicates of EPS growth), FCF/OCF growth YoY (no proven distinct value once tested at
// the composite level). Margin/ROE trend fields briefly moved to the Quality tab same day,
// then removed from scoring entirely on user feedback (see QUALITY_SCHEMA comment) - not
// re-homed, since they don't earn their keep empirically even in their correct conceptual
// home (Quality, per Piotroski F-Score / AFP Quality Minus Junk literature).
//
// REWEIGHTED 2026-08-25 (goal: horizon-matched re-audit, later same day): eps_growth_1y cut
// 45%->25% - Fama-MacBeth at the 1-month horizon (matched to this system's actual weeks-scale
// swing-trading holding period) found it robustly null (t=0.76/0.97), the cleanest null in
// this pillar across every horizon/spec tested. asset_growth_yoy/revenue_growth_1y/
// sustainable_growth_rate raised to absorb the freed weight - see
// loaders/load_stock_scores.py's _score_growth docstring for the full per-field reasoning
// (asset_growth's weaker-than-claimed showing has a specific explanation - McLean & Pontiff
// 2016 post-publication anomaly decay - that eps_growth_1y's null doesn't have).
const GROWTH_SCHEMA = [
  {
    key: "eps_growth_1y_pct",
    label: "EPS Growth (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "25%",
  },
  {
    key: "asset_growth_yoy",
    label: "Asset Growth YoY (inverted - lower is better)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "30%",
  },
  {
    key: "revenue_growth_1y_pct",
    label: "Revenue Growth (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "20%",
  },
  {
    key: "sustainable_growth_rate",
    label: "Sustainable Growth Rate",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "20%",
  },
];

// REWEIGHTED 2026-08-25 (goal: full scoring-architecture audit, user-directed): A/D rating
// raised to the top weight per explicit user direction (kept in this pillar rather than
// moved to Momentum, which this audit's own code-level analysis would otherwise have
// suggested - A/D is a volume-confirmed price-trend indicator by construction, but the
// user considers it this pillar's most important signal and that call stands).
// Institutional ownership cut from 55% - institutional_holdings_13f (4,166 rows, exactly 1
// per symbol) and institutional_ownership (0 rows) have no historical depth in this
// database, so the 55% weight could never be validated, and literature (Gompers & Metrick
// 2001 and related "smart money" work) treats institutional ownership mainly as a
// flow/change signal, not a level factor.
//
// REMOVED 2026-08-24: insider_ownership_pct (20% weight) dropped entirely - static
// governance/alignment metric, near-zero information content for this system's
// weeks-scale swing trading, recurring source of real bugs. See
// loaders/DEPRECATED_LOADERS.md. Weights below are re-normalized automatically by
// _score_positioning's weighted_sum/total_weight (no rebalancing needed here).
const POSITIONING_SCHEMA = [
  {
    key: "ad_rating",
    label: "A/D Rating",
    fmt: (v) => num(v, 1),
    used: true,
    weight: "35%",
  },
  {
    key: "institutional_ownership_pct",
    label: "Institutional Own %",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "30%",
  },
  {
    key: "short_interest_pct",
    label: "Short Interest %",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "25%",
  },
  // short_percent_of_float removed 20260816: loaders/load_positioning_metrics.py computes
  // it as short_shares / shares_outstanding, the same FINRA short_shares numerator and
  // (per that loader's own comment) "same denominator" short_interest_pct already uses -
  // a near-duplicate restatement of the field above it, not an independent signal.
  {
    key: "short_interest_pct_change",
    label: "Short Interest % Chg (MoM)",
    fmt: (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${num(v, 1)}%`),
    used: true,
    weight: "10%",
  },
  // top_10_institutions_pct/institutional_holders_count/shares_short_prior_month/
  // short_ratio cut 20260816 (second pass) - unweighted reference fields, don't feed
  // positioning_score.
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
// daily_std * sqrt(252), e.g. 0.15 for 15% - _score_stability's own 0.15/0.30/0.60 thresholds
// in load_stock_scores.py confirm this), same convention as debt_to_assets above, so they need
// the same *100 scaling pct() doesn't do itself. max_drawdown_1y is the odd one out here -
// _calculate_max_drawdown already multiplies by 100 (returns e.g. -25.5), so it's passed
// through as-is like the loader-pre-scaled *_pct fields in QUALITY_SCHEMA.
const STABILITY_SCHEMA = [
  {
    key: "volatility_60d",
    label: "Volatility (60D)",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "45%",
  },
  {
    key: "beta",
    label: "Beta vs Market",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "20%",
  },
  {
    key: "downside_volatility_60d",
    label: "Downside Volatility (60D)",
    fmt: (v) => pct(v == null ? null : v * 100, 2),
    used: true,
    weight: "15%",
  },
  {
    key: "max_drawdown_1y",
    label: "Max Drawdown (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "20%",
  },
  // volatility_12m/30d and downside_volatility_252d/30d removed 2026-08-25 - see comment
  // above.
  //
  // REWEIGHTED 2026-08-25 (goal: Fama-MacBeth factor-weighting pass, see
  // algo/research/fama_macbeth_price_factors.py): a monthly cross-sectional Fama-MacBeth
  // panel (126 months, 2016-2026) found volatility_60d the strongest, most robust
  // predictor of forward return in the whole panel (t=-6.07), while downside_volatility_60d
  // added no independent signal once volatility_60d was controlled for (t=+1.39, wrong-
  // signed) - consistent with the 2026-08-25 consolidation's own correlation finding.
  // Moved 10pts from downside_vol (25%->15%) to vol (35%->45%). See
  // _score_stability's docstring in load_stock_scores.py for the full writeup.
];
