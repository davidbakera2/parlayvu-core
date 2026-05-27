"""End-to-end smoke test for the ParlayVU client-website Teams workflow.

Simulates a Teams message landing in a client's bound channel, runs it through
the real /teams/messages handler, and prints what would have been sent back into
Teams (the text reply + any approval cards). Network egress is mocked so the
script needs only ANTHROPIC_API_KEY + XAI_API_KEY — no Cloudflare creds, no
Bot Framework auth.

Usage:
    python scripts/smoke_client_site_workflow.py --client ulcannarbor --count 3 \
        --message "Hey Nathan, give us 3 sample home pages for ulcannarbor.info"

Default client is ulcannarbor. --count is clamped by the variations service to
[1, 10]; default 3 keeps the run quick (1–2 min).

The script:
  1. Patches send_bot_framework_reply / send_bot_framework_card to capture
     outbound activities instead of POSTing to the Bot Framework API.
  2. Patches client_deploy.deploy_preview to skip the actual wrangler call
     (the script still verifies the generated files land on disk).
  3. Patches promote_to_production for the same reason.
  4. Constructs a Bot Framework activity scoped to the requested client's
     team_id + channel_id from config.yaml.
  5. POSTs it to /teams/messages via FastAPI TestClient.
  6. Prints captured replies + a summary.

Reusable for any onboarded client — pass --client <id>. No client-specific
code lives here; everything reads from client_artifacts/<id>/config.yaml.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Make `app` importable when this script is run directly from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")

# Late imports so load_dotenv runs first and env vars apply.
from fastapi.testclient import TestClient  # noqa: E402

from app.client_config import load_client_config  # noqa: E402


def _build_activity(*, text: str, team_id: str, channel_id: str) -> dict[str, Any]:
    """Construct a minimal Bot Framework `message` activity for a channel post."""
    activity_id = str(uuid.uuid4())
    conversation_id = f"{channel_id};messageid={activity_id}"
    return {
        "type": "message",
        "id": activity_id,
        "timestamp": "2026-05-27T18:00:00Z",
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "channelId": "msteams",
        "from": {
            "id": "29:smoke-test-user",
            "name": "Smoke Test User",
            "aadObjectId": "00000000-0000-0000-0000-000000000001",
        },
        "conversation": {
            "isGroup": True,
            "conversationType": "channel",
            "id": conversation_id,
            "tenantId": os.getenv("TEAMS_TENANT_ID", "00000000-0000-0000-0000-000000000002"),
        },
        "recipient": {"id": "28:bot", "name": "Nathan"},
        "channelData": {
            "team": {"id": team_id},
            "channel": {"id": channel_id},
            "tenant": {"id": os.getenv("TEAMS_TENANT_ID", "")},
        },
        "text": text,
        "textFormat": "plain",
    }


def _safe(text: str) -> str:
    """Replace characters the stdout encoding can't represent (Windows cp1252
    chokes on emojis Nathan likes to use). We only sanitize at the print
    boundary so captured text remains exact in memory."""
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
    return text.encode(enc, errors="replace").decode(enc, errors="replace")


def _print_captured(captured_text: list[str], captured_cards: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 72)
    print("CAPTURED OUTBOUND TO TEAMS")
    print("=" * 72)
    if captured_text:
        for i, t in enumerate(captured_text, 1):
            print(f"\n--- Text reply #{i} ---")
            print(_safe(t))
    else:
        print("(no text replies captured)")
    if captured_cards:
        for i, card in enumerate(captured_cards, 1):
            print(f"\n--- Adaptive Card #{i} ---")
            j = json.dumps(card, indent=2, ensure_ascii=True)
            if len(j) > 4000:
                j = j[:4000] + "\n... [truncated]"
            print(_safe(j))
    else:
        print("\n(no adaptive cards captured)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="ulcannarbor", help="client_id (default: ulcannarbor)")
    parser.add_argument(
        "--message",
        default=None,
        help='Inbound Teams message text. Default tailored to --client.',
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Variation count Nathan should request (1-10). Default 3.",
    )
    parser.add_argument(
        "--approve-variant",
        type=int,
        default=None,
        help=(
            "After variations land, simulate a button tap approving variant N. "
            "Exercises the full pipeline through promote_to_production "
            "(deploy is stubbed). Omit to stop after the picker card."
        ),
    )
    args = parser.parse_args()

    try:
        config = load_client_config(args.client)
    except Exception as exc:
        print(f"ERROR: couldn't load config for client {args.client!r}: {exc}", file=sys.stderr)
        return 2

    message = args.message or (
        f"Hey Nathan, can you have Dylan give us {args.count} sample home pages "
        f"for {config.cloudflare_config.production_domain or args.client}? "
        f"We want to see different design directions."
    )

    print(f"Client      : {args.client} ({config.display_name})")
    print(f"Team id     : {config.teams.team_id[:8]}…")
    print(f"Channel id  : {config.teams.channel_id[:24]}…")
    print(f"Prod project: {config.cloudflare_config.production_project}")
    print(f"Prod domain : {config.cloudflare_config.production_domain}")
    print(f"Message     : {message!r}")

    captured_text: list[str] = []
    captured_cards: list[dict[str, Any]] = []

    async def _capture_reply(activity, text, settings=None):
        captured_text.append(text)

    async def _capture_card(activity, card, settings=None):
        captured_cards.append(card)

    def _stub_deploy_preview(*, client_id, source_dir=None):
        return {
            "status": "success",
            "project_name": f"{client_id}-previews",
            "url": f"https://{client_id}-previews.pages.dev/",
            "stdout": "(stub — wrangler not invoked in smoke test)",
        }

    promotion_calls: list[dict[str, Any]] = []

    def _stub_promote(*, client_id, source_dir):
        promotion_calls.append(
            {"client_id": client_id, "source_dir": str(source_dir)}
        )
        return {
            "status": "success",
            "project_name": client_id,
            "production_project": client_id,
            "production_domain": load_client_config(client_id).cloudflare_config.production_domain,
            "url": f"https://{client_id}.pages.dev/",
            "active_dir": f"client_artifacts/{client_id}/03_Deliverables/sites/active",
            "stdout": "(stub — wrangler not invoked in smoke test)",
        }

    # Activity has to be built BEFORE patching so the app can read it.
    activity = _build_activity(
        text=message,
        team_id=config.teams.team_id,
        channel_id=config.teams.channel_id,
    )

    # Patch every network-egress point used by the workflow. deploy_preview
    # is imported lazily inside the variations/edit services, so we patch the
    # source module — that intercepts both call sites.
    patches = [
        patch("app.teams.send_bot_framework_reply", side_effect=_capture_reply),
        patch("app.teams.send_bot_framework_card", side_effect=_capture_card),
        patch("app.main.send_bot_framework_reply", side_effect=_capture_reply),
        patch("app.main.send_bot_framework_card", side_effect=_capture_card),
        patch("app.services.client_deploy.deploy_preview", side_effect=_stub_deploy_preview),
        patch("app.services.client_deploy.promote_to_production", side_effect=_stub_promote),
    ]
    for p in patches:
        p.start()

    try:
        # Import only after patches are active.
        from app.main import app

        with TestClient(app) as client:
            print("\nPosting activity to /teams/messages …")
            response = client.post("/teams/messages", json=activity)
            print(f"HTTP {response.status_code}")
            try:
                response_body = response.json()
                print("Response body:", json.dumps(response_body, indent=2)[:1000])
            except Exception:
                response_body = {}
                print("Response body:", response.text[:1000])

            # Optional second leg: simulate a button-tap approving a variant.
            if args.approve_variant is not None:
                posted = (response_body or {}).get("approval_cards_posted") or []
                if not posted:
                    print("\n[approve-variant] no approval was created in step 1 — skipping tap.")
                else:
                    approval_id = posted[0]
                    tap_activity = _build_activity(
                        text="",
                        team_id=config.teams.team_id,
                        channel_id=config.teams.channel_id,
                    )
                    tap_activity["value"] = {
                        "kind": "approve_site_variant",
                        "approval_id": approval_id,
                        "selected_variant": args.approve_variant,
                    }
                    print(
                        f"\nSimulating Action.Submit tap | "
                        f"approval_id={approval_id} variant={args.approve_variant}"
                    )
                    tap_response = client.post("/teams/messages", json=tap_activity)
                    print(f"HTTP {tap_response.status_code}")
                    try:
                        print("Response body:", json.dumps(tap_response.json(), indent=2)[:800])
                    except Exception:
                        print("Response body:", tap_response.text[:800])
    finally:
        for p in patches:
            p.stop()

    _print_captured(captured_text, captured_cards)

    # Verify variation files landed on disk.
    sites_dir = Path("client_artifacts") / args.client / "03_Deliverables" / "sites"
    print("\n" + "=" * 72)
    print("LOCAL ARTIFACTS")
    print("=" * 72)
    if sites_dir.exists():
        for entry in sorted(sites_dir.iterdir()):
            if entry.is_dir() and entry.name.startswith("variation-"):
                idx = entry / "index.html"
                size = idx.stat().st_size if idx.exists() else 0
                print(f"  {entry.name}/index.html  ({size:,} bytes)")
        idx_main = sites_dir / "index.html"
        if idx_main.exists():
            print(f"  index.html ({idx_main.stat().st_size:,} bytes)")
    else:
        print(f"  (no sites dir at {sites_dir} — Dylan didn't fire)")

    if promotion_calls:
        print("\n" + "=" * 72)
        print("PROMOTION CALLS")
        print("=" * 72)
        for call in promotion_calls:
            print(f"  promote_to_production(client_id={call['client_id']!r}, source_dir={call['source_dir']!r})")

    print("\nSmoke run complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
