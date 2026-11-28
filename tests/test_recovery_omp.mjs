import assert from "node:assert/strict";
import test from "node:test";
import { exhausted, executionLimits, migrateExecution, updateBudget } from "../plugins/deadlion/omp/execution.mjs";
import { recoveryDecision } from "../plugins/deadlion/omp/recovery.mjs";
import { mergeDiagnostic, observedDiagnostic } from "../plugins/deadlion/omp/lsp.mjs";
import { parsePlan, validateTechnicalRevision } from "../plugins/deadlion/omp/refactor-plan.mjs";

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
