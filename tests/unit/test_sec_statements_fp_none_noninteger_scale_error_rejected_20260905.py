"""Regression test for a second, distinct layer of the DEF 14A Pay-vs-Performance
scale-error bug (utils/external/sec_statements.py's `_aggregate_concepts_resolve_entry_period`):

commit 430cf00b5 already fixed the case where a primary financial-statement form (10-K) and
a proxy (DEF 14A) both tag the SAME concept (e.g. NetIncomeLoss) - it ranks the 10-K entry
above the DEF 14A one regardless of filing date. That fix does nothing when the filer's real
10-K never tags the corrupted concept AT ALL under any form - live-confirmed via KRC (Kilroy
Realty): its 10-K only ever tags "ProfitLoss" (correctly, $302,640,000 for FY2025), never
"NetIncomeLoss". The ONLY "NetIncomeLoss" entries anywhere in KRC's companyfacts come from its
DEF 14A Pay-vs-Performance table, tagged in $ millions with a decimal (302.64) instead of whole
dollars - with no primary-form NetIncomeLoss entry to rank-gate against, this corrupted value
sailed straight through and (via load_financial_statements.py's field_mapping, which maps both
"profit_loss" and "net_income_loss" to the same "net_income" column) silently clobbered the
correct value once written to the database - confirmed live: annual_income_statement.net_income
was 302.64 for FY2025, 232.95 for FY2024, both real corrupted DB rows as of 2026-09-05.

Fix: reject any fp=None (proxy-statement) monetary fact whose value is not a whole-dollar
integer - a genuine XBRL USD fact for a company's real financial-statement figure is always a
whole dollar amount; a non-integer value under a whole-dollar concept is the specific signature
of a "$X.XX million" scale error. Scoped to fp is None only (real 10-K/10-Q facts, which never
have this issue, are completely unaffected) and skips PerShare concepts (EPS is legitimately
fractional). Verified against EE (Excelerate Energy) - the original motivating case for
accepting fp=None proxy facts at all - whose real DEF 14A NetIncomeLoss values are genuine
whole-dollar integers, so this fix doesn't regress that recovery.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestFpNoneNonIntegerScaleErrorRejected:
    def test_krc_style_def14a_only_net_income_loss_rejected(self):
        """KRC's real shape: the 10-K tags ProfitLoss (correct), never NetIncomeLoss at
        all - the only NetIncomeLoss entries are DEF 14A Pay-vs-Performance facts scaled
        to millions with a decimal. No primary-form NetIncomeLoss entry exists to rank
        against, so the old code accepted the corrupted proxy value outright."""
        facts = {
            "us-gaap": {
                "ProfitLoss": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 302640000.0,
                            "filed": "2026-02-20",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0001193125-26-000001",
                        },
                    ]
                ),
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 302.64,
                            "filed": "2026-04-09",
                            "fp": None,
                            "fy": None,
                            "form": "DEF 14A",
                            "accn": "0001193125-26-000002",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "KRC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # The corrupted NetIncomeLoss entry must be rejected entirely (not present in the
        # row at all), leaving the real ProfitLoss value as the only candidate for
        # net_income - without the fix, "net_income_loss": 302.64 would appear in the row
        # and (via field_mapping) clobber the correct 302,640,000 once persisted.
        assert "net_income_loss" not in by_year[2025]
        assert by_year[2025]["profit_loss"] == 302640000.0

    def test_ee_style_whole_dollar_proxy_only_value_still_accepted(self):
        """The original motivating case for accepting fp=None at all (EE/Excelerate
        Energy): a proxy-only real net income figure, but a genuine whole-dollar integer -
        must still be recovered, not rejected as a false positive."""
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2022-01-01",
                            "end": "2022-12-31",
                            "val": 79996000.0,
                            "filed": "2026-04-16",
                            "fp": None,
                            "fy": None,
                            "form": "DEF 14A",
                            "accn": "0001193125-26-000003",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "EE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2022]["net_income_loss"] == 79996000.0
