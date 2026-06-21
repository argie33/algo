#!/usr/bin/env python3
import pathlib

executor_file = pathlib.Path('algo/trading/executor.py')
content = executor_file.read_bytes()

# These are UTF-8 encoded arrow characters that got corrupted
# The pattern is usually: something → something (where → is U+2192)
# When corrupted it appears as â†' in UTF-8

# Replace the corrupted UTF-8 arrows with regular arrows or dashes
content = content.replace(b'\xE2\x86\x92', b'->')  # â†' becomes ->
content = content.replace(b'\xe2\x80\x9c', b'"')    # â€œ becomes "
content = content.replace(b'\xe2\x80\x9d', b'"')    # â€" becomes "
content = content.replace(b'\xe2\x80\x98', b"'")    # â€˜ becomes '
content = content.replace(b'\xe2\x80\x99', b"'")    # â€™ becomes '
content = content.replace(b'\xe2\x80\x93', b'-')    # â€" becomes -
content = content.replace(b'\xe2\x80\x94', b'-')    # â€" becomes -

executor_file.write_bytes(content)
print("Fixed encoding issues in executor.py")
