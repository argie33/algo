#!/usr/bin/env python3

# Read the file as UTF-8 with error handling
with open('tools/dashboard/dashboard.py', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Process line by line
output = []
for i, line in enumerate(lines):
    # Find problematic f-string patterns and replace the entire f-string expression
    # Look for patterns like f"...{'...' * ...}..."
    if "f\"" in line and "{''" in line:
        # Replace the corrupted string expressions
        # The pattern is: {'...' * something} where ... is corrupted
        # Replace with {'#' * something} or {'-' * something}

        # Simple approach: replace common patterns
        line = line.replace("{'&#", "{'#")  # fix partial corruption
        line = line.replace("'&#", "'#")
        line = line.replace("'&#", "'#")

    output.append(line)

# Write back
with open('tools/dashboard/dashboard.py', 'w', encoding='utf-8') as f:
    f.writelines(output)

print('Fixed f-string expressions')
