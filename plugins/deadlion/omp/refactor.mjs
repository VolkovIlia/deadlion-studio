import { randomUUID } from "node:crypto";
import { mkdir, realpath, readdir, unlink } from "node:fs/promises";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { changedArea, contains, documentation, scopeList } from "./coverage.mjs";
import { changes, digest, openTask, persist, read, save, snapshot, stateHome } from "./evidence.mjs";
import { execute } from "./process.mjs";
import { discover } from "./setup.mjs";
import { ratchet } from "./ratchet.mjs";
export { ratchet } from "./ratchet.mjs";
import { archiveCampaign, checkpoint, finalReceiptStatus, optional, ownerAlive, readyMilestones, recoverReservation, reservation, state, withCampaignLock } from "./refactor-state.mjs";
import { exhausted, executionSnapshot, migrateExecution } from "./execution.mjs";
import { revalidateBorrowedChecks } from "./functional-receipts.mjs";

import { planSource, revisePlan } from "./refactor-plan.mjs";
export { parsePlan } from "./refactor-plan.mjs";

const metricsHelper = fileURLToPath(new URL("structural.py", import.meta.url));
export async function structuralMetrics(root, options = {}) {
  const result = await execute(["python3", "-I", metricsHelper], { cwd: root, maxBytes: 32 << 20, ...options });
  if (result.code) throw new Error(result.stderr.trim().split("\n").at(-1));
  return JSON.parse(result.stdout);
}

export async function activeRefactor(cwd) {
  const where = await execute(["git", "rev-parse", "--show-toplevel"], { cwd, timeout: 2000 });
  if (where.code) throw new Error("Refactoring requires a Git worktree");
  const root = await realpath(where.stdout.trimEnd());
  const directory = join(stateHome(), "refactoring", digest(root));
  const current = await optional(state(directory));
  return { root, directory, current };
}

export async function startRefactor(ctx, plan, task, receipt, autonomous = false) {
  const { root, directory, current } = await activeRefactor(ctx.cwd);
  if (current) throw new Error("A refactoring baseline already exists. See /deadlion refactor report.");
  const spec = await planSource(root, plan);
  const { baseline, source, checkout, checkpointHash } = await initialCheckpoint(task, root, spec.path, autonomous);
  const structure = await structuralMetrics(root);
  const architecture = await discover(root);
  const patch = await execute(["git", "diff", "--no-ext-diff", "--binary", baseline.base, "--"], { cwd: root, maxBytes: 32 << 20 });
  if (patch.code || digest(JSON.stringify(await snapshot(root))) !== checkpointHash)
    throw new Error("Could not capture a stable original checkout");
  const baselineEvidence = receipt && await read(receipt);
  const baselineStatus = captureStatus(baselineEvidence);
  if (!autonomous) task.goal = /^Goal:\s*(.+)$/m.exec(spec.text)?.[1] ?? spec.text.split("\n", 1)[0].replace(/^#+\s*/, "");
  await persist(task);
  const id = randomUUID();
  await withCampaignLock(directory, async () => {
    if (await optional(state(directory))) throw new Error("A campaign is already present");
    if (digest(JSON.stringify(await snapshot(root))) !== checkpointHash)
      throw new Error("The original checkout changed before baseline acceptance");
    await mkdir(directory, { recursive: true, mode: 0o700 });
    await save(join(directory, "global.json"), { source, baseline, structure, architecture, receipt,
      baselineStatus, measurements: measurementChecks(baselineEvidence),
      baselineTask: task.directory, trackedPatch: patch.stdout });
    const checkpointPath = checkpointHash !== source ? "checkpoint-plan-1.json" : undefined;
    if (checkpointPath) await save(join(directory, checkpointPath), checkout);
    await save(join(directory, "plans", "1.json"), { ...spec, reason: autonomous ? "Initial technical plan" : "Original approval" });
    await save(state(directory), { ...spec, id, goal: task.goal, status: "ACTIVE", revision: 1, root, execution: executionSnapshot(task),
      baseline: source, checkpoint: checkpointHash, checkpointPath, results: {}, milestones: {} });
  });
  return `Campaign ${id} · snapshot ${baseline.base} · verification ${baselineStatus}`;
}

async function initialCheckpoint(task, root, plan, autonomous) {
  const baseline = await read(join(task.directory, "baseline.json"));
  const source = digest(JSON.stringify(baseline));
  const checkout = await snapshot(root);
  const checkpointHash = digest(JSON.stringify(checkout));
  const protectedPaths = [...task.policy.protectedPaths ?? [], ...task.policy.verificationInputs ?? []];
  const planOnly = autonomous && documentation(plan) && baseline.base === checkout.base &&
    !protectedPaths.some(path => contains(path, plan)) && changes(baseline, checkout).every(path => path === plan);
  if (!baseline.base || task.root !== root || source !== task.baselineHash || checkpointHash !== source && !planOnly)
    throw new Error("The checkout changed while capturing the global baseline");
  return { baseline, source, checkout, checkpointHash };
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
  const global = await read(join(directory, "global.json"));
  const origin = await read(join(global.baselineTask, "task.json"));
  if (origin.policyHash !== task.policyHash || JSON.stringify(origin.policy) !== JSON.stringify(task.policy))
    throw new Error("Campaign engineering policy changed");
  const structure = await structuralMetrics(root);
  const missing = unresolvedConstraints(step, task);
  if (missing.length) throw new Error("Milestone constraints NOT VERIFIED: " + missing.join(", "));
  return withCampaignLock(directory, async () => {
    const latest = await read(state(directory));
    if (latest.status !== "ACTIVE" || latest.checkpoint !== task.baselineHash || latest.planHash !== spec.planHash)
      throw new Error("Campaign changed, is paused, or needs migration");
    if (latest.results[id] || !step.depends.every(dep => latest.results[dep]))
      throw new Error("Milestone or prerequisite state changed");
    if (await optional(reservation(directory))) throw new Error("A milestone is reserved. Resume or recover it.");
    if (digest(JSON.stringify(await snapshot(root))) !== latest.checkpoint)
      throw new Error("Working tree changed while binding the milestone");
    Object.assign(task, latest.execution);
    task.goal = latest.goal ?? task.goal;
    if (exhausted(task)) throw new Error(exhausted(task));
    await save(join(task.directory, "structural-baseline.json"), structure);
    const milestone = { directory, campaign: latest.id, id, step, planHash: latest.planHash };
    await save(join(task.directory, "task.json"), { ...task, refactor: milestone });
    await save(reservation(directory), { id, task: task.id, session: ctx.sessionManager?.getSessionId(),
      checkpoint: latest.checkpoint, status: "PAUSED" });
    return milestone;
  });
}

export async function verifyMilestone(task, paths, checks, options, tree) {
  const milestone = task.refactor;
  if (!milestone && !task.refactorFinal) return;
  if (task.refactorFinal) {
    const baseline = await read(join(task.refactorFinal, "global.json"));
    await verifyRatchet(baseline.structure, task, paths, checks, options, tree);
    const current = await read(state(task.refactorFinal));
    for (const step of Object.values(current.steps)) verifyConstraints(step, task, paths, checks);
    return;
  }
  const current = await read(state(milestone.directory));
  const spec = await planSource(task.root, current.path);
  const active = await read(reservation(milestone.directory));
  if (active.task !== task.id || active.owner?.pid !== process.pid || current.id !== milestone.campaign ||
      current.status !== "ACTIVE" || spec.planHash !== milestone.planHash || current.checkpoint !== task.baselineHash)
    throw new Error("Refactoring baseline, plan or active milestone changed");
  const outside = paths.filter(path => !milestone.step.scope.some(scope => contains(scope, path)));
  if (outside.length) checks.push({ name: "milestone scope", status: "NOT VERIFIED", reason: outside.slice(0, 5).join(", ") });
  if (!paths.length) checks.push({ name: "milestone changes", status: "NOT VERIFIED", reason: "No changes from the milestone checkpoint" });
  const original = await read(join(task.directory, "structural-baseline.json"));
  await verifyRatchet(original, task, paths, checks, options, tree);
  verifyConstraints(milestone.step, task, paths, checks);
}

async function verifyRatchet(original, task, paths, checks, options, tree) {
  const measured = await structuralMetrics(task.root, options);
  const violations = ratchet(original, measured, paths, tree);
  checks.push({ name: "structural ratchet", status: violations.some(item => item.status === "FAIL") ? "FAIL" : violations.length ? "INCONCLUSIVE" : "PASS",
    reason: violations.slice(0, 5).map(v => v.name + " " + (v.reason ?? v.baseline + " → " + v.value)).join(", "),
    data: { violations, sloc: measured.sloc, projects: measured.projects,
      measuredFiles: paths.filter(path => measured.files[path] && !measured.files[path].issue) } });
}

export async function finalRefactorTask(ctx) {
  const { directory, current, root } = await activeRefactor(ctx.cwd);
  if (!current || !["ACTIVE", "COMPLETED"].includes(current.status) ||
      Object.keys(current.steps).some(id => !Object.hasOwn(current.results, id)))
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
  migrateExecution(task);
  return { ...task, ...current.execution, refactorFinal: directory, missionId: current.id, finalPlanHash: current.planHash,
    finalCheckpoint: current.checkpoint };
}

export async function completeMilestone(task, report) {
  return withCampaignLock(task.refactor.directory, () => commitMilestone(task, report));
}

async function commitMilestone(task, report) {
  const { directory, id, campaign, planHash } = task.refactor;
  const current = await read(state(directory));
  const lock = reservation(directory);
  if (current.id !== campaign || current.status !== "ACTIVE" || (await planSource(task.root, current.path)).planHash !== planHash)
    throw new Error("The approved campaign changed before checkpoint acceptance");
  if (current.results[id]?.task === task.id && current.checkpoint === report.source) {
    const active = await read(lock).catch(error => { if (error.code !== "ENOENT") throw error; });
    if (active?.task === task.id) await unlink(lock);
    return;
  }
  const active = await read(lock);
  if (active.task !== task.id || active.owner?.pid !== process.pid || current.checkpoint !== task.baselineHash)
    throw new Error("Cannot advance a changed refactoring checkpoint");
  const tree = await snapshot(task.root);
  if (digest(JSON.stringify(tree)) !== report.source) throw new Error("Working tree changed after milestone verification");
  current.results[id] = { task: task.id, receipt: report.receipt, receiptHash: report.receiptHash,
    source: report.source, paths: report.paths };
  current.checkpoint = report.source;
  current.checkpointPath = "checkpoint-" + id + ".json";
  current.execution = executionSnapshot(task);
  await save(join(directory, current.checkpointPath), tree);
  await save(state(directory), current);
  await unlink(lock);
}

async function reconcileCheckpoint(ctx) {
  const { directory, root, current } = await activeRefactor(ctx.cwd);
  if (!current) throw new Error("No active refactoring");
  return withCampaignLock(directory, async () => {
    if (await optional(reservation(directory))) throw new Error("Resolve the active milestone before reconciling");
    const entry = await read(state(directory));
    const original = await checkpoint(directory, entry);
    const checkout = await snapshot(root);
    const paths = changes(original, checkout);
    if (paths.some(path => JSON.stringify(original.files[path]?.[1]) !== JSON.stringify(checkout.files[path]?.[1])))
      throw new Error("Checkpoint has changes to tested bytes. Review the checkout before proceeding.");
    if (paths.length) {
      const result = await execute(["git", "diff", "--name-only", "-z"], { cwd: root });
      const dirty = new Set(result.stdout.split("\0"));
      if (result.code || paths.some(path => dirty.has(path)))
        throw new Error("The index has changes that differ from the tested files");
    }
    entry.checkpoint = digest(JSON.stringify(checkout));
    entry.checkpointPath = "checkpoint-reconciled.json";
    await save(join(directory, entry.checkpointPath), checkout);
    await save(state(directory), entry);
    return "Checkpoint reconciled. The original baseline and milestone receipts were preserved.";
  });
}

export async function refactorStatus(ctx, report = false, validate) {
  const { directory, current, root } = await activeRefactor(ctx.cwd);
  if (!current) return "No active refactoring. Use /deadlion refactor start <approved-plan.md>.";
  const active = await optional(reservation(directory));
  const steps = Object.values(current.steps);
  const lines = steps.map(step => `${step.id} ${step.title} · ${current.results[step.id] ? "VERIFIED" :
    active?.id === step.id ? active.status ?? "PAUSED" : current.milestones?.[step.id] ??
      (step.depends.every(dep => current.results[dep]) ? "READY" : "WAITING")}`);
  if (!report) {
    lines.unshift("Campaign " + (current.id ?? "legacy") + " · " + (current.status ?? "ACTIVE"));
    if (current.goal) lines.unshift("Goal " + current.goal);
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
  const evidence = final?.receipt && await read(final.receipt);
  const plan = await planSource(root, current.path);
  const { status, staleInputs } = await finalReceiptStatus(current, plan.planHash, source, final, evidence, async () => {
    const task = await finalRefactorTask(ctx);
    const options = { timeout: 5000 };
    const tools = await validate(task, options);
    if (evidence.toolIdentity !== digest(JSON.stringify(tools)))
      throw new Error("The final receipt predates the loaded verifier. Run /deadlion refactor verify.");
    await revalidateBorrowedChecks(task, evidence, options, validate);
  });
  const result = join(directory, "comparison.json");
  await save(result, { status, base: baseline.baseline.base, source,
    changes: changedArea(files, { ...baseline.baseline.files, ...tree.files }), baselineStatus: baseline.baselineStatus,
    baselineReceipt: baseline.receipt, finalReceipt: final?.receipt,
    measurements: { baseline: baseline.measurements, final: measurementChecks(evidence) }, failedChecks: final?.failures, staleInputs,
    sloc: { before: baseline.structure.sloc, after: structure.sloc },
    before: baseline.structure.projects, after: structure.projects, milestones: current.results });
  return `${status} · SLOC ${baseline.structure.sloc} → ${structure.sloc}\n${result}`;
}

async function resolvesWithin(root, path) {
  for (let candidate = path; ; candidate = dirname(candidate)) {
    try { return await realpath(candidate) === candidate; }
    catch (error) { if (error.code !== "ENOENT" || candidate === root) return false; }
  }
}

export async function authorizeRefactorTool(task, event, ctx, edits) {
  const { scope, owners } = task.refactor.step;
  const child = ctx.agent?.kind === "sub";
  const assigned = Object.values(owners).flat();
  if (["edit", "write"].includes(event.toolName)) {
    const root = child ? await realpath(ctx.cwd) : task.root;
    const absolute = edits.map(path => resolve(root, path));
    const paths = absolute.map(path => relative(root, path));
    const allowed = child && Object.hasOwn(owners, ctx.agent.name) ? owners[ctx.agent.name] : child ? [] : scope;
    if (!scopeList(paths) || !paths.every(path => path !== "." &&
        allowed.some(item => contains(item, path)) && (child || !assigned.some(item => contains(item, path) || contains(path, item)))))
      return "Write outside the assigned refactoring scope";
    if (!(await Promise.all(absolute.map(path => resolvesWithin(root, path)))).every(Boolean))
      return "Write through a symlink or unresolved directory in refactoring scope";
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
    `Expected change ${step.change} Checks ${step.checks.join(", ") || step.verify} ${step.advisory.join(" ")}`;
}

export async function refactorCommand(command, ctx, verify, select, validate) {
  const [, operation = "status", ...words] = command.trim().split(/\s+/);
  const value = words.join(" ");
  if (operation === "start" && value) {
    const baseline = await openTask(ctx, "Capture the engineering baseline.");
    baseline.baselineCapture = true;
    const report = await verify(baseline);
    return startRefactor(ctx, value, baseline, report.receipt);
  }
  if (operation === "begin" && /^[A-Z][0-9]+$/.test(value)) {
    select("milestone " + value);
    return "Next prompt will start milestone " + value + ".";
  }
  if (operation === "run") {
    const { current, directory } = await activeRefactor(ctx.cwd);
    if (!current || await optional(reservation(directory))) throw new Error("Resolve the current reservation first");
    const [first] = readyMilestones(current);
    if (!first) throw new Error("No ready milestones. Review /deadlion refactor status");
    select("campaign " + first.id);
    return "Next prompt will run the campaign from " + first.id + ".";
  }
  if (operation === "verify") return finalizeCampaign(ctx, verify, validate);
  if (operation === "reconcile") return reconcileCheckpoint(ctx);
  if (["plan", "status", "report"].includes(operation)) return refactorStatus(ctx, operation === "report", validate);
  return manageCampaign(ctx, operation, value, select);
}

async function finalizeCampaign(ctx, verify, validate) {
  const { directory } = await activeRefactor(ctx.cwd);
  return withCampaignLock(directory, async () => {
    if (await optional(reservation(directory))) throw new Error("Resolve the active milestone before final verification");
    const final = await finalRefactorTask(ctx);
    const result = await verify(final);
    await saveCampaignFinal(final, result);
    return refactorStatus(ctx, true, validate);
  });
}

export async function saveCampaignFinal(task, report) {
  const directory = task.refactorFinal;
  const current = await read(state(directory));
  const plan = await planSource(task.root, current.path);
  if (current.id !== task.missionId || current.planHash !== task.finalPlanHash || current.planHash !== plan.planHash ||
      current.checkpoint !== task.finalCheckpoint || report.status === "PASS" && current.checkpoint !== report.source)
    throw new Error("Plan or checkpoint changed during final verification");
  await save(join(directory, "final-receipt.json"), report);
  current.status = report.status === "PASS" ? "COMPLETED" : "ACTIVE";
  current.finalPlanHash = plan.planHash;
  current.execution = executionSnapshot(task);
  await save(state(directory), current);
}

async function manageCampaign(ctx, operation, value, select) {
  const workspace = await activeRefactor(ctx.cwd);
  const { directory, current } = workspace;
  if (operation === "history") {
    const parent = join(dirname(directory), "history", basename(directory));
    const archives = await readdir(parent).catch(error => { if (error.code !== "ENOENT") throw error; return []; });
    return archives.map(id => join(parent, id)).join("\n") || "No archived campaigns.";
  }
  if (!current) throw new Error("Start or select a refactoring campaign first");
  if (operation === "recover" || operation === "cancel" && value !== "campaign")
    return recoverReservation(workspace, operation, ctx, select);
  if (operation === "revise") return revisePlan(workspace, value);
  return withCampaignLock(directory, async () => {
    const latest = await read(state(directory));
    const active = await optional(reservation(directory));
    if (await ownerAlive(active?.owner)) throw new Error("Stop the active verification first");
    if (operation === "archive") {
      if (active) throw new Error("Resolve the milestone reservation before archiving");
      return archiveCampaign({ directory, current: latest });
    }
    const status = campaignTransition(latest, active, operation, value);
    if (operation === "resume" && active && active.session === ctx.sessionManager?.getSessionId())
      select("recover " + active.task);
    await save(state(directory), { ...latest, id: latest.id ?? randomUUID(), status });
    return "Campaign " + status;
  });
}

function campaignTransition(current, active, operation, value) {
  if (operation === "pause" && current.status === "ACTIVE") return "PAUSED";
  if (operation === "resume" && current.status === "PAUSED") return "ACTIVE";
  if (operation === "cancel" && value === "campaign" && !active && current.status !== "ARCHIVED") return "CANCELLED";
  throw new Error("Allowed operations are pause, resume, recover, cancel, revise, verify, archive, history and report.");
}

function measurementChecks(evidence) {
  return evidence?.checks?.filter(item => item.data?.metrics || item.data?.resources || item.data?.contracts || item.data?.scaling)
    .map(({ name, status, data }) => ({ name, status, data })) ?? [];
}

function captureStatus(evidence) {
  if (!evidence || evidence.status !== "PASS") return evidence?.status ?? "NOT VERIFIED";
  const functional = evidence.checks.filter(check => check.status === "PASS" && check.coverage?.type === "functional" &&
    check.coverage.paths?.length);
  return functional.some(check => check.coverage.paths.includes(".")) ? "PASS" :
    functional.length ? "SCOPED PASS" : "NOT VERIFIED";
}

function unresolvedConstraints(step, task) {
  const checks = new Set((task.policy.checks ?? []).map(check => "plan: " + check.name));
  if (task.policy.tests && task.policy.testsScope) checks.add("functional tests");
  if (Object.keys(task.policy.profile?.max ?? {}).length) checks.add("trusted profile");
  if (task.approved) checks.add("performance contract");
  if (task.base) checks.add("approved contracts");
  if ([task.policy.protectedPaths, task.policy.verificationInputs].some(paths => paths?.length))
    checks.add("protected verification inputs");
  checks.add("structural ratchet");
  for (const name of step.required ?? []) {
    if (!name.startsWith("plan: ")) continue;
    const command = task.policy.checks?.find(check => name === "plan: " + check.name);
    if (!command?.type || command.type === "policy" || /^(?:true|echo|printf|:)$/.test(basename(command.argv[0])))
      checks.delete(name);
  }
  return [...step.unsupported, ...step.checks.filter(name => !checks.has(name))];
}

function verifyConstraints(step, task, paths, checks) {
  const missing = unresolvedConstraints(step, task);
  const scope = paths.filter(path => !documentation(path) && step.scope.some(allowed => contains(allowed, path)));
  for (const name of step.checks) {
    const check = checks.find(item => item.name === name && item.status === "PASS");
    if (!matchesConstraint(name, check, scope.length ? scope : step.scope, task)) missing.push(name);
  }
  const unique = [...new Set(missing)];
  if (unique.length) checks.push({ name: "required constraints " + step.id, status: "NOT VERIFIED",
    reason: unique.join(", ") });
  else if (step.checks.length) checks.push({ name: "required constraints " + step.id, status: "PASS",
    requirements: step.checks, paths: paths.filter(path => step.scope.some(scope => contains(scope, path))) });
}

function matchesConstraint(name, check, paths, task) {
  if (!check) return false;
  if (name === "trusted profile")
    return Object.keys(task.policy.profile?.max ?? {}).every(key => Number.isFinite(check.data?.metrics?.[key]));
  if (name === "performance contract") return check.data?.status === "VERIFIED";
  if (name === "approved contracts") return check.data?.status === "VERIFIED" &&
    Boolean(check.data.contracts?.length) && check.data.contracts.every(contract => contract.status === "VERIFIED");
  if (check.coverage?.type === "functional")
    return paths.every(path => check.coverage.paths?.some(scope => contains(scope, path)));
  if (name.startsWith("plan: ")) {
    const policy = task.policy.checks?.find(item => name === "plan: " + item.name);
    return Boolean(policy && JSON.stringify(policy.argv) === JSON.stringify(check.coverage?.argv));
  }
  return true;
}
