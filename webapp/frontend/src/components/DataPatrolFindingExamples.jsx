/**
 * FindingExamples — renders the specific symbols/values behind a DataPatrol finding as real
 * line items (a bordered mini-table), not a free-text blob. Used by ServiceHealth's Recent
 * Patrol Findings panel.
 *
 * NOTE 2026-09-13: originally written to also replace ScoresCorrectnessCoverage.jsx's own
 * finding-example rendering, but that panel keeps its own inline FindingDetail/formatExample
 * rendering (a compact stacked-text list, not a mini-table) since its column layout is a worse
 * fit for this component's row shape. Left this component for ServiceHealth's list/card-based
 * finding rows, where a self-contained block still makes sense.
 *
 * `details.examples` entry shape varies per check (whatever that check's own self.log(...)
 * call happened to build) - usually {"symbol": "...", <flagged fields>} but sometimes a bare
 * string/number. Column set is derived per-finding from whatever keys are actually present,
 * so this renders correctly for any check without needing a per-check schema.
 */
import React from "react";

function formatValue(v) {
  if (typeof v === "number") {
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(v);
}

export default function FindingExamples({ details, maxRows = 5 }) {
  const examples = details?.examples;
  if (!Array.isArray(examples) || examples.length === 0) return null;

  const shown = examples.slice(0, maxRows);
  const remaining = typeof details.count === "number" ? details.count - shown.length : examples.length - shown.length;

  // Column order: symbol first (if any example has one), then every other key in first-seen
  // order across examples - keeps columns stable even if one example is missing a field.
  const hasSymbol = shown.some((ex) => ex && typeof ex === "object" && "symbol" in ex);
  const otherKeys = [];
  for (const ex of shown) {
    if (!ex || typeof ex !== "object") continue;
    for (const k of Object.keys(ex)) {
      if (k !== "symbol" && !otherKeys.includes(k)) otherKeys.push(k);
    }
  }

  return (
    <div
      className="t-2xs mono"
      style={{
        marginTop: 6,
        border: "1px solid var(--border-soft)",
        borderRadius: 4,
        overflow: "hidden",
      }}
    >
      {shown.map((ex, i) => {
        const isObj = ex !== null && typeof ex === "object";
        return (
          <div
            key={i}
            className="flex items-center gap-3"
            style={{
              padding: "3px var(--space-2)",
              borderTop: i > 0 ? "1px solid var(--border-soft)" : "none",
              background: i % 2 === 1 ? "var(--surface-2)" : "transparent",
            }}
          >
            {isObj ? (
              <>
                {hasSymbol && (
                  <span className="strong" style={{ minWidth: 56, flexShrink: 0 }}>
                    {ex.symbol ?? "—"}
                  </span>
                )}
                <span className="flex gap-3 faint" style={{ flexWrap: "wrap" }}>
                  {otherKeys.map(
                    (k) =>
                      ex[k] !== undefined && (
                        <span key={k}>
                          {k}: {formatValue(ex[k])}
                        </span>
                      )
                  )}
                </span>
              </>
            ) : (
              <span className="faint">{String(ex)}</span>
            )}
          </div>
        );
      })}
      {remaining > 0 && (
        <div
          className="faint"
          style={{
            padding: "3px var(--space-2)",
            borderTop: "1px solid var(--border-soft)",
          }}
        >
          +{remaining} more
        </div>
      )}
    </div>
  );
}
