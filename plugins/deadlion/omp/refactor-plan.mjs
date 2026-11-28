import { randomUUID } from "node:crypto";
import { readFile, realpath, rename, unlink, writeFile } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";
import { contains, scopeList } from "./coverage.mjs";
import { changes, digest, read, save, snapshot } from "./evidence.mjs";
import { checkpoint, optional, reservation, state, withCampaignLock } from "./refactor-state.mjs";
import { executionSnapshot } from "./execution.mjs";

const entries = value => value.split(",").map(s => s.trim().replace(/^\x60|\x60$/g, "")).filter(s => s && s !== "—");

export function parsePlan(text) {
  if (!/^Status: (?:active|approved)\s*$/m.test(text)) throw new Error("Refactoring plan must have Status: active");
  const steps = {};
  for (const section of text.split(/^### /m).slice(1)) {
    const [heading, ...lines] = section.split("\n");
    const match = /^([A-Z][0-9]+):\s*(.+)$/.exec(heading);
    if (!match) continue;
    const [, id, title] = match;
    const fields = Object.fromEntries(lines.map(line => /^([A-Za-z]+):\s*(.+)$/.exec(line))
      .filter(Boolean).map(([, key, value]) => [key, value]));
    const scope = entries(fields.Files ?? "");
    if (!scopeList(scope) || ["Verify", "Change", "Test", "Depends"].some(name => !fields[name]) || steps[id])
      throw new Error("Invalid or incomplete milestone " + id);
    const owners = assignOwners(fields.Owners ?? "", scope, id);
    steps[id] = { id, title, scope, owners, depends: entries(fields.Depends), verify: fields.Verify, change: fields.Change,
      test: fields.Test, ...planRequirements(fields) };
  }
  if (!Object.keys(steps).length) throw new Error("Refactoring plan has no milestones");
  validateDependencies(steps);
  return steps;
}

function planRequirements(fields) {
  const required = entries(fields.Required ?? "");
  return { advisory: entries(fields.Advisory ?? ""), unsupported: entries(fields.Constraints ?? ""), required,
    checks: [...new Set([...entries(fields.Checks ?? ""), ...required])] };
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

export async function planSource(root, path) {
  const fullPath = resolve(root, path);
  const name = relative(root, fullPath);
  if (!scopeList([name]) || isAbsolute(name) || await realpath(fullPath) !== fullPath)
    throw new Error("Refactoring plan must be a regular file inside the project");
  const text = await readFile(fullPath, "utf8");
  const steps = parsePlan(text);
  return { path: name, steps, text, planHash: digest(JSON.stringify(steps)) };
}

export async function revisePlan({ directory, root }, value) {
  const [token, ...reason] = value.trim().split(/\s+/);
  return withCampaignLock(directory, async () => {
    const current = await read(state(directory));
    if (!["ACTIVE", "PAUSED"].includes(current.status) || await optional(reservation(directory)))
      throw new Error("Resolve the milestone reservation before revising the campaign");
    const spec = await planSource(root, current.path);
    if (!token) return "Candidate plan " + spec.planHash + " · use revise <hash> <reason> to approve.";
    if (token !== spec.planHash || !reason.length) throw new Error("Use the current plan hash and a reason");
    for (const id of Object.keys(current.results)) {
      if (JSON.stringify(spec.steps[id]) !== JSON.stringify(current.steps[id]))
        throw new Error("Keep verified milestones unchanged. Add a follow-up milestone for new requirements.");
    }
    const prior = await checkpoint(directory, current);
    const tree = await snapshot(root);
    if (changes(prior, tree).some(path => path !== current.path))
      throw new Error("Review unrelated checkout changes before approving the plan");
    const revision = current.revision + 1;
    await save(join(directory, "plans", revision + ".json"), { ...spec, reason: reason.join(" "), parent: current.planHash });
    const checkpointPath = "checkpoint-plan-" + revision + ".json";
    await save(join(directory, checkpointPath), tree);
    await save(state(directory), { ...current, ...spec, revision, checkpointPath,
      checkpoint: digest(JSON.stringify(tree)), finalPlanHash: undefined });
    return "Approved plan revision " + revision;
  });
}


function planHeader(text) {
  return text.split(/^### /m, 1)[0];
}

export function validateTechnicalRevision(current, proposed) {
  if (planHeader(current.text) !== planHeader(proposed.text))
    throw new Error("Keep the approved plan header and goal");
  const additions = Object.values(proposed.steps).filter(step => !Object.hasOwn(current.steps, step.id));
  if (!additions.length) throw new Error("Provide new, independently verifiable prerequisite work");
  for (const [id, before] of Object.entries(current.steps)) {
    const after = proposed.steps[id];
    if (!after) throw new Error("Existing milestones are required");
    const allowed = current.results[id] ? before : { ...before, depends: after.depends };
    if (JSON.stringify(allowed) !== JSON.stringify(after) || before.depends.some(dep => !after.depends.includes(dep)))
      throw new Error("Keep milestone requirements, scope and dependencies intact: " + id);
  }
  for (const step of additions) {
    const parents = Object.values(current.steps).filter(original => proposed.steps[original.id].depends.includes(step.id));
    const contained = original => step.scope.every(path => original.scope.some(scope => contains(scope, path)));
    if (!parents.length || !parents.every(contained)) throw new Error("New prerequisites must stay inside their approved parent scope");
    const duplicate = Object.values(current.steps).some(original =>
      original.change.trim().toLowerCase() === step.change.trim().toLowerCase() &&
      JSON.stringify(original.scope) === JSON.stringify(step.scope));
    if (duplicate) throw new Error("This prerequisite repeats recorded work");
  }
}

export async function adoptTechnicalPlan(task, text, reason, ctx) {
  const { directory, id, campaign } = task.refactor;
  return withCampaignLock(directory, async () => {
    const current = await read(state(directory));
    const active = await read(reservation(directory));
    const attempt = task.recovery?.recent.at(-1);
    if (current.id !== campaign || current.planHash !== task.refactor.planHash || active.task !== task.id ||
        active.session !== ctx.sessionManager?.getSessionId() || active.owner?.pid !== process.pid)
      throw new Error("Milestone no longer owns the approved plan");
    if (!attempt?.receipt || current.revisionCauses?.includes(attempt.signature))
      throw new Error("A plan revision needs a new recorded cause");
    const protectedPaths = [...task.policy.protectedPaths ?? [], ...task.policy.verificationInputs ?? []];
    if (protectedPaths.some(path => contains(path, current.path))) throw new Error("The operator protected the plan file");
    if (text.length > 64000 || !reason.trim()) throw new Error("Provide a compact plan and engineering rationale");
    const before = await planSource(task.root, current.path);
    const proposed = { ...before, text, steps: parsePlan(text) };
    proposed.planHash = digest(JSON.stringify(proposed.steps));
    validateTechnicalRevision(current, proposed);
    const prior = await checkpoint(directory, current);
    if (digest(JSON.stringify(await snapshot(task.root))) !== current.checkpoint || before.planHash !== current.planHash)
      throw new Error("Restore owned candidate changes to the last verified checkpoint before replanning");
    await writeTechnicalPlan(task, current, proposed, before, prior, { id, cause: attempt.signature, reason });
  });
}

async function writeTechnicalPlan(task, current, proposed, before, prior, detail) {
  const directory = task.refactor.directory;
  const path = join(task.root, current.path);
  const revision = current.revision + 1;
  // The replacement lives beside the plan, so rename is atomic on the project filesystem.
  const replacement = path + "." + randomUUID();
  let changed = false;
  let committed = false;
  try {
    const mode = prior.files[current.path]?.[1]?.[0] ?? 0o644;
    await writeFile(replacement, proposed.text, { flag: "wx", mode: mode & 0o777 });
    if (await readFile(path, "utf8") !== before.text) throw new Error("Plan changed during revision");
    await rename(replacement, path);
    changed = true;
    const tree = await snapshot(task.root);
    if (changes(prior, tree).some(item => item !== current.path)) throw new Error("Checkout changed during revision");
    const checkpointPath = "checkpoint-plan-" + revision + ".json";
    await save(join(directory, "plans", revision + ".json"), { ...proposed, ...detail, parent: current.planHash });
    await save(join(directory, checkpointPath), tree);
    const milestones = { ...current.milestones, [detail.id]: "REPLANNING" };
    await save(state(directory), { ...current, ...proposed, milestones, revision, checkpointPath, finalPlanHash: undefined,
      revisionCauses: [...current.revisionCauses ?? [], detail.cause], execution: executionSnapshot(task),
      checkpoint: digest(JSON.stringify(tree)) });
    committed = true;
    await unlink(reservation(directory));
  } catch (error) {
    if (changed && !committed && await readFile(path, "utf8") === proposed.text)
      await writeFile(path, before.text);
    throw error;
  } finally {
    await unlink(replacement).catch(error => { if (error.code !== "ENOENT") throw error; });
  }
}
