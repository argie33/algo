"""Regression test: Orchestrator._wait_for_critical_loaders_proactive() must let its own
intentionally-raised "loader stalled" RuntimeError propagate unchanged, not fall into its own
generic except-Exception handler.

Bug (found 2026-08-10 via live orchestrator log, orch_full_run.log): on timeout, the function
raises `RuntimeError("... Loader appears hung ... Halting to investigate ...")` from inside the
same outer `try:` block that also has a catch-all `except Exception as e:` clause. Since
RuntimeError is an Exception subclass, that raise was re-caught by the function's own handler
and re-wrapped as "[PROACTIVE WAIT] Unexpected error during proactive wait: ... This indicates a
programming error or unhandled exception type." - live-confirmed in orch_full_run.log lines
147-148. The caller (_wait_for_loaders_before_execution) catches RuntimeError either way and
proceeds to Phase 1 regardless, so behavior was unchanged, but the log message actively misled
anyone debugging a real stalled-loader incident into thinking it was a code bug instead of a
data/infrastructure issue.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "algo" / "orchestration" / "orchestrator.py"


def _find_method(name: str) -> ast.FunctionDef:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Method {name} not found in {SOURCE}")


def test_own_runtimeerror_reraised_before_generic_exception_handler():
    method = _find_method("_wait_for_critical_loaders_proactive")
    try_nodes = [node for node in ast.walk(method) if isinstance(node, ast.Try)]

    # The outer try (the one with a catch-all `except Exception`) is the one whose
    # handler ordering matters here.
    def _handler_types(t: ast.Try) -> list[str | None]:
        return [ast.unparse(h.type) if h.type is not None else None for h in t.handlers]

    outer_try = next(t for t in try_nodes if "Exception" in _handler_types(t))
    handler_types = _handler_types(outer_try)

    assert "RuntimeError" in handler_types, (
        "Expected an explicit `except RuntimeError` handler guarding the generic "
        "`except Exception` handler in the same try block."
    )
    runtime_error_idx = handler_types.index("RuntimeError")
    generic_idx = handler_types.index("Exception")
    assert runtime_error_idx < generic_idx, (
        "`except RuntimeError` must come before the generic `except Exception` handler, "
        "otherwise it never gets reached (Python matches the first applicable handler in "
        "order) and the intentionally-raised RuntimeError falls into the generic handler."
    )

    runtime_error_handler = outer_try.handlers[runtime_error_idx]
    body_src = "\n".join(ast.unparse(stmt) for stmt in runtime_error_handler.body)
    assert body_src.strip() == "raise", (
        "The RuntimeError handler must be a bare `raise` (propagate unchanged) - not "
        "re-wrap the message, which would reintroduce the misleading "
        "'programming error or unhandled exception type' relabeling for our own "
        "intentionally-raised stalled-loader signal."
    )
