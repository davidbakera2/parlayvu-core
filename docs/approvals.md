# Approval Workflow

Approvals are the control gate for client-facing actions. Agents can request approval for emails, publishing, deployments, claims, live-avatar answers, or other actions that should not happen automatically.

## Statuses

- `pending`: waiting for a human decision.
- `approved`: approved to proceed.
- `rejected`: not approved.
- `changes_requested`: needs revision before approval.
- `cancelled`: no longer needed.

## API Endpoints

- `GET /approvals` lists approvals.
- `GET /approvals?project_id=ramair-straight-from-the-hart` lists approvals for a project.
- `GET /approvals?status=pending` lists approvals by status.
- `POST /approvals` requests approval.
- `POST /approvals/{approval_id}/decision` records a human decision.

## Request Approval

```json
{
  "client_id": "ramair",
  "project_id": "ramair-straight-from-the-hart",
  "requested_by_agent": "dylan",
  "action_type": "deploy_site",
  "title": "Deploy updated RamAir landing page",
  "summary": "Dylan generated a new landing page and needs approval before deployment.",
  "generated_output_id": "optional-output-id",
  "metadata": {
    "target": "cloudflare_pages"
  }
}
```

## Decide Approval

```json
{
  "status": "approved",
  "approver": "dave@parlayvu.ai",
  "decision_notes": "Approved for the investor demo."
}
```

When an approval is tied to a generated output, the generated output status is updated to match the decision.

## Current Gates

- Dylan deployment requests now create a `deploy_site` approval if no `approval_id` is supplied.
- Dylan deployment only proceeds when the supplied approval is `approved`, belongs to the requested project when `project_id` is supplied, and matches `action_type=deploy_site`.
- Microsoft 365 email draft creation can create a `send_email` approval request when `client_id` and `project_id` are supplied.

These gates are intended to make Teams approval cards straightforward in the next iteration.
