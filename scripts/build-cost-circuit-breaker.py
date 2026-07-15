#!/usr/bin/env python3
"""Build Cost Circuit Breaker Lambda deployment package."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def build_lambda():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    source_lambda = project_root / "lambda" / "cost-circuit-breaker"
    terraform_lambda = project_root / "terraform" / "lambda"
    pkg_dir = Path("/tmp/cost-circuit-breaker-pkg")

    print("=== Building Cost Circuit Breaker Lambda ===")
    print(f"Source: {source_lambda}")
    print(f"Output: {terraform_lambda / 'cost_circuit_breaker.zip'}")
    print()

    # Create package directory
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True, exist_ok=True)
    terraform_lambda.mkdir(parents=True, exist_ok=True)

    # Copy Lambda function handler
    print("[1/3] Copying Lambda handler...")
    shutil.copy(source_lambda / "index.py", pkg_dir / "index.py")

    # Install dependencies
    print("[2/3] Installing dependencies...")
    req_file = source_lambda / "requirements.txt"
    if req_file.exists():
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                str(req_file),
                "-t",
                str(pkg_dir),
                "--no-cache-dir",
                "--quiet",
            ],
            check=False,
        )

    # Create ZIP
    print("[3/3] Creating deployment package...")
    zip_path = terraform_lambda / "cost_circuit_breaker.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(pkg_dir):
            for file in files:
                if file.endswith((".pyc", ".dist-info")):
                    continue
                file_path = Path(root) / file
                arcname = file_path.relative_to(pkg_dir)
                zf.write(file_path, arcname)

    # Verify
    zip_size = zip_path.stat().st_size / (1024 * 1024)
    print()
    print("✓ Build complete!")
    print(f"  File: {zip_path}")
    print(f"  Size: {zip_size:.2f} MB")
    print()
    print("Next steps:")
    print("  cd terraform")
    print("  terraform plan")
    print("  terraform apply")


if __name__ == "__main__":
    build_lambda()
