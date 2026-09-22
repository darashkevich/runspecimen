RunSpecimen reviewer demo
========================

This folder is a complete workspace. The Mac app copies it into Application
Support so App Review can inspect status and type APPROVE without picking a
git checkout or installing Python.

1. Launch RunSpecimen. The Store build opens this workspace automatically.
   Source should read Bundled Helpers.
2. Use Workspace → Open Reviewer Demo for a fresh copy if needed.
3. Inspect status / evidence (read-only).
4. Click Approve… and type APPROVE yourself on the PTY. Do not automate.
5. Quit. The loopback dashboard child must be gone.

The contract runs /bin/sh work/write_ok.sh (writes outputs/result.json).
App Sandbox confines the UI and inherit helper; it does not OS-sandbox the
payload under test. No telemetry. No host pip install.
