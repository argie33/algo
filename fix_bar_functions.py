#!/usr/bin/env python3
import re

# Read the file
with open('tools/dashboard/dashboard.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find and replace the bar function return statements
# They have patterns like: return f"[{...}]{...charblock... * ...}[/]..."
# We want to replace corrupted character blocks with ASCII

# Pattern: looks for lines with return f" followed by various content with * operators
# indicating repetition of block characters

# Simple approach: replace any f-string that has {'...' * pattern}
# with {'#' * pattern} or {'-' * pattern}

# Find all lines that are problematic (based on function names and content)
lines = content.split('\n')
output_lines = []

for i, line in enumerate(lines):
    # If this is a return statement in a bar function
    if 'return f"' in line and ('* f' in line or '* width' in line or '* fg' in line):
        # This is a bar function return statement
        # Replace any problematic string expressions

        # Replace patterns like {'corrupted' * x} with {'#' * x}
        # We can identify these by looking for quotes followed by *
        import re
        # Match {' anything '}
        pattern = r"\{\'[^\']*\' \* "
        matches = list(re.finditer(pattern, line))

        if matches:
            # For each match, check if it contains corrupted bytes
            new_line = line
            for match in reversed(matches):  # reverse to maintain indices
                start, end = match.span()
                content_part = line[start:end]

                # Determine replacement: if it ends with - or looks like a shade/dash char, use -
                # Otherwise use #
                if '-' in content_part or 'dim' in lines[max(0, i-1):i+2].__str__():
                    replacement = "{'-' * "
                else:
                    replacement = "{'#' * "

                new_line = new_line[:start] + replacement + new_line[end:]

            line = new_line

    output_lines.append(line)

# Join back
result = '\n'.join(output_lines)

# Also do a brute force fix for known patterns
replacements = [
    (r"f\"[^\"]*\{\'.*?\' \*", "f\"[...]{\'#\' *"),  # catch all with #
]

# Write back
with open('tools/dashboard/dashboard.py', 'w', encoding='utf-8') as f:
    f.write(result)

print('Fixed bar function f-strings')
