"""Regression test for lambda/api/routes/signals.py::_get_signals_stocks (2026-08-17).

Bug, live-reproduced: a SQL comment inside the SELECT ("-- RS% FIX (2026-08-03): ...")
contained a literal "%" character. psycopg2's %s-placeholder substitution scans the raw
query STRING for "%" regardless of SQL "--" comment syntax, so a bare "%" not immediately
followed by "s" (or another valid format spec) breaks its internal placeholder count and
raises "IndexError: tuple index out of range" from psycopg2.extras.DictCursorBase.execute()
on every call to this endpoint - reproduced via GET /api/signals/stocks?symbol=AAPL&limit=
10&timeframe=daily. No test previously covered this endpoint at all, which is why the bug
shipped unnoticed.

Fix: rephrased the comment to avoid any bare "%". This test guards the query text directly
so any future comment/string added to the query with a stray "%" fails fast here instead of
only surfacing as a live 500.

'lambda' is a Python keyword, so the module under test is loaded via importlib.
"""

import importlib
import inspect
import re

signals_module = importlib.import_module("lambda.api.routes.signals")


class TestSignalsStocksQueryHasNoStrayPercent:
    def test_query_text_has_no_bare_percent_outside_placeholders(self) -> None:
        source = inspect.getsource(signals_module._get_signals_stocks.__wrapped__)
        match = re.search(r'cur\.execute\(\s*f?"""(.*?)""",', source, re.DOTALL)
        assert match is not None, "could not locate the cur.execute(...) call in _get_signals_stocks"
        query = match.group(1)

        # Every "%" in the query must be part of a "%s" placeholder - a bare "%" (in a
        # comment, string literal, or anywhere else) breaks psycopg2's substitution and
        # raises IndexError at request time, regardless of SQL comment syntax.
        bare_percents = [m.start() for m in re.finditer(r"%(?!s)", query)]
        assert bare_percents == [], (
            f"found {len(bare_percents)} bare '%' character(s) not part of a '%s' "
            f"placeholder in _get_signals_stocks's query - each one breaks psycopg2's "
            f"placeholder substitution with IndexError at request time. Positions: {bare_percents}"
        )
        assert query.count("%s") >= 1, "sanity check: query should still contain real %s placeholders"
