"""Per-client configuration loaded from client_artifacts/<client_id>/config.yaml.

Replaces the singleton M365_FILES_TEAM_ID / M365_FILES_CHANNEL_ID env vars so
ParlayVU can publish meeting notes and apply per-client preferences for more
than one client.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml


CLIENT_ARTIFACTS_ROOT = Path(
    os.getenv("CLIENT_ARTIFACTS_ROOT", "client_artifacts")
)
DEFAULT_MEETING_NOTES_FOLDER = "03_Deliverables/Meeting Notes"
# Canonical meeting-notes template location. Every client has the same path —
# only the content of the docx varies. New clients inherit this default by
# leaving teams.template_path unset in their config.yaml.
DEFAULT_MEETING_NOTES_TEMPLATE_PATH = "06_Templates/Meeting_Notes_Template.docx"


class ClientConfigError(Exception):
    """Raised when a client's config.yaml is missing or malformed."""


@dataclass(frozen=True)
class TeamsConfig:
    team_id: str
    channel_id: str
    meeting_notes_folder: str = DEFAULT_MEETING_NOTES_FOLDER
    template_path: str = DEFAULT_MEETING_NOTES_TEMPLATE_PATH


@dataclass(frozen=True)
class ClientPreferences:
    pronunciation: dict[str, str] = field(default_factory=dict)
    tone: Optional[str] = None
    authorized_contacts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClientConfig:
    client_id: str
    display_name: str
    teams: TeamsConfig
    preferences: ClientPreferences

    @property
    def artifacts_dir(self) -> Path:
        return CLIENT_ARTIFACTS_ROOT / self.client_id


def _config_path(client_id: str) -> Path:
    return CLIENT_ARTIFACTS_ROOT / client_id / "config.yaml"


@lru_cache(maxsize=64)
def load_client_config(client_id: str) -> ClientConfig:
    """Load and validate a client's config.yaml.

    Raises ClientConfigError with a clear message if the file is missing,
    cannot be parsed, or is missing required fields.
    """
    if not client_id or not client_id.strip():
        raise ClientConfigError("client_id is required")

    path = _config_path(client_id)
    if not path.is_file():
        raise ClientConfigError(
            f"No client config at {path}. Create client_artifacts/{client_id}/config.yaml "
            f"to onboard this client."
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ClientConfigError(f"Malformed YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ClientConfigError(f"{path} must contain a YAML mapping at the top level")

    file_client_id = str(raw.get("client_id") or "").strip()
    if file_client_id and file_client_id != client_id:
        raise ClientConfigError(
            f"{path} declares client_id={file_client_id!r} but was loaded as {client_id!r}"
        )

    display_name = str(raw.get("display_name") or client_id)

    teams_raw = raw.get("teams") or {}
    if not isinstance(teams_raw, dict):
        raise ClientConfigError(f"{path}: 'teams' must be a mapping")
    team_id = str(teams_raw.get("team_id") or "").strip()
    channel_id = str(teams_raw.get("channel_id") or "").strip()
    if not team_id or not channel_id:
        raise ClientConfigError(
            f"{path}: teams.team_id and teams.channel_id are required"
        )

    teams = TeamsConfig(
        team_id=team_id,
        channel_id=channel_id,
        meeting_notes_folder=str(
            teams_raw.get("meeting_notes_folder") or DEFAULT_MEETING_NOTES_FOLDER
        ),
        template_path=str(
            teams_raw.get("template_path") or DEFAULT_MEETING_NOTES_TEMPLATE_PATH
        ),
    )

    prefs_raw = raw.get("preferences") or {}
    if not isinstance(prefs_raw, dict):
        raise ClientConfigError(f"{path}: 'preferences' must be a mapping")

    pronunciation_raw = prefs_raw.get("pronunciation") or {}
    if not isinstance(pronunciation_raw, dict):
        raise ClientConfigError(f"{path}: preferences.pronunciation must be a mapping")
    pronunciation = {str(k): str(v) for k, v in pronunciation_raw.items()}

    tone = prefs_raw.get("tone")
    tone_str = str(tone).strip() if tone else None

    contacts_raw = prefs_raw.get("authorized_contacts") or []
    if not isinstance(contacts_raw, list):
        raise ClientConfigError(
            f"{path}: preferences.authorized_contacts must be a list"
        )
    authorized_contacts = [str(c).strip() for c in contacts_raw if str(c).strip()]

    preferences = ClientPreferences(
        pronunciation=pronunciation,
        tone=tone_str,
        authorized_contacts=authorized_contacts,
    )

    return ClientConfig(
        client_id=client_id,
        display_name=display_name,
        teams=teams,
        preferences=preferences,
    )


def list_clients() -> list[str]:
    """Return client_ids of every client_artifacts/<id>/config.yaml on disk."""
    if not CLIENT_ARTIFACTS_ROOT.is_dir():
        return []
    return sorted(
        p.parent.name
        for p in CLIENT_ARTIFACTS_ROOT.glob("*/config.yaml")
        if p.is_file()
    )


def clear_client_config_cache() -> None:
    """Reset the lru_cache. Tests call this to isolate fixtures."""
    load_client_config.cache_clear()
