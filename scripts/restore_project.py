# Restores the project to a consistent state after cloning or switching branches.
# Does three things in sequence:
#   1. Installs requirements.txt + requirements-dev.txt into the active environment.
#   2. Regenerates AI context files via refresh_context (.ai/).
#   3. Validates that all skills declared in the registry actually exist on disk.
# Exits with code 1 if any skill files are missing.
# Usage: python scripts/restore_project.py [--project-root <path>] [--dry-run] [--pretty]
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.runtime.skill_registry import build_skills_registry  # noqa: E402
from ai.tools.refresh_context import refresh_context  # noqa: E402


def validate_consistency(project_root: Path) -> dict[str, list[str]]:
    registry = build_skills_registry(project_root)
    missing = [
        skill["path"]
        for skill in registry["skills"]
        if not (project_root / skill["path"]).exists()
    ]
    return {"missing": missing}


def install_requirements(project_root: Path, *, dry_run: bool) -> dict[str, object]:
    requirement_files = [
        project_root / name
        for name in ("requirements.txt", "requirements-dev.txt")
        if (project_root / name).exists()
    ]
    if not requirement_files:
        return {"status": "skipped", "reason": "no requirements files found"}

    command = [sys.executable, "-m", "pip", "install"]
    for requirement_file in requirement_files:
        command.extend(["-r", str(requirement_file)])

    if dry_run:
        return {"status": "skipped", "reason": "dry-run", "command": command}

    subprocess.run(command, cwd=project_root, check=True)
    return {"status": "ok"}


def restore_project(project_root: Path, *, dry_run: bool = False) -> dict[str, object]:
    project_root = project_root.resolve()
    dependencies = install_requirements(project_root, dry_run=dry_run)

    context = (
        {"status": "skipped", "reason": "dry-run"}
        if dry_run
        else refresh_context(project_root)
    )
    consistency = validate_consistency(project_root)

    return {
        "status": "ok",
        "dependencies": dependencies,
        "context": context,
        "consistency": consistency,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore a host by installing requirements and refreshing AI context."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    try:
        payload = restore_project(Path(args.project_root), dry_run=args.dry_run)
    except ValueError as exc:
        payload = {"status": "error", "error": str(exc)}
        print(json.dumps(payload, indent=2 if args.pretty else None))
        return 1

    print(json.dumps(payload, indent=2 if args.pretty else None))
    return 1 if payload["consistency"]["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
