"""Regression test: every loader name in local_loader_scheduler.py's PIPELINES
must resolve via loader_registry.normalize_loader_name().

Guards against the exact wiring-drift bug class documented throughout
steering/DATA_LOADERS.md: a loader added to a PIPELINES list without also
adding its shorthand to loader_registry.SHORTHAND_TO_FILENAME, which raises
ValueError on the very first pipeline step and blocks the whole run. Caught
live 2026-08-09: "financial_statements" was RE-ENABLED in the metrics
pipeline list but never added to SHORTHAND_TO_FILENAME.
"""

import importlib.util
from pathlib import Path

import pytest

from loaders.loader_registry import normalize_loader_name

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_pipelines():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PIPELINES


@pytest.mark.parametrize("pipeline_name,loaders", _load_pipelines().items())
def test_pipeline_loader_names_resolve(pipeline_name, loaders):
    for loader in loaders:
        normalize_loader_name(loader)  # raises ValueError if unresolvable
