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

COST: OpenFIGI's unauthenticated limit is 10 mapping jobs/request, 25 requests/minute -
a full ~34,000-CUSIP universe takes ~2.5+ hours cold EVEN WITH ZERO 429s, real-world
sustained rate-limiting can make it far worse (live-verified 2026-07-27: 93+ minutes,
zero successful batches - see below). This is longer than any sane ECS task timeout
(institutional_holdings_13f is configured for 1200s/20min), so a cold-start crosswalk
CANNOT complete in one run. See loaders/load_institutional_holdings_13f.py's
sec_13f_cusip_crosswalk table (migration 1161): CUSIP->ticker attribution is stable
across quarters, so callers should cache results there and only crosswalk each
quarter's small delta of never-seen CUSIPs, not redo the full universe every run.

FIXED 2026-07-27 (real production bug, not just a documentation gap): fetch_cusip_tickers()
used to return its FULL result only after every batch was attempted - the caller
(_crosswalk_to_tickers) then persisted the whole result to sec_13f_cusip_crosswalk in one
shot at the end. Since a cold-start run can never finish before the ECS task timeout kills
it, every single run was losing 100% of its progress: whatever CUSIPs OpenFIGI DID
successfully resolve before the kill were never saved, so the cache never grew and every
run re-started from zero - the exact "all-or-nothing discards real partial data" bug class
already found and fixed once in this codebase for growth_metrics (see
steering/DATA_LOADERS.md's 2026-07-21 entry). Live-verified this was happening: local DB
had 5,461 institutional_holdings_13f rows, ALL data_unavailable, despite
steering/DATA_LOADERS.md claiming "live-verified... AAPL 86.9%" - that claim was either
from a luckier run or is simply no longer reproducible; either way, the architecture
guaranteed eventual failure once the CUSIP backlog was large enough (33,618 CUSIPs seen
live, vastly more than one run's rate-limited budget can process).

Fixed by adding an optional `on_batch_resolved` callback (invoked after every batch,
success or failure) and a `deadline` (a `time.monotonic()` cutoff) that returns whatever
was resolved so far instead of grinding on past the caller's time budget. The caller now
persists each batch's results as they land, so a run that gets killed mid-crosswalk keeps
whatever real progress it made, and the backlog shrinks across successive scheduled runs
(the loader can run more often than the quarterly 13F cadence needs, using the extra runs
purely to keep chipping away at the crosswalk backlog) instead of resetting to zero
every time.

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
from typing import Any, cast

logger = logging.getLogger(__name__)

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 10  # OpenFIGI's per-request job limit without an API key
_REQUEST_INTERVAL_SEC = 2.5  # stays under OpenFIGI's 25 requests/minute unauthenticated limit

_CORP_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
    "HOLDINGS", "HOLDING", "GROUP", "THE", "CLASS", "A", "B", "SA", "NV", "AG",
}  # fmt: skip


def fetch_cusip_tickers(
    cusips: list[str],
    on_batch_resolved: Any = None,
    deadline: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Map CUSIPs to their real ticker/entity name via OpenFIGI (free, public API).

    Args:
        cusips: CUSIPs to resolve.
        on_batch_resolved: optional callback(dict[cusip, {"ticker":..., "name":...} | None])
            invoked after EVERY batch attempt (success or failure - failed/unresolved
            CUSIPs in the batch are passed with value None). Lets the caller persist
            progress incrementally instead of only after this function returns, since a
            large cold-start crosswalk can take hours and may never get to return at all
            if the calling process is killed first (see module docstring's 2026-07-27 fix).
        deadline: optional time.monotonic() cutoff - stop starting new batches once
            reached and return whatever was resolved so far, rather than continuing to
            grind through a backlog that can't possibly finish before the caller's own
            time budget (e.g. an ECS task timeout) runs out.

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
    deadline_hit = False

    for i in range(0, len(unique_cusips), _BATCH_SIZE):
        if deadline is not None and time.monotonic() >= deadline:
            deadline_hit = True
            logger.warning(
                f"[OpenFIGI] Time budget exhausted after {batches_attempted} batches "
                f"({i}/{len(unique_cusips)} CUSIPs attempted) - returning partial results, "
                f"remaining CUSIPs picked up next run."
            )
            break

        batch = unique_cusips[i : i + _BATCH_SIZE]
        batches_attempted += 1
        batch_results = _post_mapping_batch(batch)

        batch_resolved: dict[str, dict[str, Any] | None] = dict.fromkeys(batch)
        if batch_results is not None and len(batch_results) != len(batch):
            # OpenFIGI's contract is positional (result[i] answers job[i]) - a length
            # mismatch means that guarantee broke (API contract change, truncated
            # response) and zip() would silently pair each cusip with the WRONG
            # result. Discard the whole batch rather than risk fabricating a mapping.
            logger.warning(
                f"[OpenFIGI] Batch of {len(batch)} CUSIPs returned {len(batch_results)} "
                f"results - response length mismatch, discarding batch to avoid "
                f"misaligned cusip->data pairing."
            )
        elif batch_results is not None:
            batches_succeeded += 1
            for cusip, result in zip(batch, batch_results, strict=True):
                data = result.get("data")
                if not data:
                    continue  # OpenFIGI couldn't resolve this CUSIP - honest gap, not fabricated
                # FIXED 2026-08-18 (goal: "no SEC data"/missing factor inputs audit): a single
                # CUSIP resolves to 100+ listings across every exchange it trades on (primary
                # US listing plus every foreign cross-listing/ADR venue), and OpenFIGI does NOT
                # return them in any "primary first" order - live-confirmed via real OpenFIGI
                # response for Agilent's CUSIP (00846U101): data[0] was a German Xetra listing
                # (exchCode "GR", ticker "AG8"), with the real US listing (exchCode "US", ticker
                # "A") not appearing until index 8. The old `data[0]` pick therefore resolved a
                # real US-tracked large-cap to the WRONG ticker, which then failed the exact-match
                # `ticker not in symbols` check in load_institutional_holdings_13f.py's
                # _crosswalk_to_tickers and silently dropped real, resolved 13F holdings as
                # "no_resolved_13f_holdings" (1,668 symbols showing this reason at time of fix).
                # Prefer the entry OpenFIGI tags as the primary US composite listing (exchCode
                # "US") when one exists; fall back to data[0] unchanged for CUSIPs with no US
                # listing at all (genuine foreign-only securities - already correct for those).
                best = next((d for d in data if d.get("exchCode") == "US"), data[0])
                entry = {"ticker": best.get("ticker"), "name": best.get("name")}
                results[cusip] = entry
                batch_resolved[cusip] = entry

        if on_batch_resolved is not None:
            on_batch_resolved(batch_resolved)

        # Always pace between batches, success or failure - a non-429 failure (network
        # error, 5xx) doesn't sleep inside _post_mapping_batch at all, and even a 429's
        # internal 60s retry-wait doesn't guarantee OpenFIGI's window has actually reset;
        # skipping this sleep on failure was the original code's bug (rapid-fire retries
        # into a still-active rate limit, worsening it).
        time.sleep(_REQUEST_INTERVAL_SEC)

    if not deadline_hit and batches_attempted > 0 and batches_succeeded == 0:
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
                return cast(list[dict[str, Any]], json.loads(resp.read().decode("utf-8")))
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
        #
        # Apostrophes are the opposite case: they must be deleted outright, not
        # turned into a separator. FIXED 2026-08-18 (goal session, institutional
        # ownership audit): a possessive name like SEC's "BRINK'S CO/THE" vs
        # OpenFIGI's "BRINKS CO" tokenized to {"BRINK'S", "CO"} vs {"BRINKS", "CO"} -
        # the possessive token never matches its non-possessive counterpart, so
        # names_plausibly_match wrongly rejected a correct CUSIP resolution as a
        # "wrong entity". Live-confirmed on 8 real symbols including MCD (McDonald's)
        # and LOW (Lowe's) - large, liquid, heavily-institutionally-held stocks that
        # were falling back to institutional_ownership_pct=NULL
        # ("no_resolved_13f_holdings") purely because of this apostrophe mismatch.
        cleaned = name.upper().replace(".", " ").replace(",", " ").replace("-", " ").replace("'", "")
        return {w for w in cleaned.split() if w not in _CORP_SUFFIXES}

    a, b = tokens(figi_name), tokens(local_name)
    if not a or not b:
        return False
    overlap = a & b
    return len(overlap) / min(len(a), len(b)) >= 0.5
