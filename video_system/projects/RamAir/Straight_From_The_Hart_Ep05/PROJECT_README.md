# Straight From The Hart - Episode 5 (David Baker + David Hart + Bob Jordan)

**Client:** RamAir International
**Show:** Straight_From_The_Hart
**Episode:** Ep05
**Participants (actual from dropped assets + transcript for Ep05):**
- Host / Interviewer: David Baker (Baker Strategy LLC)
- Guest / Featured: David Hart (Founder & CEO, RamAir International)
- Guest_02: Bob Jordan, PE (author, The Mitigation Handbook; Pure Clean franchise owner)

**Raw assets location (Riverside exports):**
Drop the raw files here:
`video_system\projects\RamAir\Straight_From_The_Hart_Ep05\assets\`

Expected files:
- host.mp4          (David Hart - main host track)
- guest_01.mp4      (John Miles)
- guest_02.mp4      (other guest)
- Any separate enhanced audio tracks
- b-roll files you identified
- Branding assets if needed (show_image.png, logo_square.png, music.wav, etc.)

**Transcript:**
Export the full transcript + speaker labels + timestamps from Riverside and place as:
`planning\captions.srt`  (replace the existing sample)

**Current status:**
- Project folders created (assets, renders, previews)
- Parlay state initialized in ParlayVU system (project_id: ramair-Straight_From_The_Hart_Ep05)
- Assets confirmed present (3 Riverside tracks + generated branding/dummies)
- Stage: longform_draft (in review)
- **First pre-captions assembly draft (FFmpeg fallback)**: renders/longform_draft_v01.mp4 (~2:02). This was a structural proof using the plan + real footage while Resolve automation was being activated.
- **Real Resolve-native draft**: Run the new `video_system/tools/resolve/build_timeline.py` (while DaVinci Resolve is open with a project for this episode). It will build bins + a timeline laid out exactly from video_plan.json (clips, scene timings, lower third markers). Then render from Resolve Deliver page to renders/longform_draft_v01_resolve.mp4 (or similar). Record that as the official v1 in parlay_state. The workflow spec (PODCAST_PARLAY_FULL_WORKFLOW.md) calls for Resolve as the NLE truth for all assembly, captions, and final production work.

**Standard next steps (Podcast Parlay workflow):**
1. Copy raw footage + b-roll into assets/
2. Add real captions.srt
3. Edit planning/video_plan.xlsx with actual timings, layouts, lower thirds, broll placements
4. Run: validate_project.py + spreadsheet_to_json.py
5. Build timeline in DaVinci Resolve (v2 tools)
6. Render draft → request approval in ParlayVU (via Nathan or /approvals)
7. Iterate with client feedback (new renders, new approval cards)
8. Captions round → final production approval
9. YouTube publish (unlisted) + clips phase (5-10 shorts with their own approval loop)

See the full workflow spec:
video_system\docs\PODCAST_PARLAY_FULL_WORKFLOW.md
(and the nice HTML viewer: video_system\docs\Podcast_Parlay_Workflow.html)

Edit this README as we make progress on Ep05.

[Nathan re-entered the project]


[Nathan re-entered the project]


[Nathan re-entered the project]


[Nathan re-entered the project]
