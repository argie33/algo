#!/usr/bin/env python3
"""
Mass fix script to add sslmode='disable' to all data loader psycopg2.connect calls
"""
import os
import re
import glob

def fix_ssl_in_file(filepath):
    """Fix SSL configuration in a single Python file"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # First, fix existing sslmode='require' to sslmode='disable'
        content = re.sub(r"sslmode\s*=\s*['\"]require['\"]", "sslmode='disable'", content)
        content = re.sub(r"sslmode\s*=\s*['\"]prefer['\"]", "sslmode='disable'", content)
        content = re.sub(r"sslmode\s*=\s*['\"]allow['\"]", "sslmode='disable'", content)
        
        # Then, add sslmode='disable' to psycopg2.connect calls that don't have sslmode
        pattern = r'(psycopg2\.connect\(\s*[^)]*?)\)'
        
        def replacement(match):
            connect_call = match.group(1)
            if 'sslmode' in connect_call:
                return match.group(0)  # Already has sslmode, don't add another
            
            # Add sslmode='disable' before the closing parenthesis
            return connect_call + ",\n            sslmode='disable'\n        )"
        
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        if content != original_content:
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"✅ Fixed: {filepath}")
            return True
        else:
            print(f"⏭️  Skip: {filepath} (no changes needed)")
            return False
            
    except Exception as e:
        print(f"❌ Error fixing {filepath}: {e}")
        return False

def main():
    """Fix SSL in all Python loader files"""
    print("🔧 Starting mass SSL fix for data loaders...")
    
    # Find all Python loader files
    loader_files = glob.glob('/home/stocks/algo/load*.py')
    
    fixed_count = 0
    total_count = len(loader_files)
    
    for filepath in loader_files:
        if fix_ssl_in_file(filepath):
            fixed_count += 1
    
    print(f"\n📊 Summary:")
    print(f"   Total files: {total_count}")
    print(f"   Fixed files: {fixed_count}")
    print(f"   Skipped files: {total_count - fixed_count}")
    print(f"\n✅ Mass SSL fix complete!")

if __name__ == "__main__":
    main()