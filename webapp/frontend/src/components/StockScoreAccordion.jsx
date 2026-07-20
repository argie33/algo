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

// ─── factor inputs card ─────────────────────────────────────────────────────
function InputsCard({ title, stock, schema }) {
  const rows = schema
    .map((s) => ({ ...s, value: stock[s.key] }))
    .filter((r) => r.value != null && typeof r.fmt === "function");

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
        {rows.length === 0 ? (
          <div className="t-xs muted" style={{ padding: "var(--space-3)" }}>
            No detailed metrics available
          </div>
        ) : (
          <table className="data-table">
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className="t-xs">{r.label}</td>
                  <td className="num mono tnum t-xs">{r.fmt(r.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
      <div className="eyebrow" style={{ marginBottom: "var(--space-2)" }}>
        Detailed Factor Inputs
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

// ─── Input Schemas — every factor input the API returns ───────────────────
const QUALITY_SCHEMA = [
  { key: "roe_pct", label: "ROE", fmt: (v) => pct(v, 1) },
  { key: "roa_val", label: "ROA", fmt: (v) => pct(v, 1) },
  { key: "debt_to_equity", label: "Debt / Equity", fmt: (v) => num(v, 2) },
  { key: "current_ratio_val", label: "Current Ratio", fmt: (v) => num(v, 2) },
  { key: "quick_ratio_val", label: "Quick Ratio", fmt: (v) => num(v, 2) },
  { key: "interest_coverage_val", label: "Interest Coverage", fmt: (v) => num(v, 2) },
  { key: "operating_margin_val", label: "Operating Margin", fmt: (v) => pct(v, 1) },
  { key: "net_margin_val", label: "Profit Margin", fmt: (v) => pct(v, 1) },
];

const MOMENTUM_SCHEMA = [
  { key: "current_price", label: "Current Price", fmt: (v) => `$${num(v, 2)}` },
  { key: "change_percent", label: "1-Day Change", fmt: (v) => pct(v, 2) },
  { key: "high_52w_val", label: "52-Week High", fmt: (v) => `$${num(v, 2)}` },
  { key: "price_vs_52w_high_val", label: "vs 52w High", fmt: (v) => pct(v, 2) },
  { key: "price_vs_sma_50", label: "vs 50-SMA", fmt: (v) => pct(v, 2) },
  { key: "price_vs_sma_200", label: "vs 200-SMA", fmt: (v) => pct(v, 2) },
  { key: "tdd_roc_20d", label: "20-Day ROC", fmt: (v) => pct(v, 2) },
  { key: "tdd_roc_60d", label: "60-Day ROC", fmt: (v) => pct(v, 2) },
  { key: "tdd_roc_120d", label: "120-Day ROC", fmt: (v) => pct(v, 2) },
  { key: "tdd_roc_252d", label: "252-Day ROC", fmt: (v) => pct(v, 2) },
  { key: "tdd_rsi", label: "RSI (14)", fmt: (v) => num(v, 1) },
  { key: "tdd_macd", label: "MACD", fmt: (v) => num(v, 3) },
];

const VALUE_SCHEMA = [
  { key: "market_cap", label: "Market Cap", fmt: money },
  { key: "trailing_pe", label: "P/E", fmt: (v) => num(v, 2) },
  { key: "price_to_book", label: "P/B", fmt: (v) => num(v, 2) },
  { key: "ps_ratio_val", label: "P/S", fmt: (v) => num(v, 2) },
  { key: "peg_ratio_val", label: "PEG", fmt: (v) => num(v, 2) },
  { key: "fcf_yield_val", label: "FCF Yield", fmt: (v) => pct(v, 2) },
  { key: "dividend_yield", label: "Dividend Yield", fmt: (v) => pct(v, 2) },
];

const GROWTH_SCHEMA = [
  { key: "rev_growth_1y_val", label: "Revenue Growth (1Y)", fmt: (v) => pct(v, 2) },
  { key: "eps_growth_1y_val", label: "EPS Growth (1Y)", fmt: (v) => pct(v, 2) },
  { key: "rev_growth_3y_val", label: "Revenue Growth (3Y)", fmt: (v) => pct(v, 2) },
  { key: "eps_growth_3y_val", label: "EPS Growth (3Y)", fmt: (v) => pct(v, 2) },
  { key: "rev_growth_5y_val", label: "Revenue Growth (5Y)", fmt: (v) => pct(v, 2) },
  { key: "eps_growth_5y_val", label: "EPS Growth (5Y)", fmt: (v) => pct(v, 2) },
];

const POSITIONING_SCHEMA = [
  { key: "inst_own_val", label: "Institutional Own %", fmt: (v) => pct(v, 1) },
  { key: "insider_own_val", label: "Insider Own %", fmt: (v) => pct(v, 1) },
  { key: "short_pct_val", label: "Short Interest %", fmt: (v) => pct(v, 2) },
  { key: "short_interest_trend_val", label: "Short Interest Trend", fmt: (v) => String(v) },
  {
    key: "shares_short_prior_month_val",
    label: "Shares Short (Prior Mo)",
    fmt: (v) => (v ? Number(v).toLocaleString() : "—"),
  },
];

const STABILITY_SCHEMA = [
  { key: "volatility_12m_val", label: "Volatility (12M)", fmt: (v) => pct(v, 2) },
  { key: "volatility_60d_val", label: "Volatility (60D)", fmt: (v) => pct(v, 2) },
  { key: "volatility_30d_val", label: "Volatility (30D)", fmt: (v) => pct(v, 2) },
  { key: "beta_val", label: "Beta vs Market", fmt: (v) => num(v, 2) },
  { key: "debt_to_assets_val", label: "Debt / Assets", fmt: (v) => num(v, 2) },
];
