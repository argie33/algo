import re

# Read the file
with open('routes/market.js', 'r') as f:
    content = f.read()

# Remove duplicate const FALLBACK_SECTORS declarations but keep the references
# Find all occurrences of const FALLBACK_SECTORS = [ ... ]; and remove them except the first one
lines = content.split('\n')
new_lines = []
inside_fallback_const = False
skip_lines = False
first_declaration_kept = False

for i, line in enumerate(lines):
    # Check if this line starts a FALLBACK_SECTORS const declaration (not the first one)
    if 'const FALLBACK_SECTORS = [' in line and first_declaration_kept:
        skip_lines = True
        inside_fallback_const = True
        continue
    
    # Track the first declaration to keep it
    if 'const FALLBACK_SECTORS = [' in line and not first_declaration_kept:
        first_declaration_kept = True
    
    # If we're inside a fallback const declaration, skip until we find the closing bracket
    if inside_fallback_const:
        if line.strip() == '];':
            inside_fallback_const = False
            skip_lines = False
        continue
    
    # Keep the line if we're not skipping
    if not skip_lines:
        new_lines.append(line)

# Write the modified content back
with open('routes/market.js', 'w') as f:
    f.write('\n'.join(new_lines))

print("Removed duplicate FALLBACK_SECTORS declarations")
