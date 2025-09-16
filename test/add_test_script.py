#!/usr/bin/env python3
"""
Helper script to add additional test scripts to the test runner.
Usage: python add_test_script.py script_name.py
"""
import os
import sys


def add_test_script(script_name):
    """Add a new script to the test runner configuration"""

    test_runner_path = os.path.join(os.path.dirname(__file__), "test_runner.py")

    if not os.path.exists(test_runner_path):
        print(f"❌ test_runner.py not found at {test_runner_path}")
        return False

    # Read the current file
    with open(test_runner_path, "r") as f:
        content = f.read()

    # Find the scripts_to_test section
    script_entry = f'        ("/app/source/{script_name}", "{script_name}"),'

    if script_entry in content:
        print(f"✅ {script_name} is already in the test configuration")
        return True

    # Find the insertion point (after the first script and before the comment)
    lines = content.split("\n")
    new_lines = []
    inserted = False

    for line in lines:
        new_lines.append(line)
        if "loadstocksymbols_test.py" in line and not inserted:
            # Add the new script after the existing one
            new_lines.append(script_entry)
            inserted = True

    if not inserted:
        print(f"❌ Could not find insertion point in test_runner.py")
        return False

    # Write the updated file
    with open(test_runner_path, "w") as f:
        f.write("\n".join(new_lines))

    print(f"✅ Added {script_name} to test configuration")
    return True


def main():
    if len(sys.argv) != 2:
        print("Usage: python add_test_script.py <script_name.py>")
        print("Example: python add_test_script.py loadanalystupgradedowngrade.py")
        sys.exit(1)

    script_name = sys.argv[1]
    if not script_name.endswith(".py"):
        script_name += ".py"

    success = add_test_script(script_name)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
