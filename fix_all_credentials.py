#!/usr/bin/env python3
"""Fix all unsafe credential_manager calls."""
import os
import re
from pathlib import Path

ROOT = Path('.')
SKIP = {'credential_manager.py', 'credential_helper.py', 'fix_all_credentials.py'}

fixed = 0
for py_file in sorted(ROOT.glob('**/*.py')):
    if py_file.name in SKIP or '.git' in py_file.parts or '__pycache__' in py_file.parts:
        continue
    
    try:
        content = py_file.read_text()
        original = content
        
        if 'credential_manager.get_db_credentials()' not in content:
            continue
        
        # Replace pattern 1: credential_manager.get_db_credentials()["password"]
        content = re.sub(
            r'credential_manager\.get_db_credentials\(\)\["password"\]',
            'get_db_password()',
            content
        )
        
        # Replace pattern 2: credential_manager.get_db_credentials()
        content = re.sub(
            r'credential_manager\.get_db_credentials\(\)',
            'get_db_config()',
            content
        )
        
        if content != original:
            # Add import if needed
            if 'from credential_helper import' not in content:
                lines = content.split('\n')
                import_idx = 0
                for i, line in enumerate(lines):
                    if i < 20 and (line.startswith('import ') or line.startswith('from ')):
                        import_idx = i + 1
                lines.insert(import_idx, 'from credential_helper import get_db_password, get_db_config')
                content = '\n'.join(lines)
            
            py_file.write_text(content)
            print(f"[OK] {py_file.name}")
            fixed += 1
    except Exception as e:
        print(f"[SKIP] {py_file.name}: {e}")

print(f"\nFixed {fixed} files")
