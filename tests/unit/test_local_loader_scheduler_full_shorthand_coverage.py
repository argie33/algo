"""Regression test: every SHORTHAND_TO_FILENAME entry must be reachable from some
scripts/local_loader_scheduler.py PIPELINES list.

Bug class (2 confirmed instances, same day, 2026-08-10): a loader can be fully registered
(SHORTHAND_TO_FILENAME + LOADER_TIMEOUTS) and still be unreachable via the sanctioned
`--now {pipeline}` path (see feedback_always_use_pipeline_scheduler_for_backfills) if nobody
also added it to a PIPELINES list. First caught for 9 loaders
(local_scheduler_reference_pipeline_added_20260810), then a 10th (earnings_sec) and 6 more
were found the SAME DAY because that fix was verified by checking "does everything I added
work", not by diffing the full SHORTHAND_TO_FILENAME inventory against PIPELINES
(local_scheduler_second_wave_orphaned_loaders_20260810). This test closes the gap
permanently: any newly-registered loader that isn't wired into a pipeline fails CI instead of
silently sitting unreachable until someone happens to need it.

"momentum" is a deliberate exception: it's a second alias for load_risk_metrics_daily.py,
already reachable via its "stability_metrics" alias in the "metrics" pipeline.
"""

from loaders.loader_registry import SHORTHAND_TO_FILENAME, normalize_loader_name
from scripts.local_loader_scheduler import PIPELINES

# Documented intentional aliases that don't need their own PIPELINES entry because a
# sibling alias for the same loader file is already reachable.
ALIASED_SHORTHANDS_COVERED_BY_A_SIBLING = frozenset({"momentum"})


def test_every_registered_loader_is_reachable_from_some_pipeline():
    reachable_filenames = {normalize_loader_name(loader) for loaders in PIPELINES.values() for loader in loaders}

    orphaned = [
        shorthand
        for shorthand, filename in SHORTHAND_TO_FILENAME.items()
        if shorthand not in ALIASED_SHORTHANDS_COVERED_BY_A_SIBLING and filename not in reachable_filenames
    ]

    assert not orphaned, (
        f"These loaders are registered in SHORTHAND_TO_FILENAME but unreachable from any "
        f"PIPELINES list in scripts/local_loader_scheduler.py: {orphaned}. Add them to a "
        f"pipeline (or to ALIASED_SHORTHANDS_COVERED_BY_A_SIBLING if a sibling alias already "
        f"covers the same loader file) - otherwise `--now {{pipeline}}` can never reach them "
        f"locally, silently defeating feedback_always_use_pipeline_scheduler_for_backfills."
    )
