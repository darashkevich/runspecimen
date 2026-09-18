---
description: Read-only RunSpecimen status for a campaign/run
---

Run:

```bash
runspecimen status --workspace <workspace> \
  --campaign-id <campaign_id> --run-id <run_id>
```

Status is read-only. It cannot approve, preflight, run, or settle remote-confirm.
