#!/usr/bin/env python3
"""Automated version of scripts/xbrl_concept_coverage_scan.py - surfaces newly-adopted XBRL
concepts without a human having to remember to run the script.

Added 2026-09-07 (goal session: "is there a better way to deal with XBRL validation than
checking every symbol by hand, and how do we handle future filings"). Every other check in
this package (tie_out.py, coverage.py, etc.) validates data we already extracted. Nothing
validated the *allowlist itself* - if a filer starts tagging a us-gaap concept we've never
seen before (a newly-effective FASB taxonomy element, or a filer switching from a custom
extension tag to a standard one), nothing notices until a downstream symptom happens to trip
some other check, or a human happens to re-run the coverage scan script by hand. That's the
same "reactive, one bug at a time" pattern the rest of the 2026-09 XBRL campaign was trying to
get away from.

This wires the exact same diff logic (utils/external/xbrl_concept_coverage.py, shared with the
script) into DataPatrol, which already runs on every scheduled pipeline pass and already has a
working alert path (DataPatrol.run()'s notify() call) - so a newly-adopted concept reaches a
human via the existing patrol alert, the same run it first appears in the on-disk companyfacts
cache, without any new scheduling infrastructure.

Deliberately WARN, not ERROR/CRIT: an undismissed concept is a "go look at this", not proof of
a live bug - most companyfacts concepts belong to disclosures we deliberately don't score (see
NOISE_SUBSTRINGS). This does not dedupe against previous runs - like every other check in this
package, it just keeps reporting until a human either adds real fetch support for the concept
or dismisses it via `python scripts/xbrl_concept_coverage_scan.py --dismiss ... --reason ...`,
at which point it drops out of future WARNs automatically (dismissed.json is read fresh every
run). min_companies=50 keeps the noise floor low - a concept only a handful of filers use is
not worth an automated alert; scripts/xbrl_concept_coverage_scan.py without that filter remains
the right tool for a deliberate low-threshold deep-dive.
"""

import logging
from typing import Any

from utils.external.xbrl_concept_coverage import find_gaps, iter_companyfacts_cache

from ..base import BaseCheck, CheckResult
from ..config import ERROR, WARN

logger = logging.getLogger(__name__)

_MIN_COMPANIES = 50
_MAX_REPORTED = 20
# FIXED 2026-09-08 (goal session: "is the coverage scan catching everything it should" audit):
# this list previously omitted "ifrs-full" despite this module's own docstring and
# utils/external/xbrl_concept_coverage.py's header comment both describing it as a supported
# namespace - live-confirmed via a manual --namespace ifrs-full run that IFRS filers (Agnico
# Eagle, Bank of Nova Scotia, Unilever, Sony, PLDT, Barclays, ...) have hundreds of undismissed
# concepts tagged by 50-250+ companies each that this checker has never once scanned since it
# was added. WARN-only (see class docstring below), so enabling this does not risk a false
# halt - it only starts surfacing what was previously invisible.
_NAMESPACES = ["us-gaap", "dei", "ifrs-full"]


class NewXbrlConceptChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_new_concepts()
        return self.results

    def check_new_concepts(self) -> None:
        try:
            if not iter_companyfacts_cache():
                # No cache on this host (e.g. a fresh ECS task before any loader has run this
                # cycle) - not a data-integrity finding, just nothing to scan yet.
                return
            gaps = find_gaps(_NAMESPACES, min_companies=_MIN_COMPANIES, exclude_noise=True)
            if not gaps:
                return
            examples = [
                {"concept": key, "companies": n, "example_filer": filer} for n, key, filer in gaps[:_MAX_REPORTED]
            ]
            self.log(
                "xbrl_new_concepts",
                WARN,
                "sec_edgar_companyfacts_cache",
                f"{len(gaps)} XBRL concept(s) tagged by {_MIN_COMPANIES}+ filers each are absent "
                "from our fetch allowlist and not yet triaged - see scripts/xbrl_concept_coverage_scan.py",
                {"count": len(gaps), "examples": examples},
            )
        except Exception as e:
            logger.error(f"[NewXbrlConceptChecker] check_new_concepts failed: {e}", exc_info=True)
            self.log(
                "xbrl_new_concepts",
                ERROR,
                "sec_edgar_companyfacts_cache",
                f"check_new_concepts failed: {e}",
            )
