# ParlayVU Founder Talk Track

Draft for a 5-7 minute angel conversation. Designed for Ann Arbor/Michigan angels while remaining useful for broader B2B software meetings.

## 0:00-0:45 Opening

ParlayVU is a Microsoft-native AI operating system for client-facing expert firms.

The simple version is this: every agency, consultant, coach, and professional services firm has the same hidden margin leak. A client call ends, then the real work begins. Notes have to become follow-up. Source material has to become campaign assets. Decisions have to become tasks. Reports have to become updates. Approvals have to be tracked. Most of that work gets scattered across Teams, email, documents, dashboards, and project tools.

ParlayVU puts an AI team inside that operating surface. Nathan is the orchestrator in Teams. He routes work to specialist agents, uses project memory, produces client-ready outputs, and keeps human approval gates around anything that goes out to a client.

## 0:45-1:45 Problem

The market is full of AI tools that can write a paragraph or summarize a transcript. That is useful, but it does not run the client workflow.

For client-facing expert firms, the workflow is the product. Their expertise turns into meeting notes, campaign plans, websites, social posts, email drafts, dashboards, approvals, and weekly updates. The painful part is not just creating one asset. It is keeping all of that coordinated around a real client, a real project, and real approval constraints.

SMB and boutique firms want AI leverage, but they do not want to hire an internal AI team or rebuild their stack. They already live in Microsoft 365. So the opportunity is to make AI operational inside Teams, SharePoint Files, Word, Planner, Power BI, and agent mailboxes.

## 1:45-2:45 Solution

ParlayVU gives these firms a Teams-native AI workspace.

Nathan is the front door. A user can ask Nathan about a client project, request a weekly update, create meeting notes, prepare follow-up, or route a deliverable. Nathan pulls from project memory and hands work to specialist agents for writing, web generation, design, deployment, sales, paid media, distribution, partnerships, and customer success.

The important design choice is control. Client-facing sends, publishing, deployments, public claims, and commitments are approval-gated. ParlayVU is not trying to be an uncontrolled autonomous employee. It is trying to be the operating layer that gets work ready, grounded, routed, and approved.

## 2:45-3:45 Product Proof

The current product already demonstrates the workflow loop.

We have a FastAPI and LangGraph backend with Nathan routing and specialist agents. We have project memory scaffolding for clients, projects, source assets, generated outputs, approvals, and agent events. We have Teams-style message routing into Nathan. We have Microsoft 365 Files publishing that creates meeting notes as both `.md` for machine-readable memory and `.docx` for client review. We have approval endpoints and Teams-ready approval cards.

The RamAir pilot gives us a concrete client workspace model: Teams channel structure, SharePoint Files folders, meeting-note workflow, Planner direction, approval packets, and a Power BI starter structure for social performance reporting.

On the avatar side, we have validated a provider-hosted Nathan conversation path with Tavus and have HeyGen LiveAvatar endpoints for grounded project questions and approved notes. I am careful about this claim: Nathan is not yet a production native Teams audio/video participant. The native Teams media bot is scaffolded, and the Microsoft Graph media bridge is roadmap work.

## 3:45-4:45 Market And Wedge

The first wedge is not every enterprise. It is client-facing expert firms that already sell knowledge work and already use Microsoft 365.

That includes boutique agencies, consultants, coaches, professional services firms, and expert-led businesses. These teams have repeatable meetings, repeatable source material, repeatable deliverables, and repeatable reporting. They are also small enough that a founder-led pilot can create clear ROI quickly.

The Ann Arbor and Michigan angel angle is straightforward: this is practical B2B productivity software, built around a local founder/customer pilot story, with a Microsoft-native workflow that fits real SMB operations. But the market is not local. Michigan is the launch network and credibility base, not the ceiling.

## 4:45-5:45 Business Model And GTM

Early go-to-market is founder-led pilots.

The first 3-5 pilots should look like the RamAir workspace: configure the client channel, bind project memory, publish meeting notes, prepare weekly updates, create approval packets, and generate campaign or website assets from source material. Early pricing can include a setup or pilot fee plus monthly subscription.

Over time, the model becomes repeatable subscriptions based on active clients or projects, agent seats, integrations, generated outputs, and premium workflow modules. Services-assisted onboarding is fine at the beginning because it helps us learn which workflows become product templates.

The ask from angels is not only capital. It is introductions to agencies, consultants, Microsoft-centric SMBs, professional services operators, and other Ann Arbor/Michigan investors who understand practical workflow software.

## 5:45-6:45 Ask And Close

We are raising a $100k-$300k angel/pre-seed round.

The capital goes into product hardening, pilot delivery, Microsoft 365 and Teams integration, Tavus/LiveAvatar validation, design/pitch assets, and founder-led go-to-market. The near-term milestones are to polish the RamAir pilot, convert the demo into a repeatable pilot package, run 3-5 qualified pilot conversations, and move toward first paid pilots or signed pilot LOIs within 90 days of funding.

The reason this is investable now is that the product has moved beyond a concept. The working pieces exist: Nathan, project memory, approvals, M365 Files outputs, RamAir artifacts, hosted backend direction, and avatar-provider validation. The round is about turning that proof into repeatable revenue.

The closing line I would leave you with is: ParlayVU is building the AI operating system for client work, starting exactly where those firms already work every day: Microsoft Teams.

## Shorter 90-Second Version

ParlayVU is a Microsoft-native AI operating system for client-facing expert firms.

Every agency, consultant, coach, and professional services firm loses time after client interactions. Calls, transcripts, source assets, notes, emails, dashboards, tasks, and approvals all scatter across different tools. Generic AI helps draft content, but it does not run the workflow.

ParlayVU puts Nathan, an AI orchestrator, inside Teams. Nathan uses project memory, routes tasks to specialist agents, creates client-ready outputs, and keeps approval gates around anything that goes out to a client. The current product demonstrates Teams-style Nathan routing, project memory, approval workflows, M365 Files meeting notes as `.md` and `.docx`, a RamAir pilot workspace, Power BI starter data, and avatar-provider validation through Tavus and HeyGen scaffolds.

The first customers are boutique agencies, consultants, coaches, and professional services firms already using Microsoft 365. We will sell founder-led pilots, then productize repeatable workspace templates.

We are raising $100k-$300k to harden the product, deliver pilots, deepen Teams/M365 integration, validate the avatar roadmap, and convert the working demo into early revenue. The best help from angels is capital plus introductions to pilot customers and Michigan/Ann Arbor investor networks.
