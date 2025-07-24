#!/usr/bin/env python3
"""
Create a proper ZIP file for Lambda deployment
"""
import os
import zipfile
import tempfile
import shutil

def create_lambda_zip():
    # Remove old package if exists
    if os.path.exists('function.zip'):
        os.remove('function.zip')
    
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    print(f"Using temporary directory: {temp_dir}")
    
    # Copy files to temp directory (excluding unwanted files)
    excludes = {
        '.git', '.gitignore', 'node_modules/.cache', 'tests', 'coverage', 'coverage-integration',
        'scripts', 'deploy-unified-api-keys.sh', 'push-deploy.sh', 'unit-test-artifacts',
        'function.zip', 'function.tar.gz', 'create-zip.py', 'test-results', 'test-results-analysis',
        'SuperClaude.egg-info', 'config', '__pycache__', 'lambda-deployment.tar.gz'
    }
    
    def should_exclude(path):
        for exclude in excludes:
            if exclude in path or path.endswith('.test.js') or path.endswith('.md') or \
               path.endswith('.pyc') or path.endswith('.pyo') or path.endswith('.egg-info') or \
               path.endswith('-junit.xml') or path.endswith('.log') or path.endswith('.tar.gz'):
                return True
        # Exclude development and testing files and large artifacts
        if ('test' in path.lower() and not path.endswith('.js')) or \
           'backend-' in path or 'junit.xml' in path or 'test_results' in path or \
           'server.log' in path or 'test-output.log' in path:
            return True
        return False
    
    # Copy all files except excluded ones
    for root, dirs, files in os.walk('.'):
        # Skip hidden directories and excluded directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and not should_exclude(os.path.join(root, d))]
        
        for file in files:
            src_path = os.path.join(root, file)
            if not should_exclude(src_path) and not file.startswith('.'):
                rel_path = os.path.relpath(src_path, '.')
                dest_path = os.path.join(temp_dir, rel_path)
                
                # Create destination directory if it doesn't exist
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)
    
    # Create ZIP file
    with zipfile.ZipFile('function.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, temp_dir)
                zipf.write(file_path, arc_name)
    
    # Clean up temp directory
    shutil.rmtree(temp_dir)
    
    # Check file size
    size_mb = os.path.getsize('function.zip') / (1024 * 1024)
    print(f"Created function.zip: {size_mb:.1f}MB")
    
    return True

if __name__ == '__main__':
    create_lambda_zip()