# Ann Arbor SPARK — compact application sections

## 1. Product / Problem (1259 chars)

ParlayVU (parlayvu.ai) is an AI-orchestrated marketing operations platform for SMB and mid-market B2B companies. Teams invest in one strong source asset—a podcast, webinar, white paper, or case study—then lose momentum repurposing it across web, email, social, video, and sales. Work fragments across ChatGPT, Canva, freelancers, and project tools with no shared brand voice or publish path.

ParlayVU coordinates twelve specialist agents—Alex, Ava, Blake, Casey, Codey, Dylan, Jordan, Michael, Morgan, Nora, Riley, Taylor—under orchestrator Nathan. Roles span strategy, copy, design, web deploy, social, paid media, sales support, publishing, and retention. Humans approve before anything client-facing ships. One input becomes a structured multi-channel program plus deployment.

Based in Ann Arbor. Focus: professional services, manufacturing, associations. Proof: RamAir (ramair.co) weekly podcast → clips, posts, site updates, collateral; client David Hart cites turnkey cadence and improved sales leads. Baker Strategy Group is founder practice and early design partner.

Large U.S. B2B marketing spend; target firms wanting agency output without re-architecting martech each campaign. Early-stage; programs sold today, full self-serve SaaS later.

## 2. Competitive Advantage (1287 chars)

Market options: DIY AI/design, freelancers, traditional agencies, and platforms like HubSpot. Each handles part of the job; few link strategy, asset production, site deploy, and lead follow-up in one repeatable system. Buyers still coordinate vendors, brand, and publishing calendars manually.

ParlayVU competes on orchestration and shipped delivery: documented agent workflows, Astro client sites on Cloudflare Pages, Resend forms, and agent-readable config (site.contact.json)—not drafts alone. Clients get living infrastructure, not another content folder. Per-client voice templates, program history, and integrations raise switching costs over time.

No patent on generic “AI marketing.” Edge is integrated execution, proprietary routing/playbooks in code, and Ann Arbor relationships in Southeast Michigan. Scale/Enterprise may add Salesforce or HubSpot sync; Grow tier uses lightweight CRM-lite.

Entry barriers are moderate; model APIs are commoditized—trust, QA discipline, and customer references decide wins. Incumbents can copy features; copying operating rhythm and local proof is harder. We avoid competing as a generic chat UI; we sell outcomes and published programs. Win theme: speed from source asset to live multi-channel presence with one accountable operator.

## 3. Technology Platform (1274 chars)

Technology: Python FastAPI and LangGraph in parlayvu-core for multi-agent routing, structured task payloads, and approval gates. Specialist agents call tools—e.g., Dylan scaffolds ParlayVU client sites and triggers Cloudflare deploy from client config. Marketing sites: Astro, Tailwind, Cloudflare Pages; contact via Resend API routes (no third-party form hacks). parlayvu.ai and bakerstrategy.com run this stack today.

IP: proprietary software, prompts, and delivery standards (sites/PARLAYVU_CLIENT_SITES.md, _template/, launch-client.mjs). No issued patents; no university or employer claim on core IP. Copyright and trade secret on code and process docs. Client data stays in client-owned cloud accounts where possible.

Roadmap: harden Nathan routing, Grow-tier CRM-lite (Attorney/Pipedrive-class), pilot Salesforce/HubSpot for enterprise tier; HeyGen and Microsoft Graph for optional channels. Built on standard cloud/APIs only—no lab or corporate R&D dependency. Security posture: least-privilege API keys, client-owned Pages projects, audit trail on agent tasks awaiting approval. Version control and agent guides (AGENTS.md) keep delivery consistent as models update. Open-source dependencies are standard; differentiation is orchestration layer and playbooks.

## 4. Development Activities (1267 chars)

Current status: working prototype, not self-serve SaaS yet. parlayvu.ai live; bakerstrategy.com rebuilt on ParlayVU web playbook; RamAir pilot producing weekly multi-channel assets with client-reported lead uplift. Baker Strategy clients receive programs today while product packaging matures.

Next 90 days: (1) Grow-tier playbook for 3–5 SE Michigan pilots; (2) productize site.contact.json + launch-client.mjs onboarding; (3) two case studies including RamAir metrics; (4) CRM-lite sync from Resend form leads; (5) structured pricing with Baker Strategy accounts.

Milestones through month 12: paid pilot contracts, documented ROI narrative, 30-day onboarding kit, first monthly program revenue outside founder network, agent coverage for full “source-to-publish” loop without custom one-offs.

Partners: SPARK mentors and customer intros; Cloudflare/Resend for infra. No exclusive OEM required for Grow launch. University tech transfer not applicable. Risk: delivery capacity—mitigated by playbook automation and contract creative bench before full-time hires. Productization path: move repeatable pilot steps into self-serve onboarding while keeping strategy layer human-led. Regulatory exposure low—B2B marketing content, not healthcare or finance advice.

## 5. Business Model (1227 chars)

Revenue model: monthly marketing programs (recurring) plus setup/onboarding. Three tiers in design—Grow (SMB, ParlayVU-run programs + lightweight CRM), Scale (mid-market, deeper integrations), Enterprise (sync to client Salesforce/HubSpot). Pricing under validation; early pilots combine platform access and strategy hours from Baker Strategy.

Go-to-market: founder-led sales via existing relationships, proof-led case studies, SE Michigan networks, and SPARK mentor introductions—not broad paid ads initially. Positioning: create once, publish everywhere, with human QA on brand and compliance.

Year 1–2 targets: 5–10 paying monthly clients; improve unit economics as playbooks cut deploy and rewrite time. Modest near-term profit; reinvest in automation before scale hiring.

Retention: embedded workflows, trained brand voice per client, live sites and forms on ParlayVU infrastructure. Upsell path from Grow to Scale when clients need ERP/CRM depth. Comparable spend for buyers: often $3k–$15k/month across fractional marketing roles; ParlayVU aims to consolidate that spend with measurable output per source asset. Channel mix stays relationship-driven year one; digital funnel tests follow case-study publication.

## 6. Team (1289 chars)

David Baker — Founder, Ann Arbor. Owns product vision, client strategy, and sales. Market strategy background through Baker Strategy Group (bakerstrategy.com): association publishing, B2B research (Michigan Economic Outlook Survey), executive positioning, and campaign architecture for regional brands.

Hands-on builder on parlayvu-core—agent definitions, LangGraph flows, and client-site standards—using AI-assisted engineering. Prior roles centered on research-led GTM and content programs, not generic IT services.

Nathan and the twelve named agents are productized software roles, not a ten-person agency bench. Humans approve client deliverables and production deploys.

Team plan: founder plus contract design/copy as pilot load grows; advisors for finance and enterprise CRM integrations. SPARK mentors requested for services pricing, pilot contracting, and technical scale.

No other FTEs at filing; first hire (client success or operations) after repeatable pilot revenue and documented onboarding kit. Governance: founder-led; advisory board informal until outside investment. Open to SPARK-introduced technical co-advisor on agent ops, not seeking co-founder immediately. Principal residence and customer development centered in Ann Arbor/Ypsilanti SPARK service area.

## 7. Financial Plan (1249 chars)

Funding: fully bootstrapped/self-funded via Baker Strategy Group operating revenue and founder capital. No venture equity, bank debt, angel SAFEs, or grants disclosed at application. ParlayVU development is funded inside existing practice cash flow plus targeted founder investment.

Spend to date: Cloudflare Pages, Resend, LLM/API usage, domains, dev tools, and founder delivery time on RamAir pilot and bakerstrategy.com migration to the ParlayVU stack. No paid acquisition budget yet.

Total outside capital raised: zero—well under Ann Arbor SPARK’s $5M eligibility cap. Company revenue today is services-led through Baker Strategy; ParlayVU product revenue ramps with pilots.

Near-term fund use: SE Michigan pilot onboarding, LLC formation, basic legal/accounting, selective design contractors, case-study materials. Seek SPARK coaching on pricing and financial worksheets before any dilutive raise. No plans to seek Michigan SBIR or federal grants in year one; focus is customer-funded pilots and services cash flow. Runway tied to Baker Strategy billings plus lean SaaS/API costs—no burn from large headcount. Financial statements available on request. Balance sheet remains simple—no convertible notes or SAFE instruments outstanding.

## 8. Help from SPARK (1214 chars)

Requested from Ann Arbor SPARK:

(1) Entrepreneur Boot Camp and startup setup—LLC structure, baseline financials, pricing worksheets aligned to recurring program model.

(2) Mentor matches: B2B services/SaaS pricing, software/MSA legal, martech and agent-system architecture.

(3) Warm intros to 3–5 Southeast Michigan pilot prospects—manufacturing, professional services, trade associations—fit for Grow tier.

(4) Coworking at SPARK Central or East; principal office remains Ann Arbor.

(5) Feedback on Grow vs. Scale packaging, pilot SOW terms, and eligibility as tech-related early-stage company.

We will share quarterly updates on pilot contracts, RamAir metrics, and product milestones. Goal: credible Ann Arbor tech startup with local proof, then Michigan/Midwest expansion. Founder available for SPARK intake meetings and mentor sessions; prefers actionable feedback over generic networking. Company name on application: ParlayVU (Baker Strategy Group as related strategy entity). Website: parlayvu.ai. Eligible as tech-related, early-stage, Ann Arbor/Ypsilanti company under SPARK guidelines. Ready to complete Boot Camp prerequisites and participate in mentor office hours during pilot ramp.
