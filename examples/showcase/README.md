# Showcase workspace

Regeneratable rc2 receipt for `showcase-campaign` / `run-001`.

```bash
# Non-interactive refresh (library skip_tty_check; not for production approvals)
python3 scripts/refresh_showcase.py

# Verify
runspecimen verify --workspace examples/showcase \
  --contract examples/showcase/contract.json \
  --campaign-id showcase-campaign --run-id run-001
```

Interactive TTY demo against a temp workspace: `scripts/demo_rc.sh`.

**Historical note:** a root-workspace `demo-campaign/run-001` from earlier RCs
may lack the certificate `runtime` field and `outputs/result.json`. That tree is
not verifiable on rc2; use this showcase or regenerate with the scripts above.

Live `verify --contract …` rehashes contract, source, and the resolved
interpreter. After cloning onto another machine, re-run `refresh_showcase.py`
before expecting verify to pass.
