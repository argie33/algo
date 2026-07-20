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

const scoreColor = (v) => {
  if (v == null || isNaN(Number(v))) return "var(--text-faint)";
  const n = Number(v);
  if (n >= 80) return "var(--success)";
  if (n >= 60) return "var(--cyan)";
  if (n >= 40) return "var(--amber)";
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
function InputsCard({ title, stock, schema }) {
  const rows = schema.map((s) => ({ ...s, value: stock[s.key] }));
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
        <InputsCard title="Quality & Fundamentals" stock={stock} schema={QUALITY_SCHEMA} />
        <InputsCard title="Momentum" stock={stock} schema={MOMENTUM_SCHEMA} />
        <InputsCard title="Value" stock={stock} schema={VALUE_SCHEMA} />
        <InputsCard title="Growth" stock={stock} schema={GROWTH_SCHEMA} />
        <InputsCard title="Positioning" stock={stock} schema={POSITIONING_SCHEMA} />
        <InputsCard title="Stability" stock={stock} schema={STABILITY_SCHEMA} />
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
  {
    key: "roe_pct",
    label: "ROE",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "avg",
    collected: true,
    note: "Equal-weight average with ROA, Operating Margin, Net Margin (quality_score formula).",
  },
  {
    key: "roa_val",
    label: "ROA",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "avg",
    collected: true,
  },
  {
    key: "operating_margin_val",
    label: "Operating Margin",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "avg",
    collected: true,
  },
  {
    key: "net_margin_val",
    label: "Profit Margin",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "avg",
    collected: true,
  },
  {
    key: "debt_to_assets_val",
    label: "Debt / Assets",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "avg",
    collected: true,
    note: "Added 2026-07-20: was previously computed nowhere despite stability_score having a standing 10% slot for it. Now feeds both this average and (via merge) the stability formula.",
  },
  {
    key: "debt_to_equity",
    label: "Debt / Equity",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "fallback",
    collected: true,
    note: "Only used when the precomputed quality_score is unavailable (~18% of stocks).",
  },
  {
    key: "current_ratio_val",
    label: "Current Ratio",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "fallback",
    collected: true,
    note: "Fallback-only input (only used when the precomputed quality_score is unavailable). Added 2026-07-20: was computed nowhere despite this standing formula slot; now sourced from annual_balance_sheet current_assets/current_liabilities.",
  },
  {
    key: "quick_ratio_val",
    label: "Quick Ratio",
    fmt: (v) => num(v, 2),
    used: false,
    collected: false,
    note: "Column exists and is fetched, but no scoring path (primary or fallback) uses it.",
  },
  {
    key: "interest_coverage_val",
    label: "Interest Coverage",
    fmt: (v) => num(v, 2),
    used: false,
    collected: false,
    note: "Display-only; the scoring loader never fetches this column.",
  },
];

const MOMENTUM_SCHEMA = [
  {
    key: "momentum_1m_val",
    label: "Momentum (1M)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "22%",
    collected: true,
  },
  {
    key: "momentum_3m_val",
    label: "Momentum (3M)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "22%",
    collected: true,
  },
  {
    key: "momentum_6m_val",
    label: "Momentum (6M)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "19%",
    collected: true,
  },
  {
    key: "momentum_12m_val",
    label: "Momentum (12M)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "12%",
    collected: true,
    note: "Only ~30% of stocks have 12M history populated; frequently shows \"No data\".",
  },
  {
    key: "tdd_rsi",
    label: "RSI (14)",
    fmt: (v) => num(v, 1),
    used: true,
    weight: "15%",
    collected: true,
    note: "Added 2026-07-20: momentum-following curve (not mean-reversion) — sustained strength scores well, only extreme overbought (>85) pulls back slightly.",
  },
  {
    key: "tdd_macd",
    label: "MACD",
    fmt: (v) => num(v, 3),
    used: true,
    weight: "10%",
    collected: true,
    note: "Added 2026-07-20: sign only, not magnitude (MACD's raw value scales with a stock's price level so isn't comparable across symbols) — used as a bull/bear trend-confirmation signal.",
  },
  { key: "current_price", label: "Current Price", fmt: (v) => `$${num(v, 2)}`, used: false, collected: true },
  { key: "change_percent", label: "1-Day Change", fmt: (v) => pct(v, 2), used: false, collected: true },
  { key: "high_52w_val", label: "52-Week High", fmt: (v) => `$${num(v, 2)}`, used: false, collected: true },
  { key: "price_vs_52w_high_val", label: "vs 52w High", fmt: (v) => pct(v, 2), used: false, collected: true },
  { key: "price_vs_sma_50", label: "vs 50-SMA", fmt: (v) => pct(v, 2), used: false, collected: true },
  { key: "price_vs_sma_200", label: "vs 200-SMA", fmt: (v) => pct(v, 2), used: false, collected: true },
  {
    key: "tdd_roc_20d",
    label: "20-Day ROC",
    fmt: (v) => pct(v, 2),
    used: false,
    collected: true,
    note: "Deliberately not scored — measures the same thing as Momentum 1M/3M/6M/12M (windowed % price return) and would double-weight that signal.",
  },
  { key: "tdd_roc_60d", label: "60-Day ROC", fmt: (v) => pct(v, 2), used: false, collected: true },
  { key: "tdd_roc_120d", label: "120-Day ROC", fmt: (v) => pct(v, 2), used: false, collected: true },
  { key: "tdd_roc_252d", label: "252-Day ROC", fmt: (v) => pct(v, 2), used: false, collected: true },
];

const VALUE_SCHEMA = [
  { key: "trailing_pe", label: "P/E", fmt: (v) => num(v, 2), used: true, weight: "45%", collected: true },
  { key: "price_to_book", label: "P/B", fmt: (v) => num(v, 2), used: true, weight: "20%", collected: true },
  {
    key: "ps_ratio_val",
    label: "P/S",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "15%",
    collected: true,
    note: "Added 2026-07-20: was previously fetched and displayed but never weighted.",
  },
  { key: "fcf_yield_val", label: "FCF Yield", fmt: (v) => pct(v, 2), used: true, weight: "12%", collected: true },
  {
    key: "dividend_yield",
    label: "Dividend Yield",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "8%",
    collected: false,
    note: "Formula weight is 8%, but live DB shows 0% of stocks have this populated — this weight is currently dead for the whole universe.",
  },
  { key: "peg_ratio_val", label: "PEG", fmt: (v) => num(v, 2), used: false, collected: false },
  { key: "market_cap", label: "Market Cap", fmt: money, used: false, collected: true },
];

const GROWTH_SCHEMA = [
  {
    key: "eps_growth_1y_val",
    label: "EPS Growth (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "33%",
    collected: true,
  },
  {
    key: "rev_growth_1y_val",
    label: "Revenue Growth (1Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "24%",
    collected: true,
  },
  {
    key: "eps_growth_3y_val",
    label: "EPS Growth (3Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "19%",
    collected: true,
  },
  {
    key: "rev_growth_3y_val",
    label: "Revenue Growth (3Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "14%",
    collected: true,
  },
  {
    key: "eps_growth_5y_val",
    label: "EPS Growth (5Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "5%",
    collected: true,
  },
  {
    key: "rev_growth_5y_val",
    label: "Revenue Growth (5Y)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "5%",
    collected: true,
    note: "Added 2026-07-20: was previously fetched and displayed but the formula gave it 0% weight.",
  },
];

const POSITIONING_SCHEMA = [
  {
    key: "inst_own_val",
    label: "Institutional Own %",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "55%",
    collected: false,
    note: "Highest-weighted positioning input, but live DB shows only 2 of 4,826 stocks have this populated — effectively dead for the whole universe right now.",
  },
  {
    key: "insider_own_val",
    label: "Insider Own %",
    fmt: (v) => pct(v, 1),
    used: true,
    weight: "20%",
    collected: true,
  },
  {
    key: "short_pct_val",
    label: "Short Interest %",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "25%",
    collected: true,
  },
  {
    key: "short_interest_trend_val",
    label: "Short Interest Trend",
    fmt: (v) => String(v),
    used: false,
    collected: true,
  },
  {
    key: "shares_short_prior_month_val",
    label: "Shares Short (Prior Mo)",
    fmt: (v) => (v ? Number(v).toLocaleString() : "—"),
    used: false,
    collected: false,
  },
];

const STABILITY_SCHEMA = [
  {
    key: "volatility_12m_val",
    label: "Volatility (12M)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "40%",
    collected: true,
  },
  {
    key: "volatility_60d_val",
    label: "Volatility (60D)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "20%",
    collected: true,
  },
  {
    key: "volatility_30d_val",
    label: "Volatility (30D)",
    fmt: (v) => pct(v, 2),
    used: true,
    weight: "15%",
    collected: true,
    note: "Added 2026-07-20: best-populated volatility column (98%+) but was previously fetched and never scored.",
  },
  { key: "beta_val", label: "Beta vs Market", fmt: (v) => num(v, 2), used: true, weight: "15%", collected: true },
  {
    key: "debt_to_assets_val",
    label: "Debt / Assets",
    fmt: (v) => num(v, 2),
    used: true,
    weight: "10%",
    collected: true,
    note: "Fixed 2026-07-20: was computed nowhere (0% populated), so this weight was dead. Now sourced from quality_metrics.debt_to_assets and merged into the stability formula.",
  },
];
