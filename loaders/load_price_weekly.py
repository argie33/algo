#!/usr/bin/env python3
"""Load weekly price data - wrapper around consolidated price loader."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import subprocess

def main():
    """Delegate to consolidated price loader with 1wk interval."""
    import argparse
    from config.env_loader import load_env

    load_env()
    parser = argparse.ArgumentParser(description='Load weekly price data')
    parser.add_argument('--symbols', help='Comma-separated symbols')
    parser.add_argument('--parallelism', type=int, default=4, help='Parallel workers')
    args = parser.parse_args()

    cmd = ['python3', 'loaders/loadpricedaily.py', '--interval', '1wk', '--asset-class', 'stock']
    if args.symbols:
        cmd.extend(['--symbols', args.symbols])
    cmd.extend(['--parallelism', str(args.parallelism)])

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode

if __name__ == '__main__':
    sys.exit(main())
