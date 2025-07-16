#!/usr/bin/env python3
"""
Lambda Package Creator
Creates a ZIP file for Lambda deployment using Python zipfile module
"""

import os
import zipfile
import subprocess
import sys

def create_lambda_package():
    """Create Lambda deployment package"""
    
    print("🔧 Creating Lambda deployment package...")
    
    # Clean up node_modules dev dependencies
    print("🧹 Cleaning up development dependencies...")
    result = subprocess.run(['npm', 'prune', '--production'], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️ npm prune warning: {result.stderr}")
    
    # Create ZIP file
    zip_filename = 'function.zip'
    
    # Remove existing package if it exists
    if os.path.exists(zip_filename):
        os.remove(zip_filename)
        print(f"🗑️ Removed existing {zip_filename}")
    
    print("📦 Creating deployment package...")
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('.'):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if not d.startswith('.git') and 
                      d not in ['__pycache__', 'coverage', 'tests', '.pytest_cache']]
            
            for file in files:
                if (not file.startswith('.git') and 
                    not file.endswith('.pyc') and
                    not file.endswith('.log') and
                    file not in ['package-lambda.py', 'deploy-fix.sh']):
                    
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, '.')
                    zipf.write(file_path, arcname=arcname)
    
    # Check package size
    size = os.path.getsize(zip_filename)
    size_mb = size / (1024 * 1024)
    
    print(f"📏 Package size: {size_mb:.2f} MB")
    print(f"✅ Package created successfully: {zip_filename}")
    
    return zip_filename

if __name__ == "__main__":
    try:
        package_file = create_lambda_package()
        print(f"\n🚀 Ready for deployment with: {package_file}")
        print("Next step: aws lambda update-function-code --function-name financial-dashboard-api --zip-file fileb://function.zip")
    except Exception as e:
        print(f"❌ Error creating package: {e}")
        sys.exit(1)