#!/usr/bin/env python3
"""
Docker Python Version Standardization
Standardizes all Dockerfiles to use Python 3.11-slim for consistency
"""

import os
import glob
import re
from collections import defaultdict

def find_all_dockerfiles():
    """Find all Dockerfile* files in project"""
    project_root = '/home/stocks/algo'
    pattern = 'Dockerfile*'
    
    files = glob.glob(os.path.join(project_root, pattern), recursive=False)
    files.extend(glob.glob(os.path.join(project_root, '**/Dockerfile*'), recursive=True))
    
    # Filter out node_modules
    files = [f for f in files if 'node_modules' not in f]
    print(f"Found {len(files)} Dockerfile files")
    return files

def analyze_python_versions(files):
    """Analyze current Python versions in Dockerfiles"""
    version_counts = defaultdict(list)
    
    for filepath in files:
        try:
            with open(filepath, 'r') as f:
                content = f.read()
                
            # Find Python FROM statements
            python_matches = re.findall(r'FROM\s+(python:[^\s]+)', content, re.IGNORECASE)
            for match in python_matches:
                version_counts[match].append(os.path.relpath(filepath, '/home/stocks/algo'))
                
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
    
    return version_counts

def standardize_dockerfile(filepath, target_version="python:3.11-slim"):
    """Standardize Python version in a single Dockerfile"""
    print(f"\nProcessing: {os.path.relpath(filepath, '/home/stocks/algo')}")
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        original_content = content
        changes_made = 0
        
        # Replace all python FROM statements with target version
        python_pattern = r'FROM\s+(python:[^\s]+)'
        matches = re.findall(python_pattern, content, re.IGNORECASE)
        
        for match in matches:
            if match != target_version:
                print(f"  Replacing: {match} -> {target_version}")
                content = content.replace(f"FROM {match}", f"FROM {target_version}")
                changes_made += 1
        
        # Also handle multi-stage builds with aliases
        alias_pattern = r'FROM\s+(python:[^\s]+)\s+as\s+(\w+)'
        alias_matches = re.findall(alias_pattern, content, re.IGNORECASE)
        
        for match_version, alias in alias_matches:
            if match_version != target_version:
                old_line = f"FROM {match_version} as {alias}"
                new_line = f"FROM {target_version} as {alias}"
                print(f"  Replacing: {old_line} -> {new_line}")
                content = content.replace(old_line, new_line)
                changes_made += 1
        
        if changes_made > 0:
            # Write back to file
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"  ✅ Made {changes_made} changes")
        else:
            print(f"  ✅ Already using {target_version}")
            
        return changes_made
        
    except Exception as e:
        print(f"  ❌ Error processing {filepath}: {e}")
        return 0

def main():
    print("🐳 Docker Python Version Standardization")
    print("========================================")
    
    files = find_all_dockerfiles()
    
    if not files:
        print("No Dockerfile files found!")
        return
    
    # Analyze current versions
    print("\n📊 Current Python version distribution:")
    version_counts = analyze_python_versions(files)
    
    total_dockerfiles = 0
    for version, file_list in version_counts.items():
        print(f"  {version}: {len(file_list)} files")
        total_dockerfiles += len(file_list)
    
    if not version_counts:
        print("  No Python base images found in Dockerfiles")
        return
    
    # Recommend standardization
    target_version = "python:3.11-slim"
    print(f"\n🎯 Standardizing all Python Dockerfiles to: {target_version}")
    
    # Process all Dockerfiles
    total_changes = 0
    processed_files = 0
    
    for filepath in files:
        changes = standardize_dockerfile(filepath, target_version)
        if changes > 0:
            total_changes += changes
            processed_files += 1
    
    print(f"\n✅ Docker standardization complete!")
    print(f"   Processed {len(files)} Dockerfile files")
    print(f"   Made changes to {processed_files} files")
    print(f"   Total changes: {total_changes}")
    
    # Verify standardization
    print(f"\n🔍 Verifying standardization...")
    final_version_counts = analyze_python_versions(files)
    
    if len(final_version_counts) == 1 and target_version in final_version_counts:
        print(f"✅ All Dockerfiles now use {target_version}")
    else:
        print(f"⚠️ Still have mixed versions:")
        for version, file_list in final_version_counts.items():
            print(f"  {version}: {len(file_list)} files")

if __name__ == "__main__":
    main()