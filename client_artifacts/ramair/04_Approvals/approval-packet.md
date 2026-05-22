# Approval Packet

Project: `ramair-straight-from-the-hart`

Use this packet for client-facing publishing, deployment, outbound email, and sourced claims.

Approval request template:

```json
{
  "client_id": "ramair",
  "project_id": "ramair-straight-from-the-hart",
  "requested_by_agent": "nathan",
  "action_type": "publish_campaign_kit",
  "title": "Approve weekly RamAir campaign kit",
  "summary": "Review the weekly episode campaign kit before client-facing publishing or deployment.",
  "metadata": {
    "source": "Straight from the Hart weekly episode",
    "channel": "teams"
  }
}
```

Decision record:

- Approval ID: TBD from `/approvals` or Teams approval card.
- Decision: pending / approved / changes_requested / rejected.
- Approver: TBD.
- Notes: TBD.

Nathan instruction: include approval IDs in Teams responses and do not say work is approved until the approval record status is `approved`.
