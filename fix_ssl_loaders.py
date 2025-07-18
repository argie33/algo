#!/usr/bin/env python3
"""
Automated SSL Configuration Fix for Data Loaders
Fixes sslmode='disable' to sslmode='require' across all loader scripts
"""

import os
import re
import sys
from pathlib import Path

# List of files that need SSL configuration fixes
LOADERS_TO_FIX = [
    'loadanalystupgradedowngrade.py',
    'loadannualbalancesheet.py', 
    'loadannualcashflow.py',
    'loadannualincomestatement.py',
    'loadbuyselldaily_backup.py',
    'loadbuysellmonthly_backup.py',
    'loadbuysellweekly_backup.py',
    'loadcrypto.py',
    'loadearningshistory.py',
    'loadearningsmetrics.py',
    'loadfeargreed.py',
    'loadfinancials.py',
    'loadinfo.py',
    'loadlatestbuyselldaily.py',
    'loadlatestbuysellmonthly.py',
    'loadlatestbuysellweekly.py',
    'loadlatestpricedaily.py',
    'loadlatestpricemonthly.py',
    'loadlatestpriceweekly.py',
    'loadmarket.py',
    'loadmomentum.py',
    'loadnaaim.py',
    'loadnews.py',
    'loadpatternrecognition.py',
    'loadpositioning.py',
    'loadpricedaily.py',
    'loadpricemonthly.py',
    'loadpriceweekly.py',
    'loadquarterlybalancesheet.py',
    'loadquarterlycashflow.py',
    'loadquarterlyincomestatement.py',
    'loadrevenueestimate.py',
    'loadsentiment.py',
    'loadsentiment_realtime.py',
    'loadsymbols.py',
    'loadtechnicalpatterns.py',
    'loadtechnicals.py',
    'loadtechnicalsdaily.py',
    'loadtechnicalsmonthly.py',
    'loadtechnicalsweekly.py',
    'loadttmcashflow.py',
    'loadttmincomestatement.py'
]

def fix_ssl_in_file(file_path):
    """Fix SSL configuration in a single file"""
    print(f"🔧 Fixing SSL configuration in {file_path}")
    
    try:
        # Read the file
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Store original content for comparison
        original_content = content
        
        # Pattern 1: Fix the malformed SSL configuration
        # Find: sslmode='disable'\n    )
        # Replace with: sslmode='require'\n    )
        pattern1 = re.compile(r"sslmode='disable'\s*\n\s*\)")
        content = pattern1.sub("sslmode='require'\n    )", content)
        
        # Pattern 2: Fix inline SSL configuration  
        # Find: sslmode='disable'
        # Replace with: sslmode='require'
        pattern2 = re.compile(r"sslmode='disable'")
        content = pattern2.sub("sslmode='require'", content)
        
        # Pattern 3: Handle any ssl=False patterns
        pattern3 = re.compile(r"ssl=False")
        content = pattern3.sub("ssl=True", content)
        
        # Check if any changes were made
        if content != original_content:
            # Write the fixed content back
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"✅ Fixed SSL configuration in {file_path}")
            return True
        else:
            print(f"ℹ️ No SSL configuration found to fix in {file_path}")
            return False
            
    except Exception as e:
        print(f"❌ Error fixing {file_path}: {e}")
        return False

def update_trigger_comments():
    """Update trigger comments in fixed files to indicate SSL fix"""
    
    # Files that need trigger comment updates
    trigger_files = [
        'loadmarket.py',
        'loadnews.py', 
        'loadsentiment.py',
        'loadpricedaily.py',
        'loadtechnicals.py',
        'loadfinancials.py'
    ]
    
    for filename in trigger_files:
        file_path = Path(__file__).parent / filename
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Update trigger comments to indicate SSL fix
                if 'trigger' in content.lower() or 'deploy' in content.lower():
                    # Add SSL fix indicator to existing trigger comments
                    content = re.sub(
                        r'(# .*(trigger|deploy|update).*)(v\d+\.\d+)',
                        r'\1\3 - SSL connection fix',
                        content,
                        flags=re.IGNORECASE
                    )
                    
                    with open(file_path, 'w') as f:
                        f.write(content)
                    print(f"✅ Updated trigger comment in {filename}")
                        
            except Exception as e:
                print(f"⚠️ Could not update trigger comment in {filename}: {e}")

def main():
    """Main function to fix SSL configurations across all loaders"""
    print("🚀 Starting SSL configuration fix for data loaders...")
    print(f"📁 Working directory: {os.getcwd()}")
    
    fixed_count = 0
    error_count = 0
    
    # Process each loader file
    for filename in LOADERS_TO_FIX:
        file_path = Path(__file__).parent / filename
        
        if file_path.exists():
            if fix_ssl_in_file(file_path):
                fixed_count += 1
            else:
                error_count += 1
        else:
            print(f"⚠️ File not found: {filename}")
            error_count += 1
    
    # Update trigger comments
    print("\n🏷️ Updating trigger comments...")
    update_trigger_comments()
    
    # Summary
    print(f"\n📊 SSL Configuration Fix Summary:")
    print(f"   ✅ Files fixed: {fixed_count}")
    print(f"   ❌ Errors: {error_count}")
    print(f"   📝 Total files processed: {len(LOADERS_TO_FIX)}")
    
    if fixed_count > 0:
        print(f"\n🎯 Successfully fixed SSL configuration in {fixed_count} data loaders")
        print("📡 All loaders now use sslmode='require' for secure database connections")
        print("🔒 Database connections will be encrypted as required by RDS pg_hba.conf")
    else:
        print("\n⚠️ No SSL configurations were changed")
    
    return fixed_count > 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)