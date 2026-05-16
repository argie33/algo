#!/usr/bin/env python3
import os
import re

# Map of replacements - be careful to only replace in JSX text content
replacements = {
    r"We're": "We&apos;re",
    r"doesn't": "doesn&apos;t",
    r"can't": "can&apos;t",
    r"it's": "it&apos;s",
    r"that's": "that&apos;s",
    r"won't": "won&apos;t",
    r"they're": "they&apos;re",
    r"let's": "let&apos;s",
    r"I'm": "I&apos;m",
    r"isn't": "isn&apos;t",
    r"you're": "you&apos;re",
    r"what's": "what&apos;s",
    r"I've": "I&apos;ve",
    r"we're": "we&apos;re",
    r"'re": "&apos;re",  # Generic 're replacements
    r"'ll": "&apos;ll",  # Will contractions
    r"'ve": "&apos;ve",  # Have contractions
    r"'d": "&apos;d",    # Would/had contractions
}

def fix_file(filepath):
    """Fix unescaped entities in a single file"""
    try:
        with open(filepath, 'r', encoding='utf8') as f:
            content = f.read()

        original_content = content

        # Apply replacements
        for old, new in replacements.items():
            content = content.replace(old, new)

        # Write back if changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    src_dir = r"C:\Users\arger\code\algo\webapp\frontend\src"
    fixed_count = 0

    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith(('.jsx', '.js')):
                filepath = os.path.join(root, file)
                if fix_file(filepath):
                    fixed_count += 1
                    print(f"[+] Fixed: {os.path.relpath(filepath)}")

    print(f"\nFixed {fixed_count} files total")

if __name__ == '__main__':
    main()
