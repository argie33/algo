#!/usr/bin/env python3
"""Run all loaders with limited scope and report status."""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

loader_dir = Path("loaders")
loaders = [f for f in loader_dir.glob("*.py") if f.name not in ["__init__.py", "technical_indicators.py", "algo_continuous_monitor.py"]]
loaders = sorted(set(loaders))

print(f"\n{'='*100}")
print(f"{'LOADER':<40} {'STATUS':<10} {'NOTES':<50}")
print(f"{'='*100}")

working = []
failing = []
errors = {}

for loader in loaders:
    name = loader.name
    try:
        # Run with minimal symbols for speed
        result = subprocess.run(
            [sys.executable, str(loader), "--symbols", "AAPL", "--parallelism", "1"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Parse output for status
        output = result.stderr + result.stdout

        if result.returncode == 0:
            status = "OK"
            if "inserted=" in output:
                # Extract inserted count
                for line in output.split("\n"):
                    if "inserted=" in line:
                        notes = line.strip()[:50]
                        break
                else:
                    notes = "Completed"
            else:
                notes = "Completed"
            working.append(name)
        else:
            status = "FAIL"
            # Get error from output
            for line in output.split("\n"):
                if "error" in line.lower() or "exception" in line.lower():
                    notes = line[:50]
                    break
            else:
                notes = output.split("\n")[-2][:50] if output else "Unknown error"
            failing.append(name)
            errors[name] = notes

        print(f"{name:<40} {status:<10} {notes:<50}")

    except subprocess.TimeoutExpired:
        print(f"{name:<40} {'TIMEOUT':<10} {'Took > 30s':<50}")
        failing.append(name)
    except Exception as e:
        print(f"{name:<40} {'ERROR':<10} {str(e)[:50]:<50}")
        failing.append(name)

print(f"{'='*100}")
print(f"\nSUMMARY: {len(working)} working, {len(failing)} failing\n")

if failing:
    print("FAILING LOADERS:")
    for name in failing:
        error = errors.get(name, "Unknown error")
        print(f"  - {name}: {error}")
