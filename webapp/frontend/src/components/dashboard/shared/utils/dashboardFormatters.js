import {
  formatNumber,
  formatCurrency,
  formatPercentageChange,
} from "../../../../utils/formatters";

// Dashboard-specific number formatting (returns '—' for null/invalid, not 'N/A')

export const num = (v, dp = 2) =>
  v == null || isNaN(Number(v)) ? "—" : Number(v).toFixed(dp);

export const _num = (v, dp = 2) => formatNumber(v, dp);

export const pct = (v, dp = 2) =>
  v == null || isNaN(Number(v)) ? "—" : `${Number(v).toFixed(dp)}%`;

export const fmtMoney = (v) =>
  v == null || isNaN(Number(v))
    ? "—"
    : `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const fmtMoneyShort = (v) => {
  if (v == null || isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
};

export const fmtBig = (v) => {
  if (v == null || isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
};

export const fmtPct = (v, dp = 2) =>
  v == null || isNaN(Number(v)) ? "—" : `${Number(v).toFixed(dp)}%`;

export const fmtDate = (d) => {
  if (!d) return "—";
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d).slice(0, 10);
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export const fmtAgo = (ts) => {
  if (!ts) return "—";
  const now = new Date();
  const then = new Date(ts);
  if (isNaN(then.getTime())) return "—";

  const secs = Math.floor((now - then) / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return then.toLocaleDateString("en-US");
};

export const fmtInt = (v) =>
  v == null ? "—" : Number(v).toLocaleString("en-US");

export const bps = (v) =>
  v == null || isNaN(+v) ? "—" : `${Math.round(+v * 100)} bps`;

export const fmtD = (s) => (s ? new Date(s).toLocaleDateString() : "—");

export const money = (v) => formatCurrency(v);

export const fmtLarge = (v) => {
  if (v == null || isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
};

// Re-export main utils for convenience
export { formatNumber, formatCurrency, formatPercentageChange };
