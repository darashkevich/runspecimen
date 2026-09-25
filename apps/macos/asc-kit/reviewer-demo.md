# Reviewer demo + App Review notes

**Status:** paste-ready for a future review of successor **0.1.5 (10)**. These notes were not re-pasted into the **0.1.4 (9)** submission that is already on file. Do not treat them as proof that Apple has this build.

## Review notes (paste)

> Launch RunSpecimen. The Store build opens the bundled Reviewer Demo
> automatically (reviewer-demo / run-001 in Application Support). Source
> should read Bundled Helpers — do not pip install and do not select an
> external CLI. Workspace → Open Reviewer Demo reopens the existing demo without deleting receipts.
>
> Inspect status (read-only).
>
> Open Approve… and type APPROVE yourself on the PTY. Do not automate. The app
> never auto-approves and has no agent API.
>
> Close the main window. The app stays running. Choose File → Show Main Window
> (Command-0). The window reopens with the same workspace and contract when
> that contract is still a file inside the workspace. Quitting and launching
> again restores that selection and does not reset the demo or start a run.
> This Store build has no browser dashboard or listening network server;
> inspect evidence with Refresh Evidence, which only reads stored reports.
>
> App Sandbox confines the UI and its inherit helper; it does not OS-sandbox
> the payload under test. Certificates are hash-chained receipts, not
> asymmetric digital signatures. Data Not Collected. No telemetry.
>
> Support: https://runspecimen.darashkevich.com/support/
> Privacy: https://runspecimen.darashkevich.com/privacy/

## Demo path (5 steps)

1. Launch RunSpecimen — the bundled Reviewer Demo workspace opens automatically. Source should read **Bundled Helpers**. Do **not** pip install.
2. To reopen the existing demo, click **Open Reviewer Demo** (or Workspace → Open Reviewer Demo). Existing evidence is preserved.
3. Refresh status / inspect evidence (read-only). Contract `reviewer-demo` / `run-001` is pre-selected.
4. Open **Approve…** — type `APPROVE` yourself on the PTY (**do not automate**).
5. Close the window, choose **File → Show Main Window**, and verify the same workspace is shown. Quit when finished.

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

Covers workspace bookmark, Store dashboard refusal without spawning a server, and PTY gate wait on the sandboxed app + bundled helper. Never types approval.
