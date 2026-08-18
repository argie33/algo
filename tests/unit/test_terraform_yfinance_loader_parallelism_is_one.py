"""Regression test: yfinance-based loaders' Terraform Step Functions LOADER_PARALLELISM
override must be 1, never higher.

Bug (found 2026-08-18): terraform/modules/pipeline/main.tf's Step Functions state definitions
override LOADER_PARALLELISM=2 for several loaders, even though the ECS task-def default
(terraform/modules/loaders/main.tf's `all_loaders` map) already correctly says parallelism=1
for the same loaders - the SFN override was silently defeating the correct default. This
violates this repo's own load-bearing rule
([[analyst_loaders_reloaded_and_local_parallelism_ban_20260810]] in MEMORY.md): yfinance
blocks/rate-limits at parallelism>=2, so yfinance-based loaders must run with
LOADER_PARALLELISM=1. Confirmed via logs that local runs (which don't read this terraform-only
override) already correctly use parallelism=1 - this was a dormant AWS-deploy-only landmine
(deploy is currently blocked by an unrelated AWS IAM issue), not yet a live production incident,
but would have caused rate-limiting/ban issues on the next successful deploy. Found for
earnings_calendar, analyst_earnings_estimates, and enhanced_quality_growth_metrics; fixed for
all three (`LOADER_PARALLELISM=1`).

YFINANCE_LOADERS below is a manually-curated allowlist (not dynamically detected): several of
these loaders call yfinance indirectly through utils/external/yfinance_analyst_ratings.py or
yfinance_financials.py rather than importing yfinance directly in the loader module itself, so
a simple "grep the loader file for `import yfinance`" check would miss them - verified each via
its module docstring instead. Extend this list (with the same verification) if another
yfinance-based loader is added.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_TF = REPO_ROOT / "terraform" / "modules" / "pipeline" / "main.tf"

# Loaders confirmed yfinance-based via their module docstring/imports (see docstring above for
# why this is curated, not auto-detected). SEC-only or internal-only loaders (e.g.
# company_profile, value_quality_growth_metrics, stock_scores) are deliberately excluded - SEC
# EDGAR's documented ~2 req/sec allowance is a different constraint than yfinance's aggressive
# rate limiting, and internal-only loaders make no external API calls at all.
YFINANCE_LOADERS = {
    "earnings_calendar",
    "analyst_earnings_estimates",
    "enhanced_quality_growth_metrics",
}


def _parse_task_definition_parallelism() -> dict[str, list[int]]:
    """Map each `var.loader_task_definition_arns["<name>"]` block in pipeline/main.tf to every
    LOADER_PARALLELISM value found in its ContainerOverrides Environment list.

    A loader can appear in multiple Step Functions states (e.g. both the EOD and morning
    pipelines) - collects every occurrence so none are silently skipped.
    """
    content = PIPELINE_TF.read_text(encoding="utf-8")
    result: dict[str, list[int]] = {}
    for m in re.finditer(r'var\.loader_task_definition_arns\["(\w+)"\]', content):
        name = m.group(1)
        # Look at the next ~40 lines after this TaskDefinition reference for its
        # ContainerOverrides Environment block - LOADER_PARALLELISM always lives there.
        window = content[m.end() : m.end() + 1500]
        env_end = window.find("}]")
        env_end = env_end if env_end != -1 else len(window)
        window = window[:env_end]
        for p in re.findall(r'"LOADER_PARALLELISM"\s*,\s*Value\s*=\s*"(\d+)"', window):
            result.setdefault(name, []).append(int(p))
    return result


def test_yfinance_loaders_never_override_parallelism_above_one() -> None:
    parallelism_by_loader = _parse_task_definition_parallelism()

    assert parallelism_by_loader, (
        "parsed zero LOADER_PARALLELISM overrides from pipeline/main.tf - parser likely broken"
    )

    violations = []
    for name in sorted(YFINANCE_LOADERS):
        values = parallelism_by_loader.get(name)
        if not values:
            continue  # this yfinance loader has no explicit override in any SFN state - fine, defaults to the ECS task-def value
        bad = [v for v in values if v != 1]
        if bad:
            violations.append(f"  {name}: LOADER_PARALLELISM={bad} (must be 1 - yfinance blocks/rate-limits at >=2)")

    assert not violations, (
        "These yfinance-based loaders have a Terraform Step Functions LOADER_PARALLELISM "
        "override above 1, which will trigger yfinance rate limiting/bans on deploy:\n" + "\n".join(violations)
    )
