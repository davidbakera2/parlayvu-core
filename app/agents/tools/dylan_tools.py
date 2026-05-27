# parlayvu-core/app/agents/tools/dylan_tools.py
from datetime import datetime
from html import escape
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_core.tools import tool


GENERATED_SITES_DIR = Path("generated_sites")
SITES_DIR = Path("sites")
TEMPLATE_DIR = SITES_DIR / "_template"


def _read_site_contact(site_dir: Path) -> Dict[str, Any]:
    path = site_dir / "site.contact.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _display_title(site_name: str) -> str:
    words = site_name.replace("-", " ").split()
    return " ".join("AI" if word.lower() == "ai" else word.capitalize() for word in words)

@tool
def scaffold_parlayvu_client_site(
    client_slug: str,
    domain: str,
    contact_to: str,
    contact_from: str,
    brand_name: Optional[str] = None,
    pages_project: Optional[str] = None,
    deploy: bool = False,
) -> Dict[str, Any]:
    """
    Scaffold a ParlayVU client marketing site under sites/<slug>/ from sites/_template.
    Astro + Cloudflare Pages + Resend contact form. See sites/PARLAYVU_CLIENT_SITES.md.
    """
    script = SITES_DIR / "scripts" / "launch-client.mjs"
    if not script.exists():
        return {"status": "error", "message": f"Missing launch script: {script}"}

    args = [
        "node",
        str(script),
        client_slug,
        "--domain",
        domain,
        "--to",
        contact_to,
        "--from",
        contact_from,
    ]
    if brand_name:
        args.extend(["--brand", brand_name])
    if pages_project:
        args.extend(["--pages-project", pages_project])
    if deploy:
        args.append("--deploy")

    result = subprocess.run(
        args,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    site_dir = SITES_DIR / _slugify(client_slug, client_slug)

    if result.returncode != 0:
        return {
            "status": "error",
            "message": "ParlayVU client scaffold failed.",
            "stdout": result.stdout[-4000:] if result.stdout else "",
            "stderr": result.stderr[-4000:] if result.stderr else "",
            "details": output[-4000:],
        }

    return {
        "status": "success",
        "site_path": str(site_dir),
        "message": f"ParlayVU client site scaffolded at {site_dir}",
        "stdout": result.stdout[-4000:] if result.stdout else "",
        "playbook": "sites/PARLAYVU_CLIENT_SITES.md",
        "resend_setup": "sites/RESEND_SETUP.md",
        "deployment_hint": f"cd {site_dir} && npm run pages:deploy",
    }


@tool
def generate_astro_site(
    content: str,
    site_name: str = "marketing-landing",
    client_id: str = "default-client",
    brand_voice: str = "Professional, modern, and conversion-focused"
) -> Dict[str, Any]:
    """
    Generate a complete, production-ready Astro + Tailwind marketing landing page.
    Automatically creates the folder structure under generated_sites/.
    """
    safe_name = _slugify(site_name, "marketing-landing")
    safe_client_id = _slugify(client_id, "default-client")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    site_dir = GENERATED_SITES_DIR / safe_client_id / f"{safe_name}-{timestamp}"
    pages_dir = site_dir / "src" / "pages"
    layouts_dir = site_dir / "src" / "layouts"
    styles_dir = site_dir / "src" / "styles"
    pages_dir.mkdir(parents=True, exist_ok=True)
    layouts_dir.mkdir(parents=True, exist_ok=True)
    styles_dir.mkdir(parents=True, exist_ok=True)

    files: Dict[str, str] = {}
    display_title = _display_title(site_name)
    escaped_brand_voice = escape(brand_voice)
    escaped_content = escape(content)
    page_title = json.dumps(display_title)
    page_description = json.dumps("AI-powered content repurposing landing page")

    hero_headline = content[:80].split(".")[0] + "..." if len(content) > 80 else content
    escaped_headline = escape(hero_headline)
    index_astro = f"""---
import Layout from '../layouts/Layout.astro';
const pageTitle = {page_title};
const pageDescription = {page_description};
---

<Layout title={{pageTitle}} description={{pageDescription}}>
  <main class="parlay-shell">
    <header class="mx-auto flex max-w-6xl items-center justify-between px-6 py-7">
      <a href="#" class="text-2xl font-black tracking-tight">ParlayVu</a>
      <nav class="hidden items-center gap-8 text-sm font-semibold uppercase tracking-[0.2em] text-[#52645d] md:flex">
        <a href="#start">Method</a>
        <a href="#assets">Team</a>
        <a href="#message">Contact</a>
        <a href="#subscribe">Start</a>
      </nav>
    </header>

    <section class="px-6 pb-16 pt-10 sm:pb-24">
      <div class="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <p class="mb-5 text-sm font-bold uppercase tracking-[0.28em] text-[#a25f2b]">AI-powered content systems</p>
          <h1 class="max-w-4xl text-5xl font-black leading-[0.95] tracking-tight text-[#20352f] sm:text-6xl lg:text-7xl">
            {escaped_headline}
          </h1>
          <p class="mt-7 max-w-2xl text-xl leading-8 text-[#52645d]">
            Turn one blog, interview, podcast, or social post into threads, ads, emails, reels, shorts, and more.
          </p>
          <div class="mt-10 flex flex-col gap-4 sm:flex-row">
            <a href="#start" class="rounded-full bg-[#20352f] px-8 py-4 text-center font-bold text-white shadow-lg shadow-black/10 transition hover:bg-[#304d45]">
              Start Your Parlay
            </a>
            <a href="#assets" class="rounded-full border-2 border-[#20352f]/20 px-8 py-4 text-center font-bold text-[#20352f] transition hover:border-[#20352f]">
              Meet The Team
            </a>
          </div>
        </div>
        <div class="overflow-hidden rounded-[2rem] bg-[#20352f] shadow-2xl shadow-[#20352f]/20">
          <div class="aspect-[4/3] bg-[linear-gradient(135deg,_#d9904f,_#f3d7a6_52%,_#7f9b8f)] p-8">
            <div class="flex h-full flex-col justify-end rounded-[1.5rem] border border-white/40 bg-white/75 p-7 backdrop-blur">
              <p class="text-sm font-bold uppercase tracking-[0.25em] text-[#a25f2b]">Web & Deployment</p>
              <p class="mt-4 text-2xl font-black leading-tight text-[#20352f]">Dylan Brooks</p>
              <p class="mt-4 text-base font-semibold leading-relaxed text-[#20352f]">{escaped_content}</p>
            </div>
          </div>
          <div class="grid gap-4 p-6 text-white sm:grid-cols-2">
            <div>
              <p class="text-sm uppercase tracking-[0.25em] text-white/55">Brand Voice</p>
              <p class="mt-2 font-semibold">{escaped_brand_voice}</p>
            </div>
            <div>
              <p class="text-sm uppercase tracking-[0.25em] text-white/55">Output</p>
              <p class="mt-2 font-semibold">Astro site plus campaign-ready sections</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="border-y border-[#20352f]/10 bg-white/55 px-6 py-10">
      <div class="mx-auto grid max-w-6xl gap-6 text-center md:grid-cols-3">
        <div>
          <p class="text-3xl font-black text-[#20352f]">1</p>
          <p class="mt-2 font-semibold text-[#52645d]">source idea</p>
        </div>
        <div>
          <p class="text-3xl font-black text-[#20352f]">12+</p>
          <p class="mt-2 font-semibold text-[#52645d]">campaign assets</p>
        </div>
        <div>
          <p class="text-3xl font-black text-[#20352f]">1</p>
          <p class="mt-2 font-semibold text-[#52645d]">simple client experience</p>
        </div>
      </div>
    </section>

    <section id="start" class="px-6 py-20">
      <div class="mx-auto max-w-6xl">
        <p class="text-sm font-bold uppercase tracking-[0.28em] text-[#a25f2b]">The Parlay Method</p>
        <h2 class="mt-4 max-w-3xl text-4xl font-black tracking-tight sm:text-5xl">One source idea, many useful assets.</h2>
        <div class="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          <a href="#assets" class="rounded-[1.75rem] bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-xl">
            <h3 class="text-2xl font-black">Parlay Engine</h3>
            <p class="mt-4 text-[#52645d]">The core AI engine intelligently parlays your content across formats and platforms.</p>
            <p class="mt-6 font-bold text-[#a25f2b]">Start engine -></p>
          </a>
          <a href="#assets" class="rounded-[1.75rem] bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-xl">
            <h3 class="text-2xl font-black">Content Repurpose</h3>
            <p class="mt-4 text-[#52645d]">Transform one idea into threads, ads, emails, shorts, reels, and social posts.</p>
            <p class="mt-6 font-bold text-[#a25f2b]">Repurpose -></p>
          </a>
          <a href="#assets" class="rounded-[1.75rem] bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-xl">
            <h3 class="text-2xl font-black">Engagement Boost</h3>
            <p class="mt-4 text-[#52645d]">Use AI-optimized strategies to maximize reach, interactions, and conversions.</p>
            <p class="mt-6 font-bold text-[#a25f2b]">Boost reach -></p>
          </a>
          <a href="#subscribe" class="rounded-[1.75rem] bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-xl">
            <h3 class="text-2xl font-black">Human Review</h3>
            <p class="mt-4 text-[#52645d]">Keep approval gates, quality checks, and final delivery decisions visible.</p>
            <p class="mt-6 font-bold text-[#a25f2b]">Review -></p>
          </a>
        </div>
      </div>
    </section>

    <section id="message" class="bg-[#20352f] px-6 py-20 text-white">
      <div class="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[0.9fr_1.1fr]">
        <div>
          <p class="text-sm font-bold uppercase tracking-[0.28em] text-[#f3d7a6]">The Team</p>
          <h2 class="mt-4 text-4xl font-black tracking-tight sm:text-5xl">Nathan leads the orchestration.</h2>
        </div>
        <div class="rounded-[2rem] bg-white p-8 text-[#20352f]">
          <h3 class="text-3xl font-black">Dylan turns strategy into pages.</h3>
          <p class="mt-5 text-lg leading-8 text-[#52645d]">
            Below Nathan, specialist agents operate with defined roles, approval boundaries, and quality checks.
          </p>
          <a href="#subscribe" class="mt-8 inline-flex rounded-full bg-[#d9904f] px-7 py-3 font-bold text-white transition hover:bg-[#b86e31]">
            Play Intro
          </a>
        </div>
      </div>
    </section>

    <section id="assets" class="px-6 py-20">
      <div class="mx-auto max-w-6xl">
        <p class="text-sm font-bold uppercase tracking-[0.28em] text-[#a25f2b]">Web & Deployment</p>
        <div class="mt-10 grid gap-6 md:grid-cols-3">
          <div class="rounded-[2rem] border border-[#20352f]/10 bg-white/70 p-8">
            <h3 class="text-2xl font-black">Landing Page</h3>
            <p class="mt-4 text-[#52645d]">Hero, benefits, proof, pathways, and CTA sections ready for Astro.</p>
          </div>
          <div class="rounded-[2rem] border border-[#20352f]/10 bg-white/70 p-8">
            <h3 class="text-2xl font-black">Campaign Map</h3>
            <p class="mt-4 text-[#52645d]">A clear view of how one idea turns into follow-up assets.</p>
          </div>
          <div class="rounded-[2rem] border border-[#20352f]/10 bg-white/70 p-8">
            <h3 class="text-2xl font-black">Deployment Path</h3>
            <p class="mt-4 text-[#52645d]">Local build output now, Cloudflare Pages deployment next.</p>
          </div>
        </div>
      </div>
    </section>

    <section id="subscribe" class="px-6 pb-20">
      <div class="mx-auto max-w-6xl rounded-[2rem] bg-[#d9904f] p-10 text-center text-white sm:p-16">
        <p class="text-sm font-bold uppercase tracking-[0.28em] text-white/75">Ready to scale your reach?</p>
        <h2 class="mt-4 text-4xl font-black tracking-tight sm:text-5xl">Send the raw content. We will build the Parlay.</h2>
        <p class="mx-auto mt-5 max-w-2xl text-lg text-white/85">Fill out the form or email the team and ParlayVU will be in touch with a clear production path.</p>
        <a href="mailto:hello@parlayvu.ai" class="mt-8 inline-flex rounded-full bg-[#20352f] px-10 py-4 font-bold text-white transition hover:bg-[#304d45]">
          Book a Strategy Call
        </a>
      </div>
    </section>
  </main>
</Layout>
"""
    (pages_dir / "index.astro").write_text(index_astro, encoding="utf-8")
    files["src/pages/index.astro"] = str(pages_dir / "index.astro")

    layout = """---
export interface Props {
  title: string;
  description?: string;
}
const { title, description } = Astro.props;
---
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <meta name="description" content={description} />
  <style is:global>
    :root {
      color-scheme: dark;
      --cream: #070707;
      --ink: #f5f5f0;
      --muted: #a6a6a6;
      --rust: #f4c430;
      --rust-dark: #f4c430;
      --sage: #1a1a1a;
      --line: rgba(255, 255, 255, 0.12);
      --white: #ffffff;
      --card: #111111;
      --card-soft: #171717;
    }

    * {
      box-sizing: border-box;
    }

    html {
      scroll-behavior: smooth;
    }

    body {
      margin: 0;
      background:
        radial-gradient(circle at 18% 18%, rgba(244, 196, 48, 0.08), transparent 28%),
        linear-gradient(180deg, #050505 0%, #090909 45%, #050505 100%);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    main {
      min-height: 100vh;
      overflow: hidden;
    }

    header {
      width: min(880px, calc(100% - 48px));
      margin: 0 auto;
      padding: 18px 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      border-bottom: 1px solid var(--line);
    }

    header > a {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 0.88rem;
      font-weight: 900;
      letter-spacing: -0.04em;
    }

    header > a::before {
      content: "P";
      display: inline-grid;
      width: 22px;
      height: 22px;
      place-items: center;
      border-radius: 6px;
      background: var(--rust);
      color: #070707;
      font-size: 0.82rem;
      font-weight: 950;
    }

    nav {
      display: flex;
      align-items: center;
      gap: 24px;
      color: var(--muted);
      font-size: 0.66rem;
      font-weight: 800;
      letter-spacing: 0;
      text-transform: none;
    }

    section {
      padding: 64px 24px;
    }

    section:first-of-type {
      padding-top: 74px;
      padding-bottom: 86px;
      border-bottom: 1px solid var(--line);
    }

    section:first-of-type > div,
    section > div {
      width: min(880px, 100%);
      margin: 0 auto;
    }

    section:first-of-type > div {
      display: grid;
      grid-template-columns: 1.05fr 0.95fr;
      align-items: center;
      gap: 70px;
    }

    h1,
    h2,
    h3,
    p {
      margin-top: 0;
    }

    h1 {
      margin-bottom: 28px;
      max-width: 560px;
      font-size: clamp(3rem, 5.4vw, 4.8rem);
      line-height: 0.89;
      letter-spacing: -0.065em;
      font-weight: 950;
    }

    h2 {
      margin-bottom: 0;
      max-width: 540px;
      font-size: clamp(2.25rem, 3.5vw, 3.2rem);
      line-height: 0.95;
      letter-spacing: -0.045em;
      font-weight: 950;
    }

    h3 {
      margin-bottom: 14px;
      font-size: 1.1rem;
      line-height: 1.1;
      letter-spacing: -0.03em;
      font-weight: 850;
    }

    p {
      color: var(--muted);
    }

    p[class*="uppercase"],
    section:first-of-type p:first-child,
    #start > div > p,
    #message p:first-child,
    #assets > div > p,
    #subscribe p:first-child {
      margin-bottom: 18px;
      color: var(--rust-dark);
      font-size: 0.62rem;
      font-weight: 900;
      letter-spacing: 0.22em;
      text-transform: uppercase;
    }

    section:first-of-type h1 + p {
      max-width: 470px;
      font-size: 0.95rem;
      line-height: 1.7;
    }

    section:first-of-type a,
    #message a,
    #subscribe a {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-right: 12px;
      margin-top: 18px;
      border-radius: 999px;
      padding: 12px 20px;
      background: var(--rust);
      color: #050505;
      font-size: 0.68rem;
      font-weight: 850;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      box-shadow: 0 16px 35px rgba(244, 196, 48, 0.08);
    }

    section:first-of-type a + a {
      background: transparent;
      color: var(--ink);
      border: 1px solid rgba(255, 255, 255, 0.16);
      box-shadow: none;
    }

    section:first-of-type > div > div:last-child {
      overflow: hidden;
      border: 1px solid rgba(244, 196, 48, 0.24);
      border-radius: 4px;
      background: var(--card);
      box-shadow: 0 26px 70px rgba(0, 0, 0, 0.35);
    }

    section:first-of-type > div > div:last-child > div:first-child {
      min-height: 270px;
      padding: 22px;
      display: flex;
      align-items: flex-end;
      background:
        linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.72)),
        radial-gradient(circle at 70% 18%, rgba(244, 196, 48, 0.34), transparent 26%),
        linear-gradient(135deg, #2b1e11, #171717 52%, #080808);
    }

    section:first-of-type > div > div:last-child > div:first-child > div {
      width: 100%;
      border-radius: 0;
      padding: 0;
      border: 0;
      background: transparent;
    }

    section:first-of-type > div > div:last-child p {
      margin-bottom: 0;
      color: var(--white);
    }

    section:first-of-type > div > div:last-child > div:last-child {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      padding: 18px;
    }

    section:first-of-type > div > div:last-child > div:last-child p {
      color: rgba(255,255,255,0.76);
    }

    section:first-of-type > div > div:last-child > div:last-child p + p {
      color: var(--white);
      font-weight: 800;
    }

    section:nth-of-type(2) {
      border-bottom: 1px solid var(--line);
      background: transparent;
      padding: 48px 24px;
    }

    section:nth-of-type(2) > div {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 28px;
      text-align: center;
    }

    section:nth-of-type(2) p:first-child {
      margin-bottom: 4px;
      color: var(--ink);
      font-size: 1.45rem;
      font-weight: 950;
    }

    #start > div > div,
    #assets > div > div {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 44px;
    }

    #start a,
    #assets div div div {
      display: block;
      min-height: 150px;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 22px;
      background: linear-gradient(180deg, var(--card-soft), #101010);
      box-shadow: none;
      transition: transform 180ms ease, box-shadow 180ms ease;
    }

    #start a:hover {
      transform: translateY(-4px);
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.22);
    }

    #start a p:last-child {
      margin-top: 26px;
      color: var(--rust-dark);
      font-weight: 900;
    }

    #message {
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      background: #080808;
      color: var(--white);
    }

    #message > div {
      display: grid;
      grid-template-columns: 0.9fr 1.1fr;
      gap: 44px;
      align-items: center;
    }

    #message h2 {
      color: var(--white);
    }

    #message > div > div:last-child {
      border-radius: 32px;
      padding: 30px;
      border: 1px solid rgba(244, 196, 48, 0.22);
      background: var(--card);
      color: var(--ink);
    }

    #message a {
      background: var(--rust);
    }

    #assets > div > div {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    #subscribe {
      padding-top: 24px;
    }

    #subscribe > div {
      border-radius: 32px;
      padding: 64px 40px;
      border: 1px solid rgba(244, 196, 48, 0.26);
      background: linear-gradient(135deg, #151515, #090909);
      color: var(--white);
      text-align: center;
    }

    #subscribe h2,
    #subscribe p {
      margin-left: auto;
      margin-right: auto;
      color: var(--white);
    }

    #subscribe p:last-of-type {
      max-width: 700px;
      color: rgba(255,255,255,0.86);
      font-size: 1.12rem;
    }

    @media (max-width: 900px) {
      nav {
        display: none;
      }

      section:first-of-type > div,
      #message > div {
        grid-template-columns: 1fr;
      }

      #start > div > div,
      #assets > div > div,
      section:nth-of-type(2) > div {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <slot />
</body>
</html>
"""
    (layouts_dir / "Layout.astro").write_text(layout, encoding="utf-8")
    files["src/layouts/Layout.astro"] = str(layouts_dir / "Layout.astro")

    layout = """---
import '../styles/tailwind.css';

export interface Props {
  title: string;
  description?: string;
}
const { title, description } = Astro.props;
---
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <meta name="description" content={description} />
</head>
<body>
  <slot />
</body>
</html>
"""
    (layouts_dir / "Layout.astro").write_text(layout, encoding="utf-8")
    files["src/layouts/Layout.astro"] = str(layouts_dir / "Layout.astro")

    global_css = """@import "tailwindcss";
@source "../**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}";

@layer base {
  :root {
    color-scheme: dark;
    --cream: #070707;
    --ink: #f5f5f0;
    --muted: #a6a6a6;
    --rust: #f4c430;
    --rust-dark: #f4c430;
    --line: rgba(255, 255, 255, 0.12);
    --white: #ffffff;
    --card: #111111;
    --card-soft: #171717;
  }

  * {
    box-sizing: border-box;
  }

  html {
    scroll-behavior: smooth;
  }

  body {
    margin: 0;
    background:
      radial-gradient(circle at 18% 18%, rgba(244, 196, 48, 0.08), transparent 28%),
      linear-gradient(180deg, #050505 0%, #090909 45%, #050505 100%);
    color: var(--ink);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.5;
  }

  a {
    color: inherit;
    text-decoration: none;
  }
}

@layer components {
  main {
    min-height: 100vh;
    overflow: hidden;
  }

  header {
    width: min(880px, calc(100% - 48px));
    margin: 0 auto;
    padding: 18px 0;
    border-bottom: 1px solid var(--line);
  }

  header > a {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    font-size: 0.88rem;
    font-weight: 900;
    letter-spacing: -0.04em;
  }

  header > a::before {
    content: "P";
    display: inline-grid;
    width: 22px;
    height: 22px;
    place-items: center;
    border-radius: 6px;
    background: var(--rust);
    color: #070707;
    font-size: 0.82rem;
    font-weight: 950;
  }

  nav {
    color: var(--muted);
    font-size: 0.66rem;
    font-weight: 800;
    text-transform: none;
  }

  section {
    padding: 64px 24px;
  }

  section:first-of-type {
    padding-top: 74px;
    padding-bottom: 86px;
    border-bottom: 1px solid var(--line);
  }

  section > div,
  section:first-of-type > div {
    width: min(880px, 100%);
    margin: 0 auto;
  }

  section:first-of-type > div {
    gap: 70px;
  }

  h1,
  h2,
  h3,
  p {
    margin-top: 0;
  }

  h1 {
    margin-bottom: 28px;
    max-width: 560px;
    font-size: clamp(3rem, 5.4vw, 4.8rem);
    line-height: 0.89;
    letter-spacing: -0.065em;
    font-weight: 950;
  }

  h2 {
    margin-bottom: 0;
    max-width: 540px;
    font-size: clamp(2.25rem, 3.5vw, 3.2rem);
    line-height: 0.95;
    letter-spacing: -0.045em;
    font-weight: 950;
  }

  h3 {
    margin-bottom: 14px;
    font-size: 1.1rem;
    line-height: 1.1;
    letter-spacing: -0.03em;
    font-weight: 850;
  }

  p {
    color: var(--muted);
  }

  p[class*="uppercase"],
  section:first-of-type p:first-child,
  #start > div > p,
  #message p:first-child,
  #assets > div > p,
  #subscribe p:first-child {
    margin-bottom: 18px;
    color: var(--rust-dark);
    font-size: 0.62rem;
    font-weight: 900;
    letter-spacing: 0.22em;
    text-transform: uppercase;
  }

  section:first-of-type h1 + p {
    max-width: 470px;
    font-size: 0.95rem;
    line-height: 1.7;
  }

  section:first-of-type a,
  #message a,
  #subscribe a {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-right: 12px;
    margin-top: 18px;
    border-radius: 999px;
    padding: 12px 20px;
    background: var(--rust);
    color: #050505;
    font-size: 0.68rem;
    font-weight: 850;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  section:first-of-type a + a {
    background: transparent;
    color: var(--ink);
    border: 1px solid rgba(255, 255, 255, 0.16);
  }

  section:first-of-type > div > div:last-child {
    overflow: hidden;
    border: 1px solid rgba(244, 196, 48, 0.24);
    border-radius: 4px;
    background: var(--card);
    box-shadow: 0 26px 70px rgba(0, 0, 0, 0.35);
  }

  section:first-of-type > div > div:last-child > div:first-child {
    min-height: 270px;
    padding: 22px;
    display: flex;
    align-items: flex-end;
    background:
      linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.72)),
      radial-gradient(circle at 70% 18%, rgba(244, 196, 48, 0.34), transparent 26%),
      linear-gradient(135deg, #2b1e11, #171717 52%, #080808);
  }

  section:first-of-type > div > div:last-child > div:first-child > div {
    width: 100%;
    padding: 0;
    border: 0;
    background: transparent;
  }

  section:first-of-type > div > div:last-child p {
    margin-bottom: 0;
    color: var(--white);
  }

  section:first-of-type > div > div:last-child > div:last-child {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
    padding: 18px;
  }

  section:nth-of-type(2) {
    border-bottom: 1px solid var(--line);
    background: transparent;
    padding: 48px 24px;
  }

  section:nth-of-type(2) > div {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 28px;
    text-align: center;
  }

  section:nth-of-type(2) p:first-child {
    margin-bottom: 4px;
    color: var(--ink);
    font-size: 1.45rem;
    font-weight: 950;
  }

  #start > div > div,
  #assets > div > div {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin-top: 44px;
  }

  #start a,
  #assets div div div {
    display: block;
    min-height: 150px;
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 22px;
    background: linear-gradient(180deg, var(--card-soft), #101010);
  }

  #message {
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
    background: #080808;
    color: var(--white);
  }

  #message > div {
    gap: 44px;
  }

  #message > div > div:last-child {
    border-radius: 32px;
    padding: 30px;
    border: 1px solid rgba(244, 196, 48, 0.22);
    background: var(--card);
  }

  #subscribe > div {
    border-radius: 32px;
    padding: 64px 40px;
    border: 1px solid rgba(244, 196, 48, 0.26);
    background: linear-gradient(135deg, #151515, #090909);
    text-align: center;
  }

  #subscribe h2,
  #subscribe p {
    margin-left: auto;
    margin-right: auto;
    color: var(--white);
  }

  #subscribe p:last-of-type {
    max-width: 700px;
    color: rgba(255,255,255,0.86);
    font-size: 1.12rem;
  }
}

@media (max-width: 900px) {
  nav {
    display: none;
  }

  section:first-of-type > div,
  #message > div,
  #start > div > div,
  #assets > div > div,
  section:nth-of-type(2) > div {
    grid-template-columns: 1fr;
  }
}
"""
    (styles_dir / "global.css").write_text(global_css, encoding="utf-8")
    files["src/styles/global.css"] = str(styles_dir / "global.css")
    (styles_dir / "tailwind.css").write_text(
        "/* Generated by npm run build:css. */\n",
        encoding="utf-8",
    )
    files["src/styles/tailwind.css"] = str(styles_dir / "tailwind.css")

    package_json = {
        "name": safe_name,
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "build:css": "tailwindcss -i ./src/styles/global.css -o ./src/styles/tailwind.css --minify",
            "dev": "tailwindcss -i ./src/styles/global.css -o ./src/styles/tailwind.css --minify && astro dev",
            "build": "tailwindcss -i ./src/styles/global.css -o ./src/styles/tailwind.css --minify && astro build",
            "preview": "astro preview",
        },
        "dependencies": {
            "@tailwindcss/cli": "latest",
            "astro": "latest",
            "tailwindcss": "latest",
        },
        "devDependencies": {},
    }
    (site_dir / "package.json").write_text(
        json.dumps(package_json, indent=2) + "\n",
        encoding="utf-8",
    )
    files["package.json"] = str(site_dir / "package.json")

    tailwind_config = """/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {}
  },
  plugins: []
};
"""
    (site_dir / "tailwind.config.mjs").write_text(tailwind_config, encoding="utf-8")
    files["tailwind.config.mjs"] = str(site_dir / "tailwind.config.mjs")

    astro_config = """import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static'
});
"""
    (site_dir / "astro.config.mjs").write_text(astro_config, encoding="utf-8")
    files["astro.config.mjs"] = str(site_dir / "astro.config.mjs")

    return {
        "status": "success",
        "site_path": str(site_dir),
        "files_created": files,
        "message": f"Dylan generated an Astro site for {client_id} at {site_dir}",
        "deployment_hint": f"Run: cd {site_dir} && npm install && npm run build",
    }


@tool
def deploy_to_cloudflare(site_path: str, project_name: Optional[str] = None) -> Dict[str, str]:
    """Deploy a built Astro site to Cloudflare Pages with Wrangler."""
    site_dir = Path(site_path)
    if not site_dir.exists():
        return {
            "status": "error",
            "message": f"Site path does not exist: {site_path}",
        }

    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd") or r"C:\Program Files\nodejs\npm.cmd"
    npx_cmd = shutil.which("npx") or shutil.which("npx.cmd") or r"C:\Program Files\nodejs\npx.cmd"
    if not Path(npm_cmd).exists() and shutil.which(npm_cmd) is None:
        return {
            "status": "manual_step_required",
            "message": "npm was not found. Install Node.js/npm before deploying to Cloudflare Pages.",
        }

    if not (site_dir / "node_modules").exists():
        install = subprocess.run(
            [npm_cmd, "install"],
            cwd=site_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        if install.returncode != 0:
            return {
                "status": "error",
                "message": "npm install failed before Cloudflare deployment.",
                "stdout": install.stdout[-4000:],
                "stderr": install.stderr[-4000:],
            }

    build = subprocess.run(
        [npm_cmd, "run", "build"],
        cwd=site_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    if build.returncode != 0:
        return {
            "status": "error",
            "message": "Astro build failed before Cloudflare deployment.",
            "stdout": build.stdout[-4000:],
            "stderr": build.stderr[-4000:],
        }

    dist_dir = site_dir / "dist"
    if not dist_dir.exists():
        return {
            "status": "error",
            "message": f"Build completed, but dist directory was not found: {dist_dir}",
        }

    contact = _read_site_contact(site_dir)
    deploy_project = (
        project_name
        or contact.get("pagesProject")
        or _slugify(site_dir.name, "parlayvu-site")
    )
    if not Path(npx_cmd).exists() and shutil.which(npx_cmd) is None:
        return {
            "status": "manual_step_required",
            "message": (
                "npx was not found. Deploy manually with: "
                f"npx wrangler pages deploy dist --project-name={deploy_project}"
            ),
        }

    deploy = subprocess.run(
        [npx_cmd, "wrangler", "pages", "deploy", "dist", f"--project-name={deploy_project}"],
        cwd=site_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    if deploy.returncode != 0:
        stdout = deploy.stdout or ""
        stderr = deploy.stderr or ""
        output = (stdout + "\n" + stderr)[-4000:]
        return {
            "status": "manual_step_required",
            "message": (
                "Cloudflare deployment did not complete. You may need to run "
                "`npx wrangler login` or create/configure the Pages project."
            ),
            "project_name": deploy_project,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
            "manual_command": f"cd {site_dir} && npx wrangler pages deploy dist --project-name={deploy_project}",
            "details": output,
        }

    return {
        "status": "success",
        "project_name": deploy_project,
        "site_path": str(site_dir),
        "message": "Cloudflare Pages deployment completed.",
        "stdout": deploy.stdout[-4000:],
    }


def deploy_static_directory_to_cloudflare(
    directory: Path,
    project_name: str,
) -> Dict[str, Any]:
    """Deploy a static-HTML directory (no build step) to Cloudflare Pages.

    Used by the Dylan variation generator: each variation is a single
    self-contained `index.html` (Tailwind via CDN), so there's no `npm install`
    or `npm run build` — just `npx wrangler pages deploy <dir>`.

    Args:
        directory: Path to the directory whose contents become the Pages site.
            Must contain at least one `index.html`.
        project_name: Cloudflare Pages project slug (e.g. "ulcannarbor-previews").
            Created on first deploy if missing.

    Returns:
        {"status": "success", "project_name": ..., "url": "https://<project>.pages.dev/", ...}
        or
        {"status": "manual_step_required", "command": "...", "stdout": "...", "stderr": "..."}
        Mirrors deploy_to_cloudflare's error contract for the same UX.
    """
    if not directory.exists():
        return {
            "status": "error",
            "message": f"Directory does not exist: {directory}",
        }
    if not directory.is_dir():
        return {
            "status": "error",
            "message": f"Not a directory: {directory}",
        }

    # Prefer the globally-installed wrangler binary (baked into the prod
    # container image); fall back to npx for dev machines where wrangler isn't
    # global. The Windows fallback path covers local dev on this repo's
    # primary author machine.
    wrangler_cmd = shutil.which("wrangler") or shutil.which("wrangler.cmd")
    npx_cmd = shutil.which("npx") or shutil.which("npx.cmd") or r"C:\Program Files\nodejs\npx.cmd"
    has_npx = (
        wrangler_cmd is not None
        or (Path(npx_cmd).exists() if npx_cmd else False)
        or shutil.which(npx_cmd) is not None
    )
    if not has_npx:
        return {
            "status": "manual_step_required",
            "message": (
                f"Neither wrangler nor npx was found in PATH. Deploy manually with: "
                f"npx wrangler pages deploy {directory} --project-name={project_name}"
            ),
            "project_name": project_name,
            "command": f"npx wrangler pages deploy {directory} --project-name={project_name}",
        }

    def _wrangler_argv(*tail: str) -> list[str]:
        if wrangler_cmd:
            return [wrangler_cmd, *tail]
        return [npx_cmd, "wrangler", *tail]

    deploy_cmd = _wrangler_argv("pages", "deploy", str(directory), f"--project-name={project_name}")
    create_cmd = _wrangler_argv("pages", "project", "create", project_name, "--production-branch=main")

    # Wrangler authenticates non-interactively from CLOUDFLARE_API_TOKEN +
    # CLOUDFLARE_ACCOUNT_ID env vars. The repo's existing convention names
    # the token CLOUDFLARE_API (without _TOKEN), so we alias it for wrangler
    # without forcing a Container App env-var rename.
    subprocess_env = dict(os.environ)
    if not subprocess_env.get("CLOUDFLARE_API_TOKEN"):
        legacy_token = subprocess_env.get("CLOUDFLARE_API")
        if legacy_token:
            subprocess_env["CLOUDFLARE_API_TOKEN"] = legacy_token

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=subprocess_env,
        )

    deploy = _run(deploy_cmd)

    # Self-heal once: if the deploy failed (most commonly because the Pages
    # project doesn't exist yet — wrangler does NOT auto-create on deploy),
    # try creating the project and retrying. Creating an existing project
    # returns a non-zero exit code with an "already exists" message, which
    # is harmless — we ignore the create result and let the retry tell us
    # whether the actual deploy now works.
    if deploy.returncode != 0:
        _run(create_cmd)
        deploy = _run(deploy_cmd)

    if deploy.returncode != 0:
        stdout = deploy.stdout or ""
        stderr = deploy.stderr or ""
        return {
            "status": "manual_step_required",
            "message": (
                "Cloudflare deployment did not complete after auto-create retry. "
                "Check that CLOUDFLARE_API_TOKEN has Pages:Edit scope and "
                "CLOUDFLARE_ACCOUNT_ID is correct."
            ),
            "project_name": project_name,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
            "command": f"npx wrangler pages deploy {directory} --project-name={project_name}",
        }

    # Wrangler prints the preview URL in its stdout — pull it out for the
    # caller's convenience. Pattern: "https://<commit>.{project}.pages.dev"
    # or "https://{project}.pages.dev". We grep the simpler canonical form.
    stdout = deploy.stdout or ""
    project_url = f"https://{project_name}.pages.dev/"
    return {
        "status": "success",
        "project_name": project_name,
        "directory": str(directory),
        "url": project_url,
        "message": "Cloudflare Pages deployment completed.",
        "stdout": stdout[-4000:],
    }