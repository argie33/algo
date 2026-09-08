#!/usr/bin/env python3
"""Detects a filer that stopped tagging a core XBRL concept it used to report every year -
the "taxonomy migration" / "filer changed tags" gap that xbrl_new_concepts.py cannot see.

Added 2026-09-07 (goal session continuation: "what about when companies change things - is
that covered?"). xbrl_new_concepts.py already catches a concept appearing for the FIRST time
anywhere in the universe (a newly-effective FASB taxonomy element). It has no way to notice
the mirror-image case: a SPECIFIC filer that tagged Assets/Liabilities/NetIncomeLoss every
year for years suddenly stops tagging one of them - either because the US-GAAP taxonomy
deprecated/renamed the concept and the filer's XBRL agent switched to a synonym tag we don't
also fetch, or because something is wrong with our own extraction for that filer. Both cases
look identical from our side: a core field that was reliably populated goes quietly null.

This is a genuinely different failure mode from anything else in this package: tie_out.py and
friends validate values we already extracted; this validates that extraction kept happening
at all for values it always used to. See utils/external/xbrl_concept_coverage.py's
find_continuity_gaps() for the actual diff logic (reuses the same on-disk companyfacts cache
and CIK-keyed files as xbrl_new_concepts.py - no new network calls or scheduling).

Deliberately WARN, not ERROR/CRIT, same rationale as xbrl_new_concepts.py: this is a "go look
at this," not proof of a live bug - a filer's final 10-K before going private/bankrupt/being
acquired would trip this legitimately. Dismiss a confirmed-legitimate case via
CONTINUITY_DISMISSED_FILE (utils/external/xbrl_concept_coverage.py's
save_continuity_dismissed()), keyed "CIK:concept" - it then drops out of future WARNs
automatically, same convention as the concept-coverage dismiss log.
"""

import logging
from typing import Any

from utils.external.xbrl_concept_coverage import find_continuity_gaps, iter_companyfacts_cache

from ..base import BaseCheck, CheckResult
from ..config import ERROR, WARN

logger = logging.getLogger(__name__)

_MIN_PRIOR_YEARS = 3
_MAX_REPORTED = 20


class XbrlConceptContinuityChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_concept_continuity()
        return self.results

    def check_concept_continuity(self) -> None:
        try:
            if not iter_companyfacts_cache():
                # No cache on this host (e.g. a fresh ECS task before any loader has run this
                # cycle) - not a data-integrity finding, just nothing to scan yet.
                return
            gaps = find_continuity_gaps(min_prior_years=_MIN_PRIOR_YEARS)
            if not gaps:
                return
            examples = gaps[:_MAX_REPORTED]
            self.log(
                "xbrl_concept_continuity",
                WARN,
                "sec_edgar_companyfacts_cache",
                f"{len(gaps)} filer/concept pair(s) had a core XBRL concept tagged every year "
                f"for {_MIN_PRIOR_YEARS}+ straight prior annual filings but it is absent from "
                "the most recent one - likely a taxonomy/tag change or extraction gap, see "
                "utils/external/xbrl_concept_coverage.py's find_continuity_gaps()",
                {"count": len(gaps), "examples": examples},
            )
        except Exception as e:
            logger.error(f"[XbrlConceptContinuityChecker] check_concept_continuity failed: {e}", exc_info=True)
            self.log(
                "xbrl_concept_continuity",
                ERROR,
                "sec_edgar_companyfacts_cache",
                f"check_concept_continuity failed: {e}",
            )
