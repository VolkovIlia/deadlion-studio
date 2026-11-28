import { join } from "node:path";
import { execute } from "./process.mjs";
import { digest, persist, read, save, scripts, snapshot } from "./evidence.mjs";
import { verifyToolInputs } from "./gate.mjs";
import { chargeAnalysis, operationTimeout, timeLeft } from "./execution.mjs";
import { scalingSummary } from "./diagnostics.mjs";
import { design } from "./design.mjs";
import { adoptTechnicalPlan } from "./refactor-plan.mjs";
import { advanceMission, continueAfterFailure, startMission } from "./mission.mjs";
import { completeMilestone } from "./refactor.mjs";
import { recoveryDecision } from "./recovery.mjs";
import { prepareImportCheck } from "./import-evidence.mjs";
import { outcome } from "./task-input.mjs";

export const hashTree = async task => digest(JSON.stringify(await snapshot(task.cwd)));

export async function reusableReceipt(task, report, signal) {
  if (!report || task.refactor || task.policy.semgrepConfig || signal?.aborted) return false;
  try {
    const evidence = await read(report.receipt);
    if (report.receiptHash !== digest(JSON.stringify(evidence)) || report.source !== await hashTree(task)) return false;
    const tools = await verifyToolInputs(task, { signal });
    return !signal?.aborted && evidence.toolIdentity === digest(JSON.stringify(tools));
  } catch {
    return false;
  }
}

export async function measureBaseline(task, signal) {
  const original = await read(join(task.directory, "baseline.json"));
  await verifyToolInputs(task, { signal });
  const current = await snapshot(task.cwd);
  if (digest(JSON.stringify(original.files)) !== digest(JSON.stringify(current.files)))
    throw new Error("baseline measurement needs the original working tree");
  const started = Date.now();
  let result;
  try {
    result = await execute([join(scripts, "dl-perf-gate"), task.approved, "--isolated",
      "--candidate-dir", task.candidate], { cwd: task.root, signal, timeout: Math.min(operationTimeout(task), timeLeft(task, started)) });
  } finally {
    chargeAnalysis(task, started);
    await persist(task);
  }
  const data = JSON.parse(result.stdout);
  if (digest(JSON.stringify(current)) !== await hashTree(task)) throw new Error("workspace changed during baseline measurement");
  await verifyToolInputs(task, { signal });
  const receipt = join(task.directory, "initial-measurement.json");
  await save(receipt, data);
  if (!["VERIFIED", "PERFORMANCE REGRESSION"].includes(data.status)) throw new Error("baseline: " + data.status);
  task.baselineReceipt = receipt;
  task.designIssue = await design(task);
  await persist(task);
  return { status: data.status, receipt, purpose: "baseline", scaling: scalingSummary(data) };
}

export function registerVerifier(pi, controller) {
  if (!pi.registerTool || !pi.zod) return;
  const running = new WeakSet();
  pi.registerTool({
    name: "deadlion_verify", label: "Deadlion verification",
    description: "Run engineering checks. Start a campaign with action campaign and a project-relative Markdown plan path. verify advances a passing milestone, defer selects independent work after failure, and replan adds scoped prerequisites. characterize_imports prepares a native bash check for grouping a parametrized Python import test.",
    parameters: pi.zod.object({ action: pi.zod.enum(["verify", "campaign", "replan", "defer", "characterize_imports"]).optional(),
      plan: pi.zod.string().optional(), reason: pi.zod.string().optional(), path: pi.zod.string().optional(),
      ratchet: pi.zod.string().optional() }),
    async execute(_id, args, signal, _update, ctx) {
      if (ctx.agent.kind === "sub") throw new Error("The main session owns verification.");
      const task = await controller.taskFor(ctx);
      if (!task) throw new Error("There is no available Deadlion baseline. Continue with native OMP tools.");
      if (running.has(task)) throw new Error("An engineering check is already running for this task.");
      running.add(task);
      try { return await runVerifier(controller, task, ctx, args ?? {}, signal); }
      finally { running.delete(task); }
    },
  });
}

async function runVerifier(controller, task, ctx, args, signal) {
  switch (args.action) {
    case "campaign": return result({ next: await startMission(controller, task, ctx, args.path, signal) });
    case "replan": return replan(controller, task, ctx, args);
    case "defer": return defer(controller, task, ctx);
    case "characterize_imports": {
      const check = prepareImportCheck(task, args);
      await persist(task);
      return result(check);
    }
    default: {
      const report = await controller.fullCheck(task, signal, ctx);
      const { status, receipt, scaling, failures } = report;
      let next;
      if (status === "PASS" && task.refactor && task.autonomous) {
        next = await advanceVerified(controller, task, ctx, report);
      }
      const guidance = failures?.length ? "Resolve these checks and verify again, or continue independent work. " +
        "Use native tests and a fixed oracle. For an import test grouping, use characterize_imports." : undefined;
      return result({ status, receipt, scaling, guidance, failures: failures?.slice(0, 5), next });
    }
  }
}

async function replan(controller, task, ctx, args) {
  if (!task?.autonomous || !task.refactor || !args.plan || !args.reason)
    throw new Error("An active campaign milestone, plan and rationale are required for replanning");
  if (task.last?.receipt && task.last?.failures?.length && task.recovery?.recent.at(-1)?.receipt !== task.last.receipt)
    recoveryDecision(task, task.last);
  await adoptTechnicalPlan(task, args.plan, args.reason, ctx);
  task.stageDeferred = true;
  await persist(task);
  const next = await advanceMission(controller, task, ctx, "Accepted technical plan revision");
  return result({ next: next ?? "Recorded technical revision. Inspect campaign status." });
}

function result(data) {
  return { content: [{ type: "text", text: JSON.stringify(data) }], details: { receipt: data.receipt } };
}

async function advanceVerified(controller, task, ctx, report) {
  await completeMilestone(task, report);
  await persist(task);
  const next = await advanceMission(controller, task, ctx, "Verified milestone " + task.refactor.id);
  if (next) return next;
  return openRequirements(task, ctx);
}

async function defer(controller, task, ctx) {
  if (!task.last?.failures?.length || !task.autonomous || !task.refactor)
    throw new Error("An autonomous milestone and a recorded failed check are required.");
  const next = await continueAfterFailure(controller, task, ctx, task.last.failures[0].reason);
  if (!next && task.stageDeferred) return result({ next: await openRequirements(task, ctx) });
  return result({ next: next ?? task.blocker ?? "Dependent work remains open. Inspect the campaign DAG." });
}

async function openRequirements(task, ctx) {
  task.state = "INCOMPLETE";
  task.blocker = "Dependent requirements remain open and no independent milestone is ready.";
  await outcome(task, ctx);
  return task.blocker;
}
