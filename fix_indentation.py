#!/usr/bin/env python3
"""Fix indentation in algo.py routes file - comprehensive approach."""

file_path = "lambda/api/routes/algo.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Split into lines but preserve line endings
lines = content.split('\n')

# Fix the indentation: for lines that are part of _dispatch function body (after "def _dispatch")
# they all have 4 extra spaces that need to be removed

fixed_lines = []
in_dispatch_function = False
found_dispatch_def = False

for i, line in enumerate(lines):
    # Check if this is the _dispatch function definition
    if line.startswith("def _dispatch("):
        found_dispatch_def = True
        in_dispatch_function = True
        fixed_lines.append(line)
    # Check if we've reached the next top-level function definition (next "def" with no leading spaces)
    elif found_dispatch_def and in_dispatch_function and line.startswith("def ") and not line.startswith("    "):
        in_dispatch_function = False
        fixed_lines.append(line)
    # For lines within _dispatch, remove 4 leading spaces (all content inside _dispatch has 8 extra spaces)
    elif in_dispatch_function and line and line[0] == ' ':
        # Count leading spaces
        leading_spaces = len(line) - len(line.lstrip(' '))
        # If this line has at least 8 leading spaces, remove 4 (the extra indentation in _dispatch)
        if leading_spaces >= 8:
            fixed_line = line[4:]  # Remove 4 spaces
            fixed_lines.append(fixed_line)
        else:
            # Line has less than 8 spaces - don't modify
            fixed_lines.append(line)
    else:
        fixed_lines.append(line)

# Write back, preserving the original line structure
with open(file_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))

print(f"Fixed indentation in {file_path}")
