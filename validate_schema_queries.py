#!/usr/bin/env python3
"""
Schema Query Validator - Check all SQL queries against schema_mapping.json

Scans all .py files for SELECT statements and validates that referenced columns
actually exist in the specified tables. Catches schema mismatches early.

Usage:
  python3 validate_schema_queries.py          # Check all .py files
  python3 validate_schema_queries.py file.py  # Check specific file
"""

import json
import re
import sys
from pathlib import Path

# Load schema mapping
schema_file = Path(__file__).parent / "schema_mapping.json"
with open(schema_file) as f:
    schema = json.load(f)

CRITICAL_TABLES = schema["critical_tables"]

# Pattern to find SELECT statements
SELECT_PATTERN = re.compile(
    r"SELECT\s+([^F]+?)\s+FROM\s+(\w+)",
    re.IGNORECASE | re.MULTILINE
)

# Known safe columns (constants, functions)
SAFE_PATTERNS = {
    "COUNT\\(\\*\\)",
    "COUNT\\(\\w+\\)",
    "MAX\\(",
    "MIN\\(",
    "AVG\\(",
    "SUM\\(",
    "CURRENT_TIMESTAMP",
    "CURRENT_DATE",
    "NOW\\(\\)",
    "INTERVAL",
    "COALESCE",
    "CASE\\s+WHEN",
    "ROW_NUMBER",
}

def is_safe_expression(expr):
    """Check if expression is a function or constant"""
    expr = expr.strip()
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, expr, re.IGNORECASE):
            return True
    # Aliased expressions
    if " AS " in expr.upper():
        return True
    # Subqueries
    if expr.startswith("("):
        return True
    # Literals
    if expr.startswith("'") or expr.startswith("%"):
        return True
    return False

def extract_columns(select_expr):
    """Extract column names from SELECT clause"""
    # Remove parameter placeholders
    select_expr = re.sub(r"%s", "", select_expr)
    # Split by comma but respect parentheses
    columns = []
    for col in select_expr.split(","):
        col = col.strip()
        if col and not is_safe_expression(col):
            # Extract first word (column name before AS, operators, etc.)
            match = re.match(r"(\w+)", col)
            if match:
                columns.append(match.group(1))
    return columns

def validate_file(filepath):
    """Validate all SELECT queries in a file"""
    issues = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        line_num = 0

        for match in SELECT_PATTERN.finditer(content):
            # Count lines up to match position
            line_num = content[:match.start()].count("\n") + 1

            select_clause = match.group(1)
            table_name = match.group(2).lower()

            # Skip if table not in schema
            if table_name not in CRITICAL_TABLES:
                continue

            table_schema = CRITICAL_TABLES[table_name]
            valid_columns = table_schema["key_columns"].keys()

            # Extract and validate columns
            query_columns = extract_columns(select_clause)

            for col in query_columns:
                if col not in valid_columns and col != "*":
                    issues.append({
                        "file": filepath,
                        "line": line_num,
                        "table": table_name,
                        "column": col,
                        "valid_columns": list(valid_columns),
                        "message": f"Column '{col}' not found in table '{table_name}'"
                    })

    return issues

def main():
    # Find all Python files
    if len(sys.argv) > 1:
        files = [Path(sys.argv[1])]
    else:
        files = list(Path(".").glob("algo*.py"))
        files.extend(Path(".").glob("load*.py"))

    all_issues = []

    for filepath in files:
        if filepath.exists():
            issues = validate_file(filepath)
            all_issues.extend(issues)
            if issues:
                print(f"\n⚠️  {filepath.name}:")
                for issue in issues:
                    print(f"  Line {issue['line']}: {issue['message']}")
                    print(f"    Valid columns: {', '.join(issue['valid_columns'][:5])}")

    if all_issues:
        print(f"\n❌ Found {len(all_issues)} potential schema issues")
        return 1
    else:
        print("✅ All SQL queries validated against schema")
        return 0

if __name__ == "__main__":
    sys.exit(main())
