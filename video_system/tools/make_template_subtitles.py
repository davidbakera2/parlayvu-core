from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


TIME_RE = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})\s+-->\s+"
    r"(?P<h2>\d{2}):(?P<m2>\d{2}):(?P<s2>\d{2}),(?P<ms2>\d{3})"
)


def ass_time(h: str, m: str, s: str, ms: str) -> str:
    centis = int(ms) // 10
    return f"{int(h)}:{m}:{s}.{centis:02d}"


def ass_alpha(alpha: float) -> str:
    alpha = max(0.0, min(1.0, alpha))
    # ASS alpha is inverse: 00 opaque, FF transparent.
    return f"{round((1.0 - alpha) * 255):02X}"


def wrap_caps(text: str, max_chars: int) -> str:
    words = re.sub(r"\s+", " ", text.upper()).strip().split()
    if not words:
        return ""
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        add_len = len(word) + (1 if current else 0)
        if current and current_len + add_len > max_chars and len(lines) < 1:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += add_len
    if current:
        lines.append(" ".join(current))
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return r"\N".join(lines[:2])


def parse_srt(text: str, max_chars: int) -> list[tuple[str, str, str]]:
    blocks = re.split(r"\n\s*\n", text.strip())
    events: list[tuple[str, str, str]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        match = TIME_RE.search(lines[1])
        if not match:
            continue
        start = ass_time(match["h"], match["m"], match["s"], match["ms"])
        end = ass_time(match["h2"], match["m2"], match["s2"], match["ms2"])
        payload = wrap_caps(" ".join(lines[2:]), max_chars)
        if payload:
            events.append((start, end, payload))
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Create styled ASS subtitles from an SRT file.")
    parser.add_argument("srt")
    parser.add_argument("output")
    parser.add_argument("--style", required=True, help="Path to subtitles.json")
    args = parser.parse_args()

    style = json.loads(Path(args.style).read_text(encoding="utf-8"))
    events = parse_srt(Path(args.srt).read_text(encoding="utf-8-sig"), int(style["max_chars_per_line"]))
    back_alpha = ass_alpha(float(style.get("box_alpha", 0.35)))
    font_size = int(style.get("font_size", 42))
    margin_bottom = int(style.get("margin_bottom", 201))
    outline = float(style.get("outline", 2.4))
    bold = "-1" if style.get("bold", True) else "0"

    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TemplateSub,{style.get("font", "Arial")},{font_size},&H00FFFFFF,&H00FFFFFF,&HAA000000,&H{back_alpha}000000,{bold},0,0,0,100,100,0,0,4,{outline},0,2,90,90,{margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

    body = []
    for start, end, payload in events:
        safe = html.unescape(payload).replace("{", "").replace("}", "")
        body.append(f"Dialogue: 0,{start},{end},TemplateSub,,0,0,0,,{safe}")

    Path(args.output).write_text(header + "\n".join(body) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
