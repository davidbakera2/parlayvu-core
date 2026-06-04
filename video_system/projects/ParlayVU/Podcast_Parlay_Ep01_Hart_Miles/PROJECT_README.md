# Podcast Parlay Episode: David Hart & John Miles

**Client:** ParlayVU (internal/demo)
**Show:** Podcast_Parlay
**Episode:** Ep01_Hart_Miles
**Participants:**
- Host: David Hart (RamAir CEO)
- Guest_01: John Miles
- Guest_02: (the other participant; confirm from Riverside export)

**Raw assets from Riverside (to be placed in assets/):**
- host.mp4 (David Hart)
- guest_01.mp4 (John Miles)
- guest_02.mp4
- Enhanced audio tracks if separate
- Transcript (.srt / .txt with timestamps and speaker labels) -> copy to planning/captions.srt or .txt
- Any b-roll identified
- Branding: show_image.png, show_image_lower_third.png, logo_square.png, intro.mp4, music.wav (copy from previous or templates)

**Process status:** Project scaffolded. State initialized to intake then planning. Sample captions.srt and refined video_plan.json (with structure and lower thirds for Hart/Miles) prepared. Placeholder draft render and approval requested in ParlayVU system (see visualize output for status/Mermaid). 

Next for user: 
- Copy real raw files from Riverside to assets/ (host.mp4 for David Hart as host, guest_01.mp4 for John Miles, guest_02.mp4, broll, branding assets).
- Export real transcript from Riverside as .srt (with speakers) and replace planning/captions.srt .
- Open planning/video_plan.xlsx , update Scenes/Graphics/Broll/ to match actual timings/content from transcript (our json is guide; run tools/spreadsheet_to_json.py after edits to sync).
- Run tools/validate_project.py and tools/spreadsheet_to_json.py .
- Set up Resolve (tools/resolve/SETUP.md), build timeline from plan using resolve tools.
- Render draft, update preview in state/approval if needed.
- Review/iterate via the approval (ID from system).
- Then captions (we have .ass starter), final approval, publish, clips.

Current visualize status: longform_draft with pending approval, parlay_state.json mirrored in project.

See full workflow in video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md and HTML viewer. Use Nathan in Teams (bound to parlayvu) for help e.g. 'propose lower thirds for this episode based on transcript'.

**ParlayVU project_id:** parlayvu-Podcast_Parlay_Ep01_Hart_Miles (for state, approvals, memory)

**Next steps in Podcast Parlay workflow:**
1. Add assets to assets/
2. Prepare transcript in planning/
3. Edit planning/video_plan.xlsx (use before_ templates as starting point)
4. Run validate and to_json
5. Build timeline (Resolve v2 or render)
6. Use AI (Nathan/Alex via app) for lower thirds, broll suggestions, captions
7. Render draft, request approval via the system
8. Iterate based on feedback
9. Captions round
10. Final production approval
11. YouTube upload (unlisted), then clips phase

See video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md and the HTML viewer for full details.

Edit this README as we progress.