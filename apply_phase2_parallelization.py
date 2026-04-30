#!/usr/bin/env python3
"""
Phase 2 Parallelization Patcher
Applies ThreadPoolExecutor pattern to Phase 2 loaders
"""

import os
import re

PHASE2_LOADERS = [
    'loadsectors.py',
    'loadecondata.py', 
    'loadfactormetrics.py',
    'loadstockscores.py',
    'loadmarket.py'
]

def add_parallel_imports(file_path):
    """Add ThreadPoolExecutor imports if not present"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    if 'from concurrent.futures import ThreadPoolExecutor' in content:
        print(f"  [SKIP] {file_path} - imports already present")
        return
    
    # Add after other imports
    import_section = re.search(r'(import.*?\n)+', content)
    if import_section:
        end_pos = import_section.end()
        new_imports = "from concurrent.futures import ThreadPoolExecutor, as_completed\nimport time\n"
        content = content[:end_pos] + new_imports + content[end_pos:]
        
        with open(file_path, 'w') as f:
            f.write(content)
        print(f"  [OK] Added parallel imports to {file_path}")

print("[*] PHASE 2 PARALLELIZATION SETUP")
print("=" * 70)
print()

for loader in PHASE2_LOADERS:
    if os.path.exists(loader):
        print(f"Processing {loader}...")
        add_parallel_imports(loader)
    else:
        print(f"  [SKIP] {loader} - file not found")

print()
print("[OK] Phase 2 imports configured")
print("Next: Apply parallel worker pattern to each loader")

