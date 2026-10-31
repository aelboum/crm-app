// The dependency audit gate (decision 13-A1). Fails on every npm advisory of
// any severity, except an advisory listed in `audit-exceptions.json`, and
// only until that exception's expiry date. An exception that is no longer
// needed, or has expired, fails too, so the list cannot go stale. The
// production dependency tree never gets an exception: it must audit clean.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

// Under `npm run`, npm's own CLI runs without a shell; otherwise fall back.
const npmCli = process.env.npm_execpath;

function audit(args) {
  const command = ["audit", "--json", ...args];
  const run = npmCli
    ? spawnSync(process.execPath, [npmCli, ...command], { encoding: "utf8" })
    : spawnSync("npm", command, { encoding: "utf8", shell: process.platform === "win32" });
  if (!run.stdout) {
    console.error(run.stderr);
    throw new Error("npm audit printed no report");
  }
  const report = JSON.parse(run.stdout);
  if (report.error) throw new Error(`npm audit failed: ${report.error.summary ?? "unknown error"}`);
  const found = new Map();
  for (const [name, entry] of Object.entries(report.vulnerabilities ?? {})) {
    for (const via of entry.via) {
      if (typeof via === "object" && via.url) {
        const id = via.url.split("/").pop();
        found.set(id, { package: name, severity: via.severity, title: via.title });
      }
    }
  }
  return found;
}

const exceptions = JSON.parse(readFileSync(new URL("../audit-exceptions.json", import.meta.url), "utf8"));
const today = new Date().toISOString().slice(0, 10);
const problems = [];

const production = audit(["--omit=dev"]);
for (const [id, advisory] of production) {
  problems.push(`${id} (${advisory.package}, ${advisory.severity}) is in a production dependency: ${advisory.title}`);
}

const all = audit([]);
for (const [id, advisory] of all) {
  const exception = exceptions.find((e) => e.id === id);
  if (!exception) {
    problems.push(`${id} (${advisory.package}, ${advisory.severity}): ${advisory.title}`);
  } else if (exception.expires <= today) {
    problems.push(`${id}: the exception expired on ${exception.expires}; fix it or decide again`);
  }
}
for (const exception of exceptions) {
  if (!all.has(exception.id)) {
    problems.push(`${exception.id}: no longer reported; remove its exception`);
  }
}

if (problems.length) {
  console.error("Dependency audit failed:");
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}
const excepted = exceptions.map((e) => `${e.id} until ${e.expires}`).join(", ");
console.log(`Dependency audit passed${excepted ? ` (excepted: ${excepted})` : ""}.`);
