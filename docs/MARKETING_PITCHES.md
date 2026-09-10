# RunSpecimen marketing pitches

Catchy copy that stays honest about the current release candidate
(`0.2.0rc8` at time of writing). Use these for landing pages, GitHub social
preview, marketplace listings, and outreach. Prefer product truth over hype.

**Product in one sentence:** a local safety and evidence layer for consequential
agent-driven research and engineering commands — exactly one human-approved,
bounded run at a time, with mandatory postflight and tamper-evident receipts.

Ground truth: [ABOUT.md](ABOUT.md), [FAQ.md](FAQ.md), [USER_GUIDE.md](USER_GUIDE.md),
[PRODUCT_PLAN.md](PRODUCT_PLAN.md), [MARKET_AND_DISTRIBUTION.md](MARKET_AND_DISTRIBUTION.md).

---

## 1. One-liners

Taglines and elevator fragments. Mix and match; none claim sandboxing or
cryptographic signatures.

1. **One approved run. One receipt. No silent second launch.**
2. **Flight ops for local agent campaigns — not another firewall.**
3. **Approve once on a real TTY. Advance only after postflight.**
4. **When “the command succeeded” isn’t enough evidence.**
5. **Exclusive lease. Bound provenance. Verifiable certificate.**
6. **Agents draft. Humans approve. Receipts remember.**
7. **Campaign steps that refuse to skip the paperwork.**
8. **Local run assurance: authorized, exclusive, verified, eligible.**
9. **Stop the second worker before it costs you a night.**
10. **Hash-chained evidence for the run you meant to authorize.**
11. **The step after “looks done” — postflight, then successor.**
12. **Stdlib-only CLI. Real-TTY gate. Loopback dashboard that can’t cheat.**

---

## 2. Elevator pitches

### ~10 seconds

RunSpecimen makes consequential local agent runs **one-at-a-time and
receipt-backed**: a human types `APPROVE` on a real TTY, the workspace lease
blocks a second launch, and postflight must pass before the next campaign step.

### ~30 seconds

Agents are great at drafting scripts and launching jobs — terrible at proving
which code and binary actually ran, or at refusing a duplicate worker after a
crash. RunSpecimen is a local safety and evidence layer: bind contract, source,
and resolved executable with interactive approval; execute exactly one bounded
run under a workspace lease; assert outcomes and issue a tamper-evident
certificate. Cursor and Codex adapters help with the workflow; they cannot
approve for you. It records evidence — it does not sandbox the OS.

### ~60 seconds

If your team lets Cursor, Codex, or a bespoke agent drive long-running local
research or engineering campaigns, a green exit code is not enough. You need to
know the approved provenance ran, that nothing else held the workspace, that
outputs matched declared checks, and that the successor did not start on a
failed or unpostflighted predecessor.

RunSpecimen enforces that lifecycle locally: TTY approval with expiry, atomic
state, one execution lease per workspace, mandatory postflight, and a
SHA-256 hash-chained event log plus verifiable certificate. Install the CLI
(`pip` / clone), open the read-only loopback dashboard for visibility, and keep
approval in the terminal. Use a container when you need isolation — RunSpecimen
answers authorization, exclusivity, and verified advancement, not process
containment. Receipts are locally tamper-evident, not externally signed (yet).

---

## 3. Positioning

**For** research engineers, ML eval / quant / security teams, and founders who
supervise agents on consequential local jobs

**who struggle with** duplicate launches, stale approvals, provenance drift,
and “did this step actually certify before the next one?”

**RunSpecimen is** a local run-assurance / campaign flight-operations layer

**that** binds human approval to exact contract and provenance, allows only one
mutating lifecycle step at a time, requires postflight before succession, and
emits a locally verifiable receipt.

**Unlike** agent chat, CI alone, observability traces, or OS sandboxes —

**RunSpecimen** does not replace those tools; it answers whether a bounded
campaign step was **authorized, exclusive, reproducible under declared checks,
verified, and eligible to advance**.

**Category claim (short):** *local run assurance for agent-driven campaigns.*

**Category claim (sharp):** *flight ops for unattended local research steps —
not another AI firewall.*

---

## 4. Audience-specific pitches

### Researchers / scientific software

Your experiment isn’t just “the script exited 0.” It’s whether the approved
source and interpreter ran, required outputs appeared with the fields you
declared, and the next campaign step waited for a certified predecessor.
RunSpecimen turns each consequential step into an approve → run → postflight →
verify loop with a local certificate you can recheck. Evidence of the run —
not proof that the science is true.

### Cursor / Codex agent users

Let the agent draft contracts, validate, preflight, run, postflight, and
verify. You keep the only gate that matters: type `APPROVE` in a real terminal.
Plugins are adapters to the CLI on `PATH`; they cannot approve. Open
`runspecimen dashboard` on loopback for phase and evidence without handing the
agent the keys.

### Security / compliance-minded engineers

Narrow promise, explicit non-goals. Interactive TTY approval, workspace lease,
predecessor gating, hash-chained events, live verify against contract/source/
runtime/outputs. Not an OS sandbox; not an external signature or transparency
log in this RC. Pair with containers/firewalls for isolation; use RunSpecimen
for exclusive authorized advancement and reconstructable local evidence.

### Indie hackers / tool builders

Stdlib-only Python CLI, Apache-2.0, no telemetry, no remote control plane.
Clone, `pip install`, doctor/validate, approve on TTY, get a receipt. One
workspace = one lease — simple mental model. Build adapters; don’t invent a
shell escape hatch. When you later need signed team receipts, that’s the paid
wedge — the open core stays the enforcement boundary.

### (Bonus) Research-engineering / platform leads

Sell the operational failure you already fear: two workers, source drift before
postflight, a successor that ran on hope. RunSpecimen makes that failure
visible and refuseable — then produces a receipt the next person can verify.

---

## 5. Headline + subhead pairs

For landing page hero or GitHub social preview (`og:title` / description).

1. **One run. Then prove it.**  
   Human TTY approval, exclusive workspace lease, mandatory postflight, local
   tamper-evident receipt.

2. **Flight ops for agent campaigns.**  
   Not a sandbox. Not a scheduler. Authorization, exclusivity, and verified
   advancement for consequential local commands.

3. **Approve in the terminal. Advance on evidence.**  
   Agents draft and execute the lifecycle; only you type `APPROVE`. Successors
   wait for a certified predecessor.

4. **When exit code isn’t a receipt.**  
   Bind contract, source, and resolved executable — then assert outputs and
   verify the hash-chained certificate.

5. **Local run assurance. Stdlib-only.**  
   Clone, install, doctor, approve, run, postflight, verify. Loopback dashboard
   shows the state; it cannot approve for you.

---

## 6. Anti-pitches / what not to say

Avoid oversell. These lines sound good and are **wrong or premature** for the
current RC.

| Don’t say | Why |
| --- | --- |
| “OS sandbox / contains malicious payloads” | Wall timeout, process-group cleanup, and path checks are orchestration — not isolation. Use a container. |
| “Cryptographically signed / notarized / transparency-backed receipts” | Local SHA-256 hash chain only. Privileged full-workspace rewrite can fabricate history. Signing is M1+. |
| “Agents can approve unattended” / “set and forget approvals” | Approval requires interactive TTY; adapters exclude `approve`. |
| “Parallel workers / job scheduler / cron for campaigns” | One lease per workspace; no watchers or fan-out. |
| “Proves your model/experiment is correct” | Green postflight = declared assertions passed under recorded provenance — not scientific truth. |
| “Replaces CI / firewalls / sandboxes” | Interoperates; different question (authorization & advancement vs reachability vs pipeline). |
| “Cloud control plane / fleet enforcement shipped” | Local workspace only in this RC; team features are roadmap. |
| “Plugin is the security boundary” | CLI is the enforcement boundary; marketplace adapters are constrained helpers. |
| “CPU/memory/network policy enforced” | Not in current RC; containment adapter is M1. |
| “Drop-in proof for auditors out of the box” | Useful local evidence; not a compliance product yet. |

**Safe substitute framing:** *evidence and exclusive advancement*, not *proof*
or *containment*.

---

## 7. CTA lines

Match real install and docs paths. Prefer verbs that lead to a verified receipt,
not vanity installs.

### Install / try

- **Clone and install the local engine:**  
  `git clone https://github.com/darashkevich/runspecimen` → `sh scripts/bootstrap_dev.sh`  
  (or `python3 -m pip install .` after `setuptools>=77`)
- **Check the host before you approve:** `runspecimen doctor --workspace .`
- **Validate a contract:** `runspecimen validate --workspace . --contract examples/demo_contract.json`
- **Fresh demo workspace:** `runspecimen init-demo --workspace ./runspecimen-demo`
- **Interactive RC demo:** `sh scripts/demo_rc.sh`

### Lifecycle (human in the loop)

- **Approve on a real TTY:** `runspecimen approve --workspace . --contract …`  
  (type `APPROVE` — agents must not)
- **Run once, then certify:** `runspecimen run` → `runspecimen postflight`
- **Recheck the receipt:** `runspecimen verify --workspace . --contract … --campaign-id … --run-id …`

### Dashboard / docs

- **See phase and evidence (loopback, read-only):**  
  `runspecimen dashboard --workspace . --contract … --open`
- **Read the guide:** [USER_GUIDE.md](USER_GUIDE.md)
- **Short answers:** [FAQ.md](FAQ.md) · **What it is:** [ABOUT.md](ABOUT.md)
- **CLI shortcut:** `runspecimen about`

### Marketplace / adapters (when listing)

- **Install the free local engine, then add the Cursor/Codex adapter.**
- **Plugin helps the workflow. Human approval stays in the terminal.**
- **Success metric:** first verified local receipt — not marketplace impressions.

### Soft closes

- **Start with one consequential script. Get one certificate. Then chain a predecessor.**
- **If you only need command blocking, use a firewall. If you need certified campaign steps, start here.**

---

## Voice notes

- Sharp over fluffy. Prefer concrete nouns: lease, TTY, postflight, certificate,
  predecessor.
- Confident about the narrow wedge; humble about non-goals.
- Avoid AI-SaaS clichés: “supercharge,” “seamless,” “end-to-end AI safety,”
  “autonomous trust,” purple-gradient abstraction.
- Working name: RunSpecimen — fine for now; not a cleared trademark.
