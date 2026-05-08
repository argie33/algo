#!/usr/bin/env python3
import os
import sys
import time
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Critical loaders - no data or incomplete data
critical_loaders = [
    # Stock core data
    'loadstocksymbols.py',
    'loadpricedaily.py',
    'loadpriceweekly.py',
    'loadpricemonthly.py',
    
    # Financial statements - annual
    'loadannualincomestatement.py',
    'loadannualbalancesheet.py',
    'loadannualcashflow.py',
    
    # Financial statements - quarterly
    'loadquarterlyincomestatement.py',
    'loadquarterlybalancesheet.py',
    'loadquarterlycashflow.py',
    
    # TTM data
    'loadttmincomestatement.py',
    'loadttmcashflow.py',
    
    # Technical indicators
    'loadbuysell_etf_daily.py',
    'loadbuyselldaily.py',
    'loadbuysellweekly.py',
    'loadbuysellmonthly.py',
    
    # Earnings
    'loadearningshistory.py',
    'loadearningsrevisions.py',
    'loadearningssurprise.py',
    'load_sp500_earnings.py',
    
    # Market data
    'loadmarket.py',
    'loadmarketindices.py',
    'loadsectors.py',
    'loadrelativeperformance.py',
    'loadseasonality.py',
    
    # Sentiment and analysis
    'loadanalystsentiment.py',
    'loadanalystupgradedowngrade.py',
    'loadsentiment.py',
    'loadfactormetrics.py',
    'loadstockscores.py',
    
    # Economic data
    'loadecondata.py',
    'loadaaiidata.py',
    'loadnaaim.py',
    'loadfeargreed.py',
    
    # Calendar
    'loadcalendar.py',
    
    # ETF data
    'loadetfpricedaily.py',
    'loadetfpriceweekly.py',
    'loadetfpricemonthly.py',
    'loadetfsignals.py',
]

logger.info(f"\n{'='*70}")
logger.info(f"Running {len(critical_loaders)} critical loaders")
logger.info(f"{'='*70}\n")

failed = []
successful = []
rate_limited = []

for i, loader in enumerate(critical_loaders, 1):
    if not os.path.exists(loader):
        logging.warning(f"[{i}/{len(critical_loaders)}] SKIP {loader} - not found")
        continue
    
    logging.info(f"[{i}/{len(critical_loaders)}] Running {loader}...")
    
    try:
        result = subprocess.run(
            ['python3', loader],
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout per loader
        )
        
        if result.returncode == 0:
            successful.append(loader)
            # Extract row count from output if available
            if 'rows' in result.stdout.lower() or 'completed' in result.stdout.lower():
                logging.info(f"  [OK] {loader}")
            else:
                logging.info(f"  [OK] {loader}")
        else:
            if '429' in result.stderr or 'rate' in result.stderr.lower():
                rate_limited.append(loader)
                logging.warning(f"  [RATE_LIMITED] {loader}")
            else:
                failed.append(loader)
                logging.error(f"  [FAILED] {loader}")
                if result.stderr:
                    logging.error(f"    Error: {result.stderr[:200]}")
    
    except subprocess.TimeoutExpired:
        failed.append(loader)
        logging.error(f"  [TIMEOUT] {loader}")
    except Exception as e:
        failed.append(loader)
        logging.error(f"  [ERROR] {loader}: {str(e)[:100]}")
    
    # Rate limit protection - wait between loaders
    if i < len(critical_loaders):
        time.sleep(0.5)

logger.info(f"\n{'='*70}")
logger.info(f"SUMMARY")
logger.info(f"{'='*70}")
logger.info(f"Successful: {len(successful)}")
logger.info(f"Failed: {len(failed)}")
logger.info(f"Rate Limited: {len(rate_limited)}")

if failed:
    logger.info(f"\nFailed loaders:")
    for loader in failed[:5]:
        logger.info(f"  - {loader}")
    if len(failed) > 5:
        logger.info(f"  ... and {len(failed)-5} more")

if rate_limited:
    logger.info(f"\nRate limited loaders (retry later):")
    for loader in rate_limited[:5]:
        logger.info(f"  - {loader}")
    if len(rate_limited) > 5:
        logger.info(f"  ... and {len(rate_limited)-5} more")

logger.info(f"\n{'='*70}\n")
