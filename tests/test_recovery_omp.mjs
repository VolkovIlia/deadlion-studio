import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { digest, openTask, read, save } from "../plugins/deadlion/omp/evidence.mjs";
import { exhausted, executionLimits, migrateExecution, updateBudget } from "../plugins/deadlion/omp/execution.mjs";
import { recoveryDecision } from "../plugins/deadlion/omp/recovery.mjs";
import { mergeDiagnostic, observedDiagnostic } from "../plugins/deadlion/omp/lsp.mjs";
import { activeRefactor, bindMilestone, refactorStatus, startRefactor } from "../plugins/deadlion/omp/refactor.mjs";
import { reservation, state } from "../plugins/deadlion/omp/refactor-state.mjs";
import { parsePlan, validateTechnicalRevision } from "../plugins/deadlion/omp/refactor-plan.mjs";

async function structuralFixture(t) {
  const fixture = await mkdtemp(join(tmpdir(), "deadlion-structural-"));
  const directory = join(fixture, "source");
  await mkdir(directory);
  const previous = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = join(fixture, "state");
  t.after(async () => {
    if (previous === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previous;
    await rm(fixture, { recursive: true, force: true });
  });
  const ctx = { cwd: directory };
  const git = (...args) => execFileSync("git", args, { cwd: directory });
  git("init", "-q");
  await writeFile(join(directory, "module.py"), "answer = 42\n");
  await writeFile(join(directory, "plan.md"), "Status: active\n\n### T1: Change\n" +
    "Files: module.py\nChange: Refactor\nTest: Preserve behavior\nVerify: Run check\nDepends: —\n");
  git("add", ".");
  git("-c", "user.name=Smoke", "-c", "user.email=smoke@fixture", "commit", "-qm", "fixture");
  return ctx;
}

test("campaign scans use the configured operation deadline and the remaining shared budget", async t => {
  const ctx = await structuralFixture(t);
  const task = await openTask(ctx, "Refactor module.");
  task.policy.operationSeconds = 42;
  const timeouts = [];
  const timer = globalThis.setTimeout;
  t.mock.method(globalThis, "setTimeout", (callback, delay, ...args) => {
    if (new Error().stack.includes("at structuralMetrics")) timeouts.push(delay);
    return timer(callback, delay, ...args);
  });

  task.analysisMs = 0;
  await assert.rejects(startRefactor(ctx, "plan.md", task), /analysis budget exhausted/);
  await assert.rejects(startRefactor(ctx, "plan.md", { ...task, analysisMs: null }, undefined, false, AbortSignal.abort()), /CANCELLED/);
  assert.deepEqual(timeouts, []);
  task.analysisMs = null;
  await startRefactor(ctx, "plan.md", task);
  assert.deepEqual(timeouts.splice(0), [42000]);

  const campaign = await activeRefactor(ctx.cwd);
  const file = state(campaign.directory);
  const current = campaign.current;
  const child = await openTask(ctx, "Refactor module.");
  child.policy = task.policy;
  current.execution.analysisMs = 0;
  await save(file, current);
  await assert.rejects(bindMilestone(ctx, "T1", child), /analysis budget exhausted/);
  await assert.rejects(read(reservation(campaign.directory)), { code: "ENOENT" });
  assert.deepEqual(timeouts, []);
  current.execution.analysisMs = 27000;
  await save(file, current);
  await bindMilestone(ctx, "T1", child);
  assert.deepEqual(timeouts.splice(0), [27000]);
  const remaining = (await read(file)).execution.analysisMs;
  assert.ok(remaining < 27000 && remaining === child.analysisMs);
  await refactorStatus(ctx, true);
  assert.deepEqual(timeouts.splice(0), [remaining]);
  const next = await read(file);
  next.execution.analysisMs = 0;
  await save(file, next);
  assert.match(await refactorStatus(ctx, true), /NOT MEASURED/);

  const receipt = join(campaign.directory, "final-gate.json");
  const evidence = { source: next.checkpoint, checks: [{ name: "structural ratchet", data: { sloc: 42, projects: {} } }] };
  await save(receipt, evidence);
  await save(join(campaign.directory, "final-receipt.json"), { receipt, receiptHash: digest(JSON.stringify(evidence)) });
  assert.match(await refactorStatus(ctx, true), /→ 42/);
  assert.deepEqual(timeouts, []);
});

test("clearing a semantic failure requires a complete observation from the required server on one snapshot", async () => {
  const failed = mergeDiagnostic(undefined, { status: "FAIL", server: "pyright" });
  const report = { toolName: "lsp", input: { action: "diagnostics", file: "module.py" },
    content: [{ type: "text", text: "OK" }], details: { serverName: "pyright", success: true } };
  const pending = { task: "task", source: "original", file: report.input.file };
  const task = { id: pending.task };
  const raced = await observedDiagnostic(task, report, pending, async () => "changed");
  assert.equal(mergeDiagnostic(failed, raced), failed);

  const complete = await observedDiagnostic(task, report, pending, async () => "original");
  assert.equal(mergeDiagnostic(failed, { ...complete, server: "ruff" }), failed);
  assert.equal(mergeDiagnostic(failed, { ...complete, status: "INCONCLUSIVE" }), failed);
  const accepted = mergeDiagnostic(failed, complete);
  assert.equal(accepted.status, "PASS");
  assert.equal(accepted.sourceHash, "original");
  assert.deepEqual(accepted.requiredServers, ["pyright"]);
  assert.equal(accepted.required, true);
});

test("migration removes implicit limits and operator adjustments preserve evidence", () => {
  const original = { id: "task", started: 100, policy: { seconds: 2 }, deadline: 2100, analysisMs: 120000,
    maxCorrections: 2, baselineHash: "baseline", recovery: { recent: ["investigate"] } };
  migrateExecution(original);
  assert.equal(original.analysisMs, null);
  assert.equal(original.maxCorrections, null);
  assert.equal(exhausted(original, 2100), "wall-clock budget exhausted");
  updateBudget(original, "seconds 4", 2200);
  assert.equal(original.deadline, 6200);
  assert.equal(exhausted(original, 2200), undefined);
  updateBudget(original, "seconds unlimited", 3000);
  assert.equal(original.deadline, null);
  assert.deepEqual([original.id, original.baselineHash, original.recovery.recent[0]], ["task", "baseline", "investigate"]);
  assert.equal(original.budgetChanges.length, 2);
  assert.throws(() => executionLimits({ operationSeconds: -1 }), /Invalid limit/);
});

test("alternating evidence and source noise cannot repeatedly renew a failed strategy", () => {
  const task = {};
  let record;
  for (let n = 0; n < 8; n++) {
    const side = n % 2;
    record = recoveryDecision(task, { source: "random-" + n, confirmed: ["suite-" + side],
      failures: [{ name: "opposite-" + side, status: "FAIL", reason: "candidate rejected" }] });
  }
  assert.equal(record.progress, false);
  assert.equal(record.strategy, "DEFER");
});

test("technical plan revisions can add prerequisites while retaining approved checks and scopes", () => {
  const header = "# Mission\nGoal: Preserve expected behavior\nStatus: approved\n";
  const parent = "### T1: Compute\nFiles: compute\nDepends: —\nChange: Compute\nTest: Check result\nVerify: Run suite\nRequired: functional tests\n";
  const subs = "### T2: Kernel\nFiles: compute/kernel.py\nDepends: —\nChange: Extract kernel\nTest: Check math\nVerify: Run suite\n";
  const plan = (body, prefix = header) => ({ text: prefix + body, steps: parsePlan(prefix + body), results: {} });
  const initial = plan(parent);
  const next = parent.replace("Depends: —", "Depends: T2") + subs;
  assert.doesNotThrow(() => validateTechnicalRevision(initial, plan(next)));
  assert.throws(() => validateTechnicalRevision(initial, plan(next.replace("compute/kernel.py", "other/file.py"))), /scope/);
  assert.throws(() => validateTechnicalRevision(initial, plan(next.replace("Required: functional tests", "Advisory: Keep it fast"))), /requirements/);
  assert.throws(() => validateTechnicalRevision(initial, plan(next, header.replace("Preserve", "Remove"))), /goal/);
  assert.throws(() => validateTechnicalRevision({ ...initial, results: { T1: {} } }, plan(next)), /requirements/);
});
