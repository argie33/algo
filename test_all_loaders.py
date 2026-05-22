#!/usr/bin/env python3
"""Test all loaders for errors and print status."""
import sys
import subprocess
from pathlib import Path

loader_dir = Path("loaders")
loaders = sorted([f.stem for f in loader_dir.glob("load*.py")] + [f.stem for f in loader_dir.glob("loadapproach*.py")])

print(f"\n{'LOADER':<40} {'STATUS':<15} {'ERROR':<60}")
print("=" * 115)

for loader in loaders:
    loader_py = loader_dir / f"{loader}.py"
    if not loader_py.exists():
        continue

    # Test with --help to see if it runs without errors
    result = subprocess.run(
        [sys.executable, str(loader_py), "--help"],
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode == 0:
        status = "✅ OK"
        error = ""
    else:
        status = "❌ ERROR"
        # Get first line of error
        error = (result.stderr.split("\n")[0][:60] if result.stderr else result.stdout.split("\n")[0][:60])

    print(f"{loader:<40} {status:<15} {error:<60}")

print("\n" + "=" * 115)
