"""Regression test for a 2026-08-10 bug (ruff B023) in
loaders/load_financial_statements.py's _run_symbol_pass(): the per-symbol-timeout inner
closure `run_with_timeout` referenced `loader`, `symbol`, `result`, `exception` from the
enclosing loop scope instead of binding them at closure-creation time. Since all closures
created across loop iterations share the SAME enclosing-scope cells (one loop, one
function frame), an abandoned (timed-out but not actually killed - daemon threads can't be
force-killed) thread that finishes its real work later would write result[0]/exception[0]
into whatever the CURRENT loop iteration's result list is by then, silently corrupting a
different symbol's processed/failed accounting.

Fixed by binding loader/symbol/result/exception as default arguments (evaluated at
def-time, not call-time) - the standard fix for this class of closure-over-loop-variable
bug. Both helpers below reproduce the exact structure of _run_symbol_pass's inner loop (one
function, one loop, closures created per iteration) so the shared-cell behavior is real,
not an artifact of test scaffolding.
"""

from __future__ import annotations


class FakeLoader:
    def __init__(self, name: str) -> None:
        self.table_name = name

    def load_symbol(self, symbol: str) -> None:
        pass


ResultLists = list[tuple[list[bool], list[Exception | None]]]


def _run_late_binding_loop(items: list[tuple[FakeLoader, str]]) -> tuple[list[object], ResultLists]:
    """Mirrors the pre-fix _run_symbol_pass shape: one function, one loop, closures
    defined inline each iteration without default-arg binding. Returns the list of
    (result, exception) lists created, plus the list of created-but-not-yet-invoked
    closures, so the test can invoke them out of order like an abandoned thread would."""
    closures: list[object] = []
    results: ResultLists = []
    for loader, symbol in items:
        result: list[bool] = [False]
        exception: list[Exception | None] = [None]
        results.append((result, exception))

        # Deliberately reproduces the late-binding bug being regression-tested below.
        def run_with_timeout() -> None:
            try:
                loader.load_symbol(symbol)  # noqa: B023
                result[0] = True  # noqa: B023
            except Exception as e:
                exception[0] = e  # noqa: B023
                result[0] = False  # noqa: B023

        closures.append(run_with_timeout)
    return closures, results


def _run_early_binding_loop(items: list[tuple[FakeLoader, str]]) -> tuple[list[object], ResultLists]:
    """Mirrors the fix: default-argument binding."""
    closures: list[object] = []
    results: ResultLists = []
    for loader, symbol in items:
        result: list[bool] = [False]
        exception: list[Exception | None] = [None]
        results.append((result, exception))

        def run_with_timeout(
            loader: FakeLoader = loader,
            symbol: str = symbol,
            result: list[bool] = result,
            exception: list[Exception | None] = exception,
        ) -> None:
            try:
                loader.load_symbol(symbol)
                result[0] = True
            except Exception as e:
                exception[0] = e
                result[0] = False

        closures.append(run_with_timeout)
    return closures, results


def test_late_binding_closure_reproduces_the_bug() -> None:
    """Iteration 1's closure is created but not invoked (simulating an abandoned,
    timed-out thread). By the time it finally runs, the loop has moved on to iteration 2,
    which reassigned the SAME enclosing result/exception/loader/symbol cells - the bug: the
    late invocation corrupts iteration 2's result list instead of writing to iteration 1's
    own list."""
    items = [
        (FakeLoader("iteration_1_loader"), "SYM1"),
        (FakeLoader("iteration_2_loader"), "SYM2"),
    ]
    closures, results = _run_late_binding_loop(items)
    result_iter1, _exc_iter1 = results[0]
    result_iter2, _exc_iter2 = results[1]

    # The abandoned iteration-1 closure finally gets invoked, after iteration 2 already ran.
    closures[0]()  # type: ignore[operator]

    assert result_iter2[0] is True, (
        "reproduces the bug: iteration 1's late-completing closure wrote into "
        "iteration 2's result list because both share the same enclosing-scope cell"
    )
    assert result_iter1[0] is False, "iteration 1's own result list was never actually written"


def test_early_binding_closure_is_immune() -> None:
    """The fix: default-argument binding means each closure keeps writing to the exact
    result/exception list (and calls the exact loader/symbol) it was created with, no
    matter how many later loop iterations have reassigned the enclosing scope's names."""
    items = [
        (FakeLoader("iteration_1_loader"), "SYM1"),
        (FakeLoader("iteration_2_loader"), "SYM2"),
    ]
    closures, results = _run_early_binding_loop(items)
    result_iter1, _exc_iter1 = results[0]
    result_iter2, _exc_iter2 = results[1]

    closures[0]()  # type: ignore[operator]

    assert result_iter1[0] is True, "fixed closure must write to its own (iteration 1) result list"
    assert result_iter2[0] is False, "iteration 2's result list must be untouched by iteration 1's late completion"
