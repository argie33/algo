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
from collections import defaultdict
from typing import Any, cast

logger = logging.getLogger(__name__)

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 10  # OpenFIGI's per-request job limit without an API key
_REQUEST_INTERVAL_SEC = 2.5  # stays under OpenFIGI's 25 requests/minute unauthenticated limit

_CORP_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
    "HOLDINGS", "HOLDING", "GROUP", "THE", "CLASS", "A", "B", "SA", "NV", "AG",
}  # fmt: skip

# Bloomberg/OpenFIGI systematically abbreviates common words in closed-end fund and
# trust names (vowel-dropping style: "FLTNG" for "FLOATING", "TR" for "TRUST") in a way
# SEC's own entity_name never does. FIXED 2026-08-18 (goal session, "which factor
# inputs are missing the most" audit): names_plausibly_match's >=50% token-overlap
# threshold was rejecting dozens of genuinely-correct CUSIP resolutions purely because
# of this abbreviation gap - live-confirmed via institutional_holdings_13f rows stuck on
# "no_resolved_13f_holdings" despite the crosswalk already holding the right CUSIP, e.g.
# EFT (Eaton Vance Floating-Rate Income Trust) resolved to OpenFIGI's "EATON VANCE
# FLTNG RT INC TR" - zero overlap on FLTNG/RT/TR vs FLOATING/RATE/TRUST until expanded.
# Every key here was observed in a real mismatch, not guessed - each maps to the same
# canonical value its own full-word form (and common plural, where seen) also maps to,
# so a full-word name and an abbreviated name land on the identical token regardless of
# which one uses the short form.
_ABBREVIATION_EXPANSIONS = {
    "TR": "TRUST", "TRST": "TRUST", "TST": "TRUST", "TRS": "TRUST", "TRUST": "TRUST",
    "ALT": "ALTERNATIVE", "ALTERNATIVE": "ALTERNATIVE",
    "INTL": "INTERNATIONAL", "INTERNATIONAL": "INTERNATIONAL",
    "TRGT": "TARGET", "TARGET": "TARGET",
    "TRM": "TERM", "TERM": "TERM",
    "GRD": "GRADE", "GRADE": "GRADE",
    "MUNI": "MUNICIPAL", "MUNICIPAL": "MUNICIPAL", "MUNICIPALS": "MUNICIPAL",
    "GLB": "GLOBAL", "GLBL": "GLOBAL", "GLOBAL": "GLOBAL",
    "NTRL": "NATURAL", "NATURAL": "NATURAL",
    "RES": "RESOURCES", "RESOURCE": "RESOURCES", "RESOURCES": "RESOURCES",
    "UTIL": "UTILITIES", "UTILITY": "UTILITIES", "UTILITIES": "UTILITIES",
    "PWR": "POWER", "POWER": "POWER",
    "HLTH": "HEALTH", "HEALTH": "HEALTH",
    "SCI": "SCIENCE", "SCIENCE": "SCIENCE", "SCIENCES": "SCIENCE",
    "FLTNG": "FLOATING", "FLT": "FLOATING", "FLOATING": "FLOATING",
    "RT": "RATE", "RTE": "RATE", "RATE": "RATE",
    "DUR": "DURATION", "DURAT": "DURATION", "DURATION": "DURATION",
    "MTG": "MORTGAGE", "MORTGAGE": "MORTGAGE",
    "AGRIC": "AGRICULTURAL", "AGRICULTURAL": "AGRICULTURAL", "AGRICULTURE": "AGRICULTURAL",
    "ADV": "ADVANTAGE", "ADVANTAGE": "ADVANTAGE",
    "SPON": "SPONSORED", "SPN": "SPONSORED", "SP": "SPONSORED", "SPONSORED": "SPONSORED",
    "TEL": "TELEPHONE", "TELEPHONE": "TELEPHONE",
    "CL": "CLASS",
    "OPPS": "OPPORTUNITY", "OPPOR": "OPPORTUNITY", "OPP": "OPPORTUNITY",
    "OPPORTUNITY": "OPPORTUNITY", "OPPORTUNITIES": "OPPORTUNITY", "OPPORTUNISTIC": "OPPORTUNITY",
    "EQTY": "EQUITY", "EQUITY": "EQUITY",
    "PRIV": "PRIVATE", "PRIVATE": "PRIVATE",
    "ENRGY": "ENERGY", "ENERGY": "ENERGY",
    "INV": "INVESTMENT", "INVEST": "INVESTMENT", "INVESTMENT": "INVESTMENT", "INVESTMENTS": "INVESTMENT",
    "CIA": "COMPANY", "COMPANIA": "COMPANY",
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
    # FIXED 2026-08-19 ("no SEC data"/loader audit, institutional_holdings_13f follow-up):
    # a CUSIP whose first character is a letter is actually a CINS (CUSIP International
    # Numbering System) identifier, not a standard CUSIP - OpenFIGI requires idType
    # "ID_CINS" for these, "ID_CUSIP" returns "No identifier found." even for a real,
    # correctly-formed identifier. Live-confirmed via the real OpenFIGI API: Accenture
    # plc's real 13F-reported identifier G1151C101 (Irish-domiciled, "G"-prefix CINS)
    # fails under ID_CUSIP but resolves cleanly to ACN under ID_CINS - and Accenture, one
    # of the most widely institutionally-held stocks on Earth, was permanently cached as
    # unresolved (ticker=NULL) as a result, with sec_13f_cusip_crosswalk's "stable across
    # quarters, never re-query" caching meaning it would NEVER have been retried. 3,537 of
    # 16,177 universe-wide unresolved CUSIPs start with a letter (BAWAG Group, Erste Group
    # Bank and others confirmed resolvable this way too). Collected here and retried as a
    # second pass below, after every primary ID_CUSIP batch - never tried first, since the
    # vast majority of CUSIPs are standard (digit-prefixed) and resolve fine under
    # ID_CUSIP; this only fires for the subset ID_CUSIP already failed.
    cins_candidates: list[str] = []

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

        if batch_results is not None and len(batch_results) != len(batch):
            # OpenFIGI's contract is positional (result[i] answers job[i]) - a length
            # mismatch means that guarantee broke (API contract change, truncated
            # response) and zip() would silently pair each cusip with the WRONG
            # result. Discard the whole batch rather than risk fabricating a mapping.
            # FIXED 2026-08-18 (goal session, live-caught via Hamilton Insurance Group/HG's
            # institutional_holdings_13f gap): this branch (and the batch_results is None
            # branch below it) used to still call on_batch_resolved() with an all-None dict
            # for the batch - indistinguishable, to the caller, from OpenFIGI genuinely
            # answering "no match" for every CUSIP in it. The caller
            # (load_institutional_holdings_13f.py's _crosswalk_to_tickers) persists
            # on_batch_resolved's output straight into sec_13f_cusip_crosswalk as a
            # PERMANENT cache entry ("CUSIP->ticker attribution is stable... only
            # never-seen CUSIPs cost a live OpenFIGI call" - this module's own docstring),
            # so a transient failure (5xx, network blip, non-429 HTTP error, or an
            # exhausted 429 retry) got cached forever as "OpenFIGI has no match for this
            # CUSIP", identically to a real negative result, with no future retry ever
            # happening. Live-confirmed for Hamilton's real CUSIP G42706104 (verified
            # against its own SEC 13G/A filing) - cached NULL/NULL on 2026-08-03 despite
            # being a real, actively 13F-held NYSE common stock. Fix: simply don't call
            # on_batch_resolved for a batch OpenFIGI didn't actually answer - leaves those
            # CUSIPs out of the cache entirely so the next run's "new_cusips" filter
            # (cusip not in cached) picks them up for a fresh retry instead of treating
            # them as permanently resolved-to-nothing.
            logger.warning(
                f"[OpenFIGI] Batch of {len(batch)} CUSIPs returned {len(batch_results)} "
                f"results - response length mismatch, discarding batch to avoid "
                f"misaligned cusip->data pairing. Leaving unresolved for retry next run."
            )
        elif batch_results is not None:
            batches_succeeded += 1
            batch_resolved: dict[str, dict[str, Any] | None] = dict.fromkeys(batch)
            for cusip, result in zip(batch, batch_results, strict=True):
                data = result.get("data")
                if not data:
                    if cusip[0].isalpha():
                        # Might be a CINS identifier ID_CUSIP can't resolve (see the
                        # cins_candidates comment above) - try ID_CINS in the second pass
                        # below instead of caching this as a permanent ID_CUSIP negative.
                        cins_candidates.append(cusip)
                        del batch_resolved[cusip]
                    continue  # OpenFIGI couldn't resolve this CUSIP under ID_CUSIP - honest gap otherwise
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
        else:
            # batch_results is None: the whole batch request failed (see
            # _post_mapping_batch - network error, non-429 HTTP error, or 429 that
            # didn't clear after the one retry). Same fix as the length-mismatch branch
            # above: do NOT call on_batch_resolved, so these CUSIPs stay out of the cache
            # and get retried next run instead of being poisoned as permanent negatives.
            logger.warning(
                f"[OpenFIGI] Batch of {len(batch)} CUSIPs failed entirely - "
                f"leaving unresolved for retry next run (not caching as a negative result)."
            )

        # Always pace between batches, success or failure - a non-429 failure (network
        # error, 5xx) doesn't sleep inside _post_mapping_batch at all, and even a 429's
        # internal 60s retry-wait doesn't guarantee OpenFIGI's window has actually reset;
        # skipping this sleep on failure was the original code's bug (rapid-fire retries
        # into a still-active rate limit, worsening it).
        time.sleep(_REQUEST_INTERVAL_SEC)

    # Second pass: retry every letter-prefixed CUSIP ID_CUSIP couldn't resolve, this time
    # as ID_CINS (see cins_candidates comment above). Same batching/pacing/failure-handling
    # as the primary loop, minus the total-failure RuntimeError (a CINS retry batch failing
    # outright isn't a fatal OpenFIGI-is-down signal on its own - the primary loop above
    # already proved OpenFIGI is reachable if it got this far).
    for i in range(0, len(cins_candidates), _BATCH_SIZE):
        if deadline is not None and time.monotonic() >= deadline:
            logger.warning(
                f"[OpenFIGI] Time budget exhausted during CINS retry pass "
                f"({i}/{len(cins_candidates)} candidates attempted) - remaining picked up next run."
            )
            break

        batch = cins_candidates[i : i + _BATCH_SIZE]
        batch_results = _post_mapping_batch(batch, id_type="ID_CINS")

        if batch_results is not None and len(batch_results) == len(batch):
            batch_resolved = dict.fromkeys(batch)
            for cusip, result in zip(batch, batch_results, strict=True):
                data = result.get("data")
                if not data:
                    continue  # Genuinely not a CINS identifier either - honest gap, not fabricated
                best = next((d for d in data if d.get("exchCode") == "US"), data[0])
                entry = {"ticker": best.get("ticker"), "name": best.get("name")}
                results[cusip] = entry
                batch_resolved[cusip] = entry
            if on_batch_resolved is not None:
                on_batch_resolved(batch_resolved)
        else:
            logger.warning(
                f"[OpenFIGI] CINS retry batch of {len(batch)} CUSIPs failed or mismatched - "
                f"leaving unresolved for retry next run (not caching as a negative result)."
            )

        time.sleep(_REQUEST_INTERVAL_SEC)

    if not deadline_hit and batches_attempted > 0 and batches_succeeded == 0:
        raise RuntimeError(
            f"[OpenFIGI] All {batches_attempted} mapping request(s) failed - OpenFIGI "
            f"appears unreachable or its API contract changed. Not the same as 'resolved "
            f"zero CUSIPs' (a legitimate outcome); this is a hard fetch failure."
        )

    return results


def _post_mapping_batch(cusips: list[str], id_type: str = "ID_CUSIP") -> list[dict[str, Any]] | None:
    """POST one batch to OpenFIGI's mapping endpoint. Returns None on failure
    (caller treats this batch as unresolved, not fatal - a handful of dropped
    batches out of hundreds is not worth aborting a whole loader run over).

    id_type: "ID_CUSIP" for standard CUSIPs (default), "ID_CINS" for CINS identifiers
    (letter-prefixed, used for foreign securities - see fetch_cusip_tickers's
    cins_candidates comment for why these need a different idType entirely)."""
    jobs = [{"idType": id_type, "idValue": c} for c in cusips]
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


def name_tokens(name: str | None) -> frozenset[str]:
    """Normalize an entity name into a comparable token set.

    Extracted from names_plausibly_match (2026-08-18) so EntityNameIndex's reverse
    lookup shares the exact same normalization - keeping both directions of the
    wrong-entity defense in sync instead of two copies drifting apart.

    Treat punctuation as a separator, not noise to delete - live-verified false
    negative otherwise: OpenFIGI's "AMAZON.COM INC" would merge into one
    "AMAZONCOM" token that never matches SEC's own space-separated
    "AMAZON COM INC" entity_name.

    Apostrophes are the opposite case: they must be deleted outright, not turned
    into a separator. FIXED 2026-08-18 (goal session, institutional ownership
    audit): a possessive name like SEC's "BRINK'S CO/THE" vs OpenFIGI's
    "BRINKS CO" tokenized to {"BRINK'S", "CO"} vs {"BRINKS", "CO"} - the
    possessive token never matches its non-possessive counterpart, so
    names_plausibly_match wrongly rejected a correct CUSIP resolution as a
    "wrong entity". Live-confirmed on 8 real symbols including MCD (McDonald's)
    and LOW (Lowe's) - large, liquid, heavily-institutionally-held stocks that
    were falling back to institutional_ownership_pct=NULL
    ("no_resolved_13f_holdings") purely because of this apostrophe mismatch.
    """
    if not name:
        return frozenset()
    cleaned = name.upper().replace(".", " ").replace(",", " ").replace("-", " ").replace("&", " ").replace("'", "")
    expanded = (_ABBREVIATION_EXPANSIONS.get(w, w) for w in cleaned.split())
    return frozenset(w for w in expanded if w not in _CORP_SUFFIXES)


def names_plausibly_match(figi_name: str | None, local_name: str | None) -> bool:
    """Loose sanity check that two entity names plausibly refer to the same company.

    Not a precision matcher - corporate naming conventions vary too much for that
    (see this module's docstring: OpenFIGI's own "EXXONMOBIL HOLDINGS CORP" vs the
    real filer's "EXXON MOBIL CORP" don't share a single token after normalization,
    which is exactly the case this function exists to catch). Used as a secondary
    safety net on top of the real correctness guarantee (the CUSIP/FIGI join itself),
    never as the primary matching mechanism.
    """
    a, b = name_tokens(figi_name), name_tokens(local_name)
    if not a or not b:
        return False
    overlap = a & b
    return len(overlap) / min(len(a), len(b)) >= 0.5


class EntityNameIndex:
    """Reverse lookup: given a resolved entity name, find which tracked symbol it
    plausibly refers to - the inverse of names_plausibly_match's usual direction
    (ticker already known, name checked as a sanity gate).

    FIXED 2026-08-18 (goal session, "which factor inputs are missing the most"
    audit): OpenFIGI's ticker field for a CUSIP is sometimes simply wrong for our
    purposes even though resolved_name is correct - live-confirmed two distinct
    ways: (1) a resolved ticker that isn't in our tracked universe at all (real
    Exxon Mobil CUSIP 30231G102 resolves to ticker "EXMOC", a Bloomberg-side
    variant, not "XOM" - previously documented in this module as accepted "honest
    non-coverage", but the same pattern turned out to affect dozens of other
    megacaps: CVX, MS, C, PM, HON, MCD, LOW, ACN, LIN, and more). (2) a resolved
    ticker that collides with a DIFFERENT real tracked symbol - Verizon's real
    equity CUSIP 92343V104 resolves to ticker "BAC" (Bank of America's ticker),
    which passes the "ticker in our universe" check but is correctly rejected by
    names_plausibly_match (VERIZON COMMUNICATIONS INC vs BANK OF AMERICA CORP
    share no tokens) - previously that rejection was a dead end with no fallback,
    silently discarding Verizon's own real 13F data. This second failure mode is
    NOT fixed by the exchCode="US" preference in fetch_cusip_tickers() above -
    it's a wrong-company mapping, not a wrong-listing one.

    In both cases resolved_name (VERIZON COMMUNICATIONS INC / EXXON MOBIL CORP)
    matches our own SEC-sourced entity_name for the RIGHT symbol almost exactly -
    this index finds that symbol by searching our own tracked universe's names
    instead of trusting the crosswalk's ticker field. Same safety bar as the
    forward direction: only returns a match when names_plausibly_match's >=50%
    token-overlap threshold is met, and only when EXACTLY ONE tracked symbol
    qualifies - an ambiguous or zero-candidate result returns None rather than
    guessing, the same "never fabricate" governance as the rest of this module.
    """

    def __init__(self, local_names: dict[str, str]) -> None:
        self._local_tokens: dict[str, frozenset[str]] = {
            symbol: name_tokens(name) for symbol, name in local_names.items()
        }
        self._token_index: dict[str, set[str]] = defaultdict(set)
        for symbol, tokens in self._local_tokens.items():
            for token in tokens:
                self._token_index[token].add(symbol)

    def find(self, resolved_name: str | None) -> str | None:
        """Symbol whose local entity name plausibly matches resolved_name, or None
        if zero or more than one tracked symbol qualifies."""
        candidate_tokens = name_tokens(resolved_name)
        if not candidate_tokens:
            return None
        candidates: set[str] = set()
        for token in candidate_tokens:
            candidates |= self._token_index.get(token, set())

        matches = []
        for symbol in candidates:
            local = self._local_tokens[symbol]
            if not local:
                continue
            overlap = candidate_tokens & local
            if len(overlap) / min(len(candidate_tokens), len(local)) >= 0.5:
                matches.append(symbol)
                if len(matches) > 1:
                    return None  # ambiguous - bail without scanning the rest

        return matches[0] if len(matches) == 1 else None
