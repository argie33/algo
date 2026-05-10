import React from "react";
import { useApiQuery } from "../hooks/useApiQuery";
import { BarChart3, RefreshCw } from "lucide-react";
import { api } from "../services/api";

const MetricCard = ({ label, value, unit = "", color = "var(--text)" }) => (
  <div style={{ padding: "16px", background: "var(--surface)", borderRadius: "var(--r-md)", border: "1px solid var(--border)" }}>
    <div style={{ fontSize: "var(--t-xs)", color: "var(--text-2)", marginBottom: "8px" }}>{label}</div>
    <div style={{ fontSize: "var(--t-xl)", fontWeight: "var(--w-bold)", color }}>
      {value == null || isNaN(Number(value)) ? "—" : Number(value).toFixed(2)}{unit}
    </div>
  </div>
);

export default function PerformanceMetrics() {
  const { data: m = {}, loading, error, refetch } = useApiQuery(
    ["performance"],
    () => api.get("/api/algo/performance"),
    { staleTime: 60000 }
  );

  if (loading) return <div className="main-content"><div className="muted t-sm" style={{ padding: "40px" }}>Loading…</div></div>;
  if (error) return <div className="main-content"><div className="alert alert-danger" style={{ margin: "20px" }}>Error: {error}</div></div>;

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <BarChart3 size={20} /> Performance
          </div>
          <div className="page-head-sub">Algo trading performance metrics</div>
        </div>
        <div className="page-head-actions">
          <button className="btn btn-outline btn-sm" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px" }}>
        <MetricCard label="Total Trades" value={m.total_trades} unit="" />
        <MetricCard
          label="Win Rate"
          value={m.win_rate_pct}
          unit="%"
          color={m.win_rate_pct > 50 ? "var(--success)" : "var(--danger)"}
        />
        <MetricCard
          label="Total P&L"
          value={m.total_pnl_dollars}
          unit=" USD"
          color={m.total_pnl_dollars > 0 ? "var(--success)" : "var(--danger)"}
        />
        <MetricCard label="Sharpe (Ann.)" value={m.sharpe_annualized} />
        <MetricCard label="Sortino (Ann.)" value={m.sortino_annualized} />
        <MetricCard label="Max Drawdown" value={m.max_drawdown_pct} unit="%" color="var(--amber)" />
        <MetricCard label="Profit Factor" value={m.profit_factor} />
        <MetricCard label="Calmar Ratio" value={m.calmar_ratio} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px", marginTop: "12px" }}>
        <MetricCard label="Total Return" value={m.total_return_pct} unit="%" color={m.total_return_pct >= 0 ? "var(--success)" : "var(--danger)"} />
        <MetricCard label="Avg Win" value={m.avg_win_pct} unit="%" color="var(--success)" />
        <MetricCard label="Avg Loss" value={m.avg_loss_pct} unit="%" color="var(--danger)" />
        <MetricCard label="Expectancy R" value={m.expectancy_r} />
        <MetricCard label="Avg Hold Days" value={m.avg_hold_days} />
        <MetricCard label="Portfolio Snapshots" value={m.portfolio_snapshots} unit="" />
      </div>
    </div>
  );
}
