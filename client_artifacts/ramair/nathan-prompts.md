# Standard Nathan Prompts

Use these prompts in the RamAir Teams channel `Posts` tab.

## Project Status

```text
@ParlayVU summarize the current RamAir project status from project memory.
```

Guardrail: use only stored RamAir memory and name missing source material.

## Approvals

```text
@ParlayVU what approvals are pending for RamAir, including approval IDs and blockers?
```

Guardrail: do not imply anything is approved unless the approval record says so.

## Interviews

```text
@ParlayVU what RamAir interviews or events are planned, and what prep is missing?
```

Guardrail: say when planned interviews/events have not been stored yet.

## Metrics

```text
@ParlayVU summarize the latest RamAir performance snapshot and call out missing metrics.
```

Guardrail: never invent performance numbers; report only connected or stored metrics.

## Weekly Update

```text
@ParlayVU prepare a client-facing weekly RamAir update with decisions, blockers, and next actions.
```

Guardrail: keep the update client-safe and flag approval-required claims.
