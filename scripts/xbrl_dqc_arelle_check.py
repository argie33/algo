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

Live-verified 2026-09-12 (memory: dqc_arelle_local_validation_proven_20260912): ran against
AIT's (Applied Industrial Technologies) real FY2026 10-K and found genuine DQC.US.0001.51/.52
violations (extension members used on FairValueByFairValueHierarchyLevelAxis and
ReclassificationOutOfAccumulatedOtherComprehensiveIncomeAxis, where only standard taxonomy
members belong) - a real filing-quality defect in AIT's own filing, independent of anything our
extraction pipeline does. This is a DIFFERENT bug class from everything checks 1-5 (tie_out.py,
statistical_anomaly.py, yfinance crosscheck, calc-linkbase check, concept-coverage scan) catch:
those validate OUR extracted values; DQC validates whether the FILER's own XBRL tagging follows
the industry rulebook, which can help explain (not necessarily fix) some of the "127" missing-
data floor's stranger cases - a filer whose own filing fails DQC rules around an axis/concept
may be exactly why that concept extracts as implausible or missing in the first place.

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
import logging
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


def _parse_dqc_findings(log_path: Path, proc: subprocess.CompletedProcess[bytes]) -> list[dict[str, str]]:
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
    for entry in entries:
        code = entry.get("code", "")
        if not code.startswith("DQC."):
            continue
        message_el = entry.find("message")
        text = (message_el.text or "").strip().split("\n")[0] if message_el is not None else ""
        findings.append({"rule": code, "message": text[:300]})
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
            try:
                proc = _run_dqc(arelle_exe, plugin_path, instance_url, log_path)
                findings = _parse_dqc_findings(log_path, proc)
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
