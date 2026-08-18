"""Regression test (2026-08-18, missing factor inputs audit): _insert_growth_metrics'
VALUES clause had 50 "%s" placeholders but only 49 columns and 49 bound values - a real,
live-confirmed production bug (data_loader_status: growth_metrics/value_metrics FAILED,
consecutive_failures=4/6, "IndexError: tuple index out of range" inside psycopg2's
parameter substitution) that broke growth_metrics inserts entirely for every symbol reaching
this code path. Introduced when an earlier fix (78abb704f, same day) added
earnings_surprise_avg/earnings_beat_rate to the column list and values tuple but left one
extra "%s" behind in the VALUES clause from before that edit.

None of the existing loader tests would have caught this: they all mock the cursor with a
plain MagicMock, which records execute() calls without validating that the SQL's placeholder
count matches the params tuple length - only a real psycopg2 cursor (or a mock that checks
this explicitly, as here) exercises that. This test asserts the invariant directly against
the loader's actual source (not a hardcoded copy of the query) for all 3 INSERT methods in
this file, so a future column-list edit that forgets to update one of the two other spots
(VALUES placeholders, or the bound-values tuple) fails immediately instead of silently
breaking every future loader run.
"""

import ast
import inspect
import textwrap

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _insert_methods_with_execute_call() -> dict[str, ast.Call]:
    """Find every `_insert_*` method's cur.execute(...) call in the loader's real source,
    via AST (not string-matching) so this test can't be fooled by a query string that spans
    multiple concatenated literals or comments containing "%s"."""
    calls = {}
    for name in dir(ValueQualityGrowthMetricsLoader):
        if not name.startswith("_insert_"):
            continue
        method = getattr(ValueQualityGrowthMetricsLoader, name)
        source = textwrap.dedent(inspect.getsource(method))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute"
                and len(node.args) == 2
            ):
                calls[name] = node
                break
    return calls


class TestInsertPlaceholderCounts:
    def test_every_insert_methods_placeholder_count_matches_its_bound_values(self) -> None:
        calls = _insert_methods_with_execute_call()
        assert len(calls) >= 3, (
            f"expected to find at least 3 _insert_* methods with an execute() call, found {sorted(calls)}"
        )

        mismatches = []
        for name, call in calls.items():
            sql_node, params_node = call.args
            assert isinstance(sql_node, ast.Constant) and isinstance(sql_node.value, str), (
                f"{name}: expected a plain string literal SQL argument"
            )
            placeholder_count = sql_node.value.count("%s")

            assert isinstance(params_node, ast.Tuple), f"{name}: expected a tuple literal as the params argument"
            tuple_len = len(params_node.elts)

            if placeholder_count != tuple_len:
                mismatches.append(f"{name}: {placeholder_count} '%s' placeholders vs {tuple_len} bound values")

        assert not mismatches, "\n".join(mismatches)
