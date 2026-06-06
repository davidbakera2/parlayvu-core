# Video Plan Workbook Columns

## Scenes

- `scene_id`: Stable row identifier, unique within the project. Example: `S001`.
- `enabled`: `TRUE` or `FALSE`.
- `start`: Final rendered-video timeline start in `HH:MM:SS.000`, including intro, opening show image, interview, and outro.
- `end`: Final rendered-video timeline end in `HH:MM:SS.000`, including intro, opening show image, interview, and outro.
- `duration`: Optional helper formula. The converter can calculate this from `start` and `end`.
- `layout`: `intro`, `show_image`, `1cam`, `2cam`, `2cam_broll`, `3cam`, `3cam_broll`, `outro`.
- `source_start`: Where to begin inside the source camera media. Leave blank only when the scene should follow directly from `start - interview_start`; use this field when sections have been cut from the source footage.
- `primary_camera`: `host`, `guest_01`, `guest_02`, or blank.
- `host_source`: Usually `host.mp4`.
- `guest_01_source`: Usually `guest_01.mp4`.
- `guest_02_source`: Optional.
- `broll_id`: Links to the Broll sheet.
- `broll_file`: Optional direct filename override.
- `broll_source_start`: Where to start inside the b-roll file.
- `top_row_text`: Top lower-third row.
- `bottom_row_text`: Bottom lower-third topic row.
- `notes`: Human notes; ignored by renderer.

## Broll

- `broll_id`: Stable ID such as `broll_01`.
- `file_name`: File in the project `assets` folder.
- `description`: Human description.
- `default_source_start`: Optional default start inside the b-roll file.

## Graphics

- `graphic_id`: Stable ID.
- `enabled`: `TRUE` or `FALSE`.
- `type`: `name_card`, `broll_card`, `callout`, `topic_card`.
- `start`: Timeline start.
- `end`: Timeline end.
- `text_line_1`: Main card text.
- `text_line_2`: Secondary card text.
- `position`: Optional placement override.
- `style`: Optional style override.
- `linked_scene_id`: Optional scene reference.

## Assets

- `asset_key`: Logical key, for example `show_image_lower_third`.
- `file_name`: File in the project `assets` folder.
- `purpose`: Human description.

## Settings

- `setting`: Setting key.
- `value`: Setting value.

Common settings:

- `background_video`: Optional file in the project `assets` folder. When set, the renderer loops it behind the whole 1920x1080 program and uses cover scaling, so the background fills the full frame edge-to-edge and crops overflow as needed.
- `timeline_mode`: Use `full_rendered` for the standard workflow. This means review notes from the rendered video can be entered directly into `Scenes.start`, `Scenes.end`, `Graphics.start`, and `Graphics.end`.
