import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execute } from "./process.mjs";
import { discover, projectPolicy } from "./setup.mjs";
import { scopeList } from "./coverage.mjs";
import { executionLimits, exhausted, migrateExecution, timeLeft } from "./execution.mjs";

export const scripts = fileURLToPath(new URL("../skills/performance/scripts/", import.meta.url));
export const limits = fileURLToPath(new URL("../skills/suckless-code/scripts/", import.meta.url));
const workspace = fileURLToPath(new URL("workspace.py", import.meta.url));
export const digest = data => createHash("sha256").update(data).digest("hex");
export const stateHome = () => join(process.env.XDG_STATE_HOME || join(homedir(), ".local/state"), "deadlion");

export async function save(path, data) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = path + "." + randomUUID();
  await writeFile(temporary, JSON.stringify(data), { mode: 0o600 });
  await rename(temporary, path);
}

export async function snapshot(cwd, options = {}) {
  const result = await execute(["python3", "-I", workspace], { maxBytes: 64 << 20, ...options, cwd });
  if (result.code) throw new Error(result.stderr.trim() || "snapshot failed");
  return Object.defineProperty(JSON.parse(result.stdout), "fingerprint", { value: digest(result.stdout) });
}

export async function inventory(cwd, policy = {}, options = {}) {
  const helper = fileURLToPath(new URL("capabilities.py", import.meta.url));
  const result = await execute(["python3", "-I", helper, JSON.stringify(policy)], { ...options, cwd,
    timeout: Math.min(3000, options.timeout ?? 3000) });
  if (result.code) throw new Error(result.stderr);
  return JSON.parse(result.stdout);
}

export async function incremental(task, signal) {
  const result = await execute(["python3", "-I", workspace, task.directory, task.scanCursor ?? ""],
    { cwd: task.root, timeout: Math.min(2000, timeLeft(task)), signal });
  if (result.code) throw new Error(result.stderr);
  const batch = JSON.parse(result.stdout);
  task.scanCursor = batch.cursor;
  return batch.paths;
}

export async function samePython(task, path, digest, options) {
  const result = await execute(["python3", "-I", workspace, "--same-python", task.base, path, digest], options);
  return result.code === 0 && JSON.parse(result.stdout);
}

export function changes(before, after) {
  return [...new Set([...Object.keys(before.files), ...Object.keys(after.files)])].filter(
    p => JSON.stringify(before.files[p]) !== JSON.stringify(after.files[p]));
}

function initialIntent(prompt) {
  const rules = [
    ["research", /\b(prove|investigate|research|evaluate|analy[sz]e)\b|докажи|исследуй|проанализируй/i],
    ["explanation", /\b(explain|discuss|describe|summarize)\b|объясни|расскажи|обсуди|опиши/i],
    ["documentation", /\b(readme|documentation|comments?|typo)\b|документац|комментари|опечатк/i],
    ["experimentation", /\b(run|start|launch|enable)\s+(?:an?\s+)?autoresearch\b|запусти.{0,20}autoresearch/i],
    ["optimization", /\b(optimi[sz]e|speed up|reduce (?:latency|memory|allocations))\b|оптимизируй|ускорь|сократи.{0,15}(?:памят|аллокац)/i],
    ["refactoring", /\brefactor\w*\b|рефактор/i],
    ["architecture", /\b(redesign|rearchitect)\b|перепроектируй|измени архитектуру/i],
    ["fix", /\b(fix|repair)\b|исправь/i],
    ["implementation", /\b(implement|add|replace|write|change|update)\b|реализуй|добавь|замени|напиши|измени/i],
  ];
  const first = rules.map(([name, pattern]) => [name, prompt.search(pattern)])
    .filter(([, index]) => index >= 0).sort((a, b) => a[1] - b[1])[0]?.[0];
  const docs = rules[2][1].test(prompt);
  const readOnly = ["explanation", "research"].includes(first) ||
    /without (?:changing|editing|modifying)|без (?:изменений|правок|редактирования)/i.test(prompt);
  return readOnly ? first === "explanation" ? "explanation" : "research" :
    docs && ["fix", "implementation", "documentation"].includes(first) ? "documentation" : first ?? "implementation";
}

export function classify(prompt, policy = {}, contract = false) {
  const intent = initialIntent(prompt);
  const readOnly = intent === "explanation" || intent === "research";
  const requested = intent === "experimentation" ? "Evolution" : intent === "optimization" ? "Performance" : "Standard";
  const modes = ["Standard", "Performance", "Research", "Evolution"];
  const mode = readOnly || intent === "documentation" ? "Standard" :
    modes[Math.max(modes.indexOf(requested), modes.indexOf(policy.mode), contract ? 1 : 0)];
  return { intent, mode, readOnly, risk: readOnly || intent === "documentation" ? "low" :
    ["architecture", "experimentation"].includes(intent) ? "high" : "medium",
    scope: readOnly ? "read-only" : /\b(entire|whole|large.scale)\b|масштабн|весь проект/i.test(prompt) ? "project" : "unknown" };
}

export async function openTask(ctx, prompt) {
  const start = Date.now();
  const baseline = await snapshot(ctx.cwd);
  await pinRevision(baseline, ctx.cwd);
  const id = randomUUID();
  const directory = join(stateHome(), id);
  const policyFile = process.env.DL_ENGINEERING_POLICY && resolve(ctx.cwd, process.env.DL_ENGINEERING_POLICY);
  const approvedPolicy = policyFile && await readFile(policyFile);
  const policy = await selectPolicy(baseline.root, approvedPolicy);
  const modes = ["Standard", "Performance", "Research", "Evolution"];
  validatePolicy(policy, modes, baseline.files);
  const route = classify(prompt, policy, Boolean(process.env.DL_PERF_CONTRACT));
  const { intent: kind, mode } = route;
  const contracts = Object.keys(baseline.files).filter(p => /^\.performance\/.*\/contract\.json$/.test(p));
  const contract = mode !== "Standard" && process.env.DL_PERF_CONTRACT ? resolve(ctx.cwd, process.env.DL_PERF_CONTRACT) :
    mode !== "Standard" && contracts.length === 1 ? resolve(baseline.root, contracts[0]) : undefined;
  const task = { id, directory, cwd: ctx.cwd, root: baseline.root, base: baseline.base, git: baseline.git,
    kind, mode, route, policy, policyFile, policyHash: approvedPolicy ? digest(approvedPolicy) : undefined,
    contract, candidate: resolve(ctx.cwd, process.env.DL_PERF_CANDIDATE_DIR || "."),
    goal: prompt, started: start, ...executionLimits(policy, start), executionVersion: 1,
    corrections: 0, state: "INITIALIZED", receipts: [] };
  if (policy.semgrepConfig) {
    policy.semgrepConfig = resolve(task.root, policy.semgrepConfig);
    task.semgrepConfigHash = digest(await readFile(policy.semgrepConfig));
  }
  task.usage = { cached: 0, input: 0, output: 0 };
  task.baselineHash = digest(JSON.stringify(baseline));
  task.tools = await inventory(task.root, policy);
  await save(join(directory, "baseline.json"), baseline);
  if (contract) await freezeContract(task);
  await freezeWorkloads(task);
  await persist(task);
  return task;
}

async function selectPolicy(root, approvedPolicy) {
  if (!approvedPolicy) return projectPolicy(root, stateHome());
  const policy = JSON.parse(approvedPolicy);
  if (policy.trustProject === true && !policy.tests && !policy.checks?.length)
    policy.tests = (await discover(root)).policy.tests;
  return policy;
}

export async function approvalHash(task, options) {
  return digest(JSON.stringify((await snapshot(join(task.directory, "approved"), options)).files));
}

const pendingSaves = new WeakMap();
export function persist(task) {
  const pending = pendingSaves.get(task);
  const next = (pending?.catch(() => {}) ?? Promise.resolve()).then(() => save(join(task.directory, "task.json"), task));
  pendingSaves.set(task, next);
  return next;
}
export const read = async path => JSON.parse(await readFile(path, "utf8"));

async function freezeWorkloads(task) {
  const spec = task.policy.evolution;
  if (task.mode !== "Evolution" || !spec) return;
  if (!spec.train || !spec.holdout || resolve(task.root, spec.train) === resolve(task.root, spec.holdout))
    throw new Error("Evolution requires distinct approved training and holdout contracts");
  task.workloads = {};
  for (const role of ["train", "holdout"]) {
    const directory = join(task.directory, role);
    await mkdir(directory, { mode: 0o700 });
    task.workloads[role] = await freezeInputs(task, resolve(task.root, spec[role]), directory);
  }
}

async function freezeContract(task) {
  try {
    const frozen = await freezeInputs(task, task.contract, task.directory);
    task.approved = frozen.path;
    task.approvalHash = frozen.hash;
    if (!process.env.DL_PERF_CANDIDATE_DIR && !process.env.DL_PERF_CONTRACT) {
      const record = await read(task.approved);
      task.candidate = resolve(task.root, record.benchmark?.candidate_root ?? dirname(task.contract));
      if (task.candidate !== task.root && !task.candidate.startsWith(task.root + "/"))
        throw new Error("invalid candidate_root");
    }
  } catch (error) { delete task.approved; task.contractIssue = error.message; }
}

async function freezeInputs(task, contract, directory) {
  const helper = fileURLToPath(new URL("approved.py", import.meta.url));
  const result = await execute(["python3", "-I", helper, task.root, contract, task.base || "", directory], { cwd: task.cwd });
  if (result.code) throw new Error(result.stderr.trim().split("\n").at(-1));
  return { path: JSON.parse(result.stdout), directory, hash: await approvalHash({ directory }) };
}

function validatePolicy(policy, modes, files) {
  if (policy.mode && !modes.includes(policy.mode)) throw new Error("invalid engineering mode");
  const argv = a => Array.isArray(a) && a.length && a.every(s => typeof s === "string" && s.length);
  if (policy.tests && !argv(policy.tests)) throw new Error("tests must be argv");
  if (policy.checks && (!Array.isArray(policy.checks) || !policy.checks.every(c => c?.name && argv(c.argv))))
    throw new Error("plan checks require names and executable argv");
  validateCoveragePolicy(policy);
  if (policy.sizeExceptions && Object.entries(policy.sizeExceptions).some(([p, reason]) =>
    typeof reason !== "string" || !reason.trim() || resolve("/", p).slice(1) !== p))
    throw new Error("size exceptions require project-relative file names and a justification");
  if (policy.protectedPaths && (!Array.isArray(policy.protectedPaths) || policy.protectedPaths.some(name =>
    typeof name !== "string" || !Object.keys(files).some(p => p === name || p.startsWith(name + "/")))))
    throw new Error("missing protected verification input");
}

function validateCoveragePolicy(policy) {
  if (policy.testsScope !== undefined && (!policy.tests || !scopeList(policy.testsScope)))
    throw new Error("testsScope requires tests and normalized project-relative paths");
  if (policy.checks?.some(c => c.scope !== undefined && !scopeList(c.scope)))
    throw new Error("check scope requires normalized project-relative paths");
  if (policy.checks?.some(c => c.cwd !== undefined && !scopeList([c.cwd])))
    throw new Error("check cwd requires a normalized project-relative path");
  if (policy.checks && new Set(policy.checks.map(c => c.name)).size !== policy.checks.length)
    throw new Error("check names must be unique");
  for (const name of ["verificationInputs", "performancePaths"])
    if (policy[name] !== undefined && !scopeList(policy[name]))
      throw new Error(name + " requires normalized project-relative paths");
}

export async function restoreTask(ctx, entry, { allowMoved = false } = {}) {
  const previous = ctx.sessionManager?.getBranch().filter(e => e.type === "custom" && e.customType === entry).at(-1);
  if (!previous) return;
  const task = await read(join(previous.data.directory, "task.json"));
  if (task.id !== previous.data.id || task.directory !== previous.data.directory ||
      (task.cwd !== ctx.cwd && (!allowMoved || task.refactor)))
    throw new Error("Stored task does not match this OMP session");
  return migrateExecution(task);
}

export function resumeTask(task, selection) {
  if (!["resume", "continue"].includes(selection) && process.env.DL_RESUME_TASK !== "1")
    throw new Error("Use /deadlion new, continue or resume for the unfinished task");
  const reason = exhausted(task);
  if (reason) throw new Error(reason + ". Use /deadlion budget to continue the same task.");
  task.state = "INITIALIZED";
}

async function pinRevision(baseline, cwd) {
  const base = process.env.DL_PERF_BASE;
  if (base) {
    const resolved = await execute(["git", "rev-parse", "--verify", "--end-of-options", base + "^{commit}"], { cwd });
    if (resolved.code) throw new Error("approved base revision unavailable");
    baseline.base = resolved.stdout.trim();
  }
}
