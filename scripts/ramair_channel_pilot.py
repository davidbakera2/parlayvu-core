from pathlib import Path
import argparse
import os
import sys

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ramair_channel import (
    RAMAIR_CLIENT_ID,
    RAMAIR_PROJECT_ID,
    RAMAIR_PROJECT_NAME,
    binding_status_from_env,
    render_ramair_channel_pilot,
)


def bind_ramair_channel_from_env(env: dict[str, str] | None = None) -> dict[str, object]:
    active_env = env or os.environ
    status = binding_status_from_env(active_env)
    if not status["configured"]:
        return {
            "status": "blocked",
            "reason": "Missing real Teams identifiers.",
            "missing": status["missing"],
            "in_teams_path": status["in_teams_path"],
            "command": status["command"],
        }

    try:
        from app.database import initialize_database, session_scope
        from app.models import Client, Project
        from app.project_memory import bind_teams_channel

        initialize_database()
        with session_scope() as session:
            # Ensure the RamAir client + project rows exist so the channel binding
            # FK resolves. (Previously handled by the now-removed demo seeder.)
            if session.get(Client, RAMAIR_CLIENT_ID) is None:
                session.add(Client(id=RAMAIR_CLIENT_ID, name="RamAir International"))
            if session.get(Project, RAMAIR_PROJECT_ID) is None:
                session.add(
                    Project(
                        id=RAMAIR_PROJECT_ID,
                        client_id=RAMAIR_CLIENT_ID,
                        name=RAMAIR_PROJECT_NAME,
                    )
                )

        binding = bind_teams_channel(
            team_id=str(status["team_id"]),
            channel_id=str(status["channel_id"]),
            channel_name=str(status["channel_name"]),
            client_id=RAMAIR_CLIENT_ID,
            project_id=RAMAIR_PROJECT_ID,
            project_name=RAMAIR_PROJECT_NAME,
            bound_by=str(status["bound_by"] or "ramair_channel_pilot.py"),
        )
        return {"status": "bound", "binding": binding}
    except Exception as exc:
        return {
            "status": "blocked",
            "reason": str(exc),
            "in_teams_path": status["in_teams_path"],
            "command": status["command"],
        }


def render_binding_result(result: dict[str, object]) -> str:
    if result["status"] == "bound":
        binding = result["binding"]
        return "\n".join(
            [
                "RamAir Teams channel bound to project memory.",
                f"team_id: {binding['team_id']}",
                f"channel_id: {binding['channel_id']}",
                f"project_id: {binding['project_id']}",
            ]
        )

    lines = [
        "RamAir Teams channel binding is blocked locally.",
        f"Reason: {result.get('reason')}",
    ]
    missing = result.get("missing") or []
    if missing:
        lines.append(f"Missing: {', '.join(missing)}")
    lines.extend(["", "Bind it in Teams with:"])
    lines.extend(f"{index}. {step}" for index, step in enumerate(result["in_teams_path"], start=1))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render or bind the RamAir Teams channel pilot.")
    parser.add_argument("--bind", action="store_true", help="Bind using RAMAIR_TEAMS_TEAM_ID and RAMAIR_TEAMS_CHANNEL_ID.")
    args = parser.parse_args()

    load_dotenv()
    if args.bind:
        print(render_binding_result(bind_ramair_channel_from_env()))
        return

    print(render_ramair_channel_pilot())


if __name__ == "__main__":
    main()
