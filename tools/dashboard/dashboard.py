#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard - Delegates to main.py

For AWS mode with Cognito authentication, use:
  python tools/dashboard/main.py

For documentation on setup, see: tools/dashboard/COGNITO_SETUP.md
"""

import os
import sys
import subprocess

# Redirect to main.py which has full Cognito support
script_dir = os.path.dirname(os.path.abspath(__file__))
main_py = os.path.join(script_dir, "main.py")

sys.exit(subprocess.call([sys.executable, main_py] + sys.argv[1:]))
