from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


BASE_W, BASE_H = 1280, 720
W, H = 1920, 1080
FPS = 24
ONE_CAM_COVER_W = 1998
ONE_CAM_COVER_H = 1124
STILL_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")
FONT_REG = Path(r"C:\Windows\Fonts\arial.ttf")


def sx(value: int | float) -> int:
    return round(value * W / BASE_W)


def sy(value: int | float) -> int:
    return round(value * H / BASE_H)


def sbox(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return sx(x1), sy(y1), sx(x2), sy(y2)


def spos(x: int | float, y: int | float) -> tuple[int, int]:
    return sx(x), sy(y)


LOWER_STRIP_Y = sy(598)
ONE_CAM_LOWER_FRAME = sbox((25, 600, 1255, 700))
LOWER_LEFT = sbox((28, 604, 169, 697))
LOWER_RIGHT = sbox((1161, 604, 1254, 697))
TOP_TEXT_BOX = sbox((176, 606, 1157, 631))
BOTTOM_TEXT_BOX = sbox((184, 640, 1125, 687))


def run(cmd: list[str | Path]) -> None:
    print(" ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    winget = (
        Path(r"C:\Users\DavidBaker\AppData\Local\Microsoft\WinGet\Packages")
        / r"Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-8.1.1-full_build"
        / "bin"
        / f"{name}.exe"
    )
    if not winget.exists():
        # fallback to the 8.1 name too
        winget = (
            Path(r"C:\Users\DavidBaker\AppData\Local\Microsoft\WinGet\Packages")
            / r"Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "ffmpeg-8.1-full_build"
            / "bin"
            / f"{name}.exe"
        )
    if winget.exists():
        return str(winget)
    return name


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


def media_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


def parse_time(value: str | int | float | None, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return default
    if ":" not in text:
        try:
            return float(text)
        except ValueError:
            return default
    parts = text.split(".")
    hms = parts[0].split(":")
    if len(hms) != 3:
        return default
    h, m, s = (int(item) for item in hms)
    ms = int((parts[1] if len(parts) > 1 else "0").ljust(3, "0")[:3])
    return h * 3600 + m * 60 + s + ms / 1000


def parse_offset_time(value: str | int | float | None, default: float = 0.0) -> float:
    if isinstance(value, str) and value.strip().startswith("-"):
        return -parse_time(value.strip()[1:], abs(default))
    return parse_time(value, default)


def ffmpeg_filter_path(path: Path) -> str:
    text = path.resolve().as_posix()
    return text.replace(":", r"\:").replace("'", r"\'")


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font_path: Path,
    max_size: int,
    min_size: int,
) -> ImageFont.FreeTypeFont:
    x1, y1, x2, y2 = box
    for size in range(max_size, min_size - 1, -1):
        font = ImageFont.truetype(str(font_path), size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= x2 - x1 and bbox[3] - bbox[1] <= y2 - y1:
            return font
    return ImageFont.truetype(str(font_path), min_size)


def trim_near_white(src: Image.Image, threshold: int = 245) -> Image.Image:
    rgb = src.convert("RGB")
    white = Image.new("RGB", rgb.size, "white")
    diff = ImageChops.difference(rgb, white).convert("L")
    mask = diff.point(lambda px: 255 if px > 255 - threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return src
    return src.crop(bbox)


class Renderer:
    def __init__(self, project: Path, template: Path, max_scenes: int | None = None) -> None:
        self.project = project.resolve()
        self.assets = self.project / "assets"
        self.planning = self.project / "planning"
        self.renders = self.project / "renders"
        self.previews = self.project / "previews"
        self.template = template.resolve()
        self.template_root = self.template.parent
        self.layouts = self.template_root / "layouts"
        self.styles = self.template_root / "styles"
        self.out = self.project / "work"
        self.segments = self.out / "segments"
        self.overlays = self.out / "overlays"
        self.max_scenes = max_scenes
        self.plan = json.loads((self.planning / "video_plan.json").read_text(encoding="utf-8"))
        self.broll_index = {row.get("broll_id"): row for row in self.plan.get("broll", [])}
        self.asset_index = {row.get("asset_key"): row.get("file_name") for row in self.plan.get("assets", [])}
        self.settings = {row.get("setting"): row.get("value") for row in self.plan.get("settings", [])}
        self.graphics = [row for row in self.plan.get("graphics", []) if row.get("enabled", True)]
        self.timeline_anchors: dict[str, float] = {}

    def find_program_start(self) -> float:
        for scene in self.plan.get("scenes", []):
            if scene.get("enabled") is False:
                continue
            if scene.get("layout") in {"1cam", "2cam", "2cam_broll", "3cam", "3cam_broll"}:
                return parse_time(scene.get("start"))
        return 0.0

    def infer_scene_durations(self, scenes: list[dict[str, str]]) -> list[dict[str, str]]:
        resolved: list[dict[str, str]] = []
        for index, scene in enumerate(scenes):
            copy = dict(scene)
            start = parse_time(copy.get("start"))
            duration = parse_time(copy.get("duration"))
            if duration <= 0:
                end = parse_time(copy.get("end"))
                if end <= start:
                    next_start = 0.0
                    for next_scene in scenes[index + 1 :]:
                        next_start = parse_time(next_scene.get("start"))
                        if next_start > start:
                            break
                    end = next_start
                duration = max(0.0, end - start)
                if duration > 0:
                    copy["duration"] = f"{duration:.3f}"
            resolved.append(copy)
        return resolved

    def setting_bool(self, name: str, default: bool = True) -> bool:
        value = self.settings.get(name)
        if value in {None, ""}:
            return default
        return str(value).strip().lower() not in {"false", "0", "no", "n", "disabled"}

    def setting_time(self, name: str, default: float) -> float:
        return parse_time(self.settings.get(name), default)

    def setting_text(self, name: str, default: str) -> str:
        value = self.settings.get(name)
        return str(value).strip() if value not in {None, ""} else default

    def add_broll_input(self, inputs: list[str | Path], broll_path: Path, broll_start: float, duration: float) -> str:
        if broll_path.suffix.lower() in STILL_IMAGE_EXTENSIONS:
            inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", broll_path])
        else:
            inputs.extend(["-stream_loop", "-1", "-ss", f"{broll_start:.3f}", "-i", broll_path])
        return str(sum(1 for item in inputs if str(item) == "-i") - 1)

    def duration_if_exists(self, path: Path) -> float:
        return media_duration(path) if path.exists() else 0.0

    def asset_path(self, key_or_name: str | None) -> Path:
        name = key_or_name or ""
        mapped = self.asset_index.get(name, name)
        return self.assets / mapped

    def prepare(self) -> None:
        for folder in [self.renders, self.previews, self.out, self.segments, self.overlays]:
            folder.mkdir(parents=True, exist_ok=True)
        for folder in [self.segments, self.overlays]:
            for item in folder.glob("*"):
                if item.is_file():
                    item.unlink()

    def paste_fit(
        self,
        base: Image.Image,
        src_path: Path,
        box: tuple[int, int, int, int],
        trim: bool = False,
        scale_boost: float = 1.0,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> None:
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        src = Image.open(src_path).convert("RGB")
        if trim:
            src = trim_near_white(src)
        scale = min(bw / src.width, bh / src.height) * scale_boost
        nw, nh = max(1, round(src.width * scale)), max(1, round(src.height * scale))
        src = src.resize((nw, nh), Image.Resampling.LANCZOS)
        src = src.filter(ImageFilter.UnsharpMask(radius=0.9, percent=185, threshold=2))
        canvas = Image.new("RGB", (bw, bh), "white")
        canvas.paste(src, ((bw - nw) // 2 + offset_x, (bh - nh) // 2 + offset_y))
        base.paste(canvas, (x1, y1))

    def redraw_logo_cell_frame(self, base: Image.Image) -> None:
        x1, y1, x2, y2 = LOWER_RIGHT
        draw = ImageDraw.Draw(base)
        width = sy(2)
        draw.line((x1, y1, x2 - 1, y1), fill=(255, 255, 255), width=width)
        draw.line((x2 - 1, y1, x2 - 1, y2 - 1), fill=(255, 255, 255), width=width)
        draw.line((x1, y2 - 1, x2 - 1, y2 - 1), fill=(255, 255, 255), width=width)

    def make_overlay(self, name: str, template_name: str, top_text: str, topic: str) -> Path:
        base_rgb = Image.open(self.layouts / template_name).convert("RGB")
        base_rgb.info.clear()
        if base_rgb.size != (W, H):
            base_rgb = base_rgb.resize((W, H), Image.Resampling.LANCZOS)

        if template_name != "1cam.png" and self.setting_text("background_video", ""):
            rgb = base_rgb.convert("RGB")
            alpha = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "black")).convert("L")
            alpha = alpha.point(lambda px: 0 if px <= 3 else 255)
            base = Image.merge("RGBA", (*rgb.split(), alpha))
        else:
            base = base_rgb.convert("RGBA")
        base.info.clear()

        left_asset = self.asset_path("show_image_lower_third")
        right_asset = self.asset_path("logo_square")
        if left_asset.exists():
            self.paste_fit(base, left_asset, LOWER_LEFT)
        if right_asset.exists():
            x1, y1, x2, y2 = LOWER_RIGHT
            ImageDraw.Draw(base).rectangle((x1 - sx(2), y1, x2 - 1, y2 - 1), fill=(255, 255, 255, 255))
            self.paste_fit(base, right_asset, LOWER_RIGHT, trim=True, scale_boost=0.98, offset_y=sy(4))
            self.redraw_logo_cell_frame(base)

        draw = ImageDraw.Draw(base)
        top = (top_text or "").upper()
        bottom = (topic or "").upper()
        top_font = fit_text(draw, top, TOP_TEXT_BOX, FONT_BOLD, sx(21), sx(13))
        bottom_font = fit_text(draw, bottom, BOTTOM_TEXT_BOX, FONT_BOLD, sx(32), sx(18))

        def centered(text: str, box: tuple[int, int, int, int], font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
            x1, y1, x2, y2 = box
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x1 + (x2 - x1 - tw) / 2, y1 + (y2 - y1 - th) / 2 - 1), text, font=font, fill=fill)

        if top:
            centered(top, TOP_TEXT_BOX, top_font, (255, 255, 255, 255))
        if bottom:
            x1, y1, _x2, y2 = BOTTOM_TEXT_BOX
            bbox = draw.textbbox((0, 0), bottom, font=bottom_font)
            draw.text((x1, y1 + (y2 - y1 - (bbox[3] - bbox[1])) / 2 - 1), bottom, font=bottom_font, fill=(0, 0, 0, 255))

        out = self.overlays / f"{name}.png"
        base.save(out)
        return out

    def make_onecam_lower_third_overlay(self, name: str, top_text: str, topic: str) -> Path:
        full = self.make_overlay(name, "1cam.png", top_text, topic)
        src_rgb = Image.open(full).convert("RGB")
        src = Image.merge("RGBA", (*src_rgb.split(), Image.new("L", src_rgb.size, 255)))
        base = Image.new("RGBA", src.size, (0, 0, 0, 0))
        x1, y1, x2, y2 = ONE_CAM_LOWER_FRAME
        base.paste(src.crop((x1, y1, x2, y2)), (x1, y1))
        draw = ImageDraw.Draw(base)
        border = sy(2)
        draw.line((x1, y1, x2 - 1, y1), fill=(255, 255, 255, 255), width=border)
        draw.line((x1, y2 - 1, x2 - 1, y2 - 1), fill=(255, 255, 255, 255), width=border)
        draw.line((x1, y1, x1, y2 - 1), fill=(255, 255, 255, 255), width=border)
        draw.line((x2 - 1, y1, x2 - 1, y2 - 1), fill=(255, 255, 255, 255), width=border)
        out = self.overlays / f"{name}_onecam.png"
        base.save(out)
        return out

    def make_broll_card(self, name: str, line_1: str, line_2: str = "") -> Path:
        line_1 = (line_1 or "").upper()
        line_2 = (line_2 or "").upper()
        long_single_line = bool(line_1 and not line_2 and len(line_1) > 34)
        width, height = sx(520), sy(78 if line_2 or long_single_line else 54)
        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base)
        navy = (8, 39, 70, 205)
        blue = (44, 132, 198, 255)
        white = (255, 255, 255, 255)
        draw.rectangle((0, 0, width - sx(4), height - sy(4)), fill=navy)
        draw.rectangle((width - sx(12), sy(2), width - sx(4), height - sy(6)), fill=blue)

        pad_r = sx(28)
        max_text_width = width - pad_r - sx(14)
        if long_single_line:
            words = line_1.split()
            lines = [""]
            font_1 = ImageFont.truetype(str(FONT_BOLD), sx(16))
            for word in words:
                candidate = f"{lines[-1]} {word}".strip()
                bbox = draw.textbbox((0, 0), candidate, font=font_1)
                if bbox[2] - bbox[0] <= max_text_width or not lines[-1]:
                    lines[-1] = candidate
                else:
                    lines.append(word)
            if len(lines) > 2:
                lines = [" ".join(words[:4]), " ".join(words[4:])]
                font_1 = fit_text(draw, lines[1], (sx(14), sy(38), width - pad_r, sy(66)), FONT_BOLD, sx(15), sx(10))
            line_height = sy(25)
            y = sy(13)
            for line in lines[:2]:
                bbox = draw.textbbox((0, 0), line, font=font_1)
                draw.text((max(sx(14), width - pad_r - (bbox[2] - bbox[0])), y), line, font=font_1, fill=white)
                y += line_height
        else:
            text_box_1 = (sx(14), sy(8), width - pad_r, sy(38))
            font_1 = fit_text(draw, line_1, text_box_1, FONT_BOLD, sx(22), sx(12))
            bbox_1 = draw.textbbox((0, 0), line_1, font=font_1)
            draw.text((max(sx(14), width - pad_r - (bbox_1[2] - bbox_1[0])), sy(10)), line_1, font=font_1, fill=white)
        if line_2:
            text_box_2 = (sx(14), sy(40), width - pad_r, sy(66))
            font_2 = fit_text(draw, line_2, text_box_2, FONT_REG, sx(16), sx(10))
            bbox_2 = draw.textbbox((0, 0), line_2, font=font_2)
            draw.text((max(sx(14), width - pad_r - (bbox_2[2] - bbox_2[0])), sy(42)), line_2, font=font_2, fill=(235, 245, 255, 255))

        out = self.overlays / f"{name}.png"
        base.save(out)
        return out

    def broll_cards_for_scene(self, scene: dict[str, str]) -> list[dict[str, object]]:
        scene_start = parse_time(scene.get("start"))
        scene_end = scene_start + parse_time(scene.get("duration"))
        scene_id = str(scene.get("scene_id") or "").strip()
        cards: list[dict[str, object]] = []
        for graphic in self.graphics:
            if str(graphic.get("type", "")).strip().lower() != "broll_card":
                continue
            linked_scene = str(graphic.get("linked_scene_id") or "").strip()
            graphic_start = parse_time(graphic.get("start"))
            graphic_end = parse_time(graphic.get("end"), graphic_start + 5.0)
            if linked_scene and linked_scene == scene_id:
                start = max(0.0, graphic_start - scene_start)
                end = min(scene_end - scene_start, graphic_end - scene_start)
            elif graphic_start < scene_end and graphic_end > scene_start:
                start = max(0.0, graphic_start - scene_start)
                end = min(scene_end - scene_start, graphic_end - scene_start)
            else:
                continue
            if end <= start:
                continue
            cards.append(
                {
                    "start": start,
                    "end": end,
                    "text_line_1": graphic.get("text_line_1", ""),
                    "text_line_2": graphic.get("text_line_2", ""),
                    "graphic_id": graphic.get("graphic_id", "broll_card"),
                }
            )
        return cards

    def vf_scale_to_box(self, label: str, width: int, height: int, zoom: float = 1.0) -> str:
        scale_width = round(width * zoom)
        scale_height = round(height * zoom)
        return f"[{label}:v]scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={FPS},format=yuv420p"

    def lower_third_scene(self, scene_id: str) -> dict[str, str] | None:
        scene_id = str(scene_id or "").strip()
        if not scene_id:
            return None
        return next(
            (
                row
                for row in self.plan.get("scenes", [])
                if str(row.get("scene_id") or "").strip() == scene_id
            ),
            None,
        )

    def render_intro(self, idx: int, scene: dict[str, str]) -> Path:
        src = self.asset_path(scene.get("host_source") or scene.get("source") or self.setting_text("intro_asset", "intro.mp4"))
        duration = min(parse_time(scene.get("duration"), media_duration(src)), media_duration(src))
        out = self.segments / f"{idx:03d}_intro.mp4"
        inputs = ["-i", src]
        filters = [
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p[basev]",
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.35,alimiter=limit=0.96[a]",
        ]
        lower_third_scene_id = (
            scene.get("lower_third_scene_id")
            or scene.get("intro_lower_third_scene_id")
            or self.setting_text("intro_lower_third_scene_id", "")
        )
        lower_third = self.lower_third_scene(lower_third_scene_id)
        if lower_third:
            overlay = self.make_onecam_lower_third_overlay(
                f"lt_{idx:03d}_intro",
                str(lower_third.get("top_row_text") or ""),
                str(lower_third.get("bottom_row_text") or ""),
            )
            inputs.extend(["-i", overlay])
            filters.append(f"[1:v]fps={FPS},format=rgba[ltv]")
            filters.append("[basev][ltv]overlay=0:0:format=auto,format=yuv420p[v]")
        else:
            filters.append("[basev]format=yuv420p[v]")
        filter_complex = ";".join(filters)
        self.encode(out, inputs, filter_complex, duration)
        return out

    def render_show_image(self, idx: int, scene: dict[str, str], outro: bool = False) -> Path:
        duration = parse_time(scene.get("duration"), 5.0)
        out = self.segments / f"{idx:03d}_{'outro' if outro else 'show_image'}.mp4"
        image = self.asset_path(scene.get("host_source") or scene.get("source") or self.setting_text("show_image_asset", "show_image.png"))
        filter_complex = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"zoompan=z='min(zoom+0.0012,1.055)':d={math.ceil(duration * FPS)}:s={W}x{H}:fps={FPS},"
            f"setsar=1,unsharp=5:5:0.65:3:3:0.35,format=yuv420p[v];"
            "anullsrc=r=48000:cl=stereo[a]"
        )
        self.encode(out, ["-loop", "1", "-t", f"{duration:.3f}", "-i", image], filter_complex, duration)
        return out

    def render_program(self, idx: int, scene: dict[str, str]) -> Path:
        layout = scene.get("layout", "")
        duration = parse_time(scene.get("duration"))
        # Scene start/end use final rendered-video time. Leave source_start blank to
        # follow the interview media timeline, beginning at interview_start.
        scene_start = parse_time(scene.get("start"))
        if self.timeline_anchors.get("scenes_are_final_time"):
            default_source_start = max(0.0, scene_start - self.timeline_anchors.get("interview_start", 0.0))
        else:
            default_source_start = scene_start
        source_start = parse_time(scene.get("source_start"), default_source_start)
        top_text = scene.get("top_row_text", "")
        topic = scene.get("bottom_row_text", "")
        out = self.segments / f"{idx:03d}_{layout}.mp4"
        overlay_name = f"lt_{idx:03d}_{layout}"
        inputs: list[str | Path] = []
        filters: list[str] = []

        if layout == "1cam":
            overlay = self.make_onecam_lower_third_overlay(overlay_name, top_text, topic)
            primary = scene.get("primary_camera") or "host"
            source = self.asset_path(scene.get(f"{primary}_source") or f"{primary}.mp4")
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", source, "-i", overlay])
            filters.append(
                f"[0:v]scale={ONE_CAM_COVER_W}:{ONE_CAM_COVER_H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p[basev]"
            )
            filters.append("[1:v]fps=24,format=rgba[ltv]")
            filters.append("[basev][ltv]overlay=0:0:format=auto,format=yuv420p[v]")
            filters.append("[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.35,alimiter=limit=0.96[a]")
            self.encode(out, inputs, ";".join(filters), duration)
            return out

        template_name = {
            "2cam": "2cam.png",
            "2cam_broll": "2cam_broll.png",
            "3cam": "3cam.png",
            "3cam_broll": "3cam_broll.png",
        }[layout]
        overlay = self.make_overlay(overlay_name, template_name, top_text, topic)
        host = self.asset_path(scene.get("host_source") or "host.mp4")
        guest = self.asset_path(scene.get("guest_01_source") or "guest_01.mp4")
        background = self.asset_path(self.setting_text("background_video", ""))
        has_background = background.exists()
        if has_background:
            inputs.extend(["-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", background])
            inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", overlay])
            host_input, guest_input = "2", "3"
            filters.append(
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"setsar=1,fps={FPS},format=yuv420p[bgbase]"
            )
            filters.append(f"[1:v]fps={FPS},format=rgba[layoutv]")
            filters.append("[bgbase][layoutv]overlay=0:0:format=auto[bg]")
        else:
            inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", overlay])
            host_input, guest_input = "1", "2"
            filters.append("[0:v]fps=24,format=yuv420p[bg]")

        if layout == "2cam":
            cameras: list[tuple[str, Path]] = []
            for camera_key in ["host", "guest_01", "guest_02"]:
                source_name = scene.get(f"{camera_key}_source")
                if source_name:
                    cameras.append((camera_key, self.asset_path(source_name)))
            if len(cameras) != 2:
                raise ValueError(
                    f"2cam scene {scene.get('scene_id')} must populate exactly two camera source fields; "
                    f"found {len(cameras)}"
                )
            primary = scene.get("primary_camera") or cameras[0][0]
            left_key, left_path = next(((key, path) for key, path in cameras if key == primary), cameras[0])
            right_key, right_path = next((key, path) for key, path in cameras if key != left_key)
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", left_path])
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", right_path])
            left_input = str(sum(1 for item in inputs if str(item) == "-i") - 2)
            right_input = str(sum(1 for item in inputs if str(item) == "-i") - 1)
            host_input = left_input
            filters.append(self.vf_scale_to_box(left_input, sx(612), sy(564)) + "[hostv]")
            filters.append(self.vf_scale_to_box(right_input, sx(611), sy(564)) + "[guestv]")
            hx, hy = spos(28, 26)
            gx, gy = spos(643, 26)
            filters.append(f"[bg][hostv]overlay={hx}:{hy}[tmp1];[tmp1][guestv]overlay={gx}:{gy}[v]")
        elif layout == "2cam_broll":
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", host])
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", guest])
            broll_file = scene.get("broll_file") or self.broll_index.get(scene.get("broll_id"), {}).get("file_name")
            broll_start = parse_time(scene.get("broll_source_start") or self.broll_index.get(scene.get("broll_id"), {}).get("default_source_start"))
            broll_input = self.add_broll_input(inputs, self.asset_path(broll_file), broll_start, duration)
            filters.append(self.vf_scale_to_box(host_input, sx(217), sy(281)) + "[hostv]")
            filters.append(self.vf_scale_to_box(guest_input, sx(217), sy(280)) + "[guestv]")
            broll_zoom = 1.3 if Path(str(broll_file)).name.lower() == "davidhart1.mp4" else 1.0
            filters.append(self.vf_scale_to_box(broll_input, sx(1006), sy(564), broll_zoom) + "[brollv]")
            hx, hy = spos(28, 26)
            gx, gy = spos(28, 310)
            bx, by = spos(248, 26)
            filters.append(f"[bg][hostv]overlay={hx}:{hy}[tmp1];[tmp1][guestv]overlay={gx}:{gy}[tmp2];[tmp2][brollv]overlay={bx}:{by}[v]")
        elif layout == "3cam":
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", host])
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", guest])
            guest_02 = self.asset_path(scene.get("guest_02_source") or "guest_02.mp4")
            if guest_02.exists():
                inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", guest_02])
                guest2_input = str(sum(1 for item in inputs if str(item) == "-i") - 1)
                filters.append(self.vf_scale_to_box(host_input, sx(407), sy(564)) + "[hostv]")
                filters.append(self.vf_scale_to_box(guest_input, sx(406), sy(564)) + "[guestv]")
                filters.append(self.vf_scale_to_box(guest2_input, sx(407), sy(564)) + "[guest2v]")
                hx, hy = spos(28, 26)
                g2x, g2y = spos(438, 26)
                gx, gy = spos(848, 26)
                filters.append(f"[bg][hostv]overlay={hx}:{hy}[tmp1];[tmp1][guest2v]overlay={g2x}:{g2y}[tmp2];[tmp2][guestv]overlay={gx}:{gy}[v]")
            else:
                filters.append(self.vf_scale_to_box(host_input, sx(612), sy(564)) + "[hostv]")
                filters.append(self.vf_scale_to_box(guest_input, sx(611), sy(564)) + "[guestv]")
                hx, hy = spos(28, 26)
                gx, gy = spos(643, 26)
                filters.append(f"[bg][hostv]overlay={hx}:{hy}[tmp1];[tmp1][guestv]overlay={gx}:{gy}[v]")
        elif layout == "3cam_broll":
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", host])
            inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", guest])
            guest_02 = self.asset_path(scene.get("guest_02_source") or "guest_02.mp4")
            broll_file = scene.get("broll_file") or self.broll_index.get(scene.get("broll_id"), {}).get("file_name")
            broll_start = parse_time(scene.get("broll_source_start") or self.broll_index.get(scene.get("broll_id"), {}).get("default_source_start"))
            if guest_02.exists():
                inputs.extend(["-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", guest_02])
                guest2_input = str(sum(1 for item in inputs if str(item) == "-i") - 1)
            broll_input = self.add_broll_input(inputs, self.asset_path(broll_file), broll_start, duration)
            filters.append(self.vf_scale_to_box(host_input, sx(217), sy(186)) + "[hostv]")
            filters.append(self.vf_scale_to_box(guest_input, sx(217), sy(186)) + "[guestv]")
            if guest_02.exists():
                filters.append(self.vf_scale_to_box(guest2_input, sx(217), sy(186)) + "[guest2v]")
            broll_zoom = 1.3 if Path(str(broll_file)).name.lower() == "davidhart1.mp4" else 1.0
            filters.append(self.vf_scale_to_box(broll_input, sx(1006), sy(564), broll_zoom) + "[brollv]")
            hx, hy = spos(28, 26)
            gx, gy = spos(28, 215)
            g2x, g2y = spos(28, 404)
            bx, by = spos(248, 26)
            if guest_02.exists():
                filters.append(f"[bg][hostv]overlay={hx}:{hy}[tmp1];[tmp1][guestv]overlay={gx}:{gy}[tmp2];[tmp2][guest2v]overlay={g2x}:{g2y}[tmp3];[tmp3][brollv]overlay={bx}:{by}[v]")
            else:
                filters.append(f"[bg][hostv]overlay={hx}:{hy}[tmp1];[tmp1][guestv]overlay={gx}:{gy}[tmp2];[tmp2][brollv]overlay={bx}:{by}[v]")
        else:
            raise NotImplementedError(f"Layout not implemented yet: {layout}")

        video_label = "v"
        if layout in {"2cam_broll", "3cam_broll"}:
            current_label = "v"
            for card_index, card in enumerate(self.broll_cards_for_scene(scene), start=1):
                card_path = self.make_broll_card(
                    f"broll_card_{idx:03d}_{card_index}_{card.get('graphic_id')}",
                    str(card.get("text_line_1") or ""),
                    str(card.get("text_line_2") or ""),
                )
                input_index = sum(1 for item in inputs if str(item) == "-i")
                inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", card_path])
                card_image = Image.open(card_path)
                x = W - card_image.width - sx(42)
                y = sy(48) + (card_index - 1) * (card_image.height + sy(10))
                card_label = f"card{card_index}"
                next_label = f"vcard{card_index}"
                filters.append(f"[{input_index}:v]fps={FPS},format=rgba[{card_label}]")
                filters.append(
                    f"[{current_label}][{card_label}]overlay={x}:{y}:"
                    f"enable='between(t,{float(card['start']):.3f},{float(card['end']):.3f})':format=auto[{next_label}]"
                )
                current_label = next_label
            video_label = current_label

        filters.append(f"[{host_input}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.35,alimiter=limit=0.96[a]")
        self.encode(out, inputs, ";".join(filters), duration, video_label=video_label)
        return out

    def encode(self, out: Path, inputs: list[str | Path], filter_complex: str, duration: float, video_label: str = "v") -> None:
        run(
            [
                FFMPEG,
                "-y",
                *inputs,
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{video_label}]",
                "-map",
                "[a]",
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "19",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                out,
            ]
        )

    def concat_segments(self, paths: list[Path], output: Path) -> None:
        inputs: list[str | Path] = []
        filters: list[str] = []
        concat_inputs: list[str] = []
        for index, path in enumerate(paths):
            inputs.extend(["-i", path])
            filters.append(
                f"[{index}:v]setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H},setsar=1,format=yuv420p[v{index}]"
            )
            filters.append(
                f"[{index}:a]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[a{index}]"
            )
            concat_inputs.append(f"[v{index}][a{index}]")
        filters.append("".join(concat_inputs) + f"concat=n={len(paths)}:v=1:a=1[v][a]")
        run(
            [
                FFMPEG,
                "-y",
                *inputs,
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "19",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                output,
            ]
        )

    def normalize_master(self, source: Path, output: Path) -> None:
        run(
            [
                FFMPEG,
                "-y",
                "-i",
                source,
                "-c:v",
                "copy",
                "-af",
                "aresample=async=1:first_pts=0,loudnorm=I=-16:LRA=11:TP=-1.5",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                output,
            ]
        )

    def mix_audio_cues(self, source: Path, output: Path) -> None:
        cues = [row for row in self.plan.get("audio", []) if row.get("enabled", True)]
        if not cues:
            shutil.copy2(source, output)
            return

        inputs: list[str | Path] = ["-i", source]
        filters: list[str] = ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo[basea]"]
        mix_labels = ["[basea]"]
        for index, cue in enumerate(cues, start=1):
            file_name = cue.get("file") or cue.get("file_name") or cue.get("audio_file")
            if not file_name:
                continue
            audio_path = self.asset_path(file_name)
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio cue file not found: {audio_path}")
            anchor = str(cue.get("anchor") or "final_start").strip()
            if anchor not in self.timeline_anchors:
                raise ValueError(f"Unknown audio anchor '{anchor}'. Available anchors: {', '.join(sorted(self.timeline_anchors))}")
            start_offset = parse_offset_time(cue.get("start"))
            start = self.timeline_anchors[anchor] + start_offset
            end_offset = parse_offset_time(cue.get("end"))
            duration = parse_time(cue.get("duration"), max(0.0, end_offset - start_offset))
            source_start = parse_time(cue.get("source_start"))
            fade_in = parse_time(cue.get("fade_in"))
            fade_out = parse_time(cue.get("fade_out"))
            volume = float(cue.get("volume") or 1.0)
            label = f"a{index}"
            delayed = f"ad{index}"
            inputs.extend(["-i", audio_path])
            chain = (
                f"[{index}:a]atrim=start={source_start:.3f}:duration={duration:.3f},"
                f"asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,volume={volume:.3f}"
            )
            if fade_in > 0:
                chain += f",afade=t=in:st=0:d={fade_in:.3f}"
            if fade_out > 0:
                chain += f",afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}"
            chain += f"[{label}];[{label}]adelay={round(start * 1000)}|{round(start * 1000)}[{delayed}]"
            filters.append(chain)
            mix_labels.append(f"[{delayed}]")

        if len(mix_labels) == 1:
            shutil.copy2(source, output)
            return

        filters.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0:normalize=0,"
            + "alimiter=limit=0.96[a]"
        )
        run(
            [
                FFMPEG,
                "-y",
                *inputs,
                "-filter_complex",
                ";".join(filters),
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                output,
            ]
        )

    def burn_subtitles(self, source: Path, output: Path) -> None:
        srt = self.planning / "captions.srt"
        if not srt.exists():
            return
        ass = self.planning / "captions.ass"
        style = self.styles / "subtitles.json"
        make_subs = Path(__file__).with_name("make_template_subtitles.py")
        run([sys.executable, make_subs, srt, ass, "--style", style])
        run(
            [
                FFMPEG,
                "-y",
                "-i",
                source,
                "-vf",
                f"subtitles='{ffmpeg_filter_path(ass)}'",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                output,
            ]
        )

    def render(self, with_subtitles: bool) -> None:
        self.prepare()
        enabled_scenes = [
            row
            for row in self.plan.get("scenes", [])
            if row.get("enabled", True)
        ]
        supported_layouts = {"intro", "show_image", "outro", "1cam", "2cam", "2cam_broll", "3cam", "3cam_broll"}
        timeline_scenes = [row for row in enabled_scenes if row.get("layout") in supported_layouts]
        timeline_scenes = self.infer_scene_durations(timeline_scenes)
        has_explicit_bookends = any(row.get("layout") in {"intro", "show_image", "outro"} for row in timeline_scenes)
        program_layouts = {"1cam", "2cam", "2cam_broll", "3cam", "3cam_broll"}
        scenes = [row for row in timeline_scenes if row.get("layout") in program_layouts]
        if self.max_scenes:
            timeline_scenes = timeline_scenes[: self.max_scenes]
            scenes = scenes[: self.max_scenes]
        paths: list[Path] = []

        final_time = 0.0
        self.timeline_anchors = {"final_start": 0.0, "intro_start": 0.0}
        idx = 1

        if has_explicit_bookends:
            self.timeline_anchors["scenes_are_final_time"] = 1.0
            first_program = next((row for row in timeline_scenes if row.get("layout") in program_layouts), None)
            self.timeline_anchors["interview_start"] = parse_time(first_program.get("start")) if first_program else 0.0
            opening = next((row for row in timeline_scenes if row.get("layout") == "show_image"), None)
            if opening:
                self.timeline_anchors["opening_show_image_start"] = parse_time(opening.get("start"))
            outro = next((row for row in timeline_scenes if row.get("layout") == "outro"), None)
            if outro:
                self.timeline_anchors["outro_start"] = parse_time(outro.get("start"))

            for scene in timeline_scenes:
                layout = scene.get("layout")
                duration = parse_time(scene.get("duration"))
                if duration <= 0:
                    continue
                if layout == "intro":
                    self.timeline_anchors["intro_start"] = parse_time(scene.get("start"))
                    paths.append(self.render_intro(idx, scene))
                elif layout == "show_image":
                    paths.append(self.render_show_image(idx, scene))
                elif layout == "outro":
                    self.timeline_anchors["outro_start"] = parse_time(scene.get("start"))
                    paths.append(self.render_show_image(idx, scene, outro=True))
                elif layout in program_layouts:
                    paths.append(self.render_program(idx, scene))
                else:
                    continue
                final_time += duration
                idx += 1

            self.timeline_anchors.setdefault("opening_show_image_start", 0.0)
            self.timeline_anchors.setdefault("outro_start", final_time)
            self.timeline_anchors["final_end"] = final_time

            raw = self.out / "final_no_subtitles.raw.mp4"
            mixed = self.out / "final_no_subtitles.mixed.mp4"
            final_no_subtitles = self.renders / "final_no_subtitles.mp4"
            self.concat_segments(paths, raw)
            self.mix_audio_cues(raw, mixed)
            self.normalize_master(mixed, final_no_subtitles)
            if with_subtitles:
                self.burn_subtitles(final_no_subtitles, self.renders / "final_with_subtitles.mp4")
            return

        if self.setting_bool("auto_intro", True):
            self.timeline_anchors["scenes_are_final_time"] = 0.0
            intro_path = self.asset_path(self.setting_text("intro_asset", "intro.mp4"))
            duration = media_duration(intro_path)
            paths.append(self.render_intro(idx, {"host_source": intro_path.name, "duration": f"{duration:.3f}"}))
            final_time += duration
            idx += 1

        if self.setting_bool("auto_opening_show_image", True):
            self.timeline_anchors["opening_show_image_start"] = final_time
            duration = self.setting_time("opening_show_image_duration", 5.0)
            paths.append(self.render_show_image(idx, {"duration": f"{duration:.3f}"}))
            final_time += duration
            idx += 1

        self.timeline_anchors["interview_start"] = final_time
        for scene in scenes:
            paths.append(self.render_program(idx, scene))
            final_time += parse_time(scene.get("duration"))
            idx += 1

        self.timeline_anchors["outro_start"] = final_time
        if self.setting_bool("auto_outro_show_image", True):
            duration = self.setting_time("outro_show_image_duration", 5.0)
            paths.append(self.render_show_image(idx, {"duration": f"{duration:.3f}"}, outro=True))
            final_time += duration

        self.timeline_anchors["final_end"] = final_time

        raw = self.out / "final_no_subtitles.raw.mp4"
        mixed = self.out / "final_no_subtitles.mixed.mp4"
        final_no_subtitles = self.renders / "final_no_subtitles.mp4"
        self.concat_segments(paths, raw)
        self.mix_audio_cues(raw, mixed)
        self.normalize_master(mixed, final_no_subtitles)
        if with_subtitles:
            self.burn_subtitles(final_no_subtitles, self.renders / "final_with_subtitles.mp4")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a video project from planning/video_plan.json.")
    parser.add_argument("project", help="Path to project folder")
    parser.add_argument(
        "--template",
        default=None,
        help="Path to template_config.json. Defaults to video_system/templates/ramair_interview/template_config.json.",
    )
    parser.add_argument("--with-subtitles", action="store_true", help="Also render final_with_subtitles.mp4.")
    parser.add_argument("--max-scenes", type=int, default=None, help="Render only the first N enabled scenes for smoke tests.")
    args = parser.parse_args()

    project = Path(args.project)
    system_root = Path(__file__).resolve().parents[1]
    # The FFmpeg layout assets (1cam.png, 2cam.png, ... + styles/) live under
    # visual_systems/parlayvu_interview/legacy/. (The old templates/ramair_interview/
    # path only carries a README in the repo — its assets were relocated here.)
    default_template = system_root / "templates" / "visual_systems" / "parlayvu_interview" / "legacy" / "template_config.json"
    template = Path(args.template) if args.template else default_template
    Renderer(project, template, args.max_scenes).render(args.with_subtitles)


if __name__ == "__main__":
    main()
