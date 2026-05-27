"""Client-aware deploy primitives — the spine of every ParlayVU website workflow.

`deploy_preview()` and `promote_to_production()` are the canonical entry points.
Every workflow (variations, edits, future ones) calls these instead of touching
Cloudflare directly. Both functions read destination Pages project names from
the client's config — there is no per-client deploy code anywhere else.

Convention: a client's currently-live site is mirrored locally at
`client_artifacts/<client>/03_Deliverables/sites/active/`. Promoting any
variant or edit replaces `active/` and deploys it to prod. Subsequent edit
workflows read from `active/` as the source of truth.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from app.client_config import CLIENT_ARTIFACTS_ROOT, load_client_config

logger = logging.getLogger("parlayvu.services.client_deploy")

SITES_SUBPATH = Path("03_Deliverables") / "sites"
ACTIVE_DIR_NAME = "active"


def client_sites_root(client_id: str) -> Path:
    """Resolved path of <repo>/client_artifacts/<client_id>/03_Deliverables/sites/."""
    return (CLIENT_ARTIFACTS_ROOT / client_id / SITES_SUBPATH).resolve()


def client_active_dir(client_id: str) -> Path:
    """Resolved path of the active (currently-live) site source for this client."""
    return (client_sites_root(client_id) / ACTIVE_DIR_NAME).resolve()


def _assert_inside_client_sites(client_id: str, candidate: Path) -> Path:
    """Raise unless `candidate` resolves inside the client's sites root."""
    candidate = candidate.resolve()
    root = client_sites_root(client_id)
    if candidate == root or candidate.is_relative_to(root):
        return candidate
    raise ValueError(
        f"Path {candidate!r} is outside client {client_id!r}'s sites root ({root})."
    )


def deploy_preview(
    client_id: str,
    source_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Deploy a directory to the client's preview Pages project.

    The destination project is taken from `config.cloudflare_config.preview_project`
    (which defaults to `<client_id>-previews` by convention).

    Args:
        client_id: ParlayVU client id.
        source_dir: Directory to deploy. Defaults to the client's full
            sites/ folder (so e.g. the variations index lists every variant).
            Pass a specific subdirectory to deploy just that one.

    Returns the wrangler-helper result dict (status, project_name, url, ...).
    """
    from app.agents.tools.dylan_tools import deploy_static_directory_to_cloudflare

    config = load_client_config(client_id)
    project_name = config.cloudflare_config.preview_project

    if source_dir is None:
        source_dir = client_sites_root(client_id)
    source_dir = _assert_inside_client_sites(client_id, Path(source_dir))

    logger.info(
        "deploy_preview | client=%s project=%s source=%s",
        client_id, project_name, source_dir,
    )
    result = deploy_static_directory_to_cloudflare(source_dir, project_name)
    # Tag the result so callers don't need a separate config lookup.
    result.setdefault("project_name", project_name)
    result["preview_project"] = project_name
    return result


def promote_to_production(
    client_id: str,
    source_dir: Path,
) -> dict[str, Any]:
    """Make `source_dir` the new active site and deploy it to production.

    Steps:
      1. Validate `source_dir` is inside the client's sites/ tree (no path
         escapes).
      2. Replace `client_artifacts/<client>/03_Deliverables/sites/active/`
         with a copy of `source_dir`.
      3. Deploy `active/` to the client's production Pages project (from
         `config.cloudflare_config.production_project`, defaults to `<client_id>`).

    Returns the wrangler-helper result dict, augmented with:
      - `production_domain`: from config (the human-friendly URL the client uses)
      - `active_dir`: filesystem path to the new active/ folder

    Raises:
        ClientConfigError: if the client isn't onboarded.
        ValueError: if source_dir is missing, is the active dir itself, or
            escapes the client's sites root.
    """
    from app.agents.tools.dylan_tools import deploy_static_directory_to_cloudflare

    config = load_client_config(client_id)
    cf = config.cloudflare_config

    source_dir = _assert_inside_client_sites(client_id, Path(source_dir))
    if not source_dir.is_dir():
        raise ValueError(f"promote_to_production: source_dir not found: {source_dir}")

    active_dir = client_active_dir(client_id)
    if source_dir == active_dir:
        raise ValueError(
            "promote_to_production: source_dir is already active/. Pass the "
            "variation or edit directory, not active/ itself."
        )

    # Replace active/ atomically-ish — remove then copytree. The window is
    # tiny but the deploy step below is the actual cutover point for the
    # live site anyway, so a brief filesystem gap doesn't affect users.
    if active_dir.exists():
        shutil.rmtree(active_dir)
    shutil.copytree(source_dir, active_dir)
    logger.info(
        "Promoted active site | client=%s from=%s active=%s",
        client_id, source_dir, active_dir,
    )

    result = deploy_static_directory_to_cloudflare(active_dir, cf.production_project)
    result.setdefault("project_name", cf.production_project)
    result["production_project"] = cf.production_project
    result["production_domain"] = cf.production_domain
    result["active_dir"] = str(active_dir)
    return result
