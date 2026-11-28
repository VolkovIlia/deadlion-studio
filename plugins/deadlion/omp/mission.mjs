import { read, persist } from "./evidence.mjs";
import { activeRefactor, finalRefactorTask, milestonePrompt, saveCampaignFinal, startRefactor } from "./refactor.mjs";
import { activateMilestone, deferMilestone, readyMilestones, reservation, state, withCampaignLock, optional } from "./refactor-state.mjs";

export async function advanceMission(controller, task, ctx, reason, signal) {
  const current = await read(state(task.refactor.directory));
  const [next] = readyMilestones(current);
  if (next) {
    const child = await controller.createTask(ctx, task.goal, next.id, true, signal);
    await activateMilestone(ctx, child);
    await replaceTask(controller, ctx, task, child);
    return `${reason}. Same mission ${current.id}. ${milestonePrompt(child.refactor.step)}`;
  }
  if (current.status === "ACTIVE" && Object.values(current.steps).every(step => current.results[step.id])) {
    const final = await finalRefactorTask(ctx);
    final.autonomous = true;
    await persist(final);
    controller.rememberTask(final);
    await replaceTask(controller, ctx, task, final);
    return "Milestones verified. Run deadlion_verify for final verification against the original campaign baseline.";
  }
}

export async function startMission(controller, task, ctx, plan, signal) {
  if (!plan || task.refactor || task.refactorFinal) throw new Error("Provide the project-relative Markdown plan before implementation.");
  task.baselineCapture = true;
  const report = await controller.fullCheck(task, signal, ctx);
  const message = await startRefactor(ctx, plan, task, report.receipt, true, signal);
  const { directory } = await activeRefactor(ctx.cwd);
  return advanceMission(controller, { ...task, refactor: { directory } }, ctx, message, signal);
}

async function replaceTask(controller, ctx, prior, next) {
  controller.release(ctx, prior);
  controller.tasks.set(controller.session(ctx), next);
  await controller.prepareTask(next, ctx);
}

export async function continueAfterFailure(controller, task, ctx, reason, signal) {
  if (!task.autonomous || !task.refactor) return;
  if (!await deferMilestone(task, reason, ctx)) {
    task.blocker = "Unverified milestone edits remain. Review and restore or verify them before switching milestones.";
    return;
  }
  task.stageDeferred = true;
  await persist(task);
  return advanceMission(controller, task, ctx, `Milestone ${task.refactor.id} deferred: ${reason}`, signal);
}

export async function commitMission(task, report) {
  return withCampaignLock(task.refactorFinal, async () => {
    if (await optional(reservation(task.refactorFinal))) throw new Error("A milestone is active during final verification");
    await saveCampaignFinal(task, report);
  });
}
