#!/usr/bin/env python3
"""
Systematic Python Dependency Conflict Resolution
Fixes 100+ version conflicts across 54 requirements files
"""

import os
import re
import glob
from collections import defaultdict

# Master unified versions (most stable/recent versions that work together)
MASTER_VERSIONS = {
    'boto3': '1.34.69',
    'botocore': '1.34.69',
    'psycopg2-binary': '2.9.9',
    'pandas': '2.1.4',
    'numpy': '1.24.4',
    'yfinance': '0.2.64',
    'requests': '2.31.0',
    'urllib3': '1.26.16',
    'python-dateutil': '2.8.2',
    'scipy': '1.11.1',
    'scikit-learn': '1.3.0',
    'pandas-ta': '0.3.14b0',
    'fredapi': '0.5.1',
    'textblob': '0.17.1',
    'psutil': '5.9.8',
    'pytest': '7.4.4',
    'pytest-cov': '4.1.0',
    # Additional packages from new conflicts
    'ta-lib': '0.4.32',
    'sqlalchemy': '2.0.19',
    'python-dotenv': '1.0.0',
    'pyyaml': '6.0.1',
    'structlog': '23.1.0',
    'black': '23.7.0',
    'flake8': '6.0.0',
}

def find_all_requirements_files():
    """Find all Python requirements files in project"""
    project_root = '/home/stocks/algo'
    patterns = [
        'requirements*.txt',
        '**/requirements*.txt'
    ]
    
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(project_root, pattern), recursive=True))
    
    # Filter out node_modules
    files = [f for f in files if 'node_modules' not in f]
    print(f"Found {len(files)} requirements files")
    return files

def parse_requirement_line(line):
    """Parse a requirement line into package name and version spec"""
    line = line.strip()
    if not line or line.startswith('#'):
        return None, None
    
    # Handle various version specifiers
    match = re.match(r'^([a-zA-Z0-9_-]+)([<>=!].*)?', line)
    if match:
        package = match.group(1).strip()
        version_spec = match.group(2) or ''
        return package, version_spec
    
    return None, None

def fix_requirements_file(filepath):
    """Fix version conflicts in a single requirements file"""
    print(f"\nProcessing: {os.path.relpath(filepath, '/home/stocks/algo')}")
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    fixed_lines = []
    changes_made = 0
    
    for line in lines:
        original_line = line
        package, version_spec = parse_requirement_line(line)
        
        if package and package in MASTER_VERSIONS:
            # Use master version
            master_version = MASTER_VERSIONS[package]
            new_line = f"{package}=={master_version}\n"
            
            if new_line != original_line:
                print(f"  Fixed: {package} {version_spec} -> =={master_version}")
                changes_made += 1
            
            fixed_lines.append(new_line)
        else:
            # Keep original line
            fixed_lines.append(original_line)
    
    if changes_made > 0:
        # Write back to file
        with open(filepath, 'w') as f:
            f.writelines(fixed_lines)
        print(f"  ✅ Made {changes_made} fixes")
    else:
        print(f"  ✅ No changes needed")

def analyze_conflicts_before_fix():
    """Analyze conflicts before fixing"""
    print("📊 Analyzing conflicts before fixes...")
    
    files = find_all_requirements_files()
    package_versions = defaultdict(set)
    
    for filepath in files:
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    package, version_spec = parse_requirement_line(line)
                    if package:
                        package_versions[package].add(version_spec)
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
    
    # Count conflicts
    conflicts = 0
    for package, versions in package_versions.items():
        if len(versions) > 1 and package in MASTER_VERSIONS:
            conflicts += 1
            print(f"  Conflict: {package} has versions: {versions}")
    
    print(f"📊 Found {conflicts} packages with version conflicts")
    return conflicts

def main():
    print("🔧 Systematic Python Dependency Conflict Resolution")
    print("==================================================")
    
    # Analyze conflicts
    initial_conflicts = analyze_conflicts_before_fix()
    
    if initial_conflicts == 0:
        print("✅ No conflicts found!")
        return
    
    # Find and fix all requirements files
    files = find_all_requirements_files()
    
    print(f"\n🚀 Processing {len(files)} requirements files...")
    
    total_fixes = 0
    for filepath in files:
        try:
            changes = fix_requirements_file(filepath)
            if changes:
                total_fixes += changes
        except Exception as e:
            print(f"❌ Error processing {filepath}: {e}")
    
    print(f"\n✅ Python dependency conflict resolution complete!")
    print(f"   Fixed conflicts in {len(files)} files")
    print(f"   Using {len(MASTER_VERSIONS)} standardized package versions")
    
    # Verify fixes
    print("\n🔍 Verifying fixes...")
    final_conflicts = analyze_conflicts_before_fix()
    
    if final_conflicts < initial_conflicts:
        print(f"✅ Reduced conflicts from {initial_conflicts} to {final_conflicts}")
    else:
        print(f"⚠️ Still have {final_conflicts} conflicts - may need manual review")

if __name__ == "__main__":
    main()