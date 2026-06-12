# Ads Parlay

**Status:** Draft v1
**Owner:** ParlayVU Core
**Last Updated:** 2026-06-12

## Overview

**Ads Parlay** is a productized, recurring **managed Google Ads** service: we run
and continuously optimize a client's Google Ads account as an ongoing monthly
engagement. It is the paid-media sibling to [Podcast Parlay](podcast-parlay.md) —
same subscribe-by-magic-link + Stripe billing, same agent-orchestrated delivery
model, applied to performance advertising instead of content production.

**Price:** $500 / month (recurring). This is the **management fee only** — the
client's ad spend is billed separately by Google and is never marked up.

First client: **Alloy Gutter Company, Inc.** (Michigan home-services / gutters).
The month-one audit was delivered as `Alloy_Gutter_Ads_Analysis_v4.pptx`.

## The key framing: audit once, manage forever

The strategic deck is a **one-time deliverable with an end**. A subscription needs
an **ongoing loop with no end**. So:

- **Month 1 (onboarding):** the account audit + optimization roadmap (the deck).
  This is the one-time "fix the foundation" work — it justifies the first
  invoice and sets the 90-day plan.
- **Month 2 onward (retainer):** hands-on management against that roadmap —
  the recurring optimization cycle below. This is what the $500/mo actually buys
  in perpetuity, and what keeps the subscription worth renewing.

## What the subscription includes

| Pillar | Recurring activities |
|---|---|
| **Account health** | Monitor disapprovals, destination/URL errors, policy issues, and the optimization score; fix issues as they appear. |
| **Bidding & budget** | Manage bid strategy by campaign maturity (Maximize Conversions → soft CPA → Target CPA/ROAS); keep daily budgets aligned to proven ROI. |
| **Keywords & search terms** | Maintain match-type mix (exact / phrase / broad), mine the search-terms report, and grow shared negative-keyword lists. |
| **Ads & assets** | Keep ad copy and PMax asset groups fresh; push asset ratings toward Excellent; manage extensions/sitelinks. |
| **Geographic expansion** | Phase rollout across market zones (e.g. Alloy's SE → West → East → Central Michigan) as earlier zones prove out. |
| **Competitor intercept** | Run and tune branded-competitor campaigns with comparison ad copy. |
| **Reporting** | Monthly performance report + a live Looker Studio dashboard; a standing review cadence with the client. |

## Monthly delivery cadence (the retainer loop)

A repeatable month, mirroring the Podcast Parlay's weekly cadence:

1. **Week 1 — Review & triage:** pull the prior month's numbers, check account
   health (disapprovals, score, anomalies), set the month's priorities.
2. **Week 2–3 — Optimize:** execute changes — bids, budgets, keywords, negatives,
   new/paused campaigns, asset refreshes, geo and competitor moves.
3. **Week 4 — Measure & report:** update the Looker Studio dashboard, deliver the
   monthly report, and agree next month's focus with the client.

## Agent mapping

Reuses the existing specialist roster, led by Nathan:

- **Morgan Patel (Paid Media)** — primary operator: campaign reads, optimization moves.
- **Blake Quinn (Research & Analytics)** — competitor research, market/geo inputs, performance analysis.
- **Ava Hosseini (Content Writing)** — ad copy, comparison landing-page copy.
- **Michael Chen (Offers & Sales)** — offer/conversion-path alignment.
- **Taylor Kim (Client Success)** — reporting cadence, approvals, expectations.
- **Nathan Ellis** — strategy, routing, approval gates, monthly review.

Human approval gates apply to budget changes, new campaigns, and client-facing ad
claims (via the existing Approvals system).

## Billing & site

- Catalog entry: `ADS_PARLAY` in [`app/plans.py`](../../app/plans.py)
  (slug `ads_parlay`, price env `STRIPE_PRICE_ID_ADS_PARLAY`, lookup key
  `ads_parlay_500_per_month`).
- Subscribe flow: identical to Podcast Parlay — magic-link login → dashboard →
  Stripe Checkout. See [docs/billing.md](../billing.md).
- Marketing: the `#ads-parlay` section on parlayvu.ai.

## Roadmap

1. Onboard Alloy Gutter as the pilot subscription.
2. Formalize the monthly report + Looker Studio template as a reusable asset.
3. Build agent assists for the recurring loop (search-terms triage, anomaly
   flagging, draft optimization recommendations for human approval).
4. Generalize beyond gutters/home-services to other local-service verticals.

---

*This document will evolve as Ads Parlay is implemented and refined.*
