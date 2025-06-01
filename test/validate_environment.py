#!/usr/bin/env python3
"""
Validation script to check if the test environment is ready to run
"""
import subprocess
import sys
import os

def check_docker():
    """Check if Docker is installed and running"""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Docker found: {result.stdout.strip()}")
            return True
        else:
            print("❌ Docker command failed")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Docker not found or not responding")
        return False

def check_docker_compose():
    """Check if Docker Compose is available"""
    try:
        result = subprocess.run(['docker-compose', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Docker Compose found: {result.stdout.strip()}")
            return True
        else:
            # Try docker compose (newer syntax)
            result = subprocess.run(['docker', 'compose', 'version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"✅ Docker Compose found: {result.stdout.strip()}")
                return True
            else:
                print("❌ Docker Compose not found")
                return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Docker Compose not found")
        return False

def check_docker_running():
    """Check if Docker daemon is running"""
    try:
        result = subprocess.run(['docker', 'info'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Docker daemon is running")
            return True
        else:
            print("❌ Docker daemon is not running")
            print("   Start Docker Desktop and try again")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Cannot connect to Docker daemon")
        return False

def check_test_files():
    """Check if required test files exist"""
    required_files = [
        'docker-compose.yml',
        'Dockerfile.test',
        'mock_boto3.py',
        'test_runner.py',
        'requirements.txt'
    ]
    
    all_found = True
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ Found {file}")
        else:
            print(f"❌ Missing {file}")
            all_found = False
    
    return all_found

def check_source_scripts():
    """Check if the source scripts exist"""
    scripts_to_check = [
        '../loadstocksymbols_test.py',
        # Add other scripts when specified
        # '../loadanalystupgradedowngrade.py',
        # '../loadbuysell.py',
    ]
    
    all_found = True
    for script in scripts_to_check:
        if os.path.exists(script):
            print(f"✅ Found source script: {script}")
        else:
            print(f"❌ Missing source script: {script}")
            all_found = False
    
    return all_found

def main():
    """Run all validation checks"""
    print("🔍 Validating test environment...")
    print("=" * 50)
    
    checks = [
        ("Docker Installation", check_docker),
        ("Docker Compose", check_docker_compose),
        ("Docker Daemon", check_docker_running),
        ("Test Files", check_test_files),
        ("Source Scripts", check_source_scripts),
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 50)
    
    if all_passed:
        print("🎉 All checks passed! Ready to run tests.")
        print("\nTo run tests:")
        print("  PowerShell: .\\run_tests.ps1")
        print("  Batch:      run_tests.bat")
        print("  Python:     python run_tests.py")
    else:
        print("❌ Some checks failed. Please fix the issues above before running tests.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
