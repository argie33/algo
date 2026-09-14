#!/usr/bin/env python3
"""Detects the GRN/Barclays bug class systemically instead of one symbol at a time: a CIK
shared by many active ticker symbols (the standard SEC filing pattern for an ETF/ETN/trust
sponsor - Barclays' own CIK covers DJP/VXX/VXZ/ATMP/JJETF/TAPR/GBUG/BWVTF/GRN) where most of
those symbols correctly have no extracted company-level financial statements (an ETF/ETN
ticker has no operating-company financials of its own), but a MINORITY nonetheless have real
annual_income_statement/annual_balance_sheet rows - live-confirmed as the exact GRN bug (see
grn_barclays_etn_misattribution_fixed_20260913): GRN's own extraction pulled Barclays' real
$10B+ bank-holding-company financials, live-confirmed across 6 tables/56 rows, because two
independent ETF-detection gates (the upstream ETF flag, the "etf" name-substring check) both
missed it while `KNOWN_ETF_MISCLASSIFICATIONS` remained purely reactive (updated only after
each individual case is manually found).

This is a PROACTIVE, systemic version of that manual-discovery loop: any future case where an
ETF-family/note-issuer CIK's ticker slips through both upstream detection gates the same way
GRN did will now show up here automatically - as a minority-symbol outlier inside its own
CIK's ticker group - without needing a human to happen to notice one implausible filer first.

Deliberately WARN, not ERROR/CRIT (same posture as reverse_merger_shell.py): a genuine
multi-class/multi-listing structure under one CIK is rare but not impossible, so this needs a
human to check whether the flagged symbol is really an ETF/ETN/trust product (in which case it
belongs in KNOWN_ETF_MISCLASSIFICATIONS and its financials should be nulled, same fix as GRN)
before quarantining - not an automatic finding. Reads only the already-on-disk symbol->CIK
ticker cache (same file reverse_merger_shell.py reads, populated by normal loader runs) plus
one aggregate SQL query - no new network calls, so a full active-universe pass is cheap enough
to run every time.
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import INFO, WARN

logger = logging.getLogger(__name__)

_TICKER_CACHE_FILE = Path(tempfile.gettempdir()) / "sec_ticker_cache.json"
_MAX_REPORTED = 20

# A real single operating company essentially never has 4+ distinct ACTIVE ticker symbols
# filed under the same CIK - this is specifically the signature of an ETF/ETN/trust sponsor
# CIK covering its whole product family (Barclays' 9 tickers under one CIK, motivating this
# check). Below this size, a shared CIK is far more likely to be an ordinary dual-class share
# structure (2 tickers, both legitimately carrying the same filer's financials) - excluded by
# this threshold rather than by trying to special-case share-class suffixes.
_MIN_GROUP_SIZE = 4

# Within a qualifying group, flag the symbols WITH financials only when they're a minority -
# if every symbol in a large CIK group has financials, that's not this bug's signature (it
# reads instead as our own group threshold being wrong for that particular filer, e.g. a
# holding company with many operating subsidiaries each separately listed - genuinely rare,
# but not the shape to alarm on here).
_MAX_LEAK_FRACTION = 0.5


def _load_symbol_to_cik() -> dict[str, str]:
    try:
        with open(_TICKER_CACHE_FILE) as f:
            return dict(json.load(f).get("mapping") or {})
    except (OSError, json.JSONDecodeError, ValueError) as e:
        # Not initialized: the local ticker cache is populated by normal loader runs, not
        # fetched here - a missing/corrupt file just means no symbol->CIK mapping exists yet
        # on this machine, not a data-loss case. This check's own caller already treats an
        # empty mapping as "nothing to process" and returns cleanly with zero findings.
        logger.debug(f"[CikSharedIssuerFinancialsLeakChecker] could not load ticker cache: {e}")
        return {}


class CikSharedIssuerFinancialsLeakChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_cik_shared_issuer_financials_leak(cur)
        return self.results

    def check_cik_shared_issuer_financials_leak(self, cur: Any) -> None:
        try:
            symbol_to_cik = _load_symbol_to_cik()
            if not symbol_to_cik:
                self.log(
                    "cik_shared_issuer_financials_leak",
                    INFO,
                    "sec_edgar_submissions_cache",
                    "no local ticker cache available yet - skipping",
                )
                return

            cur.execute("SELECT symbol FROM stock_symbols WHERE active = true")
            active_symbols = {row["symbol"] for row in cur.fetchall()}

            cik_to_symbols: dict[str, list[str]] = {}
            for symbol in active_symbols:
                cik = symbol_to_cik.get(symbol.upper())
                if cik:
                    cik_to_symbols.setdefault(cik, []).append(symbol)
            qualifying_groups = {cik: syms for cik, syms in cik_to_symbols.items() if len(syms) >= _MIN_GROUP_SIZE}

            if not qualifying_groups:
                self.log(
                    "cik_shared_issuer_financials_leak",
                    INFO,
                    "annual_income_statement",
                    f"no CIK groups with >={_MIN_GROUP_SIZE} active symbols found - nothing to check",
                )
                return

            all_group_symbols = sorted({s for syms in qualifying_groups.values() for s in syms})
            cur.execute(
                """
                SELECT DISTINCT symbol
                FROM annual_income_statement
                WHERE symbol = ANY(%s) AND data_unavailable = FALSE AND revenue IS NOT NULL
                """,
                (all_group_symbols,),
            )
            symbols_with_financials = {row["symbol"] for row in cur.fetchall()}

            flagged: list[dict[str, Any]] = []
            for cik, syms in qualifying_groups.items():
                leaking = sorted(s for s in syms if s in symbols_with_financials)
                if not leaking:
                    continue
                fraction = len(leaking) / len(syms)
                if fraction > _MAX_LEAK_FRACTION:
                    continue
                for symbol in leaking:
                    flagged.append(
                        {
                            "symbol": symbol,
                            "cik": cik,
                            "group_size": len(syms),
                            "symbols_with_financials_in_group": leaking,
                        }
                    )

            if not flagged:
                self.log(
                    "cik_shared_issuer_financials_leak",
                    INFO,
                    "annual_income_statement",
                    f"checked {len(qualifying_groups)} CIK group(s) with >={_MIN_GROUP_SIZE} active "
                    "symbols - no minority-symbol financial-statement leaks found",
                )
                return

            flagged.sort(key=lambda r: r["symbol"])
            self.log(
                "cik_shared_issuer_financials_leak",
                WARN,
                "annual_income_statement",
                f"{len(flagged)} symbol(s) have extracted financial-statement data despite sharing "
                "a CIK with several other active tickers (the ETF/ETN/trust-sponsor signature) "
                "where most sibling tickers correctly have none - same bug class as GRN/Barclays "
                "(see grn_barclays_etn_misattribution_fixed_20260913). Needs review to confirm "
                "whether the flagged symbol is really a fund/note product before quarantining - "
                "not an automatic finding.",
                {"count": len(flagged), "examples": flagged[:_MAX_REPORTED]},
            )
        except Exception as e:
            logger.error(
                f"[CikSharedIssuerFinancialsLeakChecker] check_cik_shared_issuer_financials_leak failed: {e}",
                exc_info=True,
            )
            self.log(
                "cik_shared_issuer_financials_leak",
                WARN,
                "annual_income_statement",
                f"Check execution failed (not a data finding): {e}",
            )
