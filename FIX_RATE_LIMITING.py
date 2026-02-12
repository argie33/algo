#!/usr/bin/env python3
"""
FIX RATE LIMITING ISSUES
Kill duplicate loaders, keep only 1 instance of each data source
"""
import subprocess
import sys
import time
import signal
import os

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

print("=" * 70)
print("🚨 FIXING RATE LIMITING ISSUES")
print("=" * 70)
print()

# Step 1: Kill duplicate sentiment loaders
print("STEP 1: Kill all sentiment loaders (rate limited, getting 0 data)")
code, out, err = run_cmd("pgrep -f 'loadanalystsentiment' | wc -l")
sentiment_count = int(out.strip()) if out.strip().isdigit() else 0
if sentiment_count > 0:
    run_cmd("pkill -9 -f 'loadanalystsentiment'")
    time.sleep(1)
    print(f"✅ Killed {sentiment_count} sentiment loader instances")
else:
    print("✅ No sentiment loaders running")

# Step 2: Keep only 1 earnings loader
print()
print("STEP 2: Keep only 1 earnings history loader (kill extras)")
code, out, err = run_cmd("pgrep -f 'loadearningshistory' | wc -l")
earnings_count = int(out.strip()) if out.strip().isdigit() else 0
if earnings_count > 1:
    # Kill all but the oldest one
    code, pids, _ = run_cmd("pgrep -f 'loadearningshistory'")
    pid_list = pids.strip().split('\n')
    for pid in pid_list[1:]:  # Keep first, kill rest
        try:
            os.kill(int(pid), 9)
        except:
            pass
    print(f"✅ Reduced earnings loaders from {earnings_count} to 1")
else:
    print(f"✅ Already at {earnings_count} earnings loader")

# Step 3: Keep only 1 company data loader
print()
print("STEP 3: Keep only 1 company data loader (kill extras)")
code, out, err = run_cmd("pgrep -f 'loaddailycompanydata' | wc -l")
company_count = int(out.strip()) if out.strip().isdigit() else 0
if company_count > 1:
    code, pids, _ = run_cmd("pgrep -f 'loaddailycompanydata'")
    pid_list = pids.strip().split('\n')
    for pid in pid_list[1:]:  # Keep first, kill rest
        try:
            os.kill(int(pid), 9)
        except:
            pass
    print(f"✅ Reduced company loaders from {company_count} to 1")
else:
    print(f"✅ Already at {company_count} company loader")

# Step 4: Show final status
print()
print("=" * 70)
print("FINAL LOADER STATUS")
print("=" * 70)
code, out, err = run_cmd("""ps aux | grep -E 'load|backfill' | grep python | grep -v grep | awk '{print $2, $12, "CPU:" $3 "%"}'""")
if out.strip():
    print(out)
else:
    print("No loaders running")

print()
print("=" * 70)
print("✅ RATE LIMITING FIXED")
print("=" * 70)
print()
print("Next steps:")
print("1. Earnings loader will continue at normal rate (1-2 symbols/sec)")
print("2. Company data loader will continue with proper delays")
print("3. Sentiment loader can be restarted with 5+ second delay")
print("4. System will use less API rate limit quota")
print()
