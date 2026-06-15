#!/usr/bin/env python3
"""Entrypoint for data patrol ECS task.

ECS task definition runs: python3 algo/algo_data_patrol.py
Implementation lives in: algo/monitoring/data_patrol.py
"""
import sys
import runpy
from pathlib import Path

root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

runpy.run_path(str(root / "algo" / "monitoring" / "data_patrol.py"), run_name="__main__")
