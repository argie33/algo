/**
 * ScoresCorrectnessCoverage — companion to ScoresDataCoverage: instead of "is the value
 * present at all" (completeness), this answers "if a value IS present, does any DataPatrol
 * check ever validate it" (correctness). Rendered directly below ScoresDataCoverage on the
 * ServiceHealth "Scores Data Coverage" tab - same question, correctness angle.
 *
 * ADDED 2026-09-13 (goal session continuation) - a prior session found "89 of 111 pillar-input
 * fields have zero direct check" but never persisted the analysis anywhere (no memory entry, no
 * script, no commit), so that number couldn't be trusted or reproduced. This re-derives it live
 * via GET /api/algo/scores/correctness-coverage (lambda/api/routes/scores_handlers/
 * coverage_correctness.py), which cross-references the same factor universe
 * /api/algo/scores/coverage tracks against which algo/monitoring/data_patrol/checks/*.py
 * module source text mentions both that factor's table and column name.
 *
 * This is a static-text heuristic, not semantic analysis - a "checked" verdict means "a check
 * module's source references this field", not proof of what it validates or how rigorously.
 * See the backend module's own docstring for the exact matching rule and its known blind spot
 * (a check reaching a factor only through an alias/joined column name or a shared helper won't
 * be found). Treat "0 checks" rows as the real signal (a genuine, confirmable gap); treat
 * "checked" rows as a lead to spot-check, not a guarantee.
 */
import React, { useMemo, useState } from "react";
import { RefreshCw, Search, ShieldAlert, ShieldCheck } from "lucide-react";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../services/api";

const CORRECTNESS_URL = "/api/algo/scores/correctness-coverage";

export default function ScoresCorrectnessCoverage({ active }) {
  // useApiQuery's own queryFn contract: pass the raw api.get() call through - the hook
  // calls extractData() internally exactly once (see SymbolQuarantinePanel.jsx's identical
  // fix and comment for the double-extraction bug this avoids; harmless here in practice
  // since this endpoint has no "items" key to collide with extractData's pagination
  // heuristic, but the pattern should stay consistent either way).
  const { data, loading, error, isFetching, refetch } = useApiQuery(
    ["scores-correctness-coverage"],
    () => api.get(CORRECTNESS_URL),
    { enabled: active, timeout: 30000, retry: 1 }
  );

  const [search, setSearch] = useState("");
  // Defaults to the actionable view: scored factors DataPatrol never touches - the same
  // "lead with what can actually move a score" posture ScoresDataCoverage already takes for
  // completeness (its "not scored" badge + real-gap-only headline numbers). A gap on a
  // display-only field (EV/EBITDA, PEG, short-interest fields, ...) can't move stock_scores,
  // so it shouldn't compete for attention with a genuine gap on a live pillar input by
  // default - both toggles below let someone widen back out to the full picture on demand.
  const [hideChecked, setHideChecked] = useState(true);
  const [showUnscored, setShowUnscored] = useState(false);

  const factors = data?.factors || [];
  const isScored = (f) => f.scored !== false;

  const rows = useMemo(() => {
    return factors.filter((f) => {
      if (hideChecked && f.checked) return false;
      if (!showUnscored && !isScored(f)) return false;
      if (
        search &&
        !(
          f.factor.toLowerCase().includes(search.toLowerCase()) ||
          f.table.toLowerCase().includes(search.toLowerCase())
        )
      )
        return false;
      return true;
    });
  }, [factors, search, hideChecked, showUnscored]);

  if (!active) return null;

  if (error) {
    return (
      <div className="alert alert-danger" style={{ margin: "20px 0" }}>
        {error?.message || "Failed to load correctness check coverage"}
      </div>
    );
  }

  const pctScoredChecked = data?.scored_factor_count
    ? Math.round(
        (1000 * (data.scored_factor_count - data.scored_unchecked_count)) /
          data.scored_factor_count
      ) / 10
    : null;

  return (
    <div style={{ marginTop: "var(--space-5)" }}>
      <div
        className="flex items-center gap-3"
        style={{ marginBottom: "var(--space-4)" }}
      >
        <div style={{ flex: 1 }}>
          <div className="t-sm muted">
            Of the scored pillar-input factors above — the ones that can actually move a
            stock's score — which have zero DataPatrol check
            (<code className="mono t-2xs">algo/monitoring/data_patrol/checks/</code>) ever
            referencing them. A present value can still be silently wrong if nothing ever
            cross-checks it. Correctness, not completeness. Defaults to the actionable view;
            widen it with the checkboxes below.
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
          <div className="empty-title">Loading correctness check coverage…</div>
        </div>
      ) : !data ? (
        <div className="empty">
          <div className="empty-title">No correctness coverage data</div>
        </div>
      ) : (
        <>
          <div className="grid grid-4" style={{ marginBottom: "var(--space-4)" }}>
            <div className="stile">
              <div className="stile-label">Scored Factors, Zero Check</div>
              <div
                className={`stile-value ${data.scored_unchecked_count > 0 ? "down" : "up"}`}
              >
                {data.scored_unchecked_count}
              </div>
              <div className="stile-sub">
                of {data.scored_factor_count} that can actually move a score
                {pctScoredChecked != null ? ` — ${pctScoredChecked}% checked` : ""}
              </div>
            </div>
            <div className="stile">
              <div className="stile-label">Factors Tracked</div>
              <div className="stile-value">{data.factor_count}</div>
              <div className="stile-sub">
                {data.factor_count - data.scored_factor_count} display-only (unscored), same
                universe as Data Coverage above
              </div>
            </div>
            <div className="stile">
              <div className="stile-label">Referenced By a Check</div>
              <div className="stile-value">{data.checked_count}</div>
              <div className="stile-sub">≥1 DataPatrol check module mentions it</div>
            </div>
            <div className="stile">
              <div className="stile-label">Check Modules Scanned</div>
              <div className="stile-value">{data.check_module_count}</div>
              <div className="stile-sub">algo/monitoring/data_patrol/checks/*.py</div>
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
                placeholder="Search factor or table…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ paddingLeft: 32 }}
              />
            </div>
            <label
              className="flex items-center gap-2 t-sm muted"
              style={{ cursor: "pointer" }}
            >
              <input
                type="checkbox"
                checked={hideChecked}
                onChange={(e) => setHideChecked(e.target.checked)}
              />
              Show only zero-check factors
            </label>
            <label
              className="flex items-center gap-2 t-sm muted"
              style={{ cursor: "pointer" }}
            >
              <input
                type="checkbox"
                checked={showUnscored}
                onChange={(e) => setShowUnscored(e.target.checked)}
              />
              Include display-only (unscored) factors
            </label>
          </div>

          <div
            className="t-xs faint"
            style={{ padding: "0 var(--space-2) var(--space-2)" }}
          >
            {rows.length} of {factors.length} factors
            {hideChecked || !showUnscored ? " (filtered — see checkboxes above)" : ""}
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0, overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 24 }}></th>
                    <th>Factor</th>
                    <th>Referencing Checks</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((f) => {
                    const key = `${f.table}.${f.factor}`;
                    return (
                      <tr key={key}>
                        <td>
                          {f.checked ? (
                            <ShieldCheck size={14} style={{ color: "var(--success, #22ab84)" }} />
                          ) : (
                            <ShieldAlert size={14} style={{ color: "var(--danger, #e2645f)" }} />
                          )}
                        </td>
                        <td>
                          <div className="dbl">
                            <span className="dbl-main mono t-sm">{f.factor}</span>
                            <span className="dbl-sub">
                              <span
                                className="badge badge-neutral"
                                style={{ fontSize: "var(--t-2xs)" }}
                              >
                                {f.table}
                              </span>
                              {f.group && f.group !== f.table && (
                                <span
                                  className="badge badge-neutral"
                                  style={{ fontSize: "var(--t-2xs)", marginLeft: 4 }}
                                >
                                  {f.group}
                                </span>
                              )}
                              {!isScored(f) && (
                                <span
                                  className="badge"
                                  title="Computed/displayed elsewhere but not read by the live composite scoring formula - a check gap here can't move a stock's score."
                                  style={{
                                    fontSize: "var(--t-2xs)",
                                    marginLeft: 4,
                                    color: "var(--text-faint)",
                                    border: "1px solid var(--border-soft)",
                                  }}
                                >
                                  not scored
                                </span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td className="t-sm">
                          {f.checks.length ? (
                            f.checks.join(", ")
                          ) : (
                            <span className="t-2xs faint">No check references this field</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div
            className="t-2xs faint"
            style={{ marginTop: "var(--space-3)", lineHeight: 1.6 }}
          >
            "Referenced" means a check module's source text mentions both the factor's table
            and column name as whole words — a static heuristic, not proof of what the check
            actually validates or how rigorously (see this section's own header text). A
            factor referenced by name in a check that was later removed, or reached only
            through an alias/shared helper, can show up wrong in either direction — treat
            "zero direct check" rows as the reliable signal to investigate, and "referenced"
            rows as a lead to spot-check rather than a guarantee.
          </div>
        </>
      )}
    </div>
  );
}
