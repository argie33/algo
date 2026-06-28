#!/usr/bin/env python3
"""Entry point for Algo Orchestrator - delegates to orchestration module.

This file exists to maintain compatibility with ECS task definition references.
The actual orchestrator implementation is in algo/orchestration/orchestrator.py
Runs orchestrator as a subprocess to maintain proper module initialization.
"""

import subprocess
import sys

if __name__ == "__main__":
    # Run orchestrator.py as a subprocess to avoid import issues
    # Pass through all command-line arguments
    import os
    cwd = os.getenv("APP_ROOT", "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    result = subprocess.run(
        [sys.executable, "-m", "algo.orchestration.orchestrator", *sys.argv[1:]],
        cwd=cwd,
        check=False,
    )
    sys.exit(result.returncode)
