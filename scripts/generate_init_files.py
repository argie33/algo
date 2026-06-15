#!/usr/bin/env python3
"""Generate __init__.py files for all reorganized submodules."""

import ast
from pathlib import Path


def get_exports_from_module(filepath: Path) -> list:
    """Extract all top-level class and function definitions from a Python file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not parse {filepath}: {e}")
        return []

    exports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                exports.append(node.name)

    return list(set(exports))


def create_init_file(dir_path: Path):
    """Create __init__.py for a submodule directory."""
    if (dir_path / "__init__.py").exists():
        return

    py_files = [
        f
        for f in dir_path.glob("*.py")
        if f.name != "__init__.py" and f.name != "__pycache__"
    ]
    if not py_files:
        return

    imports = []
    for py_file in sorted(py_files):
        module_name = py_file.stem
        exports = get_exports_from_module(py_file)
        if exports:
            relative_import = f"from .{module_name} import {', '.join(sorted(exports))}"
            imports.append(relative_import)

    if not imports:
        # Create minimal __init__.py
        init_content = "#!/usr/bin/env python3\n"
    else:
        init_content = "#!/usr/bin/env python3\n\n" + "\n".join(imports) + "\n"

    (dir_path / "__init__.py").write_text(init_content)
    print(f"[+] Created {dir_path}/__init__.py")


def main():
    repo_root = Path(".")

    # Algo submodules
    algo_submodules = [
        "signals",
        "risk",
        "trading",
        "monitoring",
        "reporting",
        "orchestration",
        "infrastructure",
    ]
    for submod in algo_submodules:
        submod_path = repo_root / "algo" / submod
        if submod_path.exists():
            create_init_file(submod_path)

    # Utils submodules
    utils_submodules = [
        "db",
        "logging",
        "validation",
        "data",
        "signals",
        "trading",
        "loaders",
        "external",
        "infrastructure",
        "ops",
    ]
    for submod in utils_submodules:
        submod_path = repo_root / "utils" / submod
        if submod_path.exists():
            create_init_file(submod_path)


if __name__ == "__main__":
    main()
