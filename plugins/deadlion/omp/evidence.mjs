import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execute } from "./process.mjs";

export const scripts = fileURLToPath(new URL("../skills/performance/scripts/", import.meta.url));
export const limits = fileURLToPath(new URL("../skills/suckless-code/scripts/", import.meta.url));
const workspace = fileURLToPath(new URL("workspace.py", import.meta.url));
export const digest = data => createHash("sha256").update(data).digest("hex");

export async function save(path, data) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = path + "." + randomUUID();
  await writeFile(temporary, JSON.stringify(data), { mode: 0o600 });
  await rename(temporary, path);
}

export async function snapshot(cwd, options = {}) {
  const result = await execute(["python3", "-I", workspace], { cwd, maxBytes: 64 << 20, ...options });
  if (result.code) throw new Error(result.stderr.trim() || "snapshot failed");
  return JSON.parse(result.stdout);
}

export async function inventory(cwd, policy = {}) {
  const helper = fileURLToPath(new URL("capabilities.py", import.meta.url));
  const args = { tests: policy.tests, profile: policy.profile, checks: policy.checks, projectVenv: policy.projectVenv };
  const result = await execute(["python3", "-I", helper, JSON.stringify(args)], { cwd, timeout: 3000 });
  if (result.code) throw new Error(result.stderr);
  return JSON.parse(result.stdout);
}

export async function incremental(task) {
  const result = await execute(["python3", "-I", workspace, task.directory], { cwd: task.root, timeout: 2000 });
  if (result.code) throw new Error(result.stderr);
  return JSON.parse(result.stdout);
}

export function changes(before, after) {
  return [...new Set([...Object.keys(before.files), ...Object.keys(after.files)])].filter(
    p => JSON.stringify(before.files[p]) !== JSON.stringify(after.files[p]));
}

function classify(prompt) {
  const classes = [
    ["research", /experimental research|computational model|исследовани[ея]/i],
    ["numerical", /numerical|floating.point|численн|погрешност/i],
    ["algorithm", /algorithm|scaling|алгоритм|асимптот/i],
    ["memory", /memory budget|allocation|peak rss|аллокац|лимит памяти/i],
    ["performance", /optimi[sz]|performance|latency|оптимизац|производительност/i],
    ["architecture", /architectur|архитектур/i],
    ["bug", /regression|bug|исправ|ошибк/i],
  ];
  return classes.find(([,pattern]) => pattern.test(prompt))?.[0] ?? "implementation";
}

async function testCommand(root, files) {
  if (files["Makefile"] && /^test\s*:/m.test(await readFile(join(root, "Makefile"), "utf8"))) return ["make", "test"];
  if (files["Cargo.toml"]) return ["cargo", "test", "--workspace", "--offline"];
  if (files["go.mod"]) return ["go", "test", "./..."];
  if (files["package.json"] && (await read(join(root, "package.json"))).scripts?.test) return ["npm", "test"];
  if (files["gradlew"]) return ["./gradlew", "--offline", "test"];
  if (files["pom.xml"]) return ["mvn", "--offline", "test"];
  if (Object.keys(files).some(p => /(^|\/)test_[^/]*\.py$/.test(p))) return ["python3", "-m", "pytest", "-q"];
}

export async function openTask(ctx, prompt) {
  const start = Date.now();
  const baseline = await snapshot(ctx.cwd);
  await pinRevision(baseline, ctx.cwd);
  const id = randomUUID();
  const directory = join(process.env.XDG_STATE_HOME || join(homedir(), ".local/state"), "deadlion", id);
  const policy = process.env.DL_ENGINEERING_POLICY
    ? JSON.parse(await readFile(process.env.DL_ENGINEERING_POLICY, "utf8")) : {};
  if (policy.trustProject === true && !policy.tests)
    policy.tests = await testCommand(baseline.root, baseline.files);
  const integer = (name, fallback, min) => {
    const value = policy[name] ?? fallback;
    if (!Number.isSafeInteger(value) || value < min) throw new Error("invalid policy " + name);
    return value;
  };
  const modes = ["Standard", "Performance", "Research", "Evolution"];
  validatePolicy(policy, modes, baseline.files);
  const kind = classify(prompt);
  const floor = { algorithm: 2, numerical: 2, research: 2, performance: 1, memory: 1 }[kind] ?? 0;
  const mode = modes[Math.max(modes.indexOf(policy.mode), floor, process.env.DL_PERF_CONTRACT ? 1 : 0)];
  const contracts = Object.keys(baseline.files).filter(p => /^\.performance\/.*\/contract\.json$/.test(p));
  const contract = process.env.DL_PERF_CONTRACT ? resolve(ctx.cwd, process.env.DL_PERF_CONTRACT) :
    mode !== "Standard" && contracts.length === 1 ? resolve(baseline.root, contracts[0]) : undefined;
  const task = { id, directory, cwd: ctx.cwd, root: baseline.root, base: baseline.base, git: baseline.git,
    kind, mode, policy, contract, candidate: resolve(ctx.cwd, process.env.DL_PERF_CANDIDATE_DIR || "."),
    started: start, deadline: start + integer("seconds", 900, 1) * 1000,
    analysisMs: integer("analysisSeconds", 120, 1) * 1000, corrections: 0,
    maxCorrections: integer("maxCorrections", 2, 0), state: "INITIALIZED", receipts: [] };
  if (policy.semgrepConfig) {
    policy.semgrepConfig = resolve(task.root, policy.semgrepConfig);
    task.semgrepConfigHash = digest(await readFile(policy.semgrepConfig));
  }
  if (policy.tokens !== undefined) task.tokenLimit = integer("tokens", 0, 1);
  task.usage = { cached: 0, input: 0, output: 0 };
  task.baselineHash = digest(JSON.stringify(baseline));
  task.tools = await inventory(task.root, policy);
  await save(join(directory, "baseline.json"), baseline);
  if (contract) await freezeContract(task);
  await freezeWorkloads(task);
  await persist(task);
  return task;
}

export async function approvalHash(task) {
  return digest(JSON.stringify((await snapshot(join(task.directory, "approved"))).files));
}

export const persist = task => save(join(task.directory, "task.json"), task);
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
  if (policy.sizeExceptions && Object.entries(policy.sizeExceptions).some(([p, reason]) =>
    typeof reason !== "string" || !reason.trim() || resolve("/", p).slice(1) !== p))
    throw new Error("size exceptions require project-relative file names and a justification");
  if (policy.protectedPaths && (!Array.isArray(policy.protectedPaths) || policy.protectedPaths.some(name =>
    typeof name !== "string" || !Object.keys(files).some(p => p === name || p.startsWith(name + "/")))))
    throw new Error("missing protected verification input");
}

async function pinRevision(baseline, cwd) {
  const base = process.env.DL_PERF_BASE;
  if (base) {
    const resolved = await execute(["git", "rev-parse", "--verify", "--end-of-options", base + "^{commit}"], { cwd });
    if (resolved.code) throw new Error("approved base revision unavailable");
    baseline.base = resolved.stdout.trim();
  }
}
