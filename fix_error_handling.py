#!/usr/bin/env python3
"""
Systematic Error Handling Fixer for Lambda API

This script identifies and fixes all locations where we return 200 OK with
empty data when exceptions occur. Instead, we should return proper error codes.

Patterns to fix:
    return json_response(200, {})          # on exception
    return json_response(200, [])          # on exception
    return json_response(200, {'data': []})
"""

import re
import sys

# Read the Lambda function
with open('lambda/api/lambda_function.py', 'r') as f:
    content = f.read()

# Track changes
changes = 0
lines = content.split('\n')
in_except_block = False
except_indent = 0
fixes_needed = []

for i, line in enumerate(lines, 1):
    # Detect except blocks
    if 'except Exception as e:' in line:
        in_except_block = True
        except_indent = len(line) - len(line.lstrip())
        current_except_line = i

    # Check if we're still in the except block
    elif in_except_block:
        current_indent = len(line) - len(line.lstrip()) if line.strip() else 999

        # If we've dedented back out, except block is over
        if line.strip() and current_indent <= except_indent and 'except' not in line:
            in_except_block = False

        # Look for problematic returns in except blocks
        if in_except_block and ('return json_response(200, {})' in line or
                                'return json_response(200, [])' in line or
                                'return json_response(200,' in line):
            fixes_needed.append({
                'line_num': i,
                'code': line.strip(),
                'except_line': current_except_line
            })

print(f"\n{'='*80}")
print(f"ERROR HANDLING AUDIT REPORT")
print(f"{'='*80}\n")

print(f"Found {len(fixes_needed)} locations returning 200 OK on exceptions:\n")

for fix in fixes_needed:
    print(f"  Line {fix['line_num']}: {fix['code'][:70]}")

print(f"\n{'='*80}")
print(f"FIXES NEEDED")
print(f"{'='*80}\n")

print("""
To fix systematically, replace patterns:

PATTERN 1: return json_response(200, {})
REPLACE WITH: return error_response(500, 'internal_error', f'Handler error: {str(e)}')

PATTERN 2: return json_response(200, [])
REPLACE WITH: return error_response(500, 'internal_error', f'Handler error: {str(e)}')

PATTERN 3: return json_response(200, {'data': []})
REPLACE WITH: return error_response(500, 'internal_error', f'Handler error: {str(e)}')

NOTE: For some cases where empty data is acceptable (not an error),
returning 200 OK is fine. Use judgment based on context.

Acceptable cases:
  - No data found for a valid query (not an error)
  - Empty result set is expected behavior

Unacceptable cases:
  - Database query threw exception
  - Missing required parameters
  - Invalid endpoint path
  - Connection failures
""")

print(f"\nRECOMMENDED ACTION:")
print(f"  1. Manually review each of the {len(fixes_needed)} locations")
print(f"  2. Determine if empty response is acceptable or an error")
print(f"  3. Replace with error_response() for actual errors")
print(f"  4. Keep json_response(200, ...) for legitimate empty results\n")

if len(fixes_needed) > 0:
    sys.exit(1)  # Indicate fixes are needed
