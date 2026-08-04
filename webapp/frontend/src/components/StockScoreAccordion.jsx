import React, { useState, useEffect } from "react";
import { Star, Activity, DollarSign, TrendingUp, Users, Shield, Inbox } from "lucide-react";
import {
  formatNumber,
  formatPercentageChange,
  formatCurrency,
} from "../utils/formatters";
import { api } from "../services/api";

const num = (v, dp = 1) => formatNumber(v, dp);
const pct = (v, dp = 2) => formatPercentageChange(v, dp);
const money = (v) => formatCurrency(v);

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
    depreciation_amortization_not_loaded: "Depreciation/amortization not loaded",
    non_dividend_paying_stock: "Non-dividend payer",
    api_error: "Data fetch error",
    unprofitable_stock: "Company unprofitable",
    missing_price_or_shares: "Missing price/shares",
    missing_finra_data: "FINRA data unavailable",
    missing_price_data: "Price data unavailable",
    institutional_data_not_available: "Institutional data not available",
    short_float_data_not_calculated: "Short float metrics not calculated",
    ad_rating_not_available: "A/D rating not available",
    no_dividend_paying_stock: "Non-dividend payer",
    reit_special_entity: "REIT/special entity - different accounting",
    foreign_20f_filer: "Foreign 20-F filer - XBRL data limited",
    bank_special_reporting: "Financial institution - alternative metrics",
    insufficient_prior_year_data: "Prior fiscal year data unavailable",
    no_segment_disclosure: "Single-segment filer",
  };
  return reasonMap[reason] || reason;
};

// Detailed reason tooltips (hover text)
const reasonTooltips = {
  missing_sec_data: "This metric requires SEC filing data that is not available for this company type",
  non_dividend_paying_stock: "This company does not pay dividends",
  insufficient_history: "Requires historical data for calculation (typically 2+ years)",
  no_analyst_estimates: "External analyst estimates not loaded from data providers",
  unprofitable_stock: "Metric is undefined when company has negative earnings",
  missing_price_data: "Historical price data not yet available",
  institutional_data_not_available: "Institutional holding data not available for this stock",
  reit_special_entity: "REITs and special entities use different accounting; traditional financial metrics may not apply",
  foreign_20f_filer: "Foreign companies filing 20-F use different XBRL data structure; full metrics extraction limited",
  bank_special_reporting: "Banks and financial institutions use specialized accounting; different metrics apply",
  insufficient_prior_year_data: "This company's prior fiscal year filing doesn't report the comparison figure needed for this trend/growth calculation",
};

const FACTORS = [
  { key: "quality", label: "Quality", scoreKey: "quality_score", icon: Star },
  { key: "momentum", label: "Momentum", scoreKey: "momentum_score", icon: Activity },
  { key: "value", label: "Value", scoreKey: "value_score", icon: DollarSign },
  { key: "growth", label: "Growth", scoreKey: "growth_score", icon: TrendingUp },
  { key: "positioning", label: "Positioning", scoreKey: "positioning_score", icon: Users },
  { key: "stability", label: "Stability", scoreKey: "stability_score", icon: Shield },
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
          <div className="t-xs" style={{ color: "var(--danger)", padding: "var(--space-3)" }}>
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
                  <th className="num" style={{ width: 70 }}>Score</th>
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
        <div className="flex items-center gap-2" style={{ marginBottom: "var(--space-3)" }}>
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
          <span className={`badge ${scoreClass(score)}`} style={{ marginLeft: "auto" }}>
            {num(score, 1)}
          </span>
        </div>
        <div className="flex flex-col" style={{ gap: 4 }}>
          <div className="flex" style={{ fontSize: "var(--t-2xs)" }}>
            <span className="muted" style={{ minWidth: 80 }}>Sector avg</span>
            <span className="mono tnum" style={{ flex: 1, textAlign: "right" }}>
              {sectorAvg != null ? `${num(sectorAvg, 1)} (${diff(sectorAvg)})` : "—"}
            </span>
          </div>
          <div className="flex" style={{ fontSize: "var(--t-2xs)" }}>
            <span className="muted" style={{ minWidth: 80 }}>Market avg</span>
            <span className="mono tnum" style={{ flex: 1, textAlign: "right" }}>
              {marketAvg != null ? `${num(marketAvg, 1)} (${diff(marketAvg)})` : "—"}
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
    if (row.key && row.key !== "consecutive_positive_quarters" && row.key !== "price_vs_52w_high") {
      // Only log once per unique key to avoid spam
      const logKey = `no_reason_${row.key}`;
      if (!window._inputRowLogCache) window._inputRowLogCache = {};
      if (!window._inputRowLogCache[logKey]) {
        window._inputRowLogCache[logKey] = true;
        console.debug(`[InputRow] No value/reason for ${row.key}, reason=${reason}, collected=${row.collected}`);
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
          <span className="muted" title="Data tracked but missing for this stock">No data</span>
        )}
      </td>
    </tr>
  );
}

// ─── factor inputs card — always shows every field, grouped by tier ───────
function InputsCard({ title, stock, schema, inputsKey = null }) {
  const inputsObj = inputsKey ? stock?.[inputsKey] : stock;

  // DIAGNOSTIC: Log if inputsObj is missing (helps debug "No data" issues)
  if (!inputsObj && inputsKey) {
    console.warn(`[InputsCard] Missing factor inputs for ${inputsKey} on ${stock?.symbol || "unknown"}. Stock keys: ${stock ? Object.keys(stock).slice(0, 10).join(", ") : "N/A"}`);
  }

  const rows = schema.map((s) => {
    const value = inputsObj?.[s.key];
    const reason = inputsObj?.[s.key + "_unavailable_reason"];
    // DIAGNOSTIC: Log missing reason fields that have null values
    if (!value && !reason && inputsObj) {
      console.debug(`[InputsCard] No reason for ${s.key} on ${stock?.symbol || "unknown"}`);
    }
    return { ...s, value, reason };
  });
  const used = rows.filter((r) => r.used);
  const tracked = rows.filter((r) => !r.used);

  return (
    <div className="card">
      <div className="card-head">
        <div
          className="card-title"
          style={{ fontSize: "var(--t-xs)", textTransform: "uppercase", letterSpacing: "0.3px" }}
        >
          {title}
        </div>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        <table className="data-table">
          <tbody>
            {used.length > 0 && (
              <tr>
                <td
                  colSpan={2}
                  className="t-2xs muted"
                  style={{ background: "var(--surface-2)", fontWeight: "var(--w-semibold)" }}
                >
                  Used in Score
                </td>
              </tr>
            )}
            {used.map((r) => (
              <InputRow key={r.key} row={r} />
            ))}
            {tracked.length > 0 && (
              <tr>
                <td
                  colSpan={2}
                  className="t-2xs muted"
                  style={{ background: "var(--surface-2)", fontWeight: "var(--w-semibold)" }}
                >
                  Tracked (Not Scored)
                </td>
              </tr>
            )}
            {tracked.map((r) => (
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
          <span className="t-xs muted">RS percentile {num(stock.rs_percentile, 0)}</span>
        )}
        {stock.last_updated && (
          <span className="t-xs muted" style={{ marginLeft: "auto" }}>
            Updated {new Date(stock.last_updated).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Factor scores vs sector/market */}
      <div className="eyebrow" style={{ marginBottom: "var(--space-2)" }}>
        Factor Scores vs Sector &amp; Market
      </div>
      <div className="grid grid-3 gap-3" style={{ marginBottom: "var(--space-5)" }}>
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
          • <strong style={{ color: "var(--success)" }}>Value</strong> = data available for this stock
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong style={{ color: "var(--text-faint)" }}>No SEC data</strong> = SEC doesn't require this disclosure for all company types
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong style={{ color: "var(--text-faint)" }}>Non-dividend payer</strong> = stock characteristic, not a data gap
        </div>
        <div style={{ marginBottom: "4px" }}>
          • <strong style={{ color: "var(--text-faint)" }}>No data</strong> = metric tracked but missing for this stock
        </div>
        <div>
          • <strong className="badge badge-amber" style={{ fontSize: "0.65rem", padding: "1px 3px" }}>Not yet available</strong> = system-wide gap (no stock has this yet)
        </div>
      </div>
      <div className="grid grid-3 gap-3" style={{ marginBottom: "var(--space-5)" }}>
        <InputsCard title="Quality & Fundamentals" stock={stock} schema={QUALITY_SCHEMA} inputsKey="quality_inputs" />
        <InputsCard title="Momentum" stock={stock} schema={MOMENTUM_SCHEMA} inputsKey="momentum_inputs" />
        <InputsCard title="Value" stock={stock} schema={VALUE_SCHEMA} inputsKey="value_inputs" />
        <InputsCard title="Growth" stock={stock} schema={GROWTH_SCHEMA} inputsKey="growth_inputs" />
        <InputsCard title="Positioning" stock={stock} schema={POSITIONING_SCHEMA} inputsKey="positioning_inputs" />
        <InputsCard title="Stability" stock={stock} schema={STABILITY_SCHEMA} inputsKey="stability_inputs" />
      </div>

      {/* Recent trading signals */}
      <div className="eyebrow" style={{ marginBottom: "var(--space-2)" }}>
        Recent Trading Signals
      </div>
      <SignalsForStock symbol={stock.symbol} />
    </div>
  );
}

const StockScoreAccordion = ({ stocks = [], marketAvgs = {}, sectorAvgs = {} }) => {
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
// ocf_to_net_income). debt_to_equity is NOT read anywhere in quality scoring at all -
// it's a real input, but to the Financial Stability sub-score under the Stability tab
// (_score_financial_stability, 30% of that sub-score's own internal weighting) - so its
// weight badge here was attributing a real, live-used input to the wrong factor
// entirely. ROIC/FCF-to-NI/OCF-to-NI are real inputs but are bounded +/- point
// adjustments, not proportional weights, hence the "adj" labels below instead of a %.
const QUALITY_SCHEMA = [
  { key: 'return_on_equity_pct',           label: 'ROE',                      fmt: v => pct(v, 1), used: true, weight: '~17%' },
  { key: 'return_on_assets_pct',           label: 'ROA',                      fmt: v => pct(v, 1), used: true, weight: '~17%' },
  { key: 'return_on_invested_capital_pct', label: 'ROIC',                     fmt: v => pct(v, 1), used: true, weight: '±3 adj' },
  { key: 'profit_margin_pct',              label: 'Profit Margin',            fmt: v => pct(v, 1), used: true, weight: '~17%' },
  { key: 'operating_margin_pct',           label: 'Operating Margin',         fmt: v => pct(v, 1), used: true, weight: '~17%' },
  { key: 'debt_to_equity',                 label: 'Debt / Equity',            fmt: v => num(v, 2) },
  { key: 'gross_margin_pct',               label: 'Gross Margin',             fmt: v => pct(v, 1), used: true, weight: '±3 adj' },
  { key: 'ebitda_margin_pct',              label: 'EBITDA Margin',            fmt: v => pct(v, 1), used: true, weight: '±3 adj' },
  { key: 'fcf_to_net_income',              label: 'FCF / Net Income',         fmt: v => num(v, 2), used: true, weight: '±2 adj' },
  { key: 'operating_cf_to_net_income',     label: 'OCF / Net Income',         fmt: v => num(v, 2), used: true, weight: '±2 adj' },
  { key: 'current_ratio',                  label: 'Current Ratio',            fmt: v => num(v, 2) },
  { key: 'quick_ratio',                    label: 'Quick Ratio',              fmt: v => num(v, 2) },
  { key: 'interest_coverage',              label: 'Interest Coverage',        fmt: v => num(v, 2), used: true, weight: '~17%' },
  { key: 'debt_to_assets',                 label: 'Debt to Assets',           fmt: v => pct(v, 1), used: true, weight: '~17%' },
  { key: 'earnings_surprise_avg',          label: 'Earnings Surprise (4Q)',   fmt: v => pct(v, 2) },
  { key: 'eps_growth_stability',           label: 'EPS Growth Stability',     fmt: v => num(v, 2) },
  { key: 'earnings_beat_rate',             label: 'Earnings Beat Rate',       fmt: v => pct(v, 1) },
  { key: 'consecutive_positive_quarters',  label: 'Consecutive +Q',           fmt: v => num(v, 0) },
  { key: 'estimate_revision_direction',    label: 'Revision Direction',       fmt: v => num(v, 1) },
  { key: 'revision_activity_30d',          label: 'Revision Activity 30d',    fmt: v => num(v, 1) },
  { key: 'estimate_momentum_60d',          label: 'Estimate Momentum 60d',    fmt: v => pct(v, 2) },
  { key: 'estimate_momentum_90d',          label: 'Estimate Momentum 90d',    fmt: v => pct(v, 2) },
  { key: 'revision_trend_score',           label: 'Revision Trend',           fmt: v => num(v, 1) },
  { key: 'payout_ratio',                   label: 'Payout Ratio',             fmt: v => pct(v, 1) },
  { key: 'free_cashflow',                  label: 'Free Cash Flow',           fmt: money },
  { key: 'operating_cashflow',             label: 'Operating Cash Flow',      fmt: money },
  { key: 'total_debt',                     label: 'Total Debt',               fmt: money },
  { key: 'total_cash',                     label: 'Total Cash',               fmt: money },
  { key: 'cash_per_share',                 label: 'Cash / Share',             fmt: v => `$${num(v, 2)}` },
  { key: 'earnings_growth_4q_avg',         label: 'Earnings Growth 4Q Avg',   fmt: v => pct(v, 2) },
];

// FIXED 2026-08-04: momentum_score (load_stock_scores.py::_score_momentum) weights were
// stale here (25%/25%/25% for 3m/6m/12m) vs. the code's actual 16%/14%/9%, and
// momentum_1m (16% weight - tied for the second-highest input in the whole formula) was
// missing from this schema entirely despite being fetched by the API (scores.py
// momentum_1m_val) - a real, live-used, meaningfully-weighted score input was completely
// invisible on the scores page. Also added the ROC composite (avg of roc_20d/60d/120d/
// 252d, 12%) and SMA composite (avg of price_vs_sma_50/200, 8%) weight badges - both
// real inputs that were displayed as plain unweighted numbers before.
const MOMENTUM_SCHEMA = [
  { key: 'momentum_1m', label: 'Momentum (1M)', fmt: v => pct(v, 2), used: true, weight: '16%' },
  { key: 'momentum_3m', label: 'Momentum (3M)', fmt: v => pct(v, 2), used: true, weight: '16%' },
  { key: 'momentum_6m', label: 'Momentum (6M)', fmt: v => pct(v, 2), used: true, weight: '14%' },
  { key: 'momentum_12_3', label: 'Momentum (12M)', fmt: v => pct(v, 2), used: true, weight: '9%' },
  { key: 'rsi', label: 'RSI (14)', fmt: v => num(v, 1), used: true, weight: '15%' },
  { key: 'macd', label: 'MACD Line', fmt: v => num(v, 3), used: true, weight: '10%' },
  { key: 'price_vs_52w_high', label: 'Price vs 52W High', fmt: v => pct(v, 2) },
  { key: 'price_vs_sma_50', label: 'Price vs 50-SMA', fmt: v => pct(v, 2), used: true, weight: '8% avg' },
  { key: 'price_vs_sma_200', label: 'Price vs 200-SMA', fmt: v => pct(v, 2), used: true, weight: '8% avg' },
  { key: 'current_price', label: 'Current Price', fmt: v => `$${num(v, 2)}` },
];

// FIXED 2026-08-04: value_score (load_stock_scores.py::_score_value) weight badges were
// stale here vs. the code's actual constants (P/E 45% not 20%, P/B 20% not 15%, FCF
// Yield 12% not 20%), and dividend_yield (8% weight, a real input since migration 1146)
// was displayed as a plain unweighted number despite being scored.
const VALUE_SCHEMA = [
  { key: 'market_cap', label: 'Market Cap', fmt: money },
  { key: 'stock_pe', label: 'P/E', fmt: v => num(v, 2), used: true, weight: '45%' },
  { key: 'stock_forward_pe', label: 'Forward P/E', fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'stock_pb', label: 'P/B', fmt: v => num(v, 2), used: true, weight: '20%' },
  { key: 'stock_ps', label: 'P/S', fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'stock_ev_ebitda', label: 'EV / EBITDA', fmt: v => num(v, 2), used: true, weight: '12%' },
  { key: 'stock_ev_revenue', label: 'EV / Revenue', fmt: v => num(v, 2), used: true, weight: '10%' },
  { key: 'peg_ratio', label: 'PEG', fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'stock_dividend_yield', label: 'Dividend Yield', fmt: v => pct(v == null ? null : v * 100, 2), used: true, weight: '8%' },
  { key: 'fcf_yield', label: 'FCF Yield', fmt: v => pct(v, 2), used: true, weight: '12%' },
];

const GROWTH_SCHEMA = [
  { key: 'revenue_growth_1y_pct',      label: 'Revenue Growth (1Y)',     fmt: v => pct(v, 2), used: true, weight: '24%' },
  { key: 'eps_growth_1y_pct',          label: 'EPS Growth (1Y)',         fmt: v => pct(v, 2), used: true, weight: '33%' },
  { key: 'revenue_growth_3y_cagr',     label: 'Revenue CAGR (3Y)',       fmt: v => pct(v, 2), used: true, weight: '14%' },
  { key: 'eps_growth_3y_cagr',         label: 'EPS CAGR (3Y)',           fmt: v => pct(v, 2), used: true, weight: '19%' },
  { key: 'revenue_growth_5y_cagr',     label: 'Revenue CAGR (5Y)',       fmt: v => pct(v, 2), used: true, weight: '5%' },
  { key: 'eps_growth_5y_cagr',         label: 'EPS CAGR (5Y)',           fmt: v => pct(v, 2), used: true, weight: '5%' },
  { key: 'net_income_growth_yoy',      label: 'Net Income Growth YoY',   fmt: v => pct(v, 2), used: true, weight: '8%' },
  { key: 'operating_income_growth_yoy',label: 'Op Income Growth YoY',    fmt: v => pct(v, 2), used: true, weight: '6%' },
  { key: 'gross_margin_trend',         label: 'Gross Margin Trend',      fmt: v => `${num(v, 2)} pp`, used: true, weight: '3%' },
  { key: 'operating_margin_trend',     label: 'Op Margin Trend',         fmt: v => `${num(v, 2)} pp`, used: true, weight: '3%' },
  { key: 'net_margin_trend',           label: 'Net Margin Trend',        fmt: v => `${num(v, 2)} pp`, used: true, weight: '3%' },
  { key: 'roe_trend',                  label: 'ROE Trend',               fmt: v => num(v, 2), used: true, weight: '3%' },
  { key: 'sustainable_growth_rate',    label: 'Sustainable Growth Rate', fmt: v => pct(v, 2), used: true, weight: '6%' },
  // FIXED 2026-08-04: previously flagged collected:false ("quality_metrics.quarterly_growth_momentum
  // is 0/5682 populated, no computation path exists") - that was true only of
  // load_value_quality_growth_metrics.py. load_enhanced_quality_growth_metrics.py (wired into the
  // metrics pipeline as of 548dc99f5) computes this from quarterly_income_statement and writes it
  // into growth_metrics.quarterly_growth_momentum - live-verified real non-NULL value for AAPL.
  // Per-symbol "No data" now means a genuine per-stock gap (e.g. <4 quarters of history), not a
  // system-wide dead field.
  { key: 'quarterly_growth_momentum',  label: 'Quarterly Growth Mom',    fmt: v => `${num(v, 2)} pp` },
  { key: 'fcf_growth_yoy',             label: 'FCF Growth YoY',          fmt: v => pct(v, 2), used: true, weight: '6%' },
  { key: 'ocf_growth_yoy',             label: 'OCF Growth YoY',          fmt: v => pct(v, 2), used: true, weight: '4%' },
  { key: 'asset_growth_yoy',           label: 'Asset Growth YoY',        fmt: v => pct(v, 2), used: true, weight: '5%' },
  { key: 'earnings_growth_4q_avg',     label: 'Earnings Growth 4Q Avg',  fmt: v => pct(v, 2) },
];

// FIXED 2026-08-04: positioning_score (load_stock_scores.py::_score_positioning) weight
// badges were stale here vs. the code's actual constants (institutional 55% not 35%,
// insider 20% not 30%, short interest 25% not 35%), and ad_rating (15% weight, wired
// into positioning_score by commit 2bd12fcb5 the same day) was still shown as a plain
// unweighted number - the display never caught up with that fix.
const POSITIONING_SCHEMA = [
  { key: 'institutional_ownership_pct', label: 'Institutional Own %', fmt: v => pct(v, 1), used: true, weight: '55%' },
  { key: 'insider_ownership_pct',       label: 'Insider Own %',       fmt: v => pct(v, 1), used: true, weight: '20%' },
  { key: 'short_interest_pct',          label: 'Short Interest %',    fmt: v => pct(v, 2), used: true, weight: '25%' },
  { key: 'top_10_institutions_pct',     label: 'Top 10 Institutions %', fmt: v => pct(v, 1) },
  { key: 'institutional_holders_count', label: 'Institutional Holders', fmt: v => num(v, 0) },
  { key: 'short_percent_of_float',      label: 'Short % of Shares O/S', fmt: v => pct(v, 1) },
  { key: 'short_interest_trend',        label: 'Short Interest Trend', fmt: v => v == null ? '—' : v.charAt(0).toUpperCase() + v.slice(1), used: true, weight: '10%' },
  { key: 'shares_short_prior_month',    label: 'Shares Short (Prior Month)', fmt: v => num(v, 0) },
  { key: 'short_ratio',                 label: 'Days to Cover',       fmt: v => Number(v) < 99999 ? num(v, 2) : '—' },
  { key: 'ad_rating',                   label: 'A/D Rating',          fmt: v => num(v, 1), used: true, weight: '15%' },
];

// FIXED 2026-08-04: volatility weight badges were stale vs. _score_stability's actual
// constants (252d/"12M" 40% not 35%, 60D 20% not 18%, 30D 15% not 12%).
//
// FIXED 2026-08-04 (second pass): debt_to_assets/debt_to_equity/current_ratio/
// quick_ratio/cash_per_share all feed _score_financial_stability, a sub-score that is
// itself 20% of overall Stability (_score_stability) - not flat top-level weights, so
// they're labeled "part of 20%" rather than a fabricated precise percentage (their
// internal 30%/30%(avg of current+quick)/25%/15% split self-normalizes over whichever
// of the four are present, same as every other self-normalizing weight group in this
// file). debt_to_equity/current_ratio/quick_ratio/cash_per_share were previously only
// surfaced under the Quality tab's quality_inputs (unweighted there too, since none of
// them feed quality_score) and were completely absent from stability_inputs - added
// server-side in lambda/api/routes/scores.py (already-selected columns, no new SQL).
const STABILITY_SCHEMA = [
  { key: 'volatility_12m',           label: 'Volatility (12M)',     fmt: v => pct(v, 2), used: true, weight: '40%' },
  { key: 'volatility_60d',           label: 'Volatility (60D)',     fmt: v => pct(v, 2), used: true, weight: '20%' },
  { key: 'volatility_30d',           label: 'Volatility (30D)',     fmt: v => pct(v, 2), used: true, weight: '15%' },
  { key: 'beta',                     label: 'Beta vs Market',       fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'debt_to_assets',           label: 'Debt to Assets',       fmt: v => pct(v, 1), used: true, weight: 'part of 20%' },
  { key: 'debt_to_equity',           label: 'Debt / Equity',        fmt: v => num(v, 2), used: true, weight: 'part of 20%' },
  { key: 'current_ratio',            label: 'Current Ratio',        fmt: v => num(v, 2), used: true, weight: 'part of 20%' },
  { key: 'quick_ratio',              label: 'Quick Ratio',          fmt: v => num(v, 2), used: true, weight: 'part of 20%' },
  { key: 'cash_per_share',           label: 'Cash / Share',         fmt: v => `$${num(v, 2)}`, used: true, weight: 'part of 20%' },
  { key: 'downside_volatility_252d', label: 'Downside Volatility (252D)', fmt: v => pct(v, 2), used: true, weight: '15%' },
  { key: 'downside_volatility_60d',  label: 'Downside Volatility (60D)',  fmt: v => pct(v, 2) },
  { key: 'downside_volatility_30d',  label: 'Downside Volatility (30D)',  fmt: v => pct(v, 2) },
  { key: 'max_drawdown_1y',          label: 'Max Drawdown (1Y)',     fmt: v => pct(v, 2), used: true, weight: '10%' },
  { key: 'revenue_concentration_hhi', label: 'Revenue Concentration (HHI)', fmt: v => v == null ? '—' : Math.round(v).toLocaleString(), used: true, weight: '10%' },
  { key: 'segment_count',            label: 'Business Segments',    fmt: v => num(v, 0) },
  { key: 'largest_segment_revenue_pct', label: 'Largest Segment %', fmt: v => pct(v, 1) },
  { key: 'is_diversified',           label: 'Diversified',          fmt: v => v == null ? '—' : (v ? 'Yes' : 'No') },
];
