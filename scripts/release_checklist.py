from textwrap import dedent


def build_release_checks() -> list[dict[str, list[str]]]:
    return [
        {
            "title": "Secret Safety",
            "items": [
                "Rotate credentials that were stored in local .env.",
                "Confirm .env is ignored and not shared.",
                "Move production values into Azure Container App secrets or Azure Key Vault.",
                "Keep MICROSOFT_GRAPH_ALLOW_SEND=false until send approvals are fully tested.",
            ],
        },
        {
            "title": "Local Verification",
            "items": [
                "Install dependencies with pip install -r requirements.txt.",
                "Run python -m unittest discover -s tests.",
                "Confirm app and script syntax checks pass.",
            ],
        },
        {
            "title": "Demo Memory",
            "items": [
                "Run python scripts/seed_demo.py.",
                "Confirm RamAir project memory exists.",
                "Confirm pending approvals are visible.",
            ],
        },
        {
            "title": "Readiness",
            "items": [
                "Start the API with uvicorn.",
                "Check GET /health.",
                "Check GET /readiness.",
                "Confirm missing integrations are intentional if status is needs_configuration.",
            ],
        },
        {
            "title": "Demo Rehearsal",
            "items": [
                "Run python scripts/demo_runbook.py.",
                "Walk through Teams, Nathan, Dylan, approvals, M365 draft, and HeyGen question flow.",
                "Confirm deploys and sends remain approval-gated.",
            ],
        },
        {
            "title": "Pitch Materials",
            "items": [
                "Confirm live site and RamAir proof point are ready.",
                "Use the architecture story from ARCHITECTURE.md.",
                "Prepare a fallback path for unavailable external integrations.",
            ],
        },
    ]


def render_release_checklist() -> str:
    lines = [
        "# ParlayVU Pitch-Readiness Release Checklist",
        "",
        "Use this as the final gate before an investor demo or hosted release.",
        "",
    ]
    for index, section in enumerate(build_release_checks(), start=1):
        lines.append(f"## {index}. {section['title']}")
        lines.append("")
        for item in section["items"]:
            lines.append(f"- [ ] {item}")
        lines.append("")
    lines.append(
        dedent(
            """\
            ## Final Gate

            Do not pitch from a shared or production-facing environment until secrets are rotated,
            readiness is reviewed, the demo runbook is rehearsed, approval gates are confirmed,
            and the deployment target is known.
            """
        ).strip()
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    print(render_release_checklist())


if __name__ == "__main__":
    main()
