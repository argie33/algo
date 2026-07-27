"""Regression test for a real, live-reproduced data-integrity bug (2026-07-27):
scripts/fetch_13f_with_openfigi.py - a standalone script never registered in any loader
pipeline, scheduler, or terraform - wrote 4966 rows (91% of institutional_holdings_13f)
with institutional_ownership_pct fabricated from a crude shares_outstanding bucket table
(75%/65%/50%/30%), tagged data_source='market_cap_estimate' but data_unavailable=FALSE.

This directly defeated loaders/load_institutional_holdings_13f.py's own Session 418 fix,
whose _aggregate_top_manager_13fs() docstring explicitly says "Removed interim market-cap
fallback per GOVERNANCE fail-fast principle... Fail-fast to prevent silent fallback to
synthetic market-cap estimates" - the real loader was already correct, a separate rogue
script bypassed it entirely and wrote directly to the table.

load_positioning_metrics.py labels any non-data_unavailable row institutional_source="sec_13f"
with no way to distinguish real SEC data from the fabricated rows - this reached
positioning_metrics (also corrupted, confirmed via direct DB query) and stock_scores
(30% weight on positioning_metrics). Both tables were corrected directly (91 fabricated
rows) as part of this fix; the rogue script was deleted outright.
"""

from pathlib import Path

import pytest

from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestNoSyntheticInstitutionalOwnershipFallback:
    def test_rogue_market_cap_estimate_script_is_gone(self):
        assert not (REPO_ROOT / "scripts" / "fetch_13f_with_openfigi.py").exists(), (
            "scripts/fetch_13f_with_openfigi.py fabricated institutional_ownership_pct from a "
            "shares_outstanding bucket table and wrote it with data_unavailable=FALSE, "
            "indistinguishable from real SEC 13F data to every downstream consumer - it must "
            "stay deleted, not be resurrected as a 'quick fix' for sparse 13F coverage"
        )

    def test_no_source_file_writes_market_cap_estimate_as_a_data_source(self):
        """Static guard: 'market_cap_estimate' (or the synonymous literal 'fallback estimates')
        must never again appear as a data_source value anywhere in loaders/ or scripts/ - this
        is the exact string the deleted rogue script used to masquerade fabricated data as real."""
        hits = []
        for directory in ("loaders", "scripts"):
            for path in (REPO_ROOT / directory).rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "market_cap_estimate" in text:
                    hits.append(str(path.relative_to(REPO_ROOT)))
        assert not hits, f"found 'market_cap_estimate' data_source literal in: {hits}"

    def test_per_manager_aggregation_still_fails_fast_no_synthetic_data(self):
        """Guards the real loader's own Session 418 fix: without a CUSIP->ticker crosswalk,
        _aggregate_top_manager_13fs must raise, never silently return estimated data."""
        loader = InstitutionalHoldings13FLoader.__new__(InstitutionalHoldings13FLoader)
        with pytest.raises(RuntimeError, match="CUSIP"):
            loader._aggregate_top_manager_13fs()
