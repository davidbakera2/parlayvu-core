from textwrap import dedent
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.demo_seed import RAMAIR_CLIENT_ID, RAMAIR_PROJECT_ID

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def powershell_post(url: str, body: str) -> str:
    return dedent(
        f"""\
        Invoke-RestMethod -Uri "{url}" -Method POST -ContentType "application/json" -Body @'
        {body}
        '@ | ConvertTo-Json -Depth 20
        """
    ).strip()


def powershell_get(url: str) -> str:
    return f'Invoke-RestMethod -Uri "{url}" | ConvertTo-Json -Depth 20'


def build_demo_steps(base_url: str = DEFAULT_BASE_URL) -> list[dict[str, str]]:
    return [
        {
            "title": "Start the API",
            "purpose": "Run the ParlayVU backend locally for the demo.",
            "command": "python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000",
        },
        {
            "title": "Seed RamAir Project Memory",
            "purpose": "Create the investor-demo client, project, source asset, output, approval, and event records.",
            "command": "python scripts/seed_demo.py",
        },
        {
            "title": "Check Readiness",
            "purpose": "Confirm the configured demo subsystems without exposing secrets.",
            "command": powershell_get(f"{base_url}/readiness"),
        },
        {
            "title": "Show Teams Front Door",
            "purpose": "Route a Teams-style message to Nathan with RamAir project context.",
            "command": powershell_post(
                f"{base_url}/teams/messages",
                dedent(
                    f"""\
                    {{
                      "text": "Nathan, summarize the current RamAir campaign and tell me what needs approval.",
                      "from_user": "dave@parlayvu.ai",
                      "conversation_id": "demo-conversation",
                      "team_id": "demo-team",
                      "channel_id": "demo-channel",
                      "client_id": "{RAMAIR_CLIENT_ID}",
                      "project_id": "{RAMAIR_PROJECT_ID}"
                    }}
                    """
                ).strip(),
            ),
        },
        {
            "title": "Generate a Dylan Site",
            "purpose": "Generate a local Astro site from source content without deploying it.",
            "command": powershell_post(
                f"{base_url}/dylan/generate-site",
                dedent(
                    f"""\
                    {{
                      "content": "Build a RamAir campaign landing page for the Straight from the Hart content engine.",
                      "client_id": "{RAMAIR_CLIENT_ID}",
                      "project_id": "{RAMAIR_PROJECT_ID}",
                      "site_name": "ramair-campaign-demo",
                      "brand_voice": "Practical, credible, and sales-supportive",
                      "deploy": false,
                      "project_name": "Straight from the Hart Content Engine"
                    }}
                    """
                ).strip(),
            ),
        },
        {
            "title": "Request Deployment Approval",
            "purpose": "Show that deployment is gated and produces an approval instead of deploying automatically.",
            "command": powershell_post(
                f"{base_url}/dylan/deploy-site",
                dedent(
                    f"""\
                    {{
                      "site_path": "generated_sites/{RAMAIR_CLIENT_ID}/ramair-campaign-demo",
                      "client_id": "{RAMAIR_CLIENT_ID}",
                      "project_id": "{RAMAIR_PROJECT_ID}",
                      "project_name": "Straight from the Hart Content Engine"
                    }}
                    """
                ).strip(),
            ),
        },
        {
            "title": "Show Teams Approval Cards",
            "purpose": "Render pending approvals in a Teams-friendly card payload.",
            "command": powershell_get(f"{base_url}/teams/approval-cards?project_id={RAMAIR_PROJECT_ID}"),
        },
        {
            "title": "Create an Agent Email Draft",
            "purpose": "Create an M365 draft and a send-email approval request for review.",
            "command": powershell_post(
                f"{base_url}/m365/email-drafts",
                dedent(
                    f"""\
                    {{
                      "agent_name": "nathan",
                      "to_recipients": ["client@example.com"],
                      "subject": "RamAir campaign next steps",
                      "body": "Draft follow-up from Nathan summarizing the campaign and pending approvals.",
                      "client_id": "{RAMAIR_CLIENT_ID}",
                      "project_id": "{RAMAIR_PROJECT_ID}",
                      "request_approval": true
                    }}
                    """
                ).strip(),
            ),
        },
        {
            "title": "Ask Nathan a Project Question (custom LLM endpoint)",
            "purpose": "Show Claude Opus 4.7 with project context + live tools (web, URL fetch, Teams files).",
            "command": powershell_post(
                f"{base_url}/v1/chat/completions",
                dedent(
                    f"""\
                    {{
                      "model": "nathan-opus",
                      "messages": [
                        {{"role": "user", "content": "What can we safely say about the RamAir campaign status?"}}
                      ]
                    }}
                    """
                ).strip(),
            ),
        },
    ]


def render_demo_runbook(base_url: str = DEFAULT_BASE_URL) -> str:
    lines = [
        "# ParlayVU Investor Demo Runbook",
        "",
        f"Base URL: {base_url}",
        f"Demo client: {RAMAIR_CLIENT_ID}",
        f"Demo project: {RAMAIR_PROJECT_ID}",
        "",
        "Run these steps in order. Commands are safe by default: deploys and sends are approval-gated.",
        "",
    ]
    for index, step in enumerate(build_demo_steps(base_url), start=1):
        lines.extend(
            [
                f"## {index}. {step['title']}",
                "",
                step["purpose"],
                "",
                "```powershell",
                step["command"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    print(render_demo_runbook())


if __name__ == "__main__":
    main()
