from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a video project folder.")
    parser.add_argument("project", help="Path to a project folder")
    parser.add_argument("--template", default=None, help="Optional path to template_config.json")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    assets = project / "assets"
    planning = project / "planning"

    problems: list[str] = []
    for directory in [assets, planning, project / "renders", project / "previews"]:
        if not directory.exists():
            problems.append(f"Missing folder: {directory}")

    required_assets = [
        "intro.mp4",
        "show_image.png",
        "show_image_lower_third.png",
        "logo_square.png",
        "host.mp4",
        "guest_01.mp4",
    ]
    for name in required_assets:
        if not (assets / name).exists():
            problems.append(f"Missing asset: {assets / name}")

    if not (planning / "video_plan.xlsx").exists():
        problems.append(f"Missing workbook: {planning / 'video_plan.xlsx'}")

    if args.template:
        template = Path(args.template).resolve()
        if not template.exists():
            problems.append(f"Missing template config: {template}")
        else:
            json.loads(template.read_text(encoding="utf-8"))

    if problems:
        print("Project validation failed:")
        for problem in problems:
            print(f"- {problem}")
        raise SystemExit(1)

    print(f"Project validation passed: {project}")


if __name__ == "__main__":
    main()
