#!/usr/bin/env python3
"""Run all market page loaders"""
import os
import subprocess
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/home/stocks/algo/market_loaders.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Market page loaders
MARKET_LOADERS = [
    ("loadfeargreed.py", "Fear & Greed Index"),
    ("loadaaiidata.py", "AAII Sentiment"),
    ("loadnaaim.py", "NAAIM Data"),
    ("loadmarket.py", "Market Data"),
    ("loadcalendar.py", "Market Calendar"),
]

logger.info("=" * 70)
logger.info("🚀 RUNNING MARKET PAGE LOADERS")
logger.info("=" * 70)

for script_name, description in MARKET_LOADERS:
    logger.info("\n" + "=" * 70)
    logger.info(f"📦 Running: {description} ({script_name})")
    logger.info("=" * 70)

    script_path = Path("/home/stocks/algo") / script_name

    if not script_path.exists():
        logger.error(f"❌ Script not found: {script_path}")
        continue

    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            cwd="/home/stocks/algo",
            capture_output=True,
            text=True,
            timeout=1800,
        )

        if result.stdout:
            logger.info(result.stdout[-2000:])

        if result.returncode == 0:
            logger.info(f"✅ SUCCESS: {description}")
        else:
            logger.error(f"❌ FAILED: {description}")
            if result.stderr:
                logger.error(result.stderr[-2000:])
    except subprocess.TimeoutExpired:
        logger.error(f"⏱️ TIMEOUT: {description} (exceeded 30 min)")
    except Exception as e:
        logger.error(f"❌ ERROR: {description} - {e}")

logger.info("\n" + "=" * 70)
logger.info("🎉 MARKET PAGE LOADERS COMPLETED!")
logger.info("=" * 70)
