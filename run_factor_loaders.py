#!/usr/bin/env python3
"""Run all factor loaders for stock scores calculation"""
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
        logging.FileHandler("/home/stocks/algo/factor_loaders.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Factor loaders needed for stock scores
FACTOR_LOADERS = [
    ("loadanalystsentiment.py", "Analyst Sentiment"),
    ("loadmomentum.py", "Momentum Metrics"),
    ("loadgrowthmetrics.py", "Growth Metrics"),
    ("loadvaluemetrics.py", "Value Metrics"),
    ("loadqualitymetrics.py", "Quality Metrics"),
    ("loadpositioning.py", "Positioning Metrics"),
    ("loadstockscores.py", "Stock Scores (Recalculation)"),
]

logger.info("=" * 70)
logger.info("🚀 RUNNING FACTOR LOADERS FOR STOCK SCORES (FRESH START)")
logger.info("=" * 70)

for script_name, description in FACTOR_LOADERS:
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
            timeout=3600,
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
        logger.error(f"⏱️ TIMEOUT: {description} (exceeded 1 hour)")
    except Exception as e:
        logger.error(f"❌ ERROR: {description} - {e}")

logger.info("\n" + "=" * 70)
logger.info("🎉 FACTOR LOADERS COMPLETED!")
logger.info("=" * 70)
