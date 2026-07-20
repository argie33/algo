/**
 * Earnings Calendar — recent 10-K/10-Q earnings-related filings across the universe.
 *
 * Backed by GET /api/earnings (all symbols, most recent first). Surfaces
 * official SEC EDGAR filing dates for annual (10-K) and quarterly (10-Q)
 * reports, with a symbol filter. EPS actual/estimate figures are not
 * sourced by this pipeline (yfinance was deprecated project-wide; SEC EDGAR
 * provides filing dates but not consensus estimates).
 */

import React, { useState, useMemo } from "react";
import { Search, RefreshCw } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";
import ErrorBoundary from "../components/ErrorBoundary";

function Empty({ title, desc }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
    </div>
  );
}

function EarningsCalendarContent() {
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(100);

  const {
    data: rawEarnings,
    loading,
    error,
    refetch,
    isFetching,
  } = useApiQuery(["earnings-calendar", limit], () =>
    api.get(`/api/earnings?limit=${limit}`)
  );

  const earnings = useMemo(() => {
    const list = Array.isArray(rawEarnings)
      ? rawEarnings
      : rawEarnings?.items || [];
    if (!search.trim()) return list;
    const q = search.trim().toUpperCase();
    return list.filter((e) => e.symbol?.toUpperCase().startsWith(q));
  }, [rawEarnings, search]);

  return (
    <div className="main-content">
      <div className="page-head">
        <div>
          <div className="page-head-title">Earnings Calendar</div>
          <div className="page-head-sub">
            Recent annual (10-K) and quarterly (10-Q) filing dates across the
            universe, sourced from SEC EDGAR
          </div>
        </div>
        <div
          className="page-head-actions"
          style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}
        >
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="input"
            style={{ padding: "6px 8px", fontSize: "var(--t-xs)", minWidth: "100px" }}
          >
            <option value={100}>Show 100</option>
            <option value={500}>Show 500</option>
            <option value={1000}>Show 1,000</option>
          </select>
          <button
            className="btn btn-outline btn-sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      <div className="card card-pad-sm" style={{ marginBottom: "var(--space-3)" }}>
        <div style={{ position: "relative", maxWidth: 280 }}>
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
            placeholder="Symbol (starts with)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ paddingLeft: 32 }}
          />
        </div>
      </div>

      {loading ? (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            height: "300px",
            color: "var(--text-muted)",
          }}
        >
          <p>Loading earnings history...</p>
        </div>
      ) : error ? (
        <div className="card">
          <div className="card-body">
            <Empty
              title="Earnings data unavailable"
              desc={
                typeof error === "string"
                  ? error
                  : error?.message ||
                    "The earnings pipeline may not have run yet."
              }
            />
          </div>
        </div>
      ) : earnings.length === 0 ? (
        <div className="card">
          <div className="card-body">
            <Empty
              title="No earnings filings yet"
              desc="Earnings-related filings will appear here once the data pipeline populates them."
            />
          </div>
        </div>
      ) : (
        <div className="card">
          <div style={{ overflow: "auto", maxHeight: "70vh" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Filing Date</th>
                  <th>Filing Type</th>
                </tr>
              </thead>
              <tbody>
                {earnings.map((e, i) => (
                  <tr key={`${e.symbol}-${e.report_date}-${i}`}>
                    <td>
                      <span className="strong" style={{ fontWeight: "var(--w-bold)" }}>
                        {e.symbol}
                      </span>
                    </td>
                    <td>{e.report_date || "—"}</td>
                    <td>{e.fiscal_period || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function EarningsCalendar() {
  return (
    <ErrorBoundary>
      <EarningsCalendarContent />
    </ErrorBoundary>
  );
}
