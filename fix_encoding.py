#!/usr/bin/env python3

# Read the file
with open('algo/trading/exit_engine.py', 'rb') as f:
    content = f.read()

# The file contains mojibake: UTF-8 smart quote bytes that were decoded as Latin-1
# and then re-encoded as UTF-8, creating double-encoded sequences.
# Example: â€" is C3 A2 C2 80 C2 93 (the bytes for "â€"" in UTF-8)

fixes = {
    # Em dash mojibake variations (includes variants like â€˜, etc)
    b'\xc3\xa2\xc2\x80\xc2\x93': b'--',
    b'\xc3\xa2\xc2\x80\xc2\x94': b'--',
    b'\xc3\xa2\xe2\x80\xa0': b"'",  # Different variant
    b'\xc3\xa2\x80\x99': b"'",       # Another variant
    # Arrow mojibake
    b'\xc3\xa2\xc2\x86\xc2\x92': b'->',
    # Quote mojibake
    b'\xc3\xa2\xc2\x80\xc2\x9c': b'"',   # left double
    b'\xc3\xa2\xc2\x80\xc2\x9d': b'"',   # right double
    b'\xc3\xa2\xc2\x80\xc2\x98': b"'",   # left single
    b'\xc3\xa2\xc2\x80\xc2\x99': b"'",   # right single
}

for bad, good in fixes.items():
    content = content.replace(bad, good)

# Write back
with open('algo/trading/exit_engine.py', 'wb') as f:
    f.write(content)

print('Fixed mojibake encoding')
