"""Per-client configuration loaded from client_artifacts/<client_id>/config.yaml.

This is the contract every ParlayVU client honors. Onboarding a new client is
a config + folder task — no code change required — as long as their YAML
matches this schema:

    client_id: <id>                  # required, must match folder name
    display_name: "<Pretty Name>"    # required
    teams:
      team_id: "<guid>"              # required
      channel_id: "<guid>"           # required
      meeting_notes_folder: "..."    # optional, defaults to 03_Deliverables/Meeting Notes
      template_path: "..."           # optional, defaults to 06_Templates/Meeting_Notes_Template.docx
    cloudflare:                      # optional block; defaults to convention
      preview_project: "<id>-previews"   # defaults to <client_id>-previews
      production_project: "<id>"         # defaults to <client_id>
      production_domain: "<host>"        # optional; used in Teams reply text
    preferences:
      pronunciation: { ... }
      tone: "..."
      authorized_contacts: [ ... ]
    active_workflows: [ "podcast-parlay", "meeting-notes", ... ]  # optional list of workflow package ids (see workflow-packages-design.md and app/workflow_packages/)

The Cloudflare Pages naming convention (<client_id>-previews for staging,
<client_id> for production) means a new client gets correct deploy bindings
purely from their client_id — no config writes needed unless they want to
deviate from the convention.
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

# Cloudflare Pages naming convention for the ParlayVU client website workflow:
#   prod    = <client_id>           (custom domain attached here)
#   preview = <client_id>-previews  (auto-created on first deploy)
# A client can override by setting cloudflare.production_project /
# cloudflare.preview_project in their config.yaml, but defaults serve the
# common case so onboarding a new client requires zero per-client code.
CLOUDFLARE_PREVIEW_SUFFIX = "-previews"


class ClientConfigError(Exception):
    """Raised when a client's config.yaml is missing or malformed."""


@dataclass(frozen=True)
class TeamsConfig:
    team_id: str
    channel_id: str
    meeting_notes_folder: str = DEFAULT_MEETING_NOTES_FOLDER
    template_path: str = DEFAULT_MEETING_NOTES_TEMPLATE_PATH


@dataclass(frozen=True)
class CloudflareConfig:
    preview_project: str
    production_project: str
    production_domain: Optional[str] = None


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
    cloudflare: Optional[CloudflareConfig] = None
    # Workflow packages enabled for this client (viktor.com-style "packages of workflows").
    # None  = key omitted → un-migrated client; the packages layer treats this as "all
    #         packages active" for backward compatibility.
    # []    = explicitly no packages.
    # [...] = exactly these packages.
    active_workflows: Optional[list[str]] = None

    @property
    def artifacts_dir(self) -> Path:
        return CLIENT_ARTIFACTS_ROOT / self.client_id

    @property
    def cloudflare_config(self) -> CloudflareConfig:
        """Return cloudflare config, deriving convention defaults if unset.

        The YAML loader always populates `cloudflare`. Tests and ad-hoc
        construction can leave it None — this property gives callers a single
        accessor that always returns a usable config, so service code never
        needs a None check.
        """
        if self.cloudflare is not None:
            return self.cloudflare
        return CloudflareConfig(
            preview_project=f"{self.client_id}{CLOUDFLARE_PREVIEW_SUFFIX}",
            production_project=self.client_id,
        )


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

    cloudflare_raw = raw.get("cloudflare") or {}
    if not isinstance(cloudflare_raw, dict):
        raise ClientConfigError(f"{path}: 'cloudflare' must be a mapping")
    production_domain_raw = cloudflare_raw.get("production_domain")
    cloudflare = CloudflareConfig(
        preview_project=str(
            cloudflare_raw.get("preview_project")
            or f"{client_id}{CLOUDFLARE_PREVIEW_SUFFIX}"
        ),
        production_project=str(
            cloudflare_raw.get("production_project") or client_id
        ),
        production_domain=(
            str(production_domain_raw).strip() if production_domain_raw else None
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

    if "active_workflows" in raw:
        active_workflows_raw = raw.get("active_workflows")
        if active_workflows_raw is None:
            active_workflows = []  # `active_workflows:` with no value → explicitly none
        elif isinstance(active_workflows_raw, list):
            active_workflows = [str(w).strip() for w in active_workflows_raw if str(w).strip()]
        else:
            raise ClientConfigError(f"{path}: active_workflows must be a list (omit the key to leave it unset)")
    else:
        active_workflows = None  # key omitted → un-migrated; treated as "all packages"

    return ClientConfig(
        client_id=client_id,
        display_name=display_name,
        teams=teams,
        preferences=preferences,
        cloudflare=cloudflare,
        active_workflows=active_workflows,
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
