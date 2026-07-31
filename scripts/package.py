# Builds a deployment ZIP for AWS (Glue, Lambda, etc.).
# The bundle contains src/ code plus the repository's requirements.txt — the
# format cloud environments understand.
# Usage: python scripts/package.py [--clean]
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ARTIFACT_PATH = REPO_ROOT / "artifacts" / "data_platform_bundle.zip"
INCLUDE_DIRS = [REPO_ROOT / "src"]
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"


def build_bundle() -> Path:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(ARTIFACT_PATH, "w", compression=ZIP_DEFLATED) as archive:
        for directory in INCLUDE_DIRS:
            for file_path in sorted(directory.rglob("*")):
                if file_path.is_dir() and file_path.name == "__pycache__":
                    continue
                if file_path.suffix == ".pyc":
                    continue
                if "__pycache__" in file_path.parts:
                    continue
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(REPO_ROOT))
        # Ship the runtime requirements file in the bundle (dev-only deps
        # live in requirements-dev.txt and are never shipped).
        archive.write(REQUIREMENTS_PATH, "requirements.txt")
    return ARTIFACT_PATH


def clean_bundle() -> None:
    if ARTIFACT_PATH.exists():
        try:
            ARTIFACT_PATH.unlink()
        except PermissionError:
            print(
                f"Could not remove {ARTIFACT_PATH} because it is currently in use. Close any process using the bundle and retry.",
                file=sys.stderr,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or remove the deployment bundle."
    )
    parser.add_argument(
        "--clean", action="store_true", help="Remove the generated bundle."
    )
    args = parser.parse_args()

    if args.clean:
        clean_bundle()
        return

    artifact = build_bundle()
    print(artifact)


if __name__ == "__main__":
    main()
