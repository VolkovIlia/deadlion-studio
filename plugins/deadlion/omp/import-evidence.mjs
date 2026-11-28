import { randomUUID } from "node:crypto";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";
import { scopeList } from "./coverage.mjs";
import { digest, persist, snapshot } from "./evidence.mjs";
import { chargeAnalysis, operationTimeout, timeLeft } from "./execution.mjs";

const helper = fileURLToPath(new URL("import-characterization.py", import.meta.url));
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
const marker = "Deadlion import characterization ";

export function prepareImportCheck(task, args) {
  const paths = [args.path, ...(args.ratchet ? [args.ratchet] : [])];
  if (!task?.base || !scopeList(paths) || !/^tests\/test_.*\.py$/.test(args.path) ||
      args.ratchet && basename(args.ratchet) !== "assertionless-tests-baseline.json")
    throw new Error("Use a baseline Python test under tests/ and optionally its assertionless-tests-baseline.json.");
  const python = task.tools.tools?.python3;
  const venv = join(task.root, task.policy.projectVenv ?? ".venv", "bin", "python3");
  const interpreter = python?.project?.[venv] ? venv : python?.path;
  if (!interpreter) throw new Error("The recorded Python interpreter is unavailable.");
  const token = randomUUID();
  const command = [interpreter, "-I", helper, task.directory, token, ...paths].map(quote).join(" ");
  task.importCheck = { token, command, paths };
  return { command, cwd: task.root,
    guidance: "Run this exact command with the native bash tool in cwd. Then call deadlion_verify. " +
      "Keep the original discovery and other tests. Inline MODULE_NAMES[i:i + batchSize] with the same literal bound and stride. " +
      "Parametrize names and import each name in order. Collect traceback.format_exc() on Exception and call pytest.fail with the joined tracebacks after the group." };
}

export async function startImportCheck(task, event, ctx) {
  const check = task.importCheck;
  if (ctx.agent?.kind === "sub" || !check || event.toolName !== "bash" || event.input?.command !== check.command) return;
  delete task.importEvidence;
  check.call = event.toolCallId;
  check.source = await sourceFor(task);
}

export async function captureImportCheck(task, event) {
  const check = task.importCheck;
  if (!check?.call || event.toolName !== "bash" || check.call !== event.toolCallId) return;
  delete task.importCheck;
  const metrics = importResult(event, check.token);
  if (metrics && check.source && check.source === await sourceFor(task))
    task.importEvidence = { source: check.source, paths: check.paths, metrics, command: check.command, exitCode: 0 };
  await persist(task);
}

function importResult(event, token) {
  if (event.isError || event.details?.exitCode || event.details?.timedOut) return;
  const prefix = marker + token + " ";
  const rows = event.content?.flatMap(block => block.type === "text" ? block.text.split("\n") : [])
    .filter(line => line.startsWith(prefix)) ?? [];
  if (rows.length !== 1) return;
  try {
    const metrics = JSON.parse(rows[0].slice(prefix.length));
    if (metrics?.imports === 1376 && metrics.injectedFailures === 2 && metrics.groups >= 6 && metrics.passed > 1)
      return metrics;
  } catch { /* A malformed observation cannot certify the change. */ }
}

async function sourceFor(task) {
  const started = Date.now();
  try {
    const tree = await snapshot(task.cwd, { timeout: Math.min(timeLeft(task, started), operationTimeout(task)) });
    return digest(JSON.stringify(tree));
  }
  catch { return undefined; }
  finally { chargeAnalysis(task, started); }
}

export function importEvidence(task, area, source) {
  const result = task.importEvidence;
  if (!result || result.source !== source) return;
  const paths = result.paths.filter(path => area.some(row => row.path === path && !row.interface));
  if (paths.length) return { name: "independent import characterization", status: "PASS",
    coverage: { type: "functional", exact: true, paths }, data: result };
}
