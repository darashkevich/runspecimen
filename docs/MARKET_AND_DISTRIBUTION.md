# RunSpecimen: market and distribution plan

RunSpecimen is a working name, not a final brand or a trademark clearance.

## Product thesis

Do not position this as another generic AI-agent firewall, trace viewer, or sandbox. Those markets already contain credible open-source and enterprise products.

The initial wedge is **run assurance for unattended local research and engineering campaigns**:

> Execute exactly one approved, bounded run using the approved source and configuration; require independent postflight verification before continuation; produce a tamper-evident receipt.

The product is useful when a successful command is not enough. It must also prove that:

- the intended code, native binary, model, data, and configuration were used;
- resource and concurrency ceilings were enforced;
- no second controller or worker started;
- a crash or stale lease did not silently advance the campaign;
- outputs passed declared exact checks;
- the next run did not begin before its predecessor was certified.

This is closer to a local flight-operations system than an observability dashboard.

## Initial customers

The best early customers are small teams already allowing agents to operate long-running local jobs:

1. Computational research and scientific-software teams.
2. Quantitative research and backtesting teams.
3. ML evaluation, data-quality, and model-validation teams.
4. Security research and fuzzing teams.
5. Regulated engineering teams that need reproducible local evidence.

The likely buyer is a research-engineering lead, platform lead, security lead, or founder. The daily user is the engineer supervising Cursor, Codex, Claude Code, or a bespoke agent.

## Competitive boundary

RunSpecimen should interoperate with sandboxes and agent firewalls rather than claim to replace them.

- Observability products answer what the model and tools did.
- Runtime firewalls answer whether a tool call may execute.
- Sandboxes answer what a process can reach.
- RunSpecimen answers whether a bounded campaign step was authorized, exclusive, reproducible, verified, and eligible to advance.

This boundary must stay explicit. The MVP is not an operating-system sandbox and cannot contain an already-authorized malicious process.

## Distribution

### Channel priority

| Channel | What ships there | Buyer path | Revenue role | Priority |
| --- | --- | --- | --- | --- |
| PyPI / `pipx` | Open local engine | Developer installs the actual enforcement layer | Community adoption; upgrades sold directly | Launch |
| GitHub releases | Source, signed artifacts, examples, issue tracker | Technical evaluation and trust-building | Lead generation and enterprise diligence | Launch |
| Cursor Marketplace | Free plugin: skill, commands, hooks, narrow MCP adapter | Cursor user discovers RunSpecimen in-product | Acquisition; direct link to Pro/Team | Launch |
| Codex Plugin Directory | Free plugin: skill plus local-engine adapter | Codex user installs the supported workflow | Acquisition; direct link to Pro/Team | Launch |
| Claude Code marketplace | Free plugin and lifecycle hooks | Claude Code team adopts the same contracts | Acquisition and ecosystem coverage | Next |
| Homebrew tap | Versioned CLI install and upgrades | macOS/Linux developer installs without Python packaging knowledge | Reduces paid-trial friction | Next |
| VS Code Marketplace / Open VSX | Approval, status, evidence, and incident-review UI | Team uses an editor-neutral control surface | Pro feature entry point | After design partners |
| AWS/Azure/GCP marketplaces | Self-hosted control plane and support contract | Enterprise procurement buys through cloud spend | Enterprise annual contracts | Later |

The first two marketplace listings should be **free adapters**. Neither prompt instructions nor IDE hooks should be marketed as the security boundary. Both invoke the same locally installed engine, and paid plans unlock signed receipts, shared policy, delegated approval, retention, and fleet reporting.

### 1. Core engine

Ship the enforcement engine through channels developers already trust for local tools:

- PyPI and `pipx` for the Python MVP.
- Signed GitHub releases.
- A Homebrew tap for macOS and Linux once releases are stable.
- Later, a single Go or Rust binary if deployment friction or tamper resistance justifies a rewrite.

The core engine owns leases, approvals, lifecycle transitions, provenance, postflight, and receipts. Marketplace plugins must never become the sole enforcement boundary.

### 2. Cursor Marketplace

Publish a free Cursor plugin containing:

- a skill for authoring and validating run contracts;
- commands for preflight, approval handoff, status, postflight, and receipt verification;
- hooks that report lifecycle events and refuse unsupported shortcuts where Cursor exposes a reliable hook;
- an optional MCP adapter that exposes only the narrow RunSpecimen API.

Cursor plugins are Git repositories submitted at `cursor.com/marketplace/publish` and reviewed by Cursor. Use the marketplace for discovery and installation, then sell the local engine or team features directly.

### 3. Codex Plugin Directory

Publish a free Codex plugin with a skill and, if useful, a narrow local app/MCP configuration. Its job is to teach Codex to create contracts, request a human approval, and invoke RunSpecimen correctly.

The plugin is an adapter, not a security boundary: instructions alone cannot prevent a sufficiently privileged agent from bypassing the engine.

### 4. Claude Code, VS Code, and Open VSX

- A Claude Code plugin can connect pre-tool and post-tool hooks to the engine.
- A VS Code/Open VSX extension can provide a status panel, diff/evidence viewer, and out-of-band approval UI.
- Both should call the same local engine and receipt verifier.

### 5. Enterprise procurement

After product-market evidence exists, offer a self-hosted team control plane through direct sales and, later, cloud marketplaces. Enterprise buyers pay for central policy distribution, identity, delegated approvals, signed receipts, evidence retention/export, fleet inventory, support, and compliance mappings—not for the basic local lock file.

## Marketplace launch packages

### Cursor listing

The repository submitted to Cursor should contain:

- `SKILL.md`: recognize campaign work and author a safe contract;
- commands: initialize, inspect, preflight, request approval, run once, postflight, verify;
- hooks: observe lifecycle attempts and route supported executions through the engine;
- MCP adapter: a narrow, typed surface with no generic shell method;
- examples: research, ML evaluation, fuzzing, and backtest campaigns;
- a clear notice that the plugin is an adapter and requires the RunSpecimen CLI.

The listing call to action should be “Install the free local engine,” followed by “Add team evidence and signed receipts.”

### Codex listing

The Codex plugin should contain:

- the same contract-authoring and campaign-supervision skill;
- reusable commands for the lifecycle;
- an optional local app/MCP adapter exposing only contract validation, status, run-once, postflight, and verify;
- a review template that explains refusals in plain language;
- no unattended approval command and no general-purpose command-execution tool.

Keeping the engine contract identical across Cursor, Codex, and Claude prevents the adapters from fragmenting into separate products.

## Ninety-day commercial sequence

1. **Weeks 1–2:** release the CLI and a reproducible failure demo; recruit five design partners from research engineering, ML evaluation, security, and quant communities.
2. **Weeks 3–5:** publish the free Cursor and Codex adapters; measure installs that reach a verified receipt, not raw marketplace installs.
3. **Weeks 6–8:** sell a manual Team pilot: shared policy repository, signed receipt export, onboarding, and incident review.
4. **Weeks 9–12:** build only the features the pilots pay for; prepare Homebrew and Claude Code distribution; postpone a cloud dashboard unless evidence retention or fleet policy is a repeated buying requirement.

The useful funnel is:

`marketplace install -> local verified receipt -> multi-user evidence problem -> paid Team pilot`

The vanity funnel—marketplace impressions without completed verified runs—should not guide the roadmap.

## Packaging and pricing hypothesis

Marketplace listings should be free. They are acquisition channels and integration surfaces, not reliable billing channels.

- **Community:** free/open core; one local operator; contracts, exclusive leases, local receipts, verification.
- **Pro:** approximately $19–29 per user/month; richer history, reusable policy packs, signed receipts, TUI/IDE review, support.
- **Team:** approximately $49–79 per user/month with a minimum annual contract; shared policies, delegated approvals, evidence export, team analytics.
- **Enterprise:** custom, initially $20k–100k/year depending on deployment and support; SSO, on-prem control plane, fleet enforcement, retention, compliance packs, SLA.

Pricing must be tested through design-partner conversations before building a cloud control plane.

## First sellable workflow

The first demo should be a real three-run research campaign:

1. A human reviews and approves a contract bound to source and configuration hashes.
2. Cursor or Codex attempts to launch two workers; RunSpecimen permits only one and records the refusal.
3. The approved job completes, but the source changes before postflight; advancement is blocked.
4. The source is restored, the output checks pass, and a receipt is generated.
5. Only then does the successor become eligible.

This demonstrates a costly operational failure, not a synthetic prompt-safety example.

## Validation before expanding

Before building dashboards or cloud services, recruit five design partners and measure:

- unattended agent-hours supervised;
- unsafe duplicate or out-of-order launches blocked;
- stale approvals and provenance changes caught;
- time to reconstruct an incident;
- percentage of runs producing a valid receipt;
- willingness to pay for team policy and evidence retention.

If teams only want command blocking, partner with or integrate an existing runtime firewall. If they value reproducible campaign advancement, continue deepening the run-contract and postflight system.

## Verified channel references

- Cursor plugin reference: <https://prod.cursor.com/docs/reference/plugins>
- Cursor Marketplace: <https://cursor.com/marketplace>
- Codex Plugin Directory overview: <https://help.openai.com/en/articles/20001256-plugins-in-codex>
- Claude Code plugin reference: <https://code.claude.com/docs/en/plugins-reference>
- VS Code extension API: <https://code.visualstudio.com/api>
- Homebrew tap guide: <https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap>
