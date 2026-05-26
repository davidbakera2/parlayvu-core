# Meeting Notes Template Authoring Guide

> How to build a Word template that the ParlayVU meeting notes service knows how to fill in.
>
> The renderer supports three behaviors: **simple text substitution**, **list paragraph duplication**, and **action items table row duplication**. This guide tells you which placeholder goes where and how to style it so the renderer does the right thing.

## Where the template lives

Every client uses the same filename: `Meeting_Notes_Template.docx`. Only the content of the docx varies per client.

**Canonical location (Teams-first source of truth):**
```
<client Teams channel> / Files / 06_Templates / Meeting_Notes_Template.docx
```

Clients open this file in Word directly from Teams, edit branding/wording/structure, save back. Nathan picks up the change on the next `save_meeting_notes` call — no deploy required.

**Repo starter / cold-start fallback:**
```
client_artifacts/<client_id>/06_Templates/Meeting_Notes_Template.docx
```

The repo copy ships in the Docker image and is used as a starter (uploaded to Teams once at onboarding) and as a fallback if Teams is unreachable. The path can be overridden per client via `teams.template_path` in their `config.yaml`, but no client currently does.

---

## The 10 placeholders

### 1. Simple text substitutions

Just put the placeholder anywhere in the document — it gets replaced with a single string. Works in body paragraphs, headers, footers, and table cells.

| Placeholder | Filled with | Source |
|---|---|---|
| `{{MEETING_TITLE}}` | The meeting title | Nathan, from conversation |
| `{{MEETING_DATE}}` | Friendly date + time, e.g. "May 25, 2026 at 14:32 UTC" | Nathan (or server-default to "now") |
| `{{PROJECT}}` | Project display name | Nathan |
| `{{CLIENT}}` | Short client name (e.g. "RamAir") | Service (from `client_id`) |
| `{{CLIENT_NAME}}` | Full client name (e.g. "RamAir International") | Service (from project context) |
| `{{SUMMARY}}` | 2-4 paragraph plain-prose summary | Nathan |

### 2. List paragraph duplication

For these placeholders, put the placeholder **inside a bulleted-list paragraph** in Word. The renderer detects the paragraph style and duplicates the paragraph once per item.

**How to set this up in Word:**
1. Type the placeholder, e.g. `{{DECISIONS}}`
2. Select the paragraph
3. Apply the "List Bullet" style (Home → Styles → List Bullet) — or any bulleted list style
4. That's it. The paragraph stays bulleted in every copy the renderer makes.

If Nathan provides 3 items, you'll get 3 bulleted paragraphs. If he provides 0, the placeholder paragraph is deleted entirely (no orphan bullet).

| Placeholder | Filled with |
|---|---|
| `{{ATTENDEES}}` | One person per bullet |
| `{{DECISIONS}}` | One decision per bullet |
| `{{QUESTIONS}}` | One question per bullet |
| `{{NEXT_STEPS}}` | One step per bullet |
| `{{SOURCE_MATERIAL}}` | One reference per bullet |

### 3. Action items table row duplication

For action items, build a table with **a header row** (column titles) and **one template row** that contains the three action-item placeholders, one per cell:

```
+----------+------------------+----------+
| OWNER    | ACTION ITEM      | DUE DATE |     ← header row (static, keep as-is)
+----------+------------------+----------+
| {{ACTION_OWNER}} | {{ACTION_ITEM}} | {{ACTION_DUE}} |   ← template row, duplicated per action item
+----------+------------------+----------+
```

The renderer finds the row containing any of those placeholders, duplicates it once per action item Nathan extracts, and fills the cells.

**Accepted placeholder names per column** (use whichever feels natural; the renderer recognizes any of these):

| Column | Accepted placeholders |
|---|---|
| Owner | `{{ACTION_OWNER}}`, `{{OWNER}}` |
| Action item | `{{ACTION_ITEM}}`, `{{ACTION}}`, `{{ITEM}}`, `{{TASK}}` |
| Due date | `{{ACTION_DUE}}`, `{{ACTION_DATE}}`, `{{DUE_DATE}}`, `{{DUE}}` |

You can style the template row however you like — borders, fill color, font — and every duplicated row inherits the same styling.

**Empty case:** if Nathan passes no action items, the template row is filled with em-dashes ("— / No action items recorded. / —") so the table still renders cleanly.

---

## Recommended template structure

Adapt to taste, but here's a structure that maps cleanly to all 10 fields:

```
┌─────────────────────────────────────────────────────────┐
│ {{CLIENT_NAME}} — Meeting Notes                          │  (Title style)
│ {{MEETING_TITLE}}                                        │  (Heading 1)
│                                                          │
│ Date:     {{MEETING_DATE}}                               │  (info block)
│ Project:  {{PROJECT}}                                    │
│ Client:   {{CLIENT}}                                     │
│                                                          │
│ ─── ATTENDEES ───                                        │  (Heading 2)
│ • {{ATTENDEES}}                                          │  (List Bullet style)
│                                                          │
│ ─── SUMMARY ───                                          │  (Heading 2)
│ {{SUMMARY}}                                              │  (normal paragraph)
│                                                          │
│ ─── DECISIONS ───                                        │
│ • {{DECISIONS}}                                          │  (List Bullet)
│                                                          │
│ ─── ACTION ITEMS ───                                     │
│ ┌──────────┬─────────────────────┬──────────┐            │
│ │ OWNER    │ ACTION ITEM         │ DUE DATE │            │  (header row)
│ ├──────────┼─────────────────────┼──────────┤            │
│ │ {{ACTION_OWNER}} | {{ACTION_ITEM}} | {{ACTION_DUE}} │  (template row)
│ └──────────┴─────────────────────┴──────────┘            │
│                                                          │
│ ─── QUESTIONS ───                                        │
│ • {{QUESTIONS}}                                          │  (List Bullet)
│                                                          │
│ ─── NEXT STEPS ───                                       │
│ • {{NEXT_STEPS}}                                         │  (List Bullet)
│                                                          │
│ ─── SOURCE MATERIAL ───                                  │
│ • {{SOURCE_MATERIAL}}                                    │  (List Bullet)
└─────────────────────────────────────────────────────────┘
```

---

## Common pitfalls

- **Placeholder split across runs in Word.** If you typed `{{MEETING_TITLE}}`, then went back and bolded just the `MEETING_TITLE` part, Word may split the text into multiple runs internally. The renderer handles this for simple substitutions and for list paragraphs, but it's still good practice to type the placeholder in one go with consistent formatting.

- **List style not actually applied.** If your bullet looks bulleted but the paragraph isn't styled as a list (e.g. you used a literal `•` character), the renderer won't recognize it. Apply the **List Bullet** or **List Paragraph** style via Word's Style panel.

- **Action items table without a template row.** If the table has only a header row and no row containing the three `{{ACTION_*}}` placeholders, the renderer has nothing to duplicate. Always include a template row.

- **Multiple template rows in one table.** The renderer uses the *first* row containing the placeholders. If you accidentally include the placeholders in multiple rows, only the first is used.

- **Multi-paragraph summary.** `{{SUMMARY}}` is a single string substitution. If Nathan returns a multi-paragraph summary, it gets joined into one paragraph with line breaks inside. If you want each summary paragraph as a separate Word paragraph, consider switching `{{SUMMARY}}` to the list-paragraph pattern (style as normal body text and let the renderer duplicate).

---

## Testing locally

You can render a template with arbitrary data without going through Tavus:

```python
from app.microsoft365 import (
    build_meeting_notes_template_placeholders,
    render_meeting_notes_template_docx,
)

with open("client_artifacts/ramair/06_Templates/Meeting_Notes_Template.docx", "rb") as f:
    template = f.read()

placeholders = build_meeting_notes_template_placeholders(
    title="RamAir Test",
    summary="This is a test meeting.",
    client_id="ramair",
    client_name="RamAir",
    client_full_name="RamAir International",
    project_name="Straight From The Hart",
    meeting_date_time="May 25, 2026 at 10:00 AM ET",
)

rendered = render_meeting_notes_template_docx(
    template,
    placeholders,
    list_items={
        "{{ATTENDEES}}":       ["David Baker (ParlayVU)", "Sarah Hart (RamAir)"],
        "{{DECISIONS}}":       ["Approve Q3 budget shift to paid social."],
        "{{QUESTIONS}}":       ["Should we A/B test the new landing copy?"],
        "{{NEXT_STEPS}}":      ["Riley to schedule a 2-week sprint kickoff."],
        "{{SOURCE_MATERIAL}}": ["Q2 performance dashboard", "https://ramairinternational.com/about"],
    },
    action_items=[
        {"owner": "Riley", "action": "File the meeting notes.",  "due_date": "EOD today"},
        {"owner": "Dylan", "action": "Stage the site refresh.",  "due_date": "May 30"},
        {"owner": "TBD",   "action": "Confirm Q4 launch window.", "due_date": "TBD"},
    ],
)

with open("test-output.docx", "wb") as f:
    f.write(rendered)
```

Open `test-output.docx` in Word and verify all sections look right.
