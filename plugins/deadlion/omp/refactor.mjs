import { mkdir, open, readFile, realpath, unlink } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { changedArea, contains, scopeList } from "./coverage.mjs";
import { changes, digest, openTask, read, save, snapshot, stateHome } from "./evidence.mjs";
import { execute } from "./process.mjs";
import { discover } from "./setup.mjs";

const metricsHelper = fileURLToPath(new URL("structural.py", import.meta.url));
const entries = value => value.split(",").map(s => s.trim().replace(/^\x60|\x60$/g, "")).filter(s => s && s !== "—");
const state = directory => join(directory, "plan-state.json");

export function parsePlan(text) {
  if (!/^Status: approved\s*$/m.test(text)) throw new Error("Refactoring plan must have Status: approved");
  const steps = {};
  for (const section of text.split(/^### /m).slice(1)) {
    const [heading, ...lines] = section.split("\n");
    const match = /^([A-Z][0-9]+):\s*(.+)$/.exec(heading);
    if (!match) continue;
    const [, id, title] = match;
    const fields = Object.fromEntries(lines.map(line => /^([A-Za-z]+):\s*(.+)$/.exec(line))
      .filter(Boolean).map(([, key, value]) => [key, value]));
    const scope = entries(fields.Files ?? "");
    if (!scopeList(scope) || !fields.Verify || !fields.Change || !fields.Test || !fields.Depends || steps[id])
      throw new Error("Invalid or incomplete milestone " + id);
    const owners = assignOwners(fields.Owners ?? "", scope, id);
    steps[id] = { id, title, scope, owners, depends: entries(fields.Depends), verify: fields.Verify, change: fields.Change,
      test: fields.Test, constraints: entries(fields.Constraints ?? ""), checks: entries(fields.Checks ?? "") };
  }
  if (!Object.keys(steps).length) throw new Error("Refactoring plan has no milestones");
  validateDependencies(steps);
  return steps;
}

function assignOwners(value, scope, id) {
  const owners = Object.create(null);
  for (const assignment of entries(value)) {
    const [agent, path, extra] = assignment.split("=");
    if (extra || !/^[a-z][a-z0-9-]*$/.test(agent) || !scopeList([path]) ||
        !scope.some(item => contains(item, path)))
      throw new Error("Invalid subagent scope in " + id);
    if (Object.values(owners).flat().some(other => contains(other, path) || contains(path, other)))
      throw new Error("Overlapping subagent scopes in " + id);
    (owners[agent] ??= []).push(path);
  }
  return owners;
}

function validateDependencies(steps) {
  const visited = new Set();
  const visiting = new Set();
  function visit(id) {
    if (!Object.hasOwn(steps, id)) throw new Error("Unknown milestone dependency: " + id);
    if (visiting.has(id)) throw new Error("Cyclic milestone dependency at " + id);
    if (visited.has(id)) return;
    visiting.add(id);
    steps[id].depends.forEach(visit);
    visiting.delete(id);
    visited.add(id);
  }
  Object.keys(steps).forEach(visit);
}

export async function structuralMetrics(root, options = {}) {
  const result = await execute(["python3", "-I", metricsHelper], { cwd: root, maxBytes: 32 << 20, ...options });
  if (result.code) throw new Error(result.stderr.trim().split("\n").at(-1));
  return JSON.parse(result.stdout);
}

export function ratchet(before, after, paths) {
  const issues = [];
  for (const path of paths) {
    const current = after.files[path];
    if (!current) continue;
    const original = before.files[path];
    compare(path, current.lines, original?.lines, before.maxFile);
    for (const [name, lines] of Object.entries(current.functions))
      compare(path + " " + name, lines, original?.functions[name], before.maxFunction);
  }
  for (const [name, metric] of Object.entries(after.projects)) {
    if (name !== "." && !paths.some(path => contains(name, path))) continue;
    const prior = before.projects[name];
    compare(name + " SLOC", metric.sloc, prior?.sloc, (prior ?? metric).limits.DL_MAX_SLOC);
    compare(name + " direct dependencies", metric.deps, prior?.deps, (prior ?? metric).limits.DL_MAX_DEPS);
  }
  return issues;

  function compare(name, value, previous, limit) {
    if (value > Math.max(previous ?? 0, limit))
      issues.push({ name, baseline: previous ?? 0, limit, value });
  }
}

async function planSource(root, path) {
  const fullPath = resolve(root, path);
  const name = relative(root, fullPath);
  if (!scopeList([name]) || isAbsolute(name) || await realpath(fullPath) !== fullPath)
    throw new Error("Refactoring plan must be a regular file inside the project");
  const steps = parsePlan(await readFile(fullPath, "utf8"));
  return { path: name, steps, planHash: digest(JSON.stringify(steps)) };
}

export async function activeRefactor(cwd) {
  const where = await execute(["git", "rev-parse", "--show-toplevel"], { cwd, timeout: 2000 });
  if (where.code) throw new Error("Refactoring requires a Git worktree");
  const root = await realpath(where.stdout.trimEnd());
  const directory = join(stateHome(), "refactoring", digest(root));
  const current = await read(state(directory)).catch(error => {
    if (error.code !== "ENOENT") throw error;
  });
  return { root, directory, current };
}

export async function startRefactor(ctx, plan, task, receipt) {
  const { root, directory, current } = await activeRefactor(ctx.cwd);
  if (current) throw new Error("A refactoring baseline already exists. See /deadlion refactor report.");
  const spec = await planSource(root, plan);
  const baseline = await read(join(task.directory, "baseline.json"));
  const source = digest(JSON.stringify(baseline));
  if (!baseline.base || task.root !== root || source !== task.baselineHash ||
      digest(JSON.stringify(await snapshot(root))) !== source)
    throw new Error("The checkout changed while capturing the global baseline");
  const structure = await structuralMetrics(root);
  const architecture = await discover(root);
  const patch = await execute(["git", "diff", "--no-ext-diff", "--binary", baseline.base, "--"], { cwd: root, maxBytes: 32 << 20 });
  if (patch.code || digest(JSON.stringify(await snapshot(root))) !== source)
    throw new Error("Could not capture a stable original checkout");
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const gate = await open(join(directory, "initializing"), "wx", 0o600);
  try {
    await save(join(directory, "global.json"), { source, baseline, structure, architecture, receipt,
      baselineTask: task.directory, trackedPatch: patch.stdout });
    await save(state(directory), { ...spec, root, baseline: source, checkpoint: source, results: {} });
  } finally {
    await gate.close();
    await unlink(join(directory, "initializing"));
  }
  return `Global baseline ${baseline.base} · ${directory}`;
}

export async function bindMilestone(ctx, id, task) {
  const { current, root, directory } = await activeRefactor(ctx.cwd);
  if (!current || !Object.hasOwn(current.steps, id)) throw new Error("Unknown milestone " + id);
  const spec = await planSource(root, current.path);
  if (spec.planHash !== current.planHash) throw new Error("Approved refactoring plan changed");
  const step = current.steps[id];
  if (current.results[id] || !step.depends.every(dep => current.results[dep]))
    throw new Error("Milestone is complete or still has unfinished prerequisites");
  if (task.baselineHash !== current.checkpoint) throw new Error("Working tree changed since the last checkpoint");
  const lock = join(directory, "active.json");
  const structure = await structuralMetrics(root);
  const claim = await open(lock, "wx", 0o600).catch(error => {
    if (error.code === "EEXIST") throw new Error("A milestone is already active. Resume its OMP session.");
    throw error;
  });
  try {
    await claim.writeFile(JSON.stringify({ id, task: task.id, session: ctx.sessionManager?.getSessionId() }));
    await save(join(task.directory, "structural-baseline.json"), structure);
  } catch (error) {
    await unlink(lock);
    throw error;
  } finally { await claim.close(); }
  return { directory, id, step, planHash: current.planHash };
}

export async function verifyMilestone(task, paths, checks, options) {
  const milestone = task.refactor;
  if (!milestone && !task.refactorFinal) return;
  if (task.refactorFinal) {
    const baseline = await read(join(task.refactorFinal, "global.json"));
    return verifyRatchet(baseline.structure, task, paths, checks, options);
  }
  const current = await read(state(milestone.directory));
  const spec = await planSource(task.root, current.path);
  const active = await read(join(milestone.directory, "active.json"));
  if (active.task !== task.id || spec.planHash !== milestone.planHash || current.checkpoint !== task.baselineHash)
    throw new Error("Refactoring baseline, plan or active milestone changed");
  const outside = paths.filter(path => !milestone.step.scope.some(scope => contains(scope, path)));
  const required = milestone.step.checks.filter(check =>
    !checks.some(item => item.name === check && item.status === "PASS"));
  for (const [name, items] of [["milestone scope", outside], ["milestone required checks", required]])
    if (items.length) checks.push({ name, status: "NOT VERIFIED", reason: items.slice(0, 5).join(", ") });
  const original = await read(join(task.directory, "structural-baseline.json"));
  await verifyRatchet(original, task, paths, checks, options);
}

async function verifyRatchet(original, task, paths, checks, options) {
  const measured = await structuralMetrics(task.root, options);
  const violations = ratchet(original, measured, paths);
  checks.push({ name: "structural ratchet", status: violations.length ? "FAIL" : "PASS",
    reason: violations.slice(0, 5).map(v => v.name + " " + v.baseline + " → " + v.value).join(", "),
    data: { violations, sloc: measured.sloc, projects: measured.projects } });
}

export async function finalRefactorTask(ctx) {
  const { directory, current, root } = await activeRefactor(ctx.cwd);
  if (!current || Object.keys(current.steps).some(id => !Object.hasOwn(current.results, id)))
    throw new Error("Complete the milestones before verifying the global comparison");
  const plan = await planSource(root, current.path);
  const source = digest(JSON.stringify(await snapshot(root)));
  if (plan.planHash !== current.planHash || source !== current.checkpoint)
    throw new Error("Plan or checkout changed since the final checkpoint");
  for (const result of Object.values(current.results)) {
    const evidence = await read(result.receipt);
    if (evidence.status !== "PASS" || evidence.task !== result.task || evidence.source !== result.source ||
        digest(JSON.stringify(evidence)) !== result.receiptHash)
      throw new Error("A milestone receipt changed");
  }
  const baseline = await read(join(directory, "global.json"));
  const task = await read(join(baseline.baselineTask, "task.json"));
  if (task.baselineHash !== current.baseline || baseline.source !== current.baseline)
    throw new Error("Original refactoring baseline changed");
  return { ...task, refactorFinal: directory, deadline: Date.now() + 120000, analysisMs: 120000 };
}

export async function completeMilestone(task, report) {
  const { directory, id } = task.refactor;
  const current = await read(state(directory));
  const lock = join(directory, "active.json");
  if (current.results[id]?.task === task.id && current.checkpoint === report.source) {
    const active = await read(lock).catch(error => { if (error.code !== "ENOENT") throw error; });
    if (active?.task === task.id) await unlink(lock);
    return;
  }
  if ((await read(lock)).task !== task.id || current.checkpoint !== task.baselineHash)
    throw new Error("Cannot advance a changed refactoring checkpoint");
  const tree = await snapshot(task.root);
  if (digest(JSON.stringify(tree)) !== report.source) throw new Error("Working tree changed after milestone verification");
  current.results[id] = { task: task.id, receipt: report.receipt, receiptHash: report.receiptHash,
    source: report.source, paths: report.paths };
  current.checkpoint = report.source;
  current.checkpointPath = "checkpoint-" + id + ".json";
  await save(join(directory, current.checkpointPath), tree);
  await save(state(directory), current);
  await unlink(lock);
}

async function reconcileCheckpoint(ctx) {
  const { directory, root, current } = await activeRefactor(ctx.cwd);
  if (!current) throw new Error("No active refactoring");
  const lock = join(directory, "active.json");
  const claim = await open(lock, "wx", 0o600);
  try {
    const entry = await read(state(directory));
    const original = entry.checkpointPath ? await read(join(directory, entry.checkpointPath)) :
      (await read(join(directory, "global.json"))).baseline;
    if (digest(JSON.stringify(original)) !== entry.checkpoint) throw new Error("Checkpoint fingerprint changed");
    const checkout = await snapshot(root);
    const paths = changes(original, checkout);
    if (paths.some(path => JSON.stringify(original.files[path]?.[1]) !== JSON.stringify(checkout.files[path]?.[1])))
      throw new Error("Checkpoint has changes to tested bytes. Review the checkout before proceeding.");
    if (paths.length && (await execute(["git", "diff", "--quiet", "--", ...paths], { cwd: root })).code !== 0)
      throw new Error("The index has changes that differ from the tested files");
    entry.checkpoint = digest(JSON.stringify(checkout));
    entry.checkpointPath = "checkpoint-reconciled.json";
    await save(join(directory, entry.checkpointPath), checkout);
    await save(state(directory), entry);
    return "Checkpoint reconciled. The original baseline and milestone receipts were preserved.";
  } finally {
    await claim.close();
    await unlink(lock);
  }
}

export async function refactorStatus(ctx, report = false) {
  const { directory, current, root } = await activeRefactor(ctx.cwd);
  if (!current) return "No active refactoring. Use /deadlion refactor start <approved-plan.md>.";
  const active = await read(join(directory, "active.json")).catch(error => {
    if (error.code !== "ENOENT") throw error;
  });
  const steps = Object.values(current.steps);
  const lines = steps.map(step => `${step.id} ${step.title} · ${current.results[step.id] ? "VERIFIED" :
    active?.id === step.id ? "ACTIVE" : step.depends.every(dep => current.results[dep]) ? "READY" : "WAITING"}`);
  if (!report) {
    if (active?.session) lines.push("OMP session " + active.session);
    return lines.join("\n");
  }
  const baseline = await read(join(directory, "global.json"));
  const tree = await snapshot(root);
  const structure = await structuralMetrics(root);
  const files = changes(baseline.baseline, tree);
  const source = digest(JSON.stringify(tree));
  const final = await read(join(directory, "final-receipt.json")).catch(error => {
    if (error.code !== "ENOENT") throw error;
  });
  const validFinal = final?.status === "PASS" && final.source === source &&
    final.receiptHash === digest(JSON.stringify(await read(final.receipt)));
  const status = steps.every(step => current.results[step.id]) && current.checkpoint === source && validFinal ?
    "VERIFIED" : "NOT VERIFIED";
  const result = join(directory, "comparison.json");
  await save(result, { status, base: baseline.baseline.base, source,
    changes: changedArea(files, tree.files), baselineReceipt: baseline.receipt, finalReceipt: final?.receipt,
    sloc: { before: baseline.structure.sloc, after: structure.sloc },
    before: baseline.structure.projects, after: structure.projects, milestones: current.results });
  return `${status} · SLOC ${baseline.structure.sloc} → ${structure.sloc}\n${result}`;
}

export function authorizeRefactorTool(task, event, ctx, edits) {
  const { scope, owners } = task.refactor.step;
  const child = ctx.agent?.kind === "sub";
  const assigned = Object.values(owners).flat();
  if (["edit", "write"].includes(event.toolName)) {
    const paths = edits.map(path => relative(child ? ctx.cwd : task.root, resolve(ctx.cwd, path)));
    const allowed = child && Object.hasOwn(owners, ctx.agent.name) ? owners[ctx.agent.name] : child ? [] : scope;
    if (!scopeList(paths) || !paths.every(path => path !== "." &&
        allowed.some(item => contains(item, path)) && (child || !assigned.some(item => contains(item, path)))))
      return "Write outside the assigned refactoring scope";
  }
  if ((child || assigned.length) && /^(bash|eval|python|patch|apply_patch)$/.test(event.toolName))
    return "Use scoped edit and write tools during delegated refactoring";
  if (event.toolName === "lsp" &&
      !["status", "hover", "diagnostics", "references", "definition", "type_definition", "implementations", "symbols"].includes(event.input?.action))
    return "Refactoring LSP calls must be read-only";
}

export function milestonePrompt(step) {
  if (!step) return "";
  return `Milestone ${step.id}. Changes must stay in ${step.scope.join(", ")}. ` +
    `Expected change ${step.change} Checks ${step.checks.join(", ") || step.verify} ${step.constraints.join(" ")}`;
}

export async function refactorCommand(command, ctx, verify, select) {
  const [, operation = "status", ...words] = command.trim().split(/\s+/);
  const value = words.join(" ");
  if (operation === "start" && value) {
    const baseline = await openTask(ctx, "Capture the engineering baseline.");
    const report = await verify(baseline);
    return startRefactor(ctx, value, baseline, report.receipt);
  }
  if (operation === "begin" && /^[A-Z][0-9]+$/.test(value)) {
    select("milestone " + value);
    return "Next prompt will start milestone " + value + ".";
  }
  if (operation === "verify") {
    const final = await finalRefactorTask(ctx);
    await save(join(final.refactorFinal, "final-receipt.json"), await verify(final));
    return refactorStatus(ctx, true);
  }
  if (operation === "reconcile") return reconcileCheckpoint(ctx);
  if (["plan", "status", "report"].includes(operation)) return refactorStatus(ctx, operation === "report");
  throw new Error("Use refactor start <plan.md>, begin <ID>, status, reconcile, verify or report.");
}
