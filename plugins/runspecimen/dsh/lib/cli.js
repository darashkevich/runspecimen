/**
 * RunSpecimen command construction and execution for DeepSeek Harness.
 *
 * Two guarantees this module owns, and that the tests check with real processes:
 *
 *   1. **Bounded memory.** Captured output is capped *while draining*, so a
 *      noisy CLI cannot grow the host's heap past `maxOutputBytes`. A separate
 *      small tail of stderr is always retained, because the error that matters
 *      is usually the last thing a tool wrote.
 *   2. **Proven termination.** Cancellation and timeout run the child in its own
 *      process group, send SIGTERM, wait a bounded grace period, escalate to
 *      SIGKILL, and only then report. This covers that owned group, not a new
 *      session created by the CLI or workload. The registered run tool reports
 *      unconfirmed contract cleanup separately after cancellation or timeout.
 *
 * It deliberately contains no approval path — see `lib/refusal.js`.
 *
 * @module runspecimen-dsh-plugin/cli
 */

import {StringDecoder} from "node:string_decoder";
import {captureProcess,validateLimits,ProcessCaptureError} from "./process.js";
export {startDashboard,stopDashboard} from "./dashboard.js";
import { isAbsolute, resolve } from "node:path";

/** Commands a model may drive. Mirrors the RunSpecimen MCP adapter's allowlist. */
export const ALLOWED_ACTIONS = Object.freeze([
  "about",
  "doctor",
  "validate",
  "status",
  "preflight",
  "run",
  "postflight",
  "verify",
  "dashboard",
  "decisions_search",
  "requirements_report",
  "freshness_check",
]);

/**
 * Actions that cannot mutate lifecycle state, so several may run concurrently.
 *
 * `validate` is here on purpose: it reads a contract and probes provenance but
 * never writes run state. It is *not* declared exclusive — see the README table.
 */
export const READ_ONLY_ACTIONS = Object.freeze([
  "about",
  "doctor",
  "validate",
  "status",
  "decisions_search",
  "requirements_report",
  "freshness_check",
]);

/** Actions whose argv carries a path the CLI resolves against its own cwd. */
const PATH_FIELDS = Object.freeze(["contract", "manifest"]);

/**
 * Assert an action is drivable. The refusal text names the excluded commands so
 * the model learns the boundary instead of retrying the same call.
 *
 * @param action - candidate action name.
 * @returns the action, when allowed.
 * @throws Error naming the excluded human-only commands.
 */
export function assertAllowedAction(action) {
  if (typeof action !== "string" || !ALLOWED_ACTIONS.includes(action)) {
    throw new Error(
      `RunSpecimen action '${String(action)}' is not exposed to agents. ` +
        "approve, companion, remote-confirm and abandon are human-only and are never drivable from a plugin.",
    );
  }
  return action;
}

/**
 * Require a non-empty string argument.
 *
 * @param name - argument name, used in the message.
 * @param value - candidate value.
 * @returns the original value.
 * @throws Error when absent or empty.
 */
function requireText(name, value) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} is required and must be a non-empty string`);
  }
  return value;
}

/**
 * Resolve the workspace to an absolute path.
 *
 * A relative workspace is resolved against the calling session's cwd (so two
 * sessions in different projects do not collide), then the host cwd.
 *
 * @param workspace - as supplied by the caller.
 * @param base - resolution base, already absolute.
 * @returns an absolute workspace path.
 */
export function resolveWorkspace(workspace, base) {
  return isAbsolute(workspace) ? resolve(workspace) : resolve(base, workspace);
}

/**
 * Resolve a contract/manifest path against the resolved workspace.
 *
 * The CLI's own contract loader resolves relative paths against the *process*
 * cwd, which is not where a caller means them to point. Resolving here makes the
 * schema's promise ("relative to the workspace") true, and keeps absolute paths
 * working unchanged.
 *
 * @param path - contract or manifest path as supplied.
 * @param workspace - the resolved absolute workspace.
 * @returns an absolute path.
 */
export function resolveInsideWorkspace(path, workspace) {
  return isAbsolute(path) ? resolve(path) : resolve(workspace, path);
}

/**
 * Build the `runspecimen` argv for one action.
 *
 * Argument names and shapes are identical to the bundled MCP adapter, so a
 * workspace behaves the same whether reached over MCP or over this plugin.
 *
 * @param action - an allowed action name.
 * @param args - validated tool arguments.
 * @param options - resolution context.
 * @param options.base - absolute directory for relative workspaces; defaults to `process.cwd()`.
 * @returns argv excluding the executable.
 * @throws Error when a required argument for the action is missing.
 */
export function buildArgv(action, args = {}, options = {}) {
  assertAllowedAction(action);
  if (action === "about") return ["about"];

  const base = options.base ?? process.cwd();
  const workspace = resolveWorkspace(requireText("workspace", args.workspace), base);
  const inline = (name) => {
    if (args[name] === undefined || args[name] === null) return undefined;
    return resolveInsideWorkspace(String(args[name]), workspace);
  };

  switch (action) {
    case "decisions_search":
      return ["decisions", "search", "--workspace", workspace, "--query", String(args.query ?? "")];
    case "requirements_report":
      return [
        "requirements",
        "report",
        "--workspace",
        workspace,
        "--campaign-id",
        String(args.campaign_id ?? ""),
        "--run-id",
        String(args.run_id ?? ""),
      ];
    case "freshness_check": {
      const contract = resolveInsideWorkspace(requireText("contract", args.contract), workspace);
      const argv = ["freshness", "evaluate", "--workspace", workspace, "--contract", contract];
      const manifest = inline("manifest");
      if (manifest) argv.push("--manifest", manifest);
      return argv;
    }
    default: {
      const argv = [action, "--workspace", workspace];
      for (const field of PATH_FIELDS) {
        const value = inline(field);
        if (value) argv.push(`--${field}`, value);
      }
      if (args.campaign_id !== undefined && args.campaign_id !== null) argv.push("--campaign-id", String(args.campaign_id));
      if (args.run_id !== undefined && args.run_id !== null) argv.push("--run-id", String(args.run_id));
      if (args.open === true && action === "dashboard") argv.push("--open");
      return argv;
    }
  }
}

/** Marker appended when output exceeds the budget. */
const truncationNotice = (bytes) =>
  `\n\n[output truncated at ${bytes} bytes; re-run with a narrower action or read the workspace files directly]`;

/**
 * Bound one already-captured string to a byte budget.
 *
 * Kept as a pure helper for callers that hold a complete string; the streaming
 * path in {@link runCli} is what actually protects memory.
 *
 * @param text - complete text.
 * @param maxBytes - budget in UTF-8 bytes.
 * @returns the possibly-truncated text, with a marker when cut.
 */
export function boundOutput(text, maxBytes) {
  if (Buffer.byteLength(text, "utf8") <= maxBytes) return text;
  return new StringDecoder("utf8").write(Buffer.from(text,"utf8").subarray(0,maxBytes)) + truncationNotice(maxBytes);
}

/** Capture bounded stdout head and stderr tail; never retain unbounded chunks. */
export async function runCli({command,argv,cwd,signal,timeoutMs,maxOutputBytes,graceMs=2000}) {
  if(!Number.isSafeInteger(maxOutputBytes)||maxOutputBytes<1||maxOutputBytes>4194304)throw new Error('maxOutputBytes must be a positive finite number and integer no greater than 4194304');
  validateLimits(timeoutMs,maxOutputBytes);
  if(!Number.isSafeInteger(graceMs)||graceMs<1||graceMs>10000)throw new Error('graceMs must be an integer from 1 to 10000');
  if(signal?.aborted)return {exitCode:-1,text:'Call cancelled; nothing was started',truncated:false,cancelled:true,timedOut:false,cleanupFailed:false,termination:'cancelled before start',terminationKind:'cancelled',triggerKind:'cancelled',cliExitCode:null,cliSignal:null,cliOutcomeObserved:false,cleanupClassification:'not-started'};
  const stderrLimit=Math.min(maxOutputBytes,Math.max(1,Math.floor(maxOutputBytes/8)));
  const stdoutLimit=maxOutputBytes-stderrLimit;
  const stdout=[];let stdoutSize=0,stderr=Buffer.alloc(0),stderrTotal=0,truncated=false;
  let code,termination,terminationKind,triggerKind,cleanupFailed=false;
  let cliExitCode=null,cliSignal=null,cliOutcomeObserved=false,cleanupClassification='unavailable';
  try {
    code=await captureProcess({command,argv,cwd,signal,timeoutMs,graceMs,onCommandResult(outcome){
      cliOutcomeObserved=!outcome.error;
      cliExitCode=cliOutcomeObserved && Number.isInteger(outcome.code)?outcome.code:null;
      cliSignal=outcome.signal ?? null;
      cleanupClassification=outcome.classification ?? 'unavailable';
    },onData(chunk,stream) {
      if(stream==='stderr') {
        stderrTotal+=chunk.length;
        if(chunk.length>=stderrLimit)stderr=Buffer.from(chunk.subarray(chunk.length-stderrLimit));
        else stderr=Buffer.from(Buffer.concat([stderr,chunk]).subarray(-stderrLimit));
        if(stderrTotal>stderrLimit)truncated=true;
      } else {
        const count=Math.min(chunk.length,stdoutLimit-stdoutSize);
        if(count>0){stdout.push(Buffer.from(chunk.subarray(0,count)));stdoutSize+=count;}
        if(count<chunk.length)truncated=true;
      }
    }});
  } catch(error) {
    code=-1;
    if(error instanceof ProcessCaptureError){
      terminationKind=error.kind;triggerKind=error.triggerKind;cleanupFailed=!error.cleanupConfirmed;
      // Cleanup failure is the final outcome, not a replacement for its trigger.
      const messages=[];
      for(let cause=error;cause instanceof ProcessCaptureError;cause=cause.cause)messages.unshift(cause.message);
      termination=messages.filter((message,index)=>!messages.slice(index+1).some(later=>later.includes(message))).join('; ');
    }else{
      terminationKind=triggerKind='spawn';termination=error.message;
    }
  }
  if(cliSignal){
    termination=[termination,`CLI terminated by ${cliSignal}`].filter(Boolean).join('; ');
    terminationKind ??= 'signal';triggerKind ??= 'signal';
  }
  const head=new StringDecoder('utf8').write(Buffer.concat(stdout,stdoutSize));
  // A tail can begin inside a UTF-8 codepoint. Discard leading continuation bytes.
  let start=0;while(start<stderr.length && (stderr[start]&0xc0)===0x80)start++;
  const tail=stderr.subarray(start).toString('utf8');
  const body=head+tail;
  const text=(body.trim()?body:`exit_code=${code}`)+(truncated?truncationNotice(maxOutputBytes):'')+(termination?`\n[${termination}]`:'');
  return {exitCode:code,text,truncated,cancelled:triggerKind==='cancelled',timedOut:triggerKind==='timeout',cleanupFailed,cliExitCode,cliSignal,cliOutcomeObserved,cleanupClassification,...termination?{termination,terminationKind,triggerKind}:{}};
}
