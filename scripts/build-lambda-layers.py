#!/usr/bin/env python3
"""Lambda Layer Builder - Builds Lambda layer ZIPs from Python dependencies and source code."""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class LambdaLayerBuilder:
    LAYERS: ClassVar[dict] = {
        "shared_deps": {
            "requirements": "terraform/lambda-layer-requirements.txt",
            "source_dirs": [],
        },
        "orchestrator": {
            "requirements": "lambda/algo_orchestrator/requirements.txt",
            "source_dirs": ["config", "algo", "utils", "monitoring"],
        },
        "api": {"requirements": "lambda/api/requirements.txt", "source_dirs": []},
    }

    def __init__(self, output_dir: str = "terraform", runtime: str = "python3.12") -> None:
        self.output_dir = Path(output_dir)
        self.runtime = runtime
        self.repo_root = Path.cwd()

    def build_layer(self, layer_name: str, requirements_path: str, source_dirs: list[str]) -> Path:
        has_requirements = Path(requirements_path).exists()
        build_dir = self.output_dir / f"layer_build_{layer_name}_{os.getpid()}"
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True)
        python_dir = build_dir / "python"
        python_dir.mkdir()

        try:
            if has_requirements:
                logger.info(f"Installing dependencies from {requirements_path}...")
                cmd = [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--platform",
                    "manylinux2014_x86_64",
                    "--implementation",
                    "cp",
                    f"--python-version={self.runtime.replace('python', '')}",
                    "--only-binary=:all:",
                    "--upgrade",
                    "--no-cache-dir",
                    "--target",
                    str(python_dir),
                    "-r",
                    requirements_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"pip failed: {result.stderr}")
            for source_dir in source_dirs:
                src = self.repo_root / source_dir
                if src.is_dir():
                    dst = python_dir / source_dir
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            zip_path = self.output_dir / f"{layer_name}-layer.zip"
            if zip_path.exists():
                zip_path.unlink()
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in build_dir.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, file_path.relative_to(build_dir))
            return zip_path
        finally:
            if build_dir.exists():
                shutil.rmtree(build_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Lambda layers")
    parser.add_argument("--layer", help="Layer to build (shared-deps, orchestrator, api)")
    parser.add_argument("--all", action="store_true", help="Build all layers")
    parser.add_argument("--runtime", default="python3.12")
    parser.add_argument("--output-dir", default="terraform")
    args = parser.parse_args()
    if not args.layer and not args.all:
        parser.error("Specify --layer or --all")
    layers = list(LambdaLayerBuilder.LAYERS.keys()) if args.all else [args.layer]
    builder = LambdaLayerBuilder(args.output_dir, args.runtime)
    for layer_name in layers:
        if layer_name not in builder.LAYERS:
            parser.error(f"Unknown layer: {layer_name}")
        spec = builder.LAYERS[layer_name]
        logger.info(f"Building: {layer_name}")
        try:
            zip_path = builder.build_layer(layer_name, spec["requirements"], spec["source_dirs"])
            logger.info(f"OK {layer_name}: {zip_path}")
        except Exception as e:
            logger.error(f"FAILED {layer_name}: {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
