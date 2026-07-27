#!/usr/bin/env python3
"""OpenFIGI CUSIP->ticker crosswalk - closes the SEC Form 13F attribution gap.

BACKGROUND: SEC's 13F INFOTABLE bulk dataset identifies securities by CUSIP only
(never ticker, by design - see loaders/load_institutional_holdings_13f.py's module
docstring), and CUSIP itself is a licensed identifier with no free SEC-published
crosswalk. OpenFIGI (api.openfigi.com) is Bloomberg's free, public, no-signup-required
mapping service - the industry-standard way to resolve a CUSIP to its real ticker
without a CUSIP license.

REJECTED APPROACH, kept here as a documented lesson (2026-07-27): an earlier version
of this module tried to avoid OpenFIGI's CUSIP-direction cost by joining on SEC's OWN
optional FIGI column instead (query OpenFIGI ticker->FIGI for our own tracked universe
only, then match against whichever CUSIPs happened to carry a matching FIGI in the SEC
data). That join is real and correctly implemented, but live-verified against Apple's
real FY2026 13F data to be catastrophically incomplete: only ~7.4% of AAPL's total
reported institutional SHARES carry a valid FIGI tag at all (most filers simply don't
report one), so the resulting institutional_ownership_pct came out ~6% instead of the
real ~87% - a wrong-but-plausible-looking number, not an honest partial result. Fixed
by switching to the direct CUSIP->ticker OpenFIGI query below, which uses the FULL
reported share total per CUSIP, not just the FIGI-tagged subset.

COST: OpenFIGI's unauthenticated limit is 10 mapping jobs/request, ~25 requests/minute -
a full ~34,000-CUSIP universe takes ~2-2.5 hours cold. See
loaders/load_institutional_holdings_13f.py's sec_13f_cusip_crosswalk table (migration
1161): CUSIP->ticker attribution is stable across quarters, so callers should cache
results there and only crosswalk each quarter's small delta of never-seen CUSIPs, not
redo the full universe every run.

CAUTION - live-verified real-world gotcha (2026-07-27): a CUSIP->ticker resolution is
not always the correct entity, and XOM is quirky on this front in two independent,
unrelated ways. (1) OpenFIGI's ticker-FORWARD direction resolves "XOM" to
"EXXONMOBIL HOLDINGS CORP", a DIFFERENT entity than the real 10-K filer
"EXXON MOBIL CORP" that actually trades under NYSE:XOM - matches the identical
wrong-entity pattern independently found in SEC's own company_tickers.json (see
utils/external/sec_ticker_cache.py's CIK_OVERRIDES). (2) Querying OpenFIGI with the
REAL Exxon Mobil Corp's own CUSIP (30231G102, the direction this module actually uses)
resolves to ticker "EXMOC", not "XOM" - a real Bloomberg-side ticker variant, live-
confirmed against the real SEC 13F bulk dataset. Both fail safe automatically here (an
unrecognized ticker like "EXMOC" is never in our tracked universe;
`names_plausibly_match()` is a cheap defense-in-depth sanity check for the case where
a resolved ticker DOES happen to collide with one we track but names diverge) - but
neither is fabricated data, both are honest non-coverage. `names_plausibly_match()` is
not a precision name-matching algorithm and callers must not rely on it alone for
correctness - the CUSIP itself (an exact identifier, unlike a ticker) is the primary
correctness guarantee, this is a secondary net.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 10  # OpenFIGI's per-request job limit without an API key
_REQUEST_INTERVAL_SEC = 2.5  # stays under OpenFIGI's 25 requests/minute unauthenticated limit

_CORP_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
    "HOLDINGS", "HOLDING", "GROUP", "THE", "CLASS", "A", "B", "SA", "NV", "AG",
}  # fmt: skip


def fetch_cusip_tickers(cusips: list[str]) -> dict[str, dict[str, Any]]:
    """Map CUSIPs to their real ticker/entity name via OpenFIGI (free, public API).

    Returns {cusip: {"ticker": ..., "name": ...}} only for CUSIPs OpenFIGI could
    resolve. A CUSIP OpenFIGI can't resolve (bond, private placement, foreign-only
    listing, etc.) is simply absent from the result - never fabricated.

    Raises RuntimeError if every single batch request fails (OpenFIGI unreachable
    or its response contract changed) - distinct from "resolved zero matches",
    which is a legitimate, honest outcome this function does not treat as an error.
    """
    results: dict[str, dict[str, Any]] = {}
    unique_cusips = sorted({c.strip().upper() for c in cusips if c and c.strip()})

    batches_attempted = 0
    batches_succeeded = 0

    for i in range(0, len(unique_cusips), _BATCH_SIZE):
        batch = unique_cusips[i : i + _BATCH_SIZE]
        batches_attempted += 1
        batch_results = _post_mapping_batch(batch)
        if batch_results is None:
            time.sleep(_REQUEST_INTERVAL_SEC)
            continue
        batches_succeeded += 1

        for cusip, result in zip(batch, batch_results):
            data = result.get("data")
            if not data:
                continue  # OpenFIGI couldn't resolve this CUSIP - honest gap, not fabricated
            best = data[0]
            results[cusip] = {"ticker": best.get("ticker"), "name": best.get("name")}

        time.sleep(_REQUEST_INTERVAL_SEC)

    if batches_attempted > 0 and batches_succeeded == 0:
        raise RuntimeError(
            f"[OpenFIGI] All {batches_attempted} mapping request(s) failed - OpenFIGI "
            f"appears unreachable or its API contract changed. Not the same as 'resolved "
            f"zero CUSIPs' (a legitimate outcome); this is a hard fetch failure."
        )

    return results


def _post_mapping_batch(cusips: list[str]) -> list[dict[str, Any]] | None:
    """POST one batch to OpenFIGI's mapping endpoint. Returns None on failure
    (caller treats this batch as unresolved, not fatal - a handful of dropped
    batches out of hundreds is not worth aborting a whole loader run over)."""
    jobs = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
    body = json.dumps(jobs).encode("utf-8")

    for attempt in range(2):  # one retry, only for 429s
        try:
            req = urllib.request.Request(
                OPENFIGI_MAPPING_URL,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                logger.warning("[OpenFIGI] Rate limited, backing off 60s before one retry")
                time.sleep(60)
                continue
            logger.warning(f"[OpenFIGI] Batch {cusips} failed: HTTP {e.code}")
            return None
        except Exception as e:
            logger.warning(f"[OpenFIGI] Batch {cusips} failed: {type(e).__name__}: {e}")
            return None
    return None


def names_plausibly_match(figi_name: str | None, local_name: str | None) -> bool:
    """Loose sanity check that two entity names plausibly refer to the same company.

    Not a precision matcher - corporate naming conventions vary too much for that
    (see this module's docstring: OpenFIGI's own "EXXONMOBIL HOLDINGS CORP" vs the
    real filer's "EXXON MOBIL CORP" don't share a single token after normalization,
    which is exactly the case this function exists to catch). Used as a secondary
    safety net on top of the real correctness guarantee (the CUSIP/FIGI join itself),
    never as the primary matching mechanism.
    """
    if not figi_name or not local_name:
        return False

    def tokens(name: str) -> set[str]:
        # Treat punctuation as a separator, not noise to delete - live-verified
        # false negative otherwise: OpenFIGI's "AMAZON.COM INC" would merge into
        # one "AMAZONCOM" token that never matches SEC's own space-separated
        # "AMAZON COM INC" entity_name.
        cleaned = name.upper().replace(".", " ").replace(",", " ").replace("-", " ")
        return {w for w in cleaned.split() if w not in _CORP_SUFFIXES}

    a, b = tokens(figi_name), tokens(local_name)
    if not a or not b:
        return False
    overlap = a & b
    return len(overlap) / min(len(a), len(b)) >= 0.5
