import { join } from "node:path";
import { execute } from "./process.mjs";
import { approvalHash, digest, persist, read, save, scripts, snapshot } from "./evidence.mjs";
import { chargeAnalysis, operationTimeout, timeLeft } from "./execution.mjs";
import { scalingSummary } from "./diagnostics.mjs";
import { design } from "./design.mjs";
import { adoptTechnicalPlan } from "./refactor-plan.mjs";
import { advanceMission } from "./mission.mjs";
import { awaitsApproval } from "./recovery.mjs";

export const hashTree = async task => digest(JSON.stringify(await snapshot(task.cwd)));

export async function measureBaseline(task, signal) {
  const original = await read(join(task.directory, "baseline.json"));
  if (task.approvalHash !== await approvalHash(task)) throw new Error("approved fixtures changed");
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
  pi.registerTool({
    name: "deadlion_verify", label: "Deadlion verification",
    description: "Run approved checks or measure the required baseline. In an autonomous refactoring campaign, action replan can add scoped prerequisite stages to the approved plan after a recorded failure.",
    parameters: pi.zod.object({ action: pi.zod.enum(["verify", "replan"]).optional(),
      plan: pi.zod.string().optional(), reason: pi.zod.string().optional() }),
    async execute(_id, args, signal, _update, ctx) {
      if (ctx.agent.kind === "sub") throw new Error("The main session owns verification.");
      const task = await controller.taskFor(ctx);
      if (args?.action === "replan") return replan(controller, task, ctx, args);
      const report = await controller.fullCheck(task, signal, ctx);
      const { status, receipt, scaling, failures } = report;
      const guidance = awaitsApproval(report) ? "Acceptance awaits operator approval. Continue authorized independent work." : undefined;
      return { content: [{ type: "text", text: JSON.stringify({ status, receipt, scaling, guidance, failures: failures?.slice(0, 5) }) }],
        details: { receipt } };
    },
  });
}

async function replan(controller, task, ctx, args) {
  if (!task?.autonomous || !task.refactor || !args.plan || !args.reason)
    throw new Error("An active campaign milestone, plan and rationale are required for replanning");
  await adoptTechnicalPlan(task, args.plan, args.reason, ctx);
  task.stageDeferred = true;
  await persist(task);
  const next = await advanceMission(controller, task, ctx, "Accepted technical plan revision");
  return { content: [{ type: "text", text: next?.reason ?? "Recorded technical revision. Review campaign status." }] };
}
