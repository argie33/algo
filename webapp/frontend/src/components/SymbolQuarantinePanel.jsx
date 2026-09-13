/**
 * SymbolQuarantinePanel — the missing frontend surface for `symbol_quarantine`.
 *
 * ADDED 2026-09-13 (goal session: "is our patrol/quarantine architecture comprehensive and
 * visible" audit). `algo/monitoring/data_patrol/quarantine.py` excludes a per-symbol ERROR/
 * CRITICAL DataPatrol finding from scoring/trading instead of Phase 1 halting the whole
 * pipeline for it - but until this panel, an operator could only see which symbols are
 * currently excluded, and why, via raw SQL against `symbol_quarantine`. This is the direct
 * "show me the effect" companion to the "Recent Patrol Findings" panel on this same tab:
 * findings are the raw check output, quarantine is which symbols actually got isolated
 * because of them.
 *
 * Backed by GET /api/algo/quarantine (lambda/api/routes/algo_handlers/monitoring.py::
 * _get_symbol_quarantine), which mirrors _get_patrol_log's own shape (open/live rows only,
 * most-recent first, paginated) for consistency between the two "what's currently wrong"
 * surfaces on this tab.
 *
 * useApiQuery's own queryFn contract (see its module docstring) is "return an axios response
 * OR pre-parsed body - extractData strips the envelope internally, exactly once." Passing
 * `() => api.get(url)` straight through (not pre-extracting here) is required - a fetcher
 * that manually calls extractData() and returns the unwrapped result gets extracted a SECOND
 * time by the hook itself, and extractData's own "does this look like a paginated {items:...}
 * response" heuristic (webapp/frontend/src/utils/responseNormalizer.js) fires differently on
 * an already-unwrapped object than on the original envelope - live-caught here: it silently
 * flattened `items` correctly but dropped this endpoint's own `by_check` field entirely
 * because that field isn't in the heuristic's hardcoded allowlist.
 */
import React, { useMemo, useState } from "react";
import { RefreshCw, Search, ShieldOff } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";

const QUARANTINE_URL = "/api/algo/quarantine?limit=200";

function fmtAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function SymbolQuarantinePanel({ active }) {
  const { data, loading, error, isFetching, refetch } = useApiQuery(
    ["symbol-quarantine"],
    () => api.get(QUARANTINE_URL),
    { enabled: active, timeout: 30000, retry: 1, refetchInterval: 60000 }
  );

  const [search, setSearch] = useState("");

  const items = data?.items || [];
  const byCheck = data?.by_check || [];

  const rows = useMemo(() => {
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter(
      (r) => r.symbol?.toLowerCase().includes(q) || r.check_name?.toLowerCase().includes(q)
    );
  }, [items, search]);

  if (!active) return null;

  if (error) {
    const accessDenied =
      error?.status === 403 || (typeof error === "string" && error.includes("Authentication"));
    return (
      <div className="alert alert-danger" style={{ margin: "20px 0" }}>
        {accessDenied
          ? "Admin access required to view symbol quarantine."
          : error?.message || "Failed to load symbol quarantine"}
      </div>
    );
  }

  return (
    <div style={{ marginTop: "var(--space-5)" }}>
      <div
        className="flex items-center gap-3"
        style={{ marginBottom: "var(--space-4)" }}
      >
        <div style={{ flex: 1 }}>
          <div className="t-sm muted">
            Symbols currently excluded from scoring/trading because a DataPatrol check
            flagged them individually (<code className="mono t-2xs">symbol_quarantine</code>)
            — the per-symbol alternative to Phase 1 halting the whole pipeline over one
            check's finding. A symbol drops off this list automatically once the check that
            flagged it stops flagging it on a later run.
          </div>
        </div>
        <button
          className="btn btn-outline btn-sm"
          onClick={() => refetch()}
          disabled={loading || isFetching}
        >
          <RefreshCw size={14} className={isFetching ? "spin" : ""} />{" "}
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {loading ? (
        <div className="empty">
          <div className="empty-title">Loading symbol quarantine…</div>
        </div>
      ) : !data ? (
        <div className="empty">
          <div className="empty-title">No quarantine data</div>
        </div>
      ) : items.length === 0 ? (
        <div className="empty">
          <div className="empty-title">No symbols currently quarantined</div>
          <div className="t-sm muted">Every ERROR/CRITICAL finding this session was either clean or systemic (whole-pipeline halt, not per-symbol).</div>
        </div>
      ) : (
        <>
          <div className="grid grid-3" style={{ marginBottom: "var(--space-4)" }}>
            <div className="stile">
              <div className="stile-label">Symbols Quarantined</div>
              <div className={`stile-value ${items.length > 0 ? "down" : "up"}`}>
                {data.quarantine_count ?? items.length}
              </div>
              <div className="stile-sub">excluded from scoring/trading right now</div>
            </div>
            <div className="stile">
              <div className="stile-label">Checks Involved</div>
              <div className="stile-value">{byCheck.length}</div>
              <div className="stile-sub">distinct check_name currently quarantining symbols</div>
            </div>
            <div className="stile">
              <div className="stile-label">Top Check</div>
              <div className="stile-value mono t-sm" style={{ wordBreak: "break-word" }}>
                {byCheck[0]?.check_name || "—"}
              </div>
              <div className="stile-sub">
                {byCheck[0] ? `${byCheck[0].symbol_count} symbol(s)` : ""}
              </div>
            </div>
          </div>

          <div
            className="card-pad-sm flex gap-3 items-center"
            style={{ flexWrap: "wrap", marginBottom: "var(--space-2)" }}
          >
            <div style={{ position: "relative", minWidth: 200 }}>
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
                placeholder="Search symbol or check…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ paddingLeft: 32 }}
              />
            </div>
          </div>

          <div
            className="t-xs faint"
            style={{ padding: "0 var(--space-2) var(--space-2)" }}
          >
            {rows.length} of {items.length} quarantined symbols
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0, overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 24 }}></th>
                    <th>Symbol</th>
                    <th>Flagged By</th>
                    <th>Reason</th>
                    <th>Since</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={`${r.symbol}-${r.check_name}-${i}`}>
                      <td>
                        <ShieldOff size={14} style={{ color: "var(--danger, #e2645f)" }} />
                      </td>
                      <td className="mono t-sm">{r.symbol}</td>
                      <td>
                        <span className="badge badge-neutral" style={{ fontSize: "var(--t-2xs)" }}>
                          {r.check_name}
                        </span>
                      </td>
                      <td className="t-sm">{r.reason}</td>
                      <td className="t-xs faint">{fmtAgo(r.detected_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
