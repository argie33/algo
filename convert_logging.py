#!/usr/bin/env python3
"""
Safely convert print() statements to logger calls in a Python file.
Tests import after conversion to ensure no syntax errors.
"""

import sys
import re
import tempfile
import shutil
import subprocess

def convert_file_logging(filepath):
    """Convert print statements to logging in a single file."""

    print(f"\n{'='*70}")
    print(f"Converting: {filepath}")
    print(f"{'='*70}")

    # Read the file
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        original_content = content

    # Check if logging is already imported
    has_logging_import = 'import logging' in content
    has_logger_setup = "logger = logging.getLogger" in content

    lines = content.split('\n')

    # Find where to insert imports/logger (after shebang and module docstring)
    import_insert_pos = 0
    i = 0

    # Skip shebang
    if lines[0].startswith('#!'):
        i = 1

    # Skip module docstring
    if i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = '"""' if '"""' in lines[i] else "'''"
            i += 1
            # Find closing docstring
            while i < len(lines) and quote not in lines[i]:
                i += 1
            if i < len(lines):
                i += 1  # Skip the closing line

    # Find the end of all imports
    import_insert_pos = i
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('#'):
            i += 1
            continue
        if line.startswith('import ') or line.startswith('from '):
            import_insert_pos = i + 1
            i += 1
            continue
        else:
            break

    # Add logging import if missing
    if not has_logging_import:
        lines.insert(import_insert_pos, 'import logging')
        content = '\n'.join(lines)
        print("[+] Added: import logging")
        import_insert_pos += 1

    # Add logger setup after imports
    if not has_logger_setup:
        # Add blank line and logger setup
        lines.insert(import_insert_pos, '')
        lines.insert(import_insert_pos + 1, "logger = logging.getLogger(__name__)")
        content = '\n'.join(lines)
        print("[+] Added: logger = logging.getLogger(__name__)")

    # Now convert print statements
    # This is tricky - we need to preserve formatting and log level
    conversion_count = 0
    lines = content.split('\n')

    for i, line in enumerate(lines):
        # Skip lines that are comments or in docstrings
        stripped = line.strip()
        if stripped.startswith('#'):
            continue

        # Skip docstrings (very basic check)
        if '"""' in line or "'''" in line:
            continue

        # Look for print( calls
        if 'print(' in line:
            # Preserve indentation
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent

            # Extract what's being printed
            # Try to replace print(...) with logger.info(...)
            # This is a simplified approach - assumes single-line prints

            # Match print(...) patterns
            # Look for print(f"...") or print("...") or print(variable)
            match = re.search(r'print\((.*)\)\s*$', line)
            if match:
                content_to_log = match.group(1)

                # Determine log level based on content
                log_level = 'info'
                content_lower = content_to_log.lower()
                if 'error' in content_lower or 'failed' in content_lower or 'fail' in content_lower:
                    log_level = 'error'
                elif 'warn' in content_lower or 'warning' in content_lower:
                    log_level = 'warning'
                elif 'debug' in content_lower:
                    log_level = 'debug'

                # Build the replacement
                new_line = f'{indent_str}logger.{log_level}({content_to_log})'
                lines[i] = new_line
                conversion_count += 1
                print(f"[*] Line {i+1}: Converted print() to logger.{log_level}()")

    content = '\n'.join(lines)

    if conversion_count == 0:
        print("[-] No print statements found or converted")
        return False

    print(f"\n[+] Converted {conversion_count} print statements")

    # Write to temp file first
    temp_fd, temp_path = tempfile.mkstemp(suffix='.py')
    try:
        with open(temp_fd, 'w', encoding='utf-8') as f:
            f.write(content)

        # Test import
        print("\n[*] Testing import...")
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile', temp_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            print(f"[!] IMPORT FAILED:\n{result.stderr}")
            print("[!] Reverting changes...")
            return False

        print("[+] Import test PASSED")

        # All good - write to actual file
        shutil.copy(temp_path, filepath)
        print(f"[+] File updated: {filepath}")
        return True

    except Exception as e:
        print(f"[!] ERROR: {e}")
        return False
    finally:
        import os
        try:
            os.unlink(temp_path)
        except:
            pass

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: convert_logging.py <filepath> [filepath2] ...")
        sys.exit(1)

    failed = []
    for filepath in sys.argv[1:]:
        try:
            success = convert_file_logging(filepath)
            if not success:
                failed.append(filepath)
        except Exception as e:
            print(f"[!] Exception processing {filepath}: {e}")
            failed.append(filepath)

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Processed: {len(sys.argv)-1} files")
    if failed:
        print(f"Failed: {len(failed)}")
        for f in failed:
            print(f"  - {f}")
    else:
        print("All files converted successfully!")
