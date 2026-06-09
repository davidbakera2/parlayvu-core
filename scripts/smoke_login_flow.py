"""End-to-end smoke test for the parlayvu.ai login + dashboard gating flow.

Drives the real FastAPI routes (real DB, templates, and session cookie) against
a throwaway SQLite database. No Stripe or Resend needed — with no RESEND_API_KEY
the magic-link URL is logged, and this script reads it back the same way you
would from the dev server log.

    python scripts/smoke_login_flow.py

Exits non-zero if any step fails.
"""
import logging
import os
import sys
import tempfile
from pathlib import Path

# Must be set BEFORE importing the app (engine is built at import time).
_db_path = Path(tempfile.gettempdir()) / "parlayvu_smoke_login.db"
if _db_path.exists():
    _db_path.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path.as_posix()}"
os.environ.pop("RESEND_API_KEY", None)
os.environ.pop("RESEND_API", None)
os.environ["APP_BASE_URL"] = "http://localhost:8000"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_engine, initialize_database  # noqa: E402
from app.main import app  # noqa: E402

EMAIL = "test-client@example.com"


class _LinkCatcher(logging.Handler):
    """Captures the magic-link URL the app logs when no email provider is set."""

    def __init__(self):
        super().__init__()
        self.link = None

    def emit(self, record):
        args = record.args or ()
        if len(args) == 2 and isinstance(args[1], str) and "/auth/verify" in args[1]:
            self.link = args[1]


def main() -> int:
    initialize_database(get_engine())  # dev helper — fine for a throwaway DB

    catcher = _LinkCatcher()
    logging.getLogger("parlayvu.auth").addHandler(catcher)

    client = TestClient(app)
    failures = []

    def check(label, ok, detail=""):
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    print("1. Login page")
    r = client.get("/login")
    check("GET /login returns the sign-in form", r.status_code == 200 and "Sign in" in r.text)

    print("2. Request magic link")
    r = client.post("/auth/request-link", data={"email": EMAIL}, follow_redirects=False)
    check("POST /auth/request-link shows 'check your email'",
          r.status_code == 200 and "Check your email" in r.text)
    check("magic-link URL was generated", catcher.link is not None,
          catcher.link or "no link captured")

    print("3. Verify the link -> session cookie")
    token = (catcher.link or "").split("token=", 1)[-1]
    r = client.get(f"/auth/verify?token={token}", follow_redirects=False)
    cookie_set = "pv_session" in r.headers.get("set-cookie", "")
    check("GET /auth/verify redirects to /dashboard",
          r.status_code == 303 and r.headers.get("location") == "/dashboard")
    check("session cookie is set", cookie_set)

    print("4. Single-use: replaying the same link fails")
    r = client.get(f"/auth/verify?token={token}", follow_redirects=False)
    check("replayed link redirects to /login?error=invalid",
          r.status_code == 303 and "error=invalid" in r.headers.get("location", ""))

    print("5. Dashboard shows the subscribe CTA - no subscription yet")
    r = client.get("/dashboard")
    check("GET /dashboard is gated open and shows $800 subscribe CTA",
          r.status_code == 200 and "Subscribe" in r.text and "$800" in r.text)

    print("6. Logout clears the session")
    r = client.post("/auth/logout", follow_redirects=False)
    check("POST /auth/logout redirects to /login", r.status_code == 303)
    client.cookies.clear()
    r = client.get("/dashboard", follow_redirects=False)
    check("anonymous /dashboard redirects to /login",
          r.status_code == 303 and r.headers.get("location") == "/login")

    print()
    if failures:
        print(f"SMOKE TEST FAILED: {len(failures)} step(s) failed: {', '.join(failures)}")
        return 1
    print("SMOKE TEST PASSED — login + dashboard gating work end-to-end.")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        try:
            get_engine().dispose()  # release the SQLite file handle before unlink
        except Exception:
            pass
        if _db_path.exists():
            try:
                _db_path.unlink()
            except OSError:
                pass  # Windows may briefly hold the handle; the next run overwrites it
    raise SystemExit(code)
