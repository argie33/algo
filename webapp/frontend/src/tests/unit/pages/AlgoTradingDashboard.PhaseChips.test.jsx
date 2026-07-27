/**
 * Regression test for the 2026-07-27 fix: AlgoTradingDashboard.jsx's PhaseChips component
 * hardcoded only P1-P7 in its chip list, completely omitting Phase 8 (entry_execution - the
 * phase that actually places real orders) and Phase 9 (reconciliation) from the run-history
 * panel's per-phase status display. The backend already tracks all 9 phases in
 * phases_completed/phases_halted/phases_errored - this was a frontend-only display gap, not
 * a missing backend field. An operator watching this panel before trading real money had no
 * visual indication of whether the highest-stakes phases even ran.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PhaseChips } from "../../../pages/AlgoTradingDashboard.jsx";

describe("PhaseChips", () => {
  it("renders chips for all 9 orchestrator phases, including P8 and P9", () => {
    render(
      <PhaseChips
        phasesCompleted={["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"]}
        phasesHalted={[]}
        phasesErrored={[]}
      />
    );

    for (const p of ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"]) {
      expect(screen.getByText(p)).toBeInTheDocument();
    }
  });

  it("does not render a chip for a nonexistent P10", () => {
    render(<PhaseChips phasesCompleted={["P1"]} phasesHalted={[]} phasesErrored={[]} />);
    expect(screen.queryByText("P10")).not.toBeInTheDocument();
  });
});
