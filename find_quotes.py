#!/usr/bin/env python3
import pathlib

executor_file = pathlib.Path('algo/trading/executor.py')
content = executor_file.read_text(encoding='utf-8')

# Find lines with smart quotes or other non-standard characters
lines = content.split('\n')
smart_quote_chars = {'“', '”', '‘', '’', '„', '‟'}

for i, line in enumerate(lines, 1):
    for char in smart_quote_chars:
        if char in line:
            print(f"Line {i} contains smart quote: {repr(line[:100])}")
            break

# Also find invalid UTF-8 patterns
import re
for i, line in enumerate(lines, 1):
    if re.search(rb'[\x80-\xFF][\x80-\xFF]', line.encode('utf-8')):
        print(f"Line {i} may have encoding issues: {repr(line[:100])}")
