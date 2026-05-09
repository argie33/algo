import React from "react";
import { useApiQuery } from "../hooks/useApiQuery";
import { BarChart3, TrendingUp, TrendingDown } from "lucide-react";
import { getApiConfig } from "../services/api";

const Card = ({ label, value, unit = "", color = "white" }) => (
  <div style={{ padding: "16px", background: "var(--bg-secondary)", borderRadius: "6px", border: "1px solid var(--border-color)" }}>
    <div style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "8px" }}>{label}</div>
    <div style={{ fontSize: "24px", fontWeight: "bold", color }}>{typeof value === "number" ? value.toFixed(2) : value}{unit}</div>
  </div>
);

export default function PerformanceMetrics() {
  const { apiUrl } = getApiConfig();
  const { data, loading, error, refetch } = useApiQuery(["performance"], async () => {
    const res = await fetch();
    if (!res.ok) throw new Error("Failed");
    return res.json();
  }, { staleTime: 60000 });

  const m = data?.data || {};

  if (loading) return <div style={{ padding: "20px" }}>Loading...</div>;
  if (error) return <div style={{ padding: "20px", color: "red" }}>Error: {error}</div>;

  return (
    <div style={{ padding: "20px" }}>
      <h1 style={{ display: "flex", alignItems: "center", gap: "8px" }}><BarChart3 /> Performance</h1>
      <button onClick={() => refetch()}>Refresh</button>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "12px", marginTop: "20px" }}>
        <Card label="Trades" value={m.total_trades} />
        <Card label="Win Rate" value={m.win_rate_pct} unit="%" color={m.win_rate_pct > 50 ? "green" : "red"} />
        <Card label="Total P&L" value={m.total_pnl_dollars} unit=" USD" color={m.total_pnl_dollars > 0 ? "green" : "red"} />
        <Card label="Sharpe" value={m.sharpe_annualized} />
        <Card label="Sortino" value={m.sortino_annualized} />
        <Card label="Max DD" value={m.max_drawdown_pct} unit="%" color="orange" />
        <Card label="Profit Factor" value={m.profit_factor} />
        <Card label="Calmar" value={m.calmar_ratio} />
      </div>
    </div>
  );
}
