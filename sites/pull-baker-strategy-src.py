"""Download baker-strategy production source from Vercel deployment."""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

TOKEN = json.loads(Path.home().joinpath("AppData/Roaming/xdg.data/com.vercel.cli/auth.json").read_text())["token"]
TEAM_ID = "team_Ty4bEdMWqsvxqi1L710BAFFh"
DEPLOYMENT = "dpl_4KaL9MaSSd5hmPjvzm3oKDaRfv5V"
OUT = Path(__file__).resolve().parent / "baker-strategy-src"


def api(path: str) -> dict | list:
    url = f"https://api.vercel.com{path}?teamId={TEAM_ID}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def download_file(uid: str, dest: Path) -> None:
    url = f"https://api.vercel.com/v8/deployments/{DEPLOYMENT}/files/{uid}?teamId={TEAM_ID}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read().decode())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(payload["data"]))


def walk(path: str, prefix: Path) -> None:
    import urllib.parse

    q = urllib.parse.quote(path) if path else ""
    suffix = f"?path={q}" if q else ""
    entries = api(f"/v6/deployments/{DEPLOYMENT}/files{suffix}")
    for entry in entries:
        name = entry["name"]
        target = prefix / name
        if entry["type"] == "directory":
            walk(f"{path}/{name}" if path else name, target)
        else:
            print(f"  {target}")
            download_file(entry["uid"], target)


if __name__ == "__main__":
    if OUT.exists():
        import shutil

        shutil.rmtree(OUT)
    print(f"Downloading to {OUT}")
    walk("src", OUT)
