/**
 * Behavior tests for the RunSpecimen DeepSeek Harness plugin.
 *
 * These cover the parts that must not drift: CLI argument mapping (kept
 * identical to the bundled MCP adapter), workspace-relative path resolution,
 * the human-gate refusal, bounded memory, proven process termination, and the
 * dashboard's background lifetime.
 *
 * Termination and memory tests drive real child processes and then inspect
 * whether those processes are actually gone — not merely whether a promise
 * rejected. Every fixture pid is killed in cleanup.
 */

import assert from "node:assert/strict";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { mkdirSync, mkdtempSync, watch, existsSync, rmSync } from "node:fs";
import {tmpdir} from "node:os";

import {
  ALLOWED_ACTIONS,
  assertAllowedAction,
  boundOutput,
  buildArgv,
  READ_ONLY_ACTIONS,
  runCli,
  startDashboard,
  stopDashboard,
} from "../lib/cli.js";
import { REFUSED_ACTIONS, refusalMessage } from "../lib/refusal.js";
import { Config } from "../lib/index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(HERE, "fixtures", "fake-runspecimen.mjs");
const WORKSPACE = join(HERE, "fixtures", "ws");

mkdirSync(WORKSPACE, { recursive: true });

/** Pids created by this file, killed in cleanup so no fixture is left behind. */
const spawnedPids = new Set();

/** Whether a pid is still alive (signal 0 probes without delivering). */
function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

after(async () => {
  for (const pid of spawnedPids) {
    try {
      process.kill(-pid, "SIGKILL");
    } catch {
      try {
        process.kill(pid, "SIGKILL");
      } catch {
        /* already gone */
      }
    }
  }
});

test("every MCP-adapter action remains drivable", () => {
  const mcpAllowlist = [
    "about",
    "dashboard",
    "doctor",
    "validate",
    "status",
    "preflight",
    "run",
    "postflight",
    "verify",
    "decisions_search",
    "requirements_report",
    "freshness_check",
  ];
  assert.deepEqual([...ALLOWED_ACTIONS].sort(), [...mcpAllowlist].sort());
  for (const action of mcpAllowlist) assert.equal(assertAllowedAction(action), action);
});

test("human-gate actions are refused with an actionable reason", () => {
  for (const action of ["approve", "abandon", "companion", "remote-confirm"]) {
    assert.throws(() => assertAllowedAction(action), /human-only/);
    assert.throws(() => buildArgv(action, { workspace: "/ws" }), /human-only/);
  }
  for (const action of REFUSED_ACTIONS) {
    const message = refusalMessage(action);
    assert.match(message, /refused/);
    assert.match(message, /runspecimen/);
  }
});

test("about needs no workspace and takes no arguments", () => {
  assert.deepEqual(buildArgv("about", {}), ["about"]);
  assert.deepEqual(buildArgv("about", { workspace: "/ignored" }), ["about"]);
});

test("workspace actions require a non-empty workspace", () => {
  for (const action of ["doctor", "validate", "preflight", "run", "postflight", "status"]) {
    assert.throws(() => buildArgv(action, {}), /workspace is required/);
    assert.throws(() => buildArgv(action, { workspace: "   " }), /workspace is required/);
  }
});

test("relative contract resolves against the workspace, not the process cwd", () => {
  // The CLI resolves relative contract paths against its own cwd; the schema
  // promises workspace-relative, so the plugin must make it true.
  const argv = buildArgv("preflight", { workspace: WORKSPACE, contract: "contract.json" }, { base: "/" });
  assert.deepEqual(argv, ["preflight", "--workspace", WORKSPACE, "--contract", join(WORKSPACE, "contract.json")]);
  const abs = buildArgv("run", { workspace: WORKSPACE, contract: "/abs/k.json" }, { base: "/" });
  assert.deepEqual(abs, ["run", "--workspace", WORKSPACE, "--contract", "/abs/k.json"]);
});

test("a relative workspace resolves against the supplied base", () => {
  const argv = buildArgv("doctor", { workspace: "proj" }, { base: "/sessions/a" });
  assert.deepEqual(argv, ["doctor", "--workspace", resolve("/sessions/a", "proj")]);
});

test("status and verify pass campaign and run ids", () => {
  const status = buildArgv("status", { workspace: WORKSPACE, campaign_id: "c", run_id: "r" }, { base: "/" });
  assert.deepEqual(status, ["status", "--workspace", WORKSPACE, "--campaign-id", "c", "--run-id", "r"]);
  const verify = buildArgv(
    "verify",
    { workspace: WORKSPACE, contract: "k.json", campaign_id: "c", run_id: "r" },
    { base: "/" },
  );
  assert.deepEqual(verify, [
    "verify",
    "--workspace",
    WORKSPACE,
    "--contract",
    join(WORKSPACE, "k.json"),
    "--campaign-id",
    "c",
    "--run-id",
    "r",
  ]);
});

test("dashboard only forwards --open when asked", () => {
  assert.deepEqual(buildArgv("dashboard", { workspace: "/ws", contract: "k.json" }, { base: "/" }), [
    "dashboard",
    "--workspace",
    "/ws",
    "--contract",
    "/ws/k.json",
  ]);
  assert.deepEqual(buildArgv("dashboard", { workspace: "/ws", contract: "k.json", open: true }, { base: "/" }), [
    "dashboard",
    "--workspace",
    "/ws",
    "--contract",
    "/ws/k.json",
    "--open",
  ]);
});

test("subcommand actions use the CLI's nested grammar", () => {
  const decisions = buildArgv("decisions_search", { workspace: "/ws", query: "why" }, { base: "/" });
  assert.deepEqual(decisions, ["decisions", "search", "--workspace", "/ws", "--query", "why"]);
  const requirements = buildArgv(
    "requirements_report",
    { workspace: "/ws", campaign_id: "c", run_id: "r" },
    { base: "/" },
  );
  assert.deepEqual(requirements, [
    "requirements",
    "report",
    "--workspace",
    "/ws",
    "--campaign-id",
    "c",
    "--run-id",
    "r",
  ]);
  const fresh = buildArgv(
    "freshness_check",
    { workspace: "/ws", contract: "k.json", manifest: "m.json" },
    { base: "/" },
  );
  assert.deepEqual(fresh, [
    "freshness",
    "evaluate",
    "--workspace",
    "/ws",
    "--contract",
    "/ws/k.json",
    "--manifest",
    "/ws/m.json",
  ]);
  assert.throws(() => buildArgv("freshness_check", { workspace: "/ws" }), /contract is required/);
});

test("validate is declared concurrency-safe; run and dashboard are not", () => {
  assert.ok(READ_ONLY_ACTIONS.includes("validate"));
  assert.ok(!READ_ONLY_ACTIONS.includes("run"));
  assert.ok(!READ_ONLY_ACTIONS.includes("dashboard"), "a long-lived server is not concurrency-safe");
});

test("boundOutput returns short text untouched and marks a byte truncation", () => {
  assert.equal(boundOutput("short", 64_000), "short");
  const bounded = boundOutput("x".repeat(200), 50);
  assert.match(bounded, /output truncated at 50 bytes/);
  assert.equal(bounded.slice(0, 50), "x".repeat(50));
});

test("runCli captures combined output and the exit code of a real child", async () => {
  const result = await runCli({
    command: process.execPath,
    argv: [FIXTURE, "status"],
    cwd: HERE,
    timeoutMs: 20_000,
    maxOutputBytes: 64_000,
  });
  assert.equal(result.exitCode, 0);
  assert.equal(result.truncated, false);
  assert.match(result.text, /fake-runspecimen argv: status/);
  assert.match(result.text, /fake stderr note/, "stderr is part of the model-visible text");
});

test("runCli reports a non-zero exit without throwing", async () => {
  const result = await runCli({
    command: process.execPath,
    argv: [FIXTURE, "run", "--fail"],
    cwd: HERE,
    timeoutMs: 20_000,
    maxOutputBytes: 64_000,
  });
  assert.equal(result.exitCode, 7);
  assert.match(result.text, /fake refusal: contract is not approved/);
});

test("runCli truncates at the configured budget", async () => {
  const result = await runCli({
    command: process.execPath,
    argv: [FIXTURE, "noisy"],
    cwd: HERE,
    timeoutMs: 20_000,
    maxOutputBytes: 100,
  });
  assert.equal(result.truncated, true);
  assert.match(result.text, /output truncated at 100 bytes/);
});

test("truncated is true whenever a truncation notice is present", async () => {
  // Regression: the old flag compared replacement length to original length, so
  // a notice could appear while truncated read false.
  for (const size of [300, 357, 1_000, 4_096]) {
    const result = await runCli({
      command: process.execPath,
      argv: [FIXTURE, "sized", String(size)],
      cwd: HERE,
      timeoutMs: 20_000,
      maxOutputBytes: 256,
    });
    assert.match(result.text, /output truncated/);
    assert.equal(result.truncated, true, `truncated must be true at size ${size}`);
  }
});

test("captured memory stays bounded while a huge stream is drained", async () => {
  // Regression: unbounded string accumulation let a 32 MiB write grow the heap
  // far past the budget. Retained text and heap growth must both stay small.
  const before = process.memoryUsage().heapUsed;
  const result = await runCli({
    command: process.execPath,
    argv: [FIXTURE, "large", String(32 * 1024 * 1024)],
    cwd: HERE,
    timeoutMs: 60_000,
    maxOutputBytes: 256,
  });
  const grown = process.memoryUsage().heapUsed - before;
  assert.equal(result.truncated, true);
  assert.ok(Buffer.byteLength(result.text) < 1_024, "retained text respects the budget");
  assert.ok(grown < 8 * 1024 * 1024, `heap grew ${grown} bytes; expected well under 8 MiB`);
});

test("a late stderr error survives stdout consuming the budget", async () => {
  const result = await runCli({
    command: process.execPath,
    argv: [FIXTURE, "noisy-with-error"],
    cwd: HERE,
    timeoutMs: 30_000,
    maxOutputBytes: 256,
  });
  assert.match(result.text, /IMPORTANT ERROR TAIL/, "stderr tail is retained after stdout overflow");
});

test("runCli names the fix in a typed result when the CLI is absent", async () => {
  const result = await runCli({command: "runspecimen-does-not-exist-xyz", argv: ["about"], cwd: HERE,
    timeoutMs: 20_000, maxOutputBytes: 64_000});
  assert.equal(result.exitCode, -1);
  assert.equal(result.terminationKind, "spawn");
  assert.match(result.text, /RunSpecimen CLI not found/);
});

test("timeout terminates a stubborn child before reporting", async () => {
  // The fixture ignores SIGTERM, so only escalation can end it.
  const result = await runCli({
    command: process.execPath,
    argv: [FIXTURE, "stubborn"],
    cwd: HERE,
    timeoutMs: 600,
    graceMs: 200,
    maxOutputBytes: 64_000,
  });
  const pid = Number(result.text.match(/PID=(\d+)/)?.[1] ?? 0);
  assert.ok(pid > 0, `fixture should report its pid: ${result.text}`);
  spawnedPids.add(pid);
  assert.equal(result.cancelled, false);
  assert.equal(result.timedOut, true);
  assert.equal(alive(pid), false, "the child must be dead when runCli returns");
});

test("caller cancellation terminates a stubborn child before reporting", async () => {
  const controller = new AbortController();
  const dir=mkdtempSync(join(tmpdir(),"dsh-cancel-ready-"));
  const file=join(dir,"ready");
  const pending = runCli({
    command: process.execPath,
    argv: [FIXTURE, "stubborn", file],
    cwd: HERE,
    signal: controller.signal,
    timeoutMs: 60_000,
    graceMs: 200,
    maxOutputBytes: 64_000,
  });
  try {
    await new Promise((resolve,reject)=>{
      const watcher=watch(dir,()=>{if(existsSync(file)){clearTimeout(timer);watcher.close();resolve();}});
      const timer=setTimeout(()=>{watcher.close();reject(Error("fixture readiness timeout"));},10000);
      if(existsSync(file)){clearTimeout(timer);watcher.close();resolve();}
    });
  } finally {controller.abort();rmSync(dir,{recursive:true,force:true});}
  const result = await pending;
  const pid = Number(result.text.match(/PID=(\d+)/)?.[1] ?? 0);
  assert.ok(pid > 0);
  spawnedPids.add(pid);
  assert.equal(result.cancelled, true);
  assert.equal(alive(pid), false, "the child must be dead when runCli returns");
});

test("cancellation also terminates a spawned descendant", async () => {
  const controller = new AbortController();
  const pending = runCli({
    command: process.execPath,
    argv: [FIXTURE, "tree"],
    cwd: HERE,
    signal: controller.signal,
    timeoutMs: 60_000,
    graceMs: 200,
    maxOutputBytes: 64_000,
  });
  setTimeout(() => controller.abort(), 500);
  const result = await pending;
  const root = Number(result.text.match(/ROOT=(\d+)/)?.[1] ?? 0);
  const desc = Number(result.text.match(/DESC=(\d+)/)?.[1] ?? 0);
  assert.ok(root > 0 && desc > 0, `fixture should report both pids: ${result.text}`);
  spawnedPids.add(root);
  spawnedPids.add(desc);
  assert.equal(alive(root), false, "root must be dead");
  assert.equal(alive(desc), false, "descendant must be dead — the group is signalled");
});

test("timeoutMs and maxOutputBytes reject non-positive values", async () => {
  for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    await assert.rejects(
      runCli({ command: process.execPath, argv: [FIXTURE, "status"], cwd: HERE, timeoutMs: bad, maxOutputBytes: 128 }),
      /timeoutMs must be a positive finite number/,
    );
    await assert.rejects(
      runCli({ command: process.execPath, argv: [FIXTURE, "status"], cwd: HERE, timeoutMs: 5_000, maxOutputBytes: bad }),
      /maxOutputBytes must be a positive finite number/,
    );
  }
});

test("Config rejects a zero or negative execution budget", () => {
  // Regression: z.natural() accepted 0, and a zero timeout installed no timeout.
  assert.throws(() => Config({ command: "runspecimen", timeoutMs: 0 }), /timeout|positive|greater/i);
  assert.throws(() => Config({ command: "runspecimen", maxOutputBytes: 0 }), /maxOutputBytes|positive|greater/i);
  assert.throws(() => Config({ command: "runspecimen", timeoutMs: -1 }), /timeout|positive|greater/i);
  const ok = Config({ command: "runspecimen", timeoutMs: 1_000, maxOutputBytes: 1_000 });
  assert.equal(ok.timeoutMs, 1_000);
});

test("dashboard starts in the background, reports a URL, and stops on request", async () => {
  const started = await startDashboard({
    command: process.execPath,
    argv: [FIXTURE, "dashboard"],
    cwd: HERE,
    timeoutMs: 5_000,
  });
  assert.equal(started.running, true, `dashboard should still be serving: ${started.text}`);
  spawnedPids.add(started.pid);
  assert.ok(started.pid > 0);
  assert.match(String(started.url), /^http:\/\/127\.0\.0\.1:\d+/);
  assert.equal(alive(started.pid), true, "it outlives the call");
  assert.equal(await stopDashboard(started.pid, 200), true);
  await new Promise((r) => setTimeout(r, 400));
  assert.equal(alive(started.pid), false, "stopDashboard must end it");
});
