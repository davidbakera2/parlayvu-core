from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def safe_name(value: str) -> str:
    return value.strip().replace(" ", "_")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new video project from _starter_project.")
    parser.add_argument("client", help="Client folder name, e.g. RamAir")
    parser.add_argument("show", help="Show/project name, e.g. Straight_From_The_Hart")
    parser.add_argument("episode", help="Episode label, e.g. Ep01b")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    starter = root / "projects" / "_starter_project"
    client_dir = root / "projects" / safe_name(args.client)
    project = client_dir / f"{safe_name(args.show)}_{safe_name(args.episode)}"

    if not starter.exists():
        raise SystemExit(f"Starter project not found: {starter}")
    if project.exists():
        raise SystemExit(f"Project already exists: {project}")

    client_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(starter, project)
    print(f"Created project: {project}")
    print(f"Edit spreadsheet: {project / 'planning' / 'video_plan.xlsx'}")
    print(f"Add assets here: {project / 'assets'}")


if __name__ == "__main__":
    main()
