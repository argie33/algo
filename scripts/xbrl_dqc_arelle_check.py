#!/usr/bin/env python3
"""Runs the official XBRL US Data Quality Committee (DQC) rules against a batch of symbols'
latest 10-K/20-F/40-F, using the free, local, no-account-needed Arelle + dqc_us_rules stack.

Added 2026-09-12 (goal: "resources we should be tapping into" ask). This is a DIFFERENT,
independent resource from the XBRL US API (see memory xbrl_us_free_api_confirmed_real_20260912)
- the DQC ruleset (the actual industry-standard validation rules SEC filing agents and major
XBRL vendors use, github.com/DataQualityCommittee/dqc_us_rules) needs no account, no API key,
no rate limit at all: `pip install arelle-release dqc_us_rules` installs a real local XBRL
processor (Arelle) plus a native-Python Arelle plugin implementing DQC.US.0001/0004/0005/0006/
0009/0013/0014/0015/0018/0033-0036/0041 (a real subset of the full current 196-rule set, not
all of it - the rest is Xule-based and not packaged for pip as of this writing).

CORRECTED 2026-09-12: the original "live-verified against AIT, found genuine DQC.US.0001.51/.52
violations" claim (memory dqc_arelle_local_validation_proven_20260912) is retracted. Re-running
this script against AAPL's real FY2025 10-K - a company whose own real-world XBRL tagging is
about as scrutinized as any filer's gets - produced 257 DQC.US.0001.x "violations", all of them
flagging entirely standard us-gaap taxonomy members (e.g. `FairValueInputsLevel2Member`,
`DesignatedAsHedgingInstrumentMember`) as if they were the filer's own custom extensions. That is
not plausible as a real filing defect at that volume on that filer, and the same shape almost
certainly explains the original AIT "genuine" findings too. Root cause: dqc_us_rules'
`_is_extension()` check depends on the local Arelle taxonomy package cache recognizing the
filing's dated us-gaap namespace (e.g. http://fasb.org/us-gaap/2025) as "standard" - when it
doesn't, every concept in that namespace misclassifies as an extension. `_parse_dqc_findings`
now filters these out via `_is_taxonomy_resolution_false_positive` (see its docstring) before
anything is logged as a finding; see memory dqc_arelle_taxonomy_resolution_false_positive_20260912
for the full trail. This is a DIFFERENT bug class from everything checks 1-5 (tie_out.py,
statistical_anomaly.py, yfinance crosscheck, calc-linkbase check, concept-coverage scan) catch:
those validate OUR extracted values; DQC (when its own findings are trustworthy) validates
whether the FILER's own XBRL tagging follows the industry rulebook - treat any surviving finding
as a review-queue candidate, not an automatic "real filing bug," until spot-checked the way the
AAPL/AIT cases above were.

RESOLVED 2026-09-12 (was "STILL-INCOMPLETE" earlier the same day - kept below for the full trail):
the taxonomy-misclassification shape survived the first fix on MSFT (180/427 findings) and KO
(236/477) - patched further with `_KNOWN_STANDARD_AXIS_MEMBER_LABELS` (a hand-maintained label
table, reduced MSFT to 0/KO to 54) and then with the actual root-cause fix,
`_load_standard_member_labels`: instead of guessing whether a flagged member's displayed label
"looks like" a standard concept's qname, load the SAME filing via Arelle's Python API (in a
subprocess, same isolation posture as `_run_dqc`) and read every standard-namespace concept's
REAL resolved label straight from its label linkbase. KO's remaining 54 turned out not to be a
"different, structurally unfixable" gap after all - `us-gaap:CorporateNonSegmentMember`'s real
label IS "Segment Reporting, Reconciling Item, Corporate Nonsegment [Member]", an exact match for
the finding's displayed text; the earlier "no lexical resemblance" diagnosis was comparing against
the qname's local name, which was simply the wrong ground truth to compare against. Full re-test
across every symbol this bug was ever found on (AAPL, MSFT, KO, AIT, SCM, DKS) came back
completely clean. The hand-maintained label table and dimensions-text matching are kept as cheap
fallbacks (in case the label-loading subprocess fails for a given filing), but the real-label
lookup is what actually closes this bug class - trust a "genuine violation" count from this layer
now, but a sudden reappearance of a high count on a well-known filer is still worth spot-checking
once (e.g. `_load_standard_member_labels` silently failing and falling back).

Requires `pip install -r requirements-xbrl-dqc.txt` (arelle-release==2.45.0, dqc_us_rules==3.6.0,
pinned and verified to install cleanly). Deliberately its own separate requirements file, same
status as requirements-dev.txt - NOT part of requirements.txt (the app runtime deps) and not a
dependency of anything in the orchestrator/API/dashboard path; see that file's own comment for
why. The script fails fast with a clear message if either package isn't installed in whatever
environment invokes it, rather than silently skipping.

Deliberately NOT wired into any schedule: each symbol invocation shells out to `arelleCmdLine`
as a subprocess rather than importing Arelle as a library in-process (Arelle does expose a
programmatic Cntlr API - this is a deliberate isolation choice, not a technical limitation: a
crash or a plugin/taxonomy-cache state issue inside Arelle's controller stays contained to the
subprocess instead of taking down whatever long-running process invoked this). Each invocation
takes several seconds to a minute per filing (taxonomy loading + validation) and needs outbound
network access to SEC EDGAR and Arelle's own taxonomy cache - same "small periodic sample,
review-queue findings" posture as xbrl_yfinance_crosscheck.py/xbrl_calculation_linkbase_check.py.

Usage:
    python scripts/xbrl_dqc_arelle_check.py --symbols AIT,DKS,W    # explicit batch
    python scripts/xbrl_dqc_arelle_check.py --limit 10             # rotating sample of the active universe
    python scripts/xbrl_dqc_arelle_check.py --dry-run              # print, don't write to data_patrol_log
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
_USER_AGENT = "algo-research contact@example.com"
_MAX_EXAMPLES_PER_SYMBOL = 10


def _select_rotating_sample(limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of the active universe - same convention as
    xbrl_yfinance_crosscheck.py's _select_symbols, so repeated runs accumulate coverage across
    the whole universe over time instead of always re-checking the same alphabetically-first
    symbols (a plain `universe[:limit]` slice would never reach past "A"/"B" tickers)."""
    from utils.db.context import DatabaseContext
    from utils.loaders.helpers import get_active_symbols

    active = set(get_active_symbols(exclude_etfs=True))
    with DatabaseContext("read") as cur:
        cur.execute(
            """
            SELECT symbol FROM (SELECT unnest(%s::text[]) AS symbol) s
            ORDER BY md5(symbol || CURRENT_DATE::text)
            LIMIT %s
            """,
            (list(active), limit),
        )
        return [row[0] for row in cur.fetchall()]


def _find_arelle_cmdline() -> str:
    exe = shutil.which("arelleCmdLine") or shutil.which("arelleCmdLine.exe")
    if not exe:
        raise RuntimeError("arelleCmdLine not found on PATH. Install with: pip install arelle-release dqc_us_rules")
    return exe


def _find_dqc_plugin_path() -> str:
    try:
        import dqc_us_rules
    except ImportError as e:
        raise RuntimeError("dqc_us_rules not installed. Install with: pip install dqc_us_rules") from e
    return str(Path(dqc_us_rules.__file__).resolve().parent)


# Real, resolved concept LABELS (via Arelle's own label linkbase) for every concept whose
# namespace is one of these genuinely-standard taxonomies, keyed by normalized label text. Built
# once per filing by `_load_standard_member_labels` and used to close the residual DQC.US.0001.x
# false-positive gap that neither the truncated-attribute fix nor `_KNOWN_STANDARD_AXIS_MEMBER_
# LABELS` could: some standard concepts' real preferred label (e.g. us-gaap:CorporateNonSegmentMember's
# "Segment Reporting, Reconciling Item, Corporate Nonsegment [Member]") has zero lexical resemblance
# to the concept's own qname local name - live-confirmed on KO by loading the same instance via
# Arelle's Python API and reading `concept.label()` directly instead of guessing from the qname.
_STANDARD_NAMESPACE_RE = re.compile(
    r"^https?://(fasb\.org/(us-gaap|srt)|xbrl\.sec\.gov/(dei|country|currency|cyd|ecd|exch|invest|naics|sic|stpr)"
    r"|xbrl\.ifrs\.org/taxonomy)/"
)

_LOAD_STANDARD_LABELS_SNIPPET = """
import json, re, sys
from arelle import Cntlr

NS_RE = re.compile(r'''__NS_PATTERN__''')


def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


cntlr = Cntlr.Cntlr()
cntlr.startLogging(logFileName="logToPrint")
model_xbrl = cntlr.modelManager.load(sys.argv[1])
labels = set()
for qname, concept in model_xbrl.qnameConcepts.items():
    if not NS_RE.match(qname.namespaceURI):
        continue
    try:
        label = concept.label(lang="en-US")
    except Exception:
        label = None
    if label:
        labels.add(norm(label))
print(json.dumps(sorted(labels)))
""".replace("__NS_PATTERN__", _STANDARD_NAMESPACE_RE.pattern)


def _load_standard_member_labels(instance_url: str) -> set[str]:
    """Loads `instance_url` via Arelle's Python API IN A SUBPROCESS (not in-process - same
    crash-isolation reasoning as `_run_dqc` shelling out to arelleCmdLine rather than importing
    Arelle's Cntlr directly into this script's own process) and returns the normalized real
    labels of every concept in a standard taxonomy namespace. Best-effort: returns an empty set
    (not an exception) on any failure, since this is a supplementary false-positive filter, not
    the primary validation - a failure here should degrade to the existing dimensions-text/
    hardcoded-table checks, not abort the whole DQC run for that symbol.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _LOAD_STANDARD_LABELS_SNIPPET, instance_url],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if proc.returncode != 0:
            logger.debug(f"[DQC_CHECK] standard-label lookup failed for {instance_url}: {proc.stderr[-300:]!r}")
            return set()
        last_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        return set(json.loads(last_line)) if last_line else set()
    except (subprocess.TimeoutExpired, ValueError, OSError) as e:
        logger.debug(f"[DQC_CHECK] standard-label lookup errored for {instance_url}: {e}")
        return set()


def _resolve_instance_url(client: Any, symbol: str) -> tuple[str, str] | None:
    """Returns (cik, instance_xml_url) for the symbol's most recent annual filing, or None."""
    try:
        cik = client.symbol_to_cik(symbol)
        submissions = client.get_submissions(cik)
    except (FileNotFoundError, ValueError) as e:
        logger.debug(f"[DQC_CHECK] {symbol}: could not resolve CIK/submissions ({e})")
        return None

    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []
    idx = next((i for i, f in enumerate(forms) if f in _ANNUAL_FORMS), None)
    if idx is None or idx >= len(accessions) or idx >= len(primary_docs):
        logger.debug(f"[DQC_CHECK] {symbol}: no 10-K/20-F/40-F in recent filings")
        return None

    accession_nodash = accessions[idx].replace("-", "")
    primary_doc = primary_docs[idx]
    if not primary_doc.lower().endswith(".htm"):
        logger.debug(f"[DQC_CHECK] {symbol}: primary document {primary_doc!r} isn't an inline-XBRL .htm, skipping")
        return None
    instance_name = primary_doc[: -len(".htm")] + "_htm.xml"
    cik_nolead = cik.lstrip("0") or "0"
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_nolead}/{accession_nodash}/{instance_name}"
    return cik, url


def _run_dqc(
    arelle_exe: str, plugin_path: str, instance_url: str, log_path: Path
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            arelle_exe,
            "--plugins",
            plugin_path,
            "-f",
            instance_url,
            "--validate",
            "--httpUserAgent",
            _USER_AGENT,
            "--logFile",
            str(log_path),
        ],
        capture_output=True,
        timeout=180,
        check=False,
    )


class DqcRunError(Exception):
    """The instance never actually loaded/validated - distinct from "loaded fine, zero DQC
    findings". Without this distinction, a 404'd instance URL, a network blip, or a plugin
    load failure would silently report as "clean" - the exact silent-success-on-failure shape
    flagged elsewhere in this repo's own review history (see memory
    check_silent_fallbacks_worktree_skip_path_defeats_check_20260911)."""


_QNAME_TOKEN_RE = re.compile(r"([\w.-]+):(\w+)")
_ALNUM_RE = re.compile(r"[^a-z0-9]")

# Standard taxonomy namespace prefixes as they appear in Arelle's rendered fact1.dimensions
# strings. A member living under one of these can never be a filer's own "extension member" -
# extensions always live under the filer's own company-specific prefix (e.g. "aapl:", "ait:").
_STANDARD_TAXONOMY_PREFIXES = {
    "us-gaap",
    "dei",
    "srt",
    "ifrs-full",
    "invest",
    "country",
    "currency",
    "exch",
    "naics",
    "sic",
    "stpr",
}


def _normalize_xbrl_label(text: str) -> str:
    return _ALNUM_RE.sub("", text.lower())


# Axis label (as Arelle renders the "axis" attribute, normalized) -> the finite set of FASB
# extensible-list member labels (normalized) that are standard for that axis. Hand-maintained
# because DQC.US.0001 only ever fires on a small, well-known set of FASB extensible-list axes
# (that is the rule family's whole premise - these axes have a closed standard-member vocabulary,
# which is exactly what makes a real filer extension on them suspicious), and the two other
# available sources both have real gaps: dqc_us_rules' own bundled `defined_members` allowlist
# (DQC_US_0001/dqc_0001.json) is missing newer standard members (e.g. the ASU 2015-07 NAV
# practical-expedient member, `FairValueMeasuredAtNetAssetValuePerShareMember`, live-confirmed
# absent from the installed dqc_us_rules==3.6.0 package data even though it is a real, standard
# us-gaap concept) - and the fact1.dimensions text-matching fallback below cannot help either,
# since Arelle truncates that string to a fixed character budget and a fact with 2+ dimensions
# routinely gets cut before the flagged member's own qname is rendered at all (live-confirmed on
# MSFT: `fact1.dimensions='...us-gaap:FairValueBy...'`, cut off mid-axis-name, zero characters of
# the actual member's local name present to match against). Added 2026-09-12 after this exact
# gap let 180/427 (MSFT) and 236/477 (KO) DQC.US.0001.x findings survive the fact1.dimensions-only
# filter below as apparent "genuine" violations on two of the most scrutinized filers in the
# world - live re-verified as the same taxonomy-misclassification shape as the AAPL/AIT case this
# filter was originally built for, not real filing defects.
_KNOWN_STANDARD_AXIS_MEMBER_LABELS: dict[str, set[str]] = {
    "fairvaluehierarchyandnavaxis": {
        "fairvalueinputslevel1member",
        "fairvalueinputslevel2member",
        "fairvalueinputslevel3member",
        "fairvaluemeasuredatnetassetvaluepersharemember",
    },
    "hedgingdesignationaxis": {
        "designatedashedginginstrumentmember",
        "nondesignatedmember",
        "notdesignatedashedginginstrumentmember",
    },
    "consolidationitemsaxis": {
        "consolidationeliminationsmember",
        "parentcompanymember",
    },
    "statisticalmeasurementaxis": {
        "maximummember",
        "minimummember",
        "weightedaveragemember",
    },
    "positionaxis": {
        "shortmember",
        "longmember",
    },
    "rangeaxis": {
        "maximummember",
        "minimummember",
    },
}


def _is_taxonomy_resolution_false_positive(
    code: str, message_el: ET.Element, standard_member_labels: set[str] | None = None
) -> bool:
    """True if this DQC.US.0001.x finding's flagged "extension member" actually resolves to a
    standard-namespace concept in the fact's own rendered dimensions - i.e. it cannot possibly
    be a real filer extension, regardless of which axis it's on.

    Added 2026-09-12 after live-reproducing a false-positive: AAPL's real FY2025 10-K got 170
    DQC.US.0001.51 hits all claiming standard members like `us-gaap:FairValueInputsLevel2Member`
    were "extension members" on the Fair Value Hierarchy axis, plus more of the same shape under
    DQC.US.0001.66 on the (differently-configured) Hedging Designation axis for
    `us-gaap:DesignatedAsHedgingInstrumentMember`/`NondesignatedMember`. Root cause: dqc_us_rules'
    `_is_extension()` classifies a concept as an extension purely by checking
    `concept.qname.namespaceURI not in val.disclosureSystem.standardTaxonomiesDict`, which
    depends on Arelle recognizing the filing's dated us-gaap namespace (e.g.
    http://fasb.org/us-gaap/2025) as "standard" - if the local Arelle taxonomy package cache
    doesn't have that year registered, EVERY concept in that namespace misclassifies as an
    extension and every DQC.US.0001.x sub-rule fires on entirely standard tagging, on any axis.
    An earlier version of this check cross-referenced dqc_us_rules' own bundled per-axis
    `defined_members` allowlist (DQC_US_0001/dqc_0001.json) instead - that caught the Fair Value
    axis case (170/170) but missed the Hedging Designation axis case (dqc_0001.json only lists
    a handful of "well-known axes", not every axis a filer might use with a standard member), so
    it's replaced with this axis-independent check: match the finding's human-readable "member"
    label against every qname token actually present in the fact's own rendered dimensions, and
    treat it as a tool false positive if the matching qname's prefix is a standard taxonomy
    namespace. Confirmed by reproducing the same shape on the already-logged AIT example (memory
    dqc_arelle_local_validation_proven_20260912's "genuine" finding) - that claim is retracted;
    see memory dqc_arelle_taxonomy_resolution_false_positive_20260912.

    EXTENDED 2026-09-12 (first pass) with `_KNOWN_STANDARD_AXIS_MEMBER_LABELS` as a second,
    independent check (see its own docstring) after MSFT/KO exposed the fact1.dimensions
    ATTRIBUTE's truncation blind spot - kept as a defense-in-depth fallback.

    EXTENDED 2026-09-12 (second pass) to read dimensions from the message's own untruncated *text*
    (`message_el.text`, e.g. "...\nDimensions: us-gaap:FairValueByFairValueHierarchyLevelAxis =
    us-gaap:FairValueInputsLevel3Member\n...") instead of the `fact1.dimensions` XML *attribute*,
    which Arelle truncates to a fixed length and was the actual cause of the original MSFT
    truncation gap this docstring's first EXTENDED note describes. This is a strictly more
    correct data source than the attribute (more robust against long/many-dimension facts) but
    does NOT, on its own, close the separate KO "Segment Reporting, Reconciling Item, Corporate
    Nonsegment [Member]" gap - tested directly and confirmed that gap is NOT truncation at all:
    the qname (`us-gaap:CorporateNonSegmentMember`) is fully present, untruncated, in this same
    text, but its normalized local name has zero textual overlap with the member's own displayed
    label ("segmentreportingreconcilingitemcorporatenonsegmentmember" vs
    "corporatenonsegmentmember") - a genuine label-vs-qname wording mismatch, structurally
    different from anything a truncation fix (this one) or a hardcoded label table
    (`_KNOWN_STANDARD_AXIS_MEMBER_LABELS`) can close.

    EXTENDED 2026-09-12 (third pass) with `standard_member_labels` - the actual fix for the KO
    gap the second pass's docstring called "structurally different, not fixable by a lexical
    heuristic." Live-tested: `us-gaap:CorporateNonSegmentMember`'s REAL resolved label (via
    Arelle's Python API's `concept.label()`, i.e. its actual label linkbase, not a guess from its
    qname local name) is "Segment Reporting, Reconciling Item, Corporate Nonsegment [Member]" -
    an EXACT match for what the DQC finding displays. The earlier "lexical mismatch" diagnosis was
    comparing the member label against the qname's *local name*, which was simply the wrong
    comparison basis - the concept's real label was never actually different from the finding's
    displayed label, it just isn't derivable by guessing from the qname text. `_load_standard_
    member_labels` (see its own docstring) loads the filing's real DTS and returns every standard
    concept's genuine resolved label, sidestepping the guessing problem entirely.
    """
    if not code.startswith("DQC.US.0001."):
        return False
    member_label = message_el.get("member", "")
    target = _normalize_xbrl_label(member_label)
    if not target:
        return False
    if standard_member_labels and target in standard_member_labels:
        return True
    axis_key = _normalize_xbrl_label(message_el.get("axis", ""))
    if target in _KNOWN_STANDARD_AXIS_MEMBER_LABELS.get(axis_key, ()):
        return True
    # Prefer the message's own untruncated text (the "Dimensions: ..." section) over the
    # fact1.dimensions attribute, which Arelle truncates to a fixed length and can cut off the
    # flagged member's qname entirely on a fact with several dimensions. Fall back to the
    # attribute for older/malformed entries that lack the expected text section.
    text = message_el.text or ""
    dims_marker = text.find("Dimensions:")
    dimensions_text = text[dims_marker:] if dims_marker != -1 else message_el.get("fact1.dimensions", "")
    for prefix, local in _QNAME_TOKEN_RE.findall(dimensions_text):
        if prefix not in _STANDARD_TAXONOMY_PREFIXES:
            continue
        normalized_local = _normalize_xbrl_label(local)
        if normalized_local == target:
            return True
        # Truncated-attribute fallback only: a one-sided prefix match is only trustworthy once
        # long enough that a coincidental short-prefix collision is implausible.
        if len(normalized_local) >= 8 and target.startswith(normalized_local):
            return True
    return False


def _parse_dqc_findings(
    log_path: Path, proc: subprocess.CompletedProcess[bytes], standard_member_labels: set[str] | None = None
) -> list[dict[str, str]]:
    if not log_path.exists():
        raise DqcRunError(f"arelleCmdLine produced no log file (exit code {proc.returncode}): {proc.stderr[-500:]!r}")
    tree = ET.parse(log_path)
    entries = tree.getroot().findall("entry")
    if not any(e.get("code") == "info" and "validated in" in (e.findtext("message") or "") for e in entries):
        error_texts = [e.findtext("message", "") for e in entries if e.get("level") == "error"]
        raise DqcRunError(
            "instance never reached a 'validated in ...' info entry - it did not load/validate "
            f"(errors: {error_texts[:3]})"
        )
    findings = []
    suspected_false_positives = 0
    for entry in entries:
        code = entry.get("code", "")
        if not code.startswith("DQC."):
            continue
        message_el = entry.find("message")
        if message_el is None:
            continue
        if _is_taxonomy_resolution_false_positive(code, message_el, standard_member_labels):
            suspected_false_positives += 1
            continue
        text = (message_el.text or "").strip().split("\n")[0]
        findings.append({"rule": code, "message": text[:300]})
    if suspected_false_positives:
        logger.warning(
            f"[DQC_CHECK] excluded {suspected_false_positives} finding(s) whose flagged member "
            "resolves to a standard taxonomy namespace in the fact's own dimensions - taxonomy-"
            "recognition false positive, not a real filing defect (see "
            "_is_taxonomy_resolution_false_positive docstring)"
        )
    return findings


def run(symbols: list[str], dry_run: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection
    from utils.external.sec_edgar_client import SecEdgarClient

    arelle_exe = _find_arelle_cmdline()
    plugin_path = _find_dqc_plugin_path()
    client = SecEdgarClient()

    all_findings: dict[str, list[dict[str, str]]] = {}
    checked = 0
    failed: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for symbol in symbols:
            resolved = _resolve_instance_url(client, symbol)
            if resolved is None:
                continue
            _cik, instance_url = resolved
            log_path = Path(tmpdir) / f"{symbol}_dqc.xml"
            standard_member_labels = _load_standard_member_labels(instance_url)
            try:
                proc = _run_dqc(arelle_exe, plugin_path, instance_url, log_path)
                findings = _parse_dqc_findings(log_path, proc, standard_member_labels)
            except subprocess.TimeoutExpired:
                logger.warning(f"[DQC_CHECK] {symbol}: arelleCmdLine timed out, skipping")
                failed.append(symbol)
                continue
            except DqcRunError as e:
                logger.warning(f"[DQC_CHECK] {symbol}: run failed, not counted as clean - {e}")
                failed.append(symbol)
                continue
            checked += 1
            if findings:
                all_findings[symbol] = findings
                logger.info(f"[DQC_CHECK] {symbol}: {len(findings)} DQC rule violation(s)")
            else:
                logger.info(f"[DQC_CHECK] {symbol}: clean")

    if failed:
        logger.warning(
            f"[DQC_CHECK] {len(failed)}/{len(symbols)} symbol(s) failed to validate (not clean, not counted): {failed}"
        )

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    results: list[CheckResult] = []
    total_findings = sum(len(v) for v in all_findings.values())
    if all_findings:
        examples = [
            {"symbol": sym, **f} for sym, findings in all_findings.items() for f in findings[:_MAX_EXAMPLES_PER_SYMBOL]
        ]
        results.append(
            CheckResult(
                "xbrl_dqc_arelle_check",
                "warn",
                "annual_income_statement",
                f"{total_findings} official DQC rule violation(s) across {len(all_findings)}/{checked} "
                "checked filer(s)' own filings - review queue: these are the FILER's own XBRL "
                "tagging failing the industry-standard DQC ruleset, not necessarily an error in "
                "our extraction of their data.",
                {"checked": checked, "flagged_symbols": len(all_findings), "examples": examples},
            )
        )
    else:
        results.append(
            CheckResult(
                "xbrl_dqc_arelle_check",
                "info",
                "annual_income_statement",
                f"no DQC rule violations found across {checked} checked filer(s)",
            )
        )

    if dry_run:
        for r in results:
            logger.info(f"[DRY-RUN] [{r.severity.upper()}] {r.check_name}: {r.message}")
    else:
        run_id = uuid.uuid4().hex
        patrol_logger = PatrolLogger(run_id)
        patrol_logger.log_results(cur, results)
        conn.commit()
        logger.info(f"[DQC_CHECK] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {
        "checked": checked,
        "failed": len(failed),
        "flagged_symbols": len(all_findings),
        "results": [r.to_dict() for r in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list")
    parser.add_argument(
        "--limit", type=int, default=10, help="Rotating sample size if --symbols not given (default 10)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to data_patrol_log")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = _select_rotating_sample(args.limit)

    started = time.monotonic()
    summary = run(symbols=symbols, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info(
        f"[DQC_CHECK] Done in {elapsed:.1f}s - checked={summary['checked']} flagged={summary['flagged_symbols']}"
    )


if __name__ == "__main__":
    main()
