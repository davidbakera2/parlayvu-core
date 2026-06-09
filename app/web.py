"""Shared server-rendered web layer for parlayvu.ai (login + subscription).

Holds the single Jinja2 templates instance used by the auth and billing
routers so both render from the same ``app/templates`` directory.
"""
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Session cookie name shared by the auth router and dependencies.
SESSION_COOKIE = "pv_session"
