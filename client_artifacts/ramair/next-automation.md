# Next Automation

First next automation after binding: planned interviews/events capture.

Why this comes first:

- It lets Nathan answer what interviews or events are planned without guessing.
- It supports reliable weekly client updates.
- It is simpler than document ingestion or dashboard integration because Teams posts can provide the first structured input.

Target Teams command:

```text
@ParlayVU add this planned RamAir interview to project memory: <guest/topic/date/prep notes>
```

Initial storage target:

- Project memory agent event, or a future structured interview/event table.

Acceptance criteria:

- Nathan can store a planned interview/event from a Teams post.
- Nathan can list planned interviews/events for RamAir.
- Nathan clearly says when no interviews/events are stored.
- Weekly updates include planned interviews/events only when stored.
