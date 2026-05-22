# ParlayVU Deck Proof And Demo Map

Use this as the bridge between the pitch deck, the live/product demo, and credible investor claims.

## Proof Points By Slide

| Deck slide | Claim | Current proof | Demo moment |
| --- | --- | --- | --- |
| 2. Problem | Client work fragments across Teams, files, approvals, dashboards, and follow-up | RamAir channel standard documents the actual workspace sprawl ParlayVU organizes | Show the RamAir channel model: Posts, Files, Planner/Tasks, Meeting Notes, Power BI, Nathan |
| 3. Solution | Nathan orchestrates specialist agents with project memory and approval gates | FastAPI/LangGraph Nathan routing, specialist agent registry, SQLAlchemy memory scaffold, approvals endpoints | Send a Teams-style message to Nathan and show a grounded response or approval-aware output |
| 4. Product | ParlayVU is Microsoft-native, not a generic chatbot | Microsoft Graph setup, Teams front-door endpoints, M365 Files `.md`/`.docx` meeting notes, approval cards | Show the meeting-note publishing flow and the generated Files-ready outputs |
| 5. What Exists Now | The workflow loop is working enough for pilot demos | Readiness checks, demo runbook, RamAir seed data, Dylan site generation, approval request workflow | Run or narrate the investor demo sequence: readiness, Nathan prompt, Dylan generation, approval gate |
| 7. Market Wedge | Client-facing expert firms need repeatable AI workspaces | RamAir pilot artifacts model repeatable client work: source material, planning, deliverables, approvals, performance | Walk through the RamAir folder structure and explain how it becomes a template |
| 8. Business Model | Early pilots can become repeatable workspace subscriptions | Setup/pilot work maps to recurring modules: client channel setup, meeting notes, campaign kits, dashboards | Show which RamAir artifacts are reusable templates versus client-specific content |
| 10. Differentiation | Project memory, approvals, and Microsoft 365 outputs are the moat | Project memory schema ties outputs to clients/projects/source material/approval state; M365 outputs are native files | Contrast a generic AI answer with a project-bound Nathan answer and approval status |
| 11. Roadmap | Native Teams avatar is roadmap, not current production | Teams media bot scaffold, Tavus harness, HeyGen endpoints, provider spike findings | Show the roadmap diagram or docs, and explicitly state media bridge is not yet validated |
| 12. Ask | $100k-$300k funds pilot readiness and early revenue | Known hardening priorities, pilot playbook, demo artifacts, and integration roadmap | Tie each dollar use to a milestone: RamAir polish, pilots, templates, M365/Teams hardening |

## Recommended 7-Minute Demo Flow

1. Open with the RamAir workspace model.
   - Show how Teams is the front door and SharePoint Files holds canonical client artifacts.
   - Emphasize that ParlayVU is organizing existing Microsoft 365 work, not asking customers to move systems.

2. Show Nathan responding in project context.
   - Use a RamAir prompt such as: `@ParlayVU summarize the current RamAir project status from project memory.`
   - If data is missing, let Nathan say so. Strictness about missing memory is a credibility feature.

3. Show meeting notes in Teams Files.
   - Explain the `.md` plus `.docx` pattern.
   - `.md` supports future agent ingestion and search; `.docx` supports client review in Word/Teams.

4. Show approvals.
   - Demonstrate that deployment, send, publishing, and claims are not automatic.
   - Position approval gates as the reason expert firms can trust the system.

5. Show the RamAir performance starter.
   - Walk through the Power BI starter data/spec at a high level.
   - Do not overclaim live metrics automation unless the data is actually wired for the demo.

6. Show avatar status carefully.
   - Tavus validates provider-hosted Nathan conversation grounding.
   - HeyGen endpoints support operator-controlled grounded Q&A and approved notes.
   - Native Teams audio/video participation remains a future milestone after Graph media bridge validation.

7. Close with the funding milestone.
   - The raise converts this from a working demo and pilot scaffold into repeatable customer pilots.

## Claims To Use

- "Working Teams-style Nathan routing into project memory."
- "Hosted backend direction on Azure Container Apps, with readiness checks for investor demos."
- "RamAir pilot workspace defines the repeatable customer pattern."
- "Nathan can publish meeting notes to Teams/SharePoint Files as `.md` and `.docx`."
- "Approval gates are designed into client-facing actions."
- "Power BI starter assets exist for client performance reporting."
- "Tavus has validated a provider-hosted Nathan conversation path; the native Teams media bridge is roadmap."

## Claims To Avoid

- "Nathan autonomously joins Teams calls as a production audio/video participant."
- "Tavus or HeyGen media is already injected into Microsoft Teams through Graph."
- "ParlayVU has mature SaaS traction" unless paid pilots, signed LOIs, or production users are documented.
- "All client reporting is automated" unless the specific dashboard and data refresh are wired for the demo.
- "Outbound sends are automated" while Microsoft Graph send behavior remains disabled by default.

## Demo Backup Plan

If external services or credentials are unavailable, keep the investor demo credible by showing:

- The documented runbook and readiness endpoints.
- Seeded RamAir project memory and channel structure.
- Generated meeting-note artifacts and approval records.
- The Tavus/Teams media bot docs as roadmap evidence, not live production proof.

The backup story should still prove the product thesis: ParlayVU turns client conversations and source material into governed Microsoft-native outputs.
