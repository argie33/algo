#!/usr/bin/env python3
import sys
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_script.py <script_name>")
        sys.exit(1)

    script_name = sys.argv[1]
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    
    if not os.path.exists(script_path):
        print(f"Error: Script {script_path} not found")
        sys.exit(1)

    print(f"Running {script_path}...")
    
    # Open file with explicit UTF-8 encoding
    with open(script_path, 'r', encoding='utf-8') as f:
        exec(f.read())

if __name__ == "__main__":
    main()
