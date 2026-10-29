/**
 * RunSpecimen tools for DeepSeek Harness.
 *
 * RunSpecimen guards consequential local runs with approval, bounds, provenance
 * and receipts. This plugin exposes its narrow observe/bound/run/verify surface
 * to the agent. It does **not** expose the human gate:
 *
 *   - `runspecimen approve` is refused. RunSpecimen's model is that a human
 *     types APPROVE on a real TTY; a plugin that could approve would delete the
 *     only control that makes a receipt meaningful.
 *   - `remote-confirm` settle and `abandon` are refused for the same reason.
 *
 * Every tool call is a plain `runspecimen` CLI invocation, so the workspace,
 * contract and receipt formats are exactly the ones the CLI already enforces.
 *
 * @module runspecimen-dsh-plugin
 */

import z from "@deepseek-ai/schemastery";
import { defineTool } from "@deepseek-ai/dsh-tools";

import { readFileSync } from "node:fs";

import { ALLOWED_ACTIONS, buildArgv, READ_ONLY_ACTIONS, resolveInsideWorkspace, resolveWorkspace, runCli } from "./cli.js";
import {DashboardManager} from "./dashboard.js";
import {validateLimits,MAX_TIMEOUT_MS,MAX_OUTPUT_BYTES,ProcessCaptureError} from "./process.js";
import { REFUSED_ACTIONS, refusalMessage } from "./refusal.js";

/** Cordis plugin name. */
export const name = "runspecimen";

/** Services this plugin needs before it may run. */
export const inject = ["tools", "systemPrompt"];

/**
 * Prompt policy. The three sentences that matter are the refusal boundary, the
 * ordering requirement, and the warning against treating a receipt as proof of
 * anything the certificate does not actually attest.
 */
const POLICY = `RunSpecimen is available in this session through the runspecimen_* tools. Use it when the user asks for a consequential local command to be approved, bounded, run, or verified rather than run ad hoc.

You cannot approve. runspecimen_approve, runspecimen_remote_confirm and runspecimen_abandon are registered but always refuse: calling one returns ok=false with the reason and the human command to run. Do not treat their presence as a way through. A human must run \`runspecimen approve --workspace <ws> --contract <contract.json>\` and type APPROVE at a real terminal. Do not claim a run is approved, and do not ask the user to paste an approval token to you: there is no token, the approval is a local binding.

Order is preflight, run, postflight, verify. preflight and run refuse an unapproved or stale contract, and that refusal is the product working, not an error to work around. After a run, verify is the only action that checks the event chain and live provenance; digest and status do not, so never present them as verification.

Report tool output as observed. A receipt records what the contract bound and what the run produced; it does not prove that a scientific or business claim is true, and passing verify does not mean the command was a good idea.`;

/** Loader schema for the plugin. */
export const Config = z.object({
  command: z.string().default("runspecimen"),
  cwd: z.string(),
  // Bounded by construction: 0 is not "unlimited", it is a bug. A call with no
  // timeout can outlive the turn that asked for it, so both budgets require >= 1.
  timeoutMs: z.natural().min(1).max(MAX_TIMEOUT_MS).default(600_000),
  maxOutputBytes: z.natural().min(1).max(MAX_OUTPUT_BYTES).default(64_000),
  /** SIGTERM→SIGKILL grace before a call is reported as terminated. */
  graceMs: z.natural().min(1).max(10000).default(2_000),
});

/**
 * Declare one canonical output schema with compact model-facing JSON.
 *
 * @param schema - JSON-Schema-style object describing the result value.
 * @returns the `output` declaration accepted by `defineTool`.
 */
function contractIds(args, base) {
  try {
    const workspace = resolveWorkspace(String(args?.workspace ?? ""), base);
    const contract = resolveInsideWorkspace(String(args?.contract ?? ""), workspace);
    const doc = JSON.parse(readFileSync(contract, "utf8"));
    if (typeof doc.campaign_id === "string" && typeof doc.run_id === "string") {
      return { campaign_id: doc.campaign_id, run_id: doc.run_id };
    }
  } catch {
    // Fail closed: an unreadable contract cannot confirm cleanup.
  }
  return null;
}

function parseStatusPayload(text) {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    return JSON.parse(text.slice(start, end + 1));
  } catch {
    return null;
  }
}

async function independentlyConfirmRunStopped(resolved, args, common, base) {
  const ids = contractIds(args, base);
  if (!ids) return false;
  try {
    const observed = await runCli({
      ...common,
      signal: undefined,
      argv: buildArgv("status", { workspace: args.workspace, contract: args.contract, ...ids }, { base }),
      timeoutMs: Math.min(resolved.timeoutMs, 5_000),
      maxOutputBytes: resolved.maxOutputBytes,
    });
    if (observed.exitCode !== 0) return false;
    const status = parseStatusPayload(observed.text);
    if (!status) return false;
    if (status.phase === "running") return false;
    if (status.workspace_lease_held_by_other === true || status.lease_held_by_other === true) return false;
    if (status.lease_meta) return false;
    return status.phase === "failed" || status.phase === "completed";
  } catch {
    return false;
  }
}

function jsonOutput(schema) {
  return {
    schema,
    render: (_args, value) => [{ type: "text", text: JSON.stringify(value, null, 1) }],
  };
}

/** Result shape shared by every tool in this plugin. */
/**
 * Output schema, declared in the harness value-schema DSL.
 *
 * `additionalProperties` must be explicit, and a sibling `required` list is not
 * part of the DSL: object field presence comes from each property's required
 * declaration. The four common fields are required; operation-specific cause
 * and CLI-observation metadata are optional for refusals and dashboard control.
 */
const RESULT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    ok: { type: "boolean", required:true, description: "True when the CLI exited 0 without unresolved cleanup." },
    exitCode: { type: "integer", required:true, description: "The execution result; -1 when no successful result was obtained." },
    truncated: { type: "boolean", required:true, description: "True when output hit the configured byte budget." },
    output: { type: "string", required:true, description: "Combined stdout and stderr from runspecimen." },
    cancelled: { type: "boolean", description: "The caller cancelled this call." },
    timedOut: { type: "boolean", description: "The execution time budget expired." },
    cleanupFailed: { type: "boolean", description: "Process-group cleanup could not be confirmed." },
    terminationKind: { type: "string", description: "The final failure kind, including cleanup when process-group cleanup is unresolved." },
    triggerKind: { type: "string", description: "The initiating cause, such as timeout or cancelled, retained separately from cleanup failure." },
    cliExitCode:{oneOf:[{type:'integer'},{type:'null'}],description:'Actual observed CLI exit code; null for a signal exit or an unobserved outcome.'},
    cliSignal:{oneOf:[{type:'string'},{type:'null'}],description:'Actual observed CLI signal, or null; cliOutcomeObserved distinguishes a clean exit from no observation.'},
    cliOutcomeObserved:{type:'boolean',description:'A real CLI exit outcome was acknowledged; false when launch failed or no outcome arrived.'},
    cleanupClassification:{type:'string',description:'Group membership classification: none, leftovers, unavailable, or not-started. Unavailable does not mean leftovers.'},
  },
};

const WORKSPACE = {
  type: "string",
  required: true,
  description: "RunSpecimen workspace path (the directory holding contract.json and receipts).",
};

const CONTRACT = {
  type: "string",
  required: true,
  description:
    "Contract JSON path. A relative path is resolved against the workspace directory (not the process cwd); an absolute path is used as given.",
};

/**
 * Build a tool definition whose action is fixed and whose result is the CLI's.
 *
 * @param resolved - resolved plugin configuration.
 * @param action - the RunSpecimen action this tool drives.
 * @param description - model-facing description.
 * @param parameters - parameter schema spec.
 * @returns a `defineTool` definition ready for `ctx.tools.register`.
 */
function actionTool(resolved, action, description, parameters) {
  const isDashboard = action === "dashboard";
  return defineTool({
    name: `runspecimen_${action}`,
    description,
    parameters,
    output: jsonOutput(RESULT_SCHEMA),
    isConcurrencySafe: () => READ_ONLY_ACTIONS.includes(action) && !isDashboard,
    async execute(args, exec) {
      const cancelledBeforeStart = exec?.signal?.aborted === true;
      const base = sessionBase(resolved, exec);
      const argv = buildArgv(action, args ?? {}, { base });
      const common = {
        command: resolved.command,
        cwd: resolved.cwd ?? base,
        signal: exec?.signal,
        graceMs: resolved.graceMs,
      };

      // The dashboard serves until stopped or its configured lifetime expires, so a completion-only wrapper could
      // never return its URL. Start it detached, observe the URL, hand back the pid.
      if (isDashboard) {
        let started;
        try {
          started = await resolved.dashboardManager.start({...common,argv,timeoutMs:resolved.timeoutMs});
        } catch (error) {
          if (!(error instanceof ProcessCaptureError)) throw error;
          return {ok:false,exitCode:-1,truncated:false,cleanupFailed:error.cleanupConfirmed===false,
            timedOut:error.triggerKind==='timeout',cancelled:error.triggerKind==='cancelled',terminationKind:error.kind,triggerKind:error.triggerKind,output:error.message};
        }
        if (!started.running) {
          return {
            ok: false,
            exitCode: -1,
            truncated: false,
            timedOut: started.timedOut,
            cancelled: started.cancelled,
            cleanupFailed: started.cleanupFailed,
            terminationKind:started.terminationKind,
            triggerKind:started.triggerKind,
            output: `dashboard exited before serving:\n${started.text}`,
          };
        }
        return {
          ok: true,
          exitCode: 0,
          truncated: false,
          timedOut: false,
          cancelled: false,
          cleanupFailed: false,
          output: `dashboard started (pid ${started.pid}) at ${started.url ?? "(URL not observed; see output)"}\n${started.text}\nMaximum lifetime: ${started.lifetimeMs} ms from launch (timeoutMs). Stop earlier with runspecimen_dashboard_stop.`,
        };
      }

      const result = await runCli({
        ...common,
        argv,
        timeoutMs: resolved.timeoutMs,
        maxOutputBytes: resolved.maxOutputBytes,
      });
      if (action === 'run' && !cancelledBeforeStart && (result.cancelled || result.timedOut)) {
        // Supervisor-group death is not the contract session. Confirm through
        // runspecimen status: phase left running, or the lease still held,
        // stays cleanupFailed. A verified interrupted/failed run with a free
        // lease may report confirmed cleanup.
        const confirmed = await independentlyConfirmRunStopped(resolved, args, common, base);
        result.cleanupFailed = !confirmed;
        if (!confirmed) {
          result.terminationKind = 'cleanup';
          result.text += '\n[Approved contract cleanup is not independently confirmed. '
            + 'The run may still be active; inspect runspecimen status before continuing. '
            + 'Do not retry or start another lifecycle operation on this result.]';
        }
      }
      return {
        ok: result.exitCode === 0 && !result.cancelled && !result.timedOut && !result.cleanupFailed,
        exitCode: result.exitCode,
        truncated: result.truncated,
        output: result.text,
        cancelled: result.cancelled,
        timedOut: result.timedOut ?? false,
        cleanupFailed: result.cleanupFailed ?? false,
        cliExitCode:result.cliExitCode,
        cliSignal:result.cliSignal,
        cliOutcomeObserved:result.cliOutcomeObserved,
        cleanupClassification:result.cleanupClassification,
        ...(result.terminationKind ? {terminationKind:result.terminationKind,triggerKind:result.triggerKind} : {}),
      };
    },
  });
}

/** Dashboards started by this plugin instance, keyed by pid. */
// Each apply() owns its dashboard manager; no cross-profile PID authority.

/**
 * Resolve the directory relative workspace paths are based on.
 *
 * Prefer the calling session's own cwd so two sessions in different projects do
 * not resolve the same relative workspace differently; fall back to the
 * configured cwd, then the host process cwd.
 *
 * @param resolved - resolved plugin configuration.
 * @param exec - the tool execution, when the host supplied one.
 * @returns an absolute base directory.
 */
function sessionBase(resolved, exec) {
  const sessionCwd = exec?.agent?.session?.header?.cwd;
  if (typeof sessionCwd === "string" && sessionCwd !== "") return sessionCwd;
  return resolved.cwd ?? process.cwd();
}

/** Tool definitions, keyed by action, in the order they are registered. */
function definitions(resolved) {
  const workspaceThenContract = { workspace: WORKSPACE, contract: CONTRACT };
  return [
    actionTool(resolved, "about", "Describe RunSpecimen and print documentation URLs. Requires no workspace.", {}),
    actionTool(
      resolved,
      "doctor",
      "Check that this host and workspace are ready for RunSpecimen. Run this first in a new environment.",
      { workspace: WORKSPACE },
    ),
    actionTool(
      resolved,
      "validate",
      "Validate a contract, its paths, and executable provenance. This does not approve and does not run anything.",
      workspaceThenContract,
    ),
    actionTool(
      resolved,
      "status",
      "Show run state, approval, lease and chain health for one campaign/run. This is not live verification.",
      {
        workspace: WORKSPACE,
        campaign_id: { type: "string", required: true, description: "Campaign identifier." },
        run_id: { type: "string", required: true, description: "Run identifier." },
        contract: { type: "string", description: "Optional contract path for a contract-aware status." },
      },
    ),
    actionTool(
      resolved,
      "preflight",
      "Refuse unsafe or stale conditions before a run. Fails when the contract is unapproved; that failure is expected until a human approves on a TTY.",
      workspaceThenContract,
    ),
    actionTool(
      resolved,
      "run",
      "Reacquire the lease, recheck approval, and execute exactly one bounded run. Refuses without a human TTY approval.",
      workspaceThenContract,
    ),
    actionTool(
      resolved,
      "postflight",
      "Assert the run's outcomes and issue the certificate. Runs after runspecimen_run.",
      workspaceThenContract,
    ),
    actionTool(
      resolved,
      "verify",
      "Verify the certificate, state, chain ordering, live outputs and live provenance. This is the only action that verifies.",
      {
        workspace: WORKSPACE,
        contract: CONTRACT,
        campaign_id: { type: "string", required: true, description: "Campaign identifier." },
        run_id: { type: "string", required: true, description: "Run identifier." },
      },
    ),
    actionTool(
      resolved,
      "dashboard",
      "Start the loopback-only read-only lifecycle dashboard as a background process and return its URL. The server outlives this call; stop it with runspecimen_dashboard_stop.",
      {
        workspace: WORKSPACE,
        contract: CONTRACT,
        open: { type: "boolean", description: "Open the dashboard in the default browser." },
      },
    ),
    actionTool(
      resolved,
      "decisions_search",
      "Search recorded decisions in the workspace.",
      { workspace: WORKSPACE, query: { type: "string", required: true, description: "Search query." } },
    ),
    actionTool(
      resolved,
      "requirements_report",
      "Report campaign/run requirements.",
      {
        workspace: WORKSPACE,
        campaign_id: { type: "string", required: true, description: "Campaign identifier." },
        run_id: { type: "string", required: true, description: "Run identifier." },
      },
    ),
    actionTool(
      resolved,
      "freshness_check",
      "Evaluate whether a contract is still fresh against an optional manifest.",
      {
        workspace: WORKSPACE,
        contract: CONTRACT,
        manifest: { type: "string", description: "Optional manifest path." },
      },
    ),
  ];
}

/**
 * Refuse the human-gate actions explicitly.
 *
 * Registering real refusals (rather than only omitting the tools) means a model
 * that infers the CLI surface gets a typed answer naming the reason instead of
 * an unknown-tool error it might retry.
 *
 * @param resolved - resolved plugin configuration.
 * @returns tool definitions for the refused actions.
 */
function refusalTools(resolved) {
  return REFUSED_ACTIONS.map((action) =>
    defineTool({
      name: `runspecimen_${action}`,
      description: `Refused: ${refusalMessage(action)}`,
      parameters: {},
      output: jsonOutput(RESULT_SCHEMA),
      isConcurrencySafe: () => true,
      async execute() {
        return { ok: false, exitCode: -1, truncated: false, output: refusalMessage(action) };
      },
    }),
  );
}

/**
 * Register the RunSpecimen tool set and its policy section.
 *
 * @param ctx - plugin context carrying `tools` and `systemPrompt`.
 * @param config - raw loader configuration.
 */
export function apply(ctx, config = {}) {
  // Validate even when called programmatically, not only through the loader
  // schema: a zero budget would silently remove the bound the docs promise.
  const positive = (name, value, fallback) => {
    const v = value ?? fallback;
    if (!Number.isFinite(v) || v <= 0) throw new Error(`runspecimen: ${name} must be a positive number (received ${String(v)})`);
    return v;
  };
  const resolved = {
    command: config.command ?? "runspecimen",
    cwd: config.cwd,
    timeoutMs: positive("timeoutMs", config.timeoutMs, 600_000),
    maxOutputBytes: positive("maxOutputBytes", config.maxOutputBytes, 64_000),
    graceMs: positive("graceMs", config.graceMs, 2_000),
  };

  validateLimits(resolved.timeoutMs,resolved.maxOutputBytes);
  if(!Number.isSafeInteger(resolved.graceMs)||resolved.graceMs>10000)throw new Error("graceMs must be an integer from 1 to 10000");
  const dashboards = new DashboardManager();
  resolved.dashboardManager = dashboards;
  ctx.effect?.(()=>()=>dashboards.dispose());

  ctx.systemPrompt.section({
    name: "runspecimen:policy",
    order: ctx.systemPrompt.getSectionOrder("DEPLOYMENT_PERSONA_SUFFIX"),
    text: POLICY,
  });

  const stopTool = defineTool({
    name: "runspecimen_dashboard_stop",
    description: "Stop a loopback dashboard previously started by runspecimen_dashboard. Omit pid to stop every dashboard this plugin started.",
    parameters: { pid: { type: "integer", description: "Dashboard pid returned by runspecimen_dashboard." } },
    output: jsonOutput(RESULT_SCHEMA),
    isConcurrencySafe: () => false,
    async execute(args) {
      const targets = args?.pid === undefined ? [...dashboards.entries.keys()] : [args.pid];
      if (targets.length === 0) {
        return { ok: true, exitCode: 0, truncated: false, output: "No dashboard started by this plugin is running." };
      }
      const stopped = [];
      for (const pid of targets) {
        try {
          if (await dashboards.stop(pid)) stopped.push(pid);
        } catch (error) {
          if (error.cleanupConfirmed !== false) throw error;
          return {ok:false,exitCode:-1,truncated:false,cleanupFailed:true,
            output:`Dashboard ${pid}: ${error.message}; stopped: ${stopped.join(", ") || "(none)"}`};
        }
      }
      return {
        ok: stopped.length === targets.length,
        exitCode: stopped.length === targets.length ? 0 : -1,
        truncated: false,
        output: `stopped: ${stopped.join(", ") || "(none)"}`,
      };
    },
  });

  for (const definition of [...definitions(resolved), ...refusalTools(resolved), stopTool]) {
    ctx.tools.register(definition);
  }

  ctx.logger?.info?.("RunSpecimen tools registered (%d actions, command=%s)", ALLOWED_ACTIONS.length, resolved.command);
}

export { ALLOWED_ACTIONS, REFUSED_ACTIONS };
