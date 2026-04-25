#!/usr/bin/env python3
"""
Parallel Loader Runner - Execute loaders with offset/limit parallelism
Splits the 4,969 symbols into chunks and runs them in parallel to avoid timeouts
"""

import subprocess
import time
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Load environment
env_file = Path('.') / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Configuration
PARALLEL_CHUNKS = 4  # Split symbols into 4 parallel loads
SYMBOLS_PER_CHUNK = 1250  # ~4970 symbols / 4 = ~1250 per chunk

# Loaders that support offset/limit parallelism
PARALLEL_LOADERS = [
    {
        'name': 'Daily Company Data',
        'script': 'loaddailycompanydata.py',
        'supports_parallel': True
    }
]

def run_loader_chunk(script, offset, limit, chunk_num):
    """Run a single loader with offset/limit"""
    cmd = ['python3', script, '--offset', str(offset), '--limit', str(limit)]
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Chunk {chunk_num}: Running {script} (offset={offset}, limit={limit})")

    try:
        result = subprocess.run(cmd, timeout=1800, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[✓] Chunk {chunk_num} completed successfully")
            return True
        else:
            print(f"[✗] Chunk {chunk_num} failed with return code {result.returncode}")
            if result.stderr:
                print(f"    Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"[✗] Chunk {chunk_num} timed out after 30 minutes")
        return False
    except Exception as e:
        print(f"[✗] Chunk {chunk_num} error: {e}")
        return False

def run_parallel_load(script):
    """Run a loader in parallel chunks"""
    print(f"\n{'='*60}")
    print(f"Running {script} in parallel ({PARALLEL_CHUNKS} chunks)")
    print(f"{'='*60}")

    processes = []
    results = []

    # Start all chunks
    for chunk_num in range(PARALLEL_CHUNKS):
        offset = chunk_num * SYMBOLS_PER_CHUNK
        limit = SYMBOLS_PER_CHUNK

        success = run_loader_chunk(script, offset, limit, chunk_num + 1)
        results.append((chunk_num + 1, success))

        # Stagger the starts slightly
        time.sleep(2)

    # Report results
    print(f"\n{'='*60}")
    print("PARALLEL LOAD RESULTS")
    print(f"{'='*60}")

    completed = sum(1 for _, success in results if success)
    print(f"Completed: {completed}/{PARALLEL_CHUNKS} chunks")

    for chunk_num, success in results:
        status = "[✓] PASS" if success else "[✗] FAIL"
        print(f"  Chunk {chunk_num}: {status}")

    return completed == PARALLEL_CHUNKS

if __name__ == '__main__':
    print("\n╔════════════════════════════════════════════════════════╗")
    print("║  Parallel Loader Runner                              ║")
    print("║  Loads data in parallel chunks to avoid timeouts     ║")
    print("╚════════════════════════════════════════════════════════╝\n")

    # Run each parallel-capable loader
    all_success = True
    for loader in PARALLEL_LOADERS:
        if not run_parallel_load(loader['script']):
            all_success = False

    print(f"\n{'='*60}")
    if all_success:
        print("✓ All parallel loads completed successfully")
    else:
        print("✗ Some loads failed - check logs above")
    print(f"{'='*60}\n")

    sys.exit(0 if all_success else 1)
