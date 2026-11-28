import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { scopeList } from "./coverage.mjs";
import { digest, inventory, persist, snapshot } from "./evidence.mjs";
import { testInput, verifyToolInputs } from "./gate.mjs";

export async function approveTaskTests(task, ctx, args) {
  if (ctx.isIdle?.() !== true) throw new Error("Wait for OMP to settle before approving checks");
  if (task.cwd !== ctx.cwd) throw new Error("The current checkout does not match the task");
  if (task.refactor || task.refactorFinal) throw new Error("Campaigns retain their approved verification policy");
  const [, expected, file] = /^([\da-f]{64})\s+(.+)$/i.exec(args) ?? [];
  if (!file) throw new Error("Use /deadlion approve-tests <sha256> <file.json>");
  const data = await readFile(resolve(ctx.cwd, file));
  if (digest(data) !== expected.toLowerCase()) throw new Error("Test approval file differs from the reviewed digest");
  const approval = JSON.parse(data);
  const checks = approvedChecks(approval, task);
  await verifyToolInputs(task);
  const revisions = await approvedRevisions(task, approval.testRevision);
  if (!checks.length && !Object.keys(revisions).length) throw new Error("No checks or test revisions to approve");
  const policy = checks.length ? { ...task.policy, checks: [...task.policy.checks ?? [], ...checks] } : task.policy;
  const tools = await inventory(task.root, policy);
  if (!sameInputs(task.tools, tools)) throw new Error("Existing tool or verification inputs changed during approval");
  const updated = { ...task, policy, tools, approvedTestRevisions: { ...task.approvedTestRevisions, ...revisions },
    testApprovals: [...task.testApprovals ?? [], { digest: expected.toLowerCase(), at: Date.now(), checks, revisions }] };
  await persist(updated);
  Object.assign(task, updated);
  return `Approved checks for task ${task.id}. Continue the same session and run the verifier.`;
}

function approvedChecks(approval, task) {
  if (!approval || typeof approval !== "object" || Array.isArray(approval) ||
      Object.keys(approval).some(key => !["checks", "testRevision"].includes(key)))
    throw new Error("Approval accepts only checks and testRevision");
  const checks = approval.checks ?? [];
  if (!Array.isArray(checks)) throw new Error("checks must be an array");
  const names = new Set((task.policy.checks ?? []).map(check => check.name));
  for (const check of checks) {
    if (!validCheck(check)) throw new Error("Each check needs a name, executable argv and an explicit functional scope");
    if (names.has(check.name)) throw new Error("Existing checks cannot be replaced");
    names.add(check.name);
  }
  return checks;
}

function validCheck(check) {
  const fields = new Set(["name", "type", "scope", "argv", "cwd", "requireTestCount"]);
  return check?.type === "functional" && typeof check.name === "string" && check.name.trim() &&
    Object.keys(check).every(key => fields.has(key)) && scopeList(check.scope) && scopeList([check.cwd ?? "."]) &&
    Array.isArray(check.argv) && check.argv.length && check.argv.every(arg => typeof arg === "string" && arg.length && !arg.includes("\0")) &&
    (check.requireTestCount === undefined || typeof check.requireTestCount === "boolean");
}

async function approvedRevisions(task, requested) {
  if (requested === undefined) return {};
  if (!requested || typeof requested !== "object" || Array.isArray(requested))
    throw new Error("testRevision must map test paths to reviewed SHA-256 digests");
  const tree = await snapshot(task.root);
  const revisions = Object.entries(requested).map(([path, sha]) => {
    const entry = tree.files[path]?.[1];
    if (!scopeList([path]) || !testInput.test(path) || typeof entry?.[0] !== "number" || sha !== entry[1])
      throw new Error("Unreviewed or unsupported test revision: " + path);
    return [path, entry];
  });
  return Object.fromEntries(revisions);
}

function sameInputs(before, after) {
  const { inputs, ...fixed } = before;
  const { inputs: next, ...current } = after;
  return JSON.stringify(fixed) === JSON.stringify(current) &&
    Object.entries(inputs).every(([path, value]) => JSON.stringify(next[path]) === JSON.stringify(value));
}
