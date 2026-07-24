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
    missing_sec_data: "No SEC data",
    insufficient_history: "Insufficient history",
    no_analyst_estimates: "Analyst data unavailable",
    analyst_estimates_not_in_sec_filings: "Analyst data not in SEC",
    ebitda_not_extracted: "Not extracted",
    depreciation_amortization_not_loaded: "Depreciation/amortization not loaded",
    non_dividend_paying_stock: "Non-dividend payer",
    api_error: "Data fetch error",
    unprofitable_stock: "Unprofitable stock",
    missing_price_or_shares: "Missing price/shares",
    missing_finra_data: "FINRA data unavailable",
    missing_price_data: "Price data unavailable",
  };
  return reasonMap[reason] || reason;
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
  const reasonKey = row.key + "_unavailable_reason";
  const reason = row.reason || row.stock?.[reasonKey];
  const reasonDisplay = formatReasonDisplay(reason);

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
          <span className="muted" title={reason}>
            {reasonDisplay}
          </span>
        ) : row.collected === false ? (
          <span className="badge badge-amber" style={{ fontSize: "0.65rem" }}>
            Not yet available
          </span>
        ) : (
          <span className="muted">No data</span>
        )}
      </td>
    </tr>
  );
}

// ─── factor inputs card — always shows every field, grouped by tier ───────
function InputsCard({ title, stock, schema, inputsKey = null }) {
  const inputsObj = inputsKey ? stock[inputsKey] : stock;
  const rows = schema.map((s) => ({
    ...s,
    value: inputsObj?.[s.key],
    reason: inputsObj?.[s.key + "_unavailable_reason"]
  }));
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
        Cyan tag = weight in the live scoring formula · amber &quot;Not yet available&quot; = this
        metric is not populated for any stock yet (system-wide data gap, not just this one) ·
        plain &quot;No data&quot; = tracked but missing for this stock only.
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
// plus a live-DB column-population audit (2026-07-20) to flag fields that are
// queried/displayed but essentially never populated for any stock ("not yet
// available" rather than an ordinary per-stock null).
//
// used: true  -> this field is a genuine input to the score formula
// weight: display string for the "Used in Score" badge
// collected: false -> live-DB audit found ~0% population across the whole
//   universe (i.e. this isn't a per-stock gap, the pipeline doesn't produce it)

const QUALITY_SCHEMA = [
  { key: 'return_on_equity_pct',           label: 'ROE',                      fmt: v => pct(v, 1), used: true, weight: '20%' },
  { key: 'return_on_assets_pct',           label: 'ROA',                      fmt: v => pct(v, 1), used: true, weight: '15%' },
  { key: 'return_on_invested_capital_pct', label: 'ROIC',                     fmt: v => pct(v, 1), used: true, weight: '15%' },
  { key: 'profit_margin_pct',              label: 'Profit Margin',            fmt: v => pct(v, 1), used: true, weight: '20%' },
  { key: 'operating_margin_pct',           label: 'Operating Margin',         fmt: v => pct(v, 1), used: true, weight: '15%' },
  { key: 'debt_to_equity',                 label: 'Debt / Equity',            fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'gross_margin_pct',               label: 'Gross Margin',             fmt: v => pct(v, 1) },
  { key: 'ebitda_margin_pct',              label: 'EBITDA Margin',            fmt: v => pct(v, 1) },
  { key: 'fcf_to_net_income',              label: 'FCF / Net Income',         fmt: v => num(v, 2) },
  { key: 'operating_cf_to_net_income',     label: 'OCF / Net Income',         fmt: v => num(v, 2) },
  { key: 'current_ratio',                  label: 'Current Ratio',            fmt: v => num(v, 2) },
  { key: 'quick_ratio',                    label: 'Quick Ratio',              fmt: v => num(v, 2) },
  { key: 'interest_coverage',              label: 'Interest Coverage',        fmt: v => num(v, 2) },
  { key: 'debt_to_assets',                 label: 'Debt to Assets',           fmt: v => pct(v, 1) },
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
  { key: 'earnings_growth_pct',            label: 'Earnings Growth',          fmt: v => pct(v, 2) },
  { key: 'revenue_growth_pct',             label: 'Revenue Growth',           fmt: v => pct(v, 2) },
  { key: 'earnings_growth_4q_avg',         label: 'Earnings Growth 4Q Avg',   fmt: v => pct(v, 2) },
];

const MOMENTUM_SCHEMA = [
  { key: 'momentum_3m', label: 'Momentum (3M)', fmt: v => pct(v, 2), used: true, weight: '25%' },
  { key: 'momentum_6m', label: 'Momentum (6M)', fmt: v => pct(v, 2), used: true, weight: '25%' },
  { key: 'momentum_12_3', label: 'Momentum (12M)', fmt: v => pct(v, 2), used: true, weight: '25%' },
  { key: 'rsi', label: 'RSI (14)', fmt: v => num(v, 1), used: true, weight: '15%' },
  { key: 'macd', label: 'MACD Line', fmt: v => num(v, 3), used: true, weight: '10%' },
  { key: 'price_vs_52w_high', label: 'Price vs 52W High', fmt: v => pct(v, 2) },
  { key: 'price_vs_sma_50', label: 'Price vs 50-SMA', fmt: v => pct(v, 2) },
  { key: 'price_vs_sma_200', label: 'Price vs 200-SMA', fmt: v => pct(v, 2) },
  { key: 'current_price', label: 'Current Price', fmt: v => `$${num(v, 2)}` },
];

const VALUE_SCHEMA = [
  { key: 'stock_pe', label: 'P/E', fmt: v => num(v, 2), used: true, weight: '20%' },
  { key: 'stock_forward_pe', label: 'Forward P/E', fmt: v => num(v, 2) },
  { key: 'stock_pb', label: 'P/B', fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'stock_ps', label: 'P/S', fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'stock_ev_ebitda', label: 'EV / EBITDA', fmt: v => num(v, 2) },
  { key: 'stock_ev_revenue', label: 'EV / Revenue', fmt: v => num(v, 2) },
  { key: 'peg_ratio', label: 'PEG', fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'stock_dividend_yield', label: 'Dividend Yield', fmt: v => pct(v == null ? null : v * 100, 2) },
  { key: 'fcf_yield', label: 'FCF Yield', fmt: v => pct(v, 2), used: true, weight: '20%' },
];

const GROWTH_SCHEMA = [
  { key: 'revenue_growth_1y_pct',      label: 'Revenue Growth (1Y)',     fmt: v => pct(v, 2), used: true, weight: '20%' },
  { key: 'eps_growth_1y_pct',          label: 'EPS Growth (1Y)',         fmt: v => pct(v, 2), used: true, weight: '20%' },
  { key: 'revenue_growth_3y_cagr',     label: 'Revenue CAGR (3Y)',       fmt: v => pct(v, 2), used: true, weight: '20%' },
  { key: 'eps_growth_3y_cagr',         label: 'EPS CAGR (3Y)',           fmt: v => pct(v, 2), used: true, weight: '20%' },
  { key: 'revenue_growth_5y_cagr',     label: 'Revenue CAGR (5Y)',       fmt: v => pct(v, 2), used: true, weight: '10%' },
  { key: 'eps_growth_5y_cagr',         label: 'EPS CAGR (5Y)',           fmt: v => pct(v, 2), used: true, weight: '10%' },
  { key: 'net_income_growth_yoy',      label: 'Net Income Growth YoY',   fmt: v => pct(v, 2) },
  { key: 'operating_income_growth_yoy',label: 'Op Income Growth YoY',    fmt: v => pct(v, 2) },
  { key: 'gross_margin_trend',         label: 'Gross Margin Trend',      fmt: v => `${num(v, 2)} pp` },
  { key: 'operating_margin_trend',     label: 'Op Margin Trend',         fmt: v => `${num(v, 2)} pp` },
  { key: 'net_margin_trend',           label: 'Net Margin Trend',        fmt: v => `${num(v, 2)} pp` },
  { key: 'roe_trend',                  label: 'ROE Trend',               fmt: v => num(v, 2) },
  { key: 'sustainable_growth_rate',    label: 'Sustainable Growth Rate', fmt: v => pct(v, 2) },
  { key: 'quarterly_growth_momentum',  label: 'Quarterly Growth Mom',    fmt: v => `${num(v, 2)} pp` },
  { key: 'fcf_growth_yoy',             label: 'FCF Growth YoY',          fmt: v => pct(v, 2) },
  { key: 'ocf_growth_yoy',             label: 'OCF Growth YoY',          fmt: v => pct(v, 2) },
  { key: 'asset_growth_yoy',           label: 'Asset Growth YoY',        fmt: v => pct(v, 2) },
];

const POSITIONING_SCHEMA = [
  { key: 'institutional_ownership_pct', label: 'Institutional Own %', fmt: v => pct(v, 1), used: true, weight: '35%' },
  { key: 'insider_ownership_pct',       label: 'Insider Own %',       fmt: v => pct(v, 1), used: true, weight: '30%' },
  { key: 'short_interest_pct',          label: 'Short Interest %',    fmt: v => pct(v, 2), used: true, weight: '35%' },
  { key: 'top_10_institutions_pct',     label: 'Top 10 Institutions %', fmt: v => pct(v, 1) },
  { key: 'institutional_holders_count', label: 'Institutional Holders', fmt: v => num(v, 0) },
  { key: 'short_percent_of_float',      label: 'Short % of Float',    fmt: v => pct(v, 1) },
  { key: 'short_interest_trend',        label: 'Short Interest Trend', fmt: v => num(v, 1) },
  { key: 'shares_short_prior_month',    label: 'Shares Short (Prior Month)', fmt: v => num(v, 0) },
  { key: 'short_ratio',                 label: 'Days to Cover',       fmt: v => Number(v) < 99999 ? num(v, 2) : '—' },
  { key: 'ad_rating',                   label: 'A/D Rating',          fmt: v => num(v, 1) },
];

const STABILITY_SCHEMA = [
  { key: 'volatility_12m',           label: 'Volatility (12M)',     fmt: v => pct(v, 2), used: true, weight: '35%' },
  { key: 'volatility_60d',           label: 'Volatility (60D)',     fmt: v => pct(v, 2), used: true, weight: '18%' },
  { key: 'volatility_30d',           label: 'Volatility (30D)',     fmt: v => pct(v, 2), used: true, weight: '12%' },
  { key: 'beta',                     label: 'Beta vs Market',       fmt: v => num(v, 2), used: true, weight: '15%' },
  { key: 'debt_to_assets',           label: 'Debt to Assets',       fmt: v => pct(v, 1), used: true, weight: '10%' },
];
