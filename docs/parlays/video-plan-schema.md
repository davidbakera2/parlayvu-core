# Video Plan Schema (Podcast Parlay output contract)

The Podcast Parlay **Agentic Planning** stage emits a `video_plan` — a structured,
machine-readable plan that drives downstream video assembly (DaVinci Resolve). This is
the contract the planning agents target.

A `video_plan` is a JSON object:

```json
{
  "project": "string",
  "scenes": [ ... ],
  "graphics": [ ... ],
  "broll": [ ... ],
  "assets": [ ... ],
  "settings": [ ... ]
}
```

The agentic planning layer produces **`scenes`, `graphics`, and `broll`** (the
transcript-derived, creative parts). `assets` and `settings` are project configuration
(template, file names, render settings) and are normally supplied by project setup, not
inferred from the transcript.

## scenes[]

| Field | Notes |
|---|---|
| `scene_id` | Stable ID, unique in the plan. e.g. `S001`. |
| `enabled` | bool. |
| `start` / `end` | Final rendered-timeline times, `HH:MM:SS.000` (includes intro/outro). |
| `duration` | Optional helper; derivable from start/end. |
| `layout` | One of: `intro`, `show_image`, `1cam`, `2cam`, `2cam_broll`, `3cam`, `3cam_broll`, `outro`. |
| `source_start` | Where to begin inside source media; blank when the scene follows directly. |
| `primary_camera` | `host`, `guest_01`, `guest_02`, or blank. |
| `host_source` / `guest_01_source` / `guest_02_source` | Source file names (e.g. `host.mp4`). |
| `broll_id` / `broll_file` / `broll_source_start` | Link to a `broll[]` entry / override file / start inside the b-roll. |
| `top_row_text` / `bottom_row_text` | Lower-third rows (top = name/identity, bottom = topic). |
| `notes` | Human notes; ignored by the renderer. |

## graphics[]

| Field | Notes |
|---|---|
| `graphic_id` | Stable ID, e.g. `G001`. |
| `enabled` | bool. |
| `type` | One of: `name_card`, `broll_card`, `callout`, `topic_card`. |
| `start` / `end` | Timeline times, `HH:MM:SS.000`. |
| `text_line_1` / `text_line_2` | Main / secondary card text. |
| `position` / `style` | Optional placement / style overrides. |
| `linked_scene_id` | Optional scene reference. |
| `notes` | Human notes. |

## broll[]

| Field | Notes |
|---|---|
| `broll_id` | Stable ID, e.g. `broll_01`. |
| `file_name` | File in the project `assets` folder. |
| `description` | Human description. |
| `default_source_start` | Optional default start inside the file. |
| `notes` | Human notes. |

## assets[] / settings[]

Project configuration, not transcript-derived:

- `assets[]`: `{ asset_key, file_name, purpose }` — logical media keys (show image, lower-third bg, etc.).
- `settings[]`: `{ setting, value, notes }` — e.g. `template_name`, `background_video`, `timeline_mode` (`full_rendered` for the standard workflow).

> History: this contract was originally defined in `video_system/schemas/spreadsheet_columns.md`.
> `video_system` (the DaVinci Resolve execution tooling) has been split out of this repo;
> this document preserves the planning-output contract so the agentic planning layer has a
> stable target.
