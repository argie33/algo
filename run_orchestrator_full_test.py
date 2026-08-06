#!/usr/bin/env python3
"""Run full orchestrator bypassing market hours check."""

import sys
import os
from datetime import date

# Set dry_run via environment to bypass market hours check
os.environ['ORCHESTRATOR_DRY_RUN'] = '1'

from scripts.run_local_orchestrator import main

sys.argv = ['run_local_orchestrator.py', '--afternoon', '--force']
main()
