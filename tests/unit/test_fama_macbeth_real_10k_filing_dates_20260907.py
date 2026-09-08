"""Regression test for a 2026-09-07 fix (/goal "cheaters and samplers" audit) to
algo/research/fama_macbeth_growth_factors.py's point-in-time known_date computation.

Every Fama-MacBeth backtest script in algo/research (growth/quality/value/composite-weights -
the ones that directly justify the live BASE_PILLAR_WEIGHTS) previously assumed EVERY company
has a calendar (Dec 31) fiscal year-end plus a flat 90-day reporting lag, because none of the
three annual statement tables carry a real filing_date or fiscal-year-end date. This is a real
lookahead-bias risk for non-calendar-FY companies (AAPL/MSFT-style) - already self-disclosed in
that module's own docstring, not a hidden bug.

Fix: real_10k_filing_dates()/compute_known_dates() recover the REAL 10-K filing date per
(symbol, fiscal_year) from this machine's local SEC EDGAR disk caches (already populated by
ordinary loader runs - see utils/external/sec_ticker_cache.py / sec_edgar_client.py), falling
back to the old calendar-year-end + REPORTING_LAG_DAYS approximation only where the local cache
has no entry. These tests build a throwaway cache under tmp_path so they don't depend on
whatever happens to be cached on the machine running them.
"""

import json

import pandas as pd

from algo.research import fama_macbeth_growth_factors as g


def _write_fake_caches(tmp_path, ticker_map: dict[str, str], companyfacts: dict[str, dict]) -> None:
    ticker_file = tmp_path / "sec_ticker_cache.json"
    ticker_file.write_text(json.dumps({"mapping": ticker_map, "timestamp": 0}))

    facts_dir = tmp_path / "algo-sec-edgar-cache" / "companyfacts"
    facts_dir.mkdir(parents=True)
    for cik, facts in companyfacts.items():
        (facts_dir / f"{cik}.json").write_text(json.dumps({"timestamp": 0, "data": {"facts": facts}}))


def _fake_facts(rows: list[tuple[int, str, str, str]]) -> dict:
    """rows: (fy, fp, form, filed) tuples, all filed under one us-gaap concept/unit."""
    return {
        "us-gaap": {
            "Assets": {
                "units": {"USD": [{"fy": fy, "fp": fp, "form": form, "filed": filed} for fy, fp, form, filed in rows]}
            }
        }
    }


class TestReal10kFilingDates:
    def test_real_filing_date_recovered_for_cached_symbol(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(g, "_TICKER_CACHE_FILE", tmp_path / "sec_ticker_cache.json")
        monkeypatch.setattr(g, "_COMPANYFACTS_CACHE_DIR", tmp_path / "algo-sec-edgar-cache" / "companyfacts")
        # AAPL-shaped: non-calendar fiscal year-end (real FY2024 10-K filed 2024-11-01, not
        # anywhere near the old assumed 2025-03-31 = Dec-31 + 90 days).
        _write_fake_caches(
            tmp_path,
            ticker_map={"AAPL": "0000320193"},
            companyfacts={"0000320193": _fake_facts([(2024, "FY", "10-K", "2024-11-01")])},
        )

        result = g.real_10k_filing_dates(["AAPL"])

        assert result[("AAPL", 2024)] == pd.Timestamp("2024-11-01")

    def test_uncached_symbol_absent_not_erroring(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(g, "_TICKER_CACHE_FILE", tmp_path / "sec_ticker_cache.json")
        monkeypatch.setattr(g, "_COMPANYFACTS_CACHE_DIR", tmp_path / "algo-sec-edgar-cache" / "companyfacts")
        _write_fake_caches(tmp_path, ticker_map={}, companyfacts={})

        result = g.real_10k_filing_dates(["NOSUCHSYMBOL"])

        assert result == {}

    def test_10q_rows_ignored_only_10k_fy_rows_used(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(g, "_TICKER_CACHE_FILE", tmp_path / "sec_ticker_cache.json")
        monkeypatch.setattr(g, "_COMPANYFACTS_CACHE_DIR", tmp_path / "algo-sec-edgar-cache" / "companyfacts")
        _write_fake_caches(
            tmp_path,
            ticker_map={"AAPL": "0000320193"},
            companyfacts={
                "0000320193": _fake_facts(
                    [
                        (2024, "Q3", "10-Q", "2024-08-01"),  # must be ignored
                        (2024, "FY", "10-K", "2024-11-01"),  # must be used
                    ]
                )
            },
        )

        result = g.real_10k_filing_dates(["AAPL"])

        assert result[("AAPL", 2024)] == pd.Timestamp("2024-11-01")


class TestComputeKnownDates:
    def test_falls_back_to_approximation_when_no_real_date_cached(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(g, "_TICKER_CACHE_FILE", tmp_path / "sec_ticker_cache.json")
        monkeypatch.setattr(g, "_COMPANYFACTS_CACHE_DIR", tmp_path / "algo-sec-edgar-cache" / "companyfacts")
        _write_fake_caches(tmp_path, ticker_map={}, companyfacts={})
        df = pd.DataFrame({"symbol": ["ZZZZ"], "fiscal_year": [2023]})

        result = g.compute_known_dates(df)

        expected = pd.Timestamp("2023-12-31") + pd.Timedelta(days=g.REPORTING_LAG_DAYS)
        assert result.iloc[0] == expected

    def test_uses_real_date_when_cached_mixed_with_fallback_rows(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(g, "_TICKER_CACHE_FILE", tmp_path / "sec_ticker_cache.json")
        monkeypatch.setattr(g, "_COMPANYFACTS_CACHE_DIR", tmp_path / "algo-sec-edgar-cache" / "companyfacts")
        _write_fake_caches(
            tmp_path,
            ticker_map={"AAPL": "0000320193"},
            companyfacts={"0000320193": _fake_facts([(2024, "FY", "10-K", "2024-11-01")])},
        )
        df = pd.DataFrame({"symbol": ["AAPL", "NOCACHE"], "fiscal_year": [2024, 2024]})

        result = g.compute_known_dates(df)

        assert result.iloc[0] == pd.Timestamp("2024-11-01")
        assert result.iloc[1] == pd.Timestamp("2024-12-31") + pd.Timedelta(days=g.REPORTING_LAG_DAYS)
