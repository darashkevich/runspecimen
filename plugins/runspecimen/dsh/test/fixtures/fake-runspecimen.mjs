#!/usr/bin/env node
/**
 * A stand-in `runspecimen` for plugin tests.
 *
 * Each mode exercises one property of the wrapper. It is not a RunSpecimen
 * implementation and asserts nothing about RunSpecimen itself.
 *
 * Modes:
 *   status | anything else   echo the argv, exit 0
 *   --fail                   exit 7 with a refusal line
 *   noisy                    write 4 KiB, exit 0
 *   noisy-with-error         write 4 KiB to stdout, then an error line to stderr
 *   sized <n>                write exactly n characters, exit 0
 *   large <n>                write n characters, exit 0
 *   stubborn                 ignore SIGTERM, print PID=<pid>, spin forever
 *   tree                     spawn a child, print ROOT=<pid> DESC=<pid>, spin forever
 *   dashboard                print a loopback URL, then serve forever
 */

import { spawn } from "node:child_process";

const argv = process.argv.slice(2);
const [action, ...rest] = argv;

process.stderr.write("fake stderr note\n");

switch (action) {
  case "hang":
    setInterval(() => {}, 1_000);
    break;

  case "noisy":
    process.stdout.write("y".repeat(4_096));
    process.exit(0);
    break;

  case "noisy-with-error":
    process.stdout.write("y".repeat(4_096));
    process.stderr.write("IMPORTANT ERROR TAIL");
    process.exit(0);
    break;

  case "sized":
  case "large": {
    const n = Number(rest[0] ?? 0);
    // Write in chunks so the child never holds one enormous buffer.
    let written = 0;
    while (written < n) {
      const chunk = Math.min(65_536, n - written);
      process.stdout.write("z".repeat(chunk));
      written += chunk;
    }
    process.exit(0);
    break;
  }

  case "stubborn":
    // Ignore the polite kill; only SIGKILL can end this process.
    process.on("SIGTERM", () => {});
    process.stdout.write(`PID=${process.pid}\n`);
    setInterval(() => {}, 1_000);
    break;

  case "tree": {
    process.on("SIGTERM", () => {});
    const child = spawn(process.execPath, ["-e", "process.on('SIGTERM',()=>{}); setInterval(()=>{},1000)"], {
      stdio: "ignore",
    });
    process.stdout.write(`ROOT=${process.pid} DESC=${child.pid}\n`);
    setInterval(() => {}, 1_000);
    break;
  }

  case "dashboard":
    process.stdout.write("serving on http://127.0.0.1:45919/\n");
    setInterval(() => {}, 1_000);
    break;

  default:
    if (argv.includes("--fail")) {
      process.stdout.write("fake refusal: contract is not approved\n");
      process.exit(7);
    }
    process.stdout.write(`fake-runspecimen argv: ${argv.join(" ")}\n`);
    process.exit(0);
}
