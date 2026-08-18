"""Regression test: every Step Functions state's TimeoutSeconds
(terraform/modules/pipeline/main.tf) must be >= that loader's ECS task-def timeout
(terraform/modules/loaders/main.tf's `all_loaders` map).

Bug class (found 2026-08-18, the same day the sibling ECS-vs-Python test
[[test_terraform_loader_timeouts_not_less_than_python]] was added for a related but
distinct gap): that test's own docstring flagged this exact blind spot - Step Functions
TimeoutSeconds "needs its own margin-aware comparison and isn't name-mechanically
mappable... without a hardcoded alias table" - and left it "unenforced... worth
automating separately if this class recurs a third time." It did: live-confirmed 5
states (AaiiSentiment, InsiderTransactionVelocity x2, SecValuations,
EnhancedQualityGrowthMetrics, InsiderHoldingsSec) had a Step Functions TimeoutSeconds
LOWER than their own ECS task-def timeout - as low as 6.7% of the real ECS budget for
EnhancedQualityGrowthMetrics (1200s SFN vs 18000s ECS). In production this kills the
Step Functions execution (and the ECS task under it) before the ECS-level timeout, or
the real workload, ever gets a chance to finish - silently truncating real work on
every run, exactly like the ECS-vs-Python bug class this mirrors.

Avoids the PascalCase-state-name-to-snake_case-loader-key guessing problem entirely:
every Task state's `TaskDefinition` line already references
`var.loader_task_definition_arns["<loader_name>"]` directly, which IS the loader's real
config/ECS key - so this pairs each TimeoutSeconds with the nearest preceding
TaskDefinition's loader key instead of guessing from the state name.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_TF = REPO_ROOT / "terraform" / "modules" / "pipeline" / "main.tf"
LOADERS_TF = REPO_ROOT / "terraform" / "modules" / "loaders" / "main.tf"


def _parse_terraform_all_loaders_timeouts() -> dict[str, int]:
    """Extract {loader_name: timeout_seconds} from the `all_loaders` HCL map.

    Duplicated (not imported) from test_terraform_loader_timeouts_not_less_than_python.py -
    cross-importing between test modules by bare name isn't set up in this repo's pytest
    config, and this parser is small enough that duplicating it beats fighting sys.path.
    Scoped to the `all_loaders = { ... }` block specifically (matching braces) so this
    doesn't accidentally pick up an unrelated `timeout = N` elsewhere in the file. Skips
    commented-out entries (deprecated/consolidated loaders) - those aren't live infrastructure.
    """
    content = LOADERS_TF.read_text(encoding="utf-8")
    start = content.index("all_loaders = {")
    depth = 0
    end = start
    for i, ch in enumerate(content[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    block = content[start:end]

    live_lines = [line for line in block.splitlines() if not line.strip().startswith("#")]
    live_block = "\n".join(live_lines)

    timeouts: dict[str, int] = {}
    for name, secs in re.findall(r'"(\w+)"\s*=\s*\{[^}]*timeout\s*=\s*(\d+)', live_block):
        timeouts[name] = int(secs)
    return timeouts


def _parse_sfn_timeouts_by_loader_key() -> list[tuple[str, int]]:
    """Pair each Step Functions TimeoutSeconds with its loader key, via the
    `loader_task_definition_arns["<key>"]` reference in that same Task state (the
    nearest one following the TimeoutSeconds line). Returns a list, not a dict, since
    several loaders legitimately appear in more than one pipeline/state machine."""
    content = PIPELINE_TF.read_text(encoding="utf-8")

    ts_matches = [(m.start(), int(m.group(1))) for m in re.finditer(r"TimeoutSeconds\s*=\s*(\d+)", content)]
    td_matches = [(m.start(), m.group(1)) for m in re.finditer(r'loader_task_definition_arns\["(\w+)"\]', content)]

    pairs = []
    for td_pos, loader_key in td_matches:
        preceding = [t for t in ts_matches if t[0] < td_pos]
        if preceding:
            pairs.append((loader_key, preceding[-1][1]))
    return pairs


def test_parser_finds_a_reasonable_number_of_states() -> None:
    """Sanity check the parser itself isn't broken (e.g. by a terraform refactor
    changing the TaskDefinition line's shape) - a suspiciously low count means pairs
    are silently being dropped, not that the pipeline shrank."""
    pairs = _parse_sfn_timeouts_by_loader_key()
    assert len(pairs) >= 30, (
        f"Only found {len(pairs)} Step Functions state timeout/loader-key pairs - "
        "expected 30+. The TaskDefinition/TimeoutSeconds parsing regex likely needs updating."
    )


def test_no_step_functions_timeout_is_less_than_its_ecs_task_def_timeout() -> None:
    sfn_pairs = _parse_sfn_timeouts_by_loader_key()
    ecs_timeouts = _parse_terraform_all_loaders_timeouts()

    violations = [
        f"  {loader_key}: sfn={sfn_secs}s ecs={ecs_timeouts[loader_key]}s "
        f"(sfn is only {100 * sfn_secs // ecs_timeouts[loader_key]}% of ecs)"
        for loader_key, sfn_secs in sfn_pairs
        if loader_key in ecs_timeouts and sfn_secs < ecs_timeouts[loader_key]
    ]
    assert not violations, (
        "Step Functions TimeoutSeconds is LOWER than the ECS task-def timeout for these "
        "loaders - production would kill the Step Functions execution (and the ECS task "
        "under it) before the ECS timeout, or the real workload, ever finishes:\n" + "\n".join(violations)
    )
