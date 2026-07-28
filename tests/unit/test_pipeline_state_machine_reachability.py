"""Regression test for terraform/modules/pipeline/main.tf's Step Functions wiring.

This exact bug class has recurred 4+ times in this file (see steering/DATA_LOADERS.md's
"FIXED 2026-07-20/27/28" entries): a state gets added or renamed, but some predecessor's
`Next` (often a failure handler's, pointed the "right" way by accident while the success
path's `Next` is left stale) doesn't get updated to match - either producing a dangling
`Next` (AWS rejects this at deploy time) or a structurally orphaned state that only ever
runs via an unlikely path (e.g. only on a sibling's failure), so it silently never
exercises in production even though `terraform validate`/`fmt` see nothing wrong (HCL has
no concept of Step Functions state names, so this class of bug is invisible to Terraform
itself - AWS only validates it at `CreateStateMachine`/`UpdateStateMachine` time, and nothing
in this repo runs that against real AWS in CI).

This test parses the 3 top-level state machines (eod_pipeline, morning_pipeline,
computed_metrics_pipeline - identified by their distinct `StartAt` declarations) and checks,
per machine: every `Next`/`StartAt` target actually exists as a defined state, and every
defined top-level state is reachable from at least one `Next`/`StartAt` reference (a
same-file "orphaned state" check - a lighter-weight proxy for the "structurally unreachable
on the success path" bug specifically, which needs a human to judge whether an orphaned
state is intentional dead code or a real gap, but catches the mechanical case immediately).

Deliberately NOT a full ASL semantic parser: does not distinguish top-level states from
states nested inside a `Parallel` state's own `Branches` (those have their own independent
namespace) - nested branch states are folded into the same section's defined-state set,
which can only ever make the "orphaned" check too lenient (a branch-internal state that's
only reachable from inside its own branch still counts as "reached"), never too strict.
"""

import re
from pathlib import Path

PIPELINE_TF = Path(__file__).resolve().parents[2] / "terraform" / "modules" / "pipeline" / "main.tf"

# Structural ASL/HCL keys that share the "Key = {" shape but are not state names.
_NON_STATE_KEYS = {"States", "Parameters", "Overrides"}
_STATE_DEF_RE = re.compile(r"^\s{6,}([A-Za-z0-9]+)\s*=\s*\{", re.MULTILINE)
_NEXT_RE = re.compile(r'Next\s*=\s*"([A-Za-z0-9]+)"')
_STARTAT_RE = re.compile(r'StartAt\s*=\s*"([A-Za-z0-9]+)"')


_TOP_LEVEL_STATES_RE = re.compile(r'^\s{4}States\s*=\s*\{', re.MULTILINE)


def _matching_brace(content: str, open_brace_idx: int) -> int:
    """Given the index of a '{' character, return the index of its matching '}'."""
    depth = 0
    for i in range(open_brace_idx, len(content)):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced braces - no matching close found")


def _split_into_state_machines(content: str) -> list[str]:
    """Split the file into one chunk per top-level state machine's own `States = { ... }`
    block (brace-matched, so trailing unrelated Terraform resources after the last state
    machine - e.g. IAM role/policy blocks - are correctly excluded)."""
    states_blocks = list(_TOP_LEVEL_STATES_RE.finditer(content))
    assert len(states_blocks) >= 2, (
        f"expected multiple top-level state machines in {PIPELINE_TF}, found {len(states_blocks)} - "
        "either the file structure changed or this test's boundary regex needs updating"
    )
    sections = []
    for m in states_blocks:
        # The pipeline's entry point ("StartAt") is a sibling key just before "States = {",
        # not inside it - fold it back in as a synthetic reference so the entry state isn't
        # flagged as orphaned (nothing inside States itself points to it).
        preceding = content[: m.start()]
        startat_match = list(_STARTAT_RE.finditer(preceding))
        assert startat_match, f"no StartAt found before States block at offset {m.start()}"
        entry_state = startat_match[-1].group(1)

        open_idx = content.index("{", m.start())
        close_idx = _matching_brace(content, open_idx)
        sections.append(f'StartAt = "{entry_state}"\n' + content[open_idx : close_idx + 1])
    return sections


def _reachability_gaps(section: str) -> tuple[set[str], set[str]]:
    state_defs = set(_STATE_DEF_RE.findall(section)) - _NON_STATE_KEYS
    next_refs = set(_NEXT_RE.findall(section))
    startat_refs = set(_STARTAT_RE.findall(section))
    referenced = next_refs | startat_refs

    dangling = referenced - state_defs
    orphaned = state_defs - referenced
    return dangling, orphaned


class TestPipelineStateMachineReachability:
    def test_no_dangling_next_targets(self):
        """Every Next/StartAt must point at a state actually defined somewhere in the
        same state machine - a dangling reference is rejected by AWS at deploy time."""
        content = PIPELINE_TF.read_text()
        for i, section in enumerate(_split_into_state_machines(content)):
            dangling, _ = _reachability_gaps(section)
            assert not dangling, f"state machine #{i}: dangling Next/StartAt target(s): {dangling}"

    def test_no_orphaned_states(self):
        """Every defined state must be reachable from at least one Next/StartAt in the
        same state machine - an orphaned state runs only via chance (e.g. only from a
        sibling's failure handler), the exact recurring bug class this test guards."""
        content = PIPELINE_TF.read_text()
        for i, section in enumerate(_split_into_state_machines(content)):
            _, orphaned = _reachability_gaps(section)
            assert not orphaned, f"state machine #{i}: orphaned (unreachable) state(s): {orphaned}"

    def test_current_reports_8k_and_dividend_data_are_wired(self):
        """FIX 2026-07-28: these two loaders were registered in the task-def catalog and
        critical_loaders but had zero Step Functions states anywhere in this file."""
        content = PIPELINE_TF.read_text()
        assert "CurrentReports8k" in content
        assert "DividendData" in content
        assert 'var.loader_task_definition_arns["current_reports_8k"]' in content
        assert 'var.loader_task_definition_arns["dividend_data"]' in content

    def test_insider_transaction_velocity_reachable_on_success(self):
        """FIX 2026-07-28: InsiderHoldingsSec's success Next used to skip straight to
        PositioningMetrics, bypassing InsiderTransactionVelocity - only its OWN failure
        handler pointed at it, so it only ran when InsiderHoldingsSec itself failed."""
        content = PIPELINE_TF.read_text()
        match = re.search(
            r"InsiderHoldingsSec\s*=\s*\{.*?\n\s{6}\}", content, re.DOTALL
        )
        assert match, "could not locate the InsiderHoldingsSec state block"
        assert 'Next = "InsiderTransactionVelocity"' in match.group(0), (
            "InsiderHoldingsSec's success path must chain to InsiderTransactionVelocity, "
            "not skip past it"
        )
