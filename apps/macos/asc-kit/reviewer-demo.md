# Reviewer demo + App Review notes

**Status:** paste-ready. The Store build now embeds `Resources/ReviewerDemo`.
No zip attachment is required.

## Review notes (paste)

> Launch RunSpecimen. The Store build opens the bundled Reviewer Demo
> automatically (reviewer-demo / run-001 in Application Support). Source
> should read Bundled Helpers — do not pip install and do not select an
> external CLI. Use Workspace → Open Reviewer Demo if you need a fresh copy.
>
> Inspect status (read-only).
>
> Open Approve… and type APPROVE yourself on the PTY. Do not automate. The app
> never auto-approves and has no agent API.
>
> Quit and confirm the loopback dashboard child is gone.
>
> App Sandbox confines the UI and its inherit helper; it does not OS-sandbox
> the payload under test. Certificates are hash-chained receipts, not
> asymmetric digital signatures. Data Not Collected. No telemetry.
>
> Support: https://runspecimen.darashkevich.com/support/
> Privacy: https://runspecimen.darashkevich.com/privacy/

## Demo path (5 steps)

1. Launch RunSpecimen — the bundled Reviewer Demo workspace opens automatically. Source should read **Bundled Helpers**. Do **not** pip install.
2. If you need a fresh copy, click **Open Reviewer Demo** (or Workspace → Open Reviewer Demo).
3. Refresh status / inspect evidence (read-only). Contract `reviewer-demo` / `run-001` is pre-selected.
4. Open **Approve…** — type `APPROVE` yourself on the PTY (**do not automate**).
5. Quit — confirm the loopback dashboard child is gone (Activity Monitor / no stray port).

## Contact for Review

| Field | Value | Status |
| --- | --- | --- |
| Demo account | N/A — no accounts | Ready |
| Contact | Yahor (ASC Account Holder) | In Connect |
| Notes attachment | not required | Bundled ReviewerDemo |

## Automated evidence (not a substitute for Review)

Local positive e2e (never types APPROVE):

```bash
cd apps/macos
./Scripts/archive_mas.sh
./Scripts/test_mas_sandbox_e2e.sh
```

Covers workspace bookmark, dashboard cleanup, and PTY gate wait on the sandboxed app + bundled helper.
