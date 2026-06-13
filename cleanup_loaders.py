#!/usr/bin/env python3
import os
import re
from pathlib import Path

def clean_loader_file(file_path):
    """Remove sys.path manipulation and add setup_imports."""
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    original_content = content

    # Remove all sys.path.insert calls (handle both \n and \r\n line endings)
    # Match the entire line containing sys.path.insert to avoid issues with nested parentheses
    content = re.sub(r".*sys\.path\.insert.*\r?\n", "", content, flags=re.MULTILINE)

    # Remove "from pathlib import Path" if not used elsewhere
    if "Path(" not in content and "from pathlib import Path" in original_content:
        content = re.sub(r"from pathlib import Path\s*\r?\n", "", content)

    # Remove "import sys" if not used elsewhere
    if re.search(r"\bsys\.", content) is None and "import sys" in original_content:
        content = re.sub(r"import sys\s*\r?\n", "", content)

    # Add setup_imports if not already there
    if "from loaders.loader_helper import setup_imports" not in content:
        # Try to find a good place to add it - after shebang and docstring
        lines = content.split('\n')
        insert_index = 0

        # Skip shebang
        for i, line in enumerate(lines):
            if line.startswith('#!'):
                insert_index = i + 1
                break

        # Skip docstring
        in_docstring = False
        for i in range(insert_index, len(lines)):
            line = lines[i]
            if '"""' in line or "'''" in line:
                if in_docstring:
                    insert_index = i + 1
                    break
                else:
                    in_docstring = True

        # Insert the import and setup call
        setup_code = [
            "from loaders.loader_helper import setup_imports",
            "setup_imports()",
            ""
        ]

        for j, code_line in enumerate(setup_code):
            lines.insert(insert_index + j, code_line)

        content = '\n'.join(lines)

    # Clean up extra blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)

    # Only write if content changed
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

# Find all loader files
loaders_dir = Path("loaders")
loader_files = list(loaders_dir.glob("load_*.py")) + list(loaders_dir.glob("compute_*.py"))

updated_count = 0
for file_path in loader_files:
    if clean_loader_file(file_path):
        print(f"Updated: {file_path.name}")
        updated_count += 1

print(f"\nTotal updated: {updated_count}")
