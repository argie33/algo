#!/usr/bin/env python3
"""Run dashboard - no -m flag needed. Defaults to AWS mode."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard.dashboard import main
if __name__ == "__main__":
    main()
