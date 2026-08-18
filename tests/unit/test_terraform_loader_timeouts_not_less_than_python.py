"""Regression test: every loader's Terraform ECS task-def timeout must be >= its Python
timeout (loaders/loader_timeout_config.py).

Bug class (found repeatedly - 2026-08-17 for current_reports_8k/dividend_data, 2026-08-18 for
9 more loaders): this repo's own load-bearing rule
([[terraform_loader_timeouts_must_match_python_config]] in MEMORY.md) says the ECS task-def
timeout must track the Python-side timeout, but nothing ever enforced it - a Python timeout
gets raised after a live timeout-kill, the fix lands, and terraform silently drifts out of
sync until the next person happens to notice. Live-confirmed on the 2026-08-18 sweep: 9
loaders (company_info_sec, sec_segment_info, analyst_earnings_estimates, and 6 others) had a
Terraform timeout as low as 55% of the Python value - in production this would kill the ECS
task long before the loader's own internal timeout logic (or the actual workload) ever got a
chance to finish, silently truncating real work on every run.

This only checks terraform/modules/loaders/main.tf's `all_loaders` map (the ECS task
definition timeout) - not terraform/modules/pipeline/main.tf's Step Functions TimeoutSeconds,
which needs its own margin-aware comparison and isn't name-mechanically mappable from the
loader's snake_case name to the state machine's PascalCase state name without a hardcoded
alias table. That side was manually re-audited and fixed as part of the same 2026-08-18 sweep,
but stays unenforced by this test - worth automating separately if this class recurs a third
time.
"""

import re
from pathlib import Path

from loaders.loader_timeout_config import get_loader_timeouts

REPO_ROOT = Path(__file__).resolve().parents[2]
LOADERS_TF = REPO_ROOT / "terraform" / "modules" / "loaders" / "main.tf"


def _parse_terraform_all_loaders_timeouts() -> dict[str, int]:
    """Extract {loader_name: timeout_seconds} from the `all_loaders` HCL map.

    Scoped to the `all_loaders = { ... }` block specifically (matching braces) so this
    doesn't accidentally pick up an unrelated `timeout = N` elsewhere in the file (e.g. a
    health-check script timeout). Skips commented-out entries (deprecated/consolidated
    loaders) - those aren't live infrastructure.
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


def test_no_terraform_loader_timeout_is_less_than_python_timeout() -> None:
    python_timeouts = get_loader_timeouts()
    terraform_timeouts = _parse_terraform_all_loaders_timeouts()

    assert terraform_timeouts, "parsed zero entries from terraform's all_loaders map - parser likely broken"

    shared_names = set(python_timeouts) & set(terraform_timeouts)
    assert shared_names, "zero loader names in common between Python config and Terraform - name parsing likely broken"

    violations = [
        f"  {name}: python={python_timeouts[name]}s terraform={terraform_timeouts[name]}s "
        f"(terraform is only {100 * terraform_timeouts[name] // python_timeouts[name]}% of python)"
        for name in sorted(shared_names)
        if terraform_timeouts[name] < python_timeouts[name]
    ]
    assert not violations, (
        "Terraform ECS task-def timeout is LOWER than the Python timeout for these loaders - "
        "production would kill the task before the loader's own timeout logic (or the real "
        "workload) finishes:\n" + "\n".join(violations)
    )
