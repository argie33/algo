#!/bin/bash
# Run AWS database fix now - copy/paste this entire command in AWS CloudShell

cd algo && python3 scripts/aws_complete_database_fix.py && echo "
=== FIX COMPLETE ===" && echo "
Now restart the system:
  pkill -9 python
  python -m dashboard -w
" && echo "Orchestrator will resume on schedule (2:15 AM or 4:05 PM ET)"
