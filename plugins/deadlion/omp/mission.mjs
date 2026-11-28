import { read, persist } from "./evidence.mjs";
import { finalRefactorTask, milestonePrompt, saveCampaignFinal } from "./refactor.mjs";
import { activateMilestone, deferMilestone, readyMilestones, reservation, state, withCampaignLock, optional } from "./refactor-state.mjs";

export async function advanceMission(controller, task, ctx, reason) {
  const current = await read(state(task.refactor.directory));
  const [next] = readyMilestones(current);
  if (next) {
    const child = await controller.createTask(ctx, task.goal, next.id, true);
    await activateMilestone(ctx, child);
    await replaceTask(controller, ctx, task, child);
    return { decision: "block", reason: `${reason}. Same mission ${current.id}. ${milestonePrompt(child.refactor.step)}` };
  }
  if (current.status === "ACTIVE" && Object.values(current.steps).every(step => current.results[step.id])) {
    const final = await finalRefactorTask(ctx);
    final.autonomous = true;
    await persist(final);
    controller.rememberTask(final);
    await replaceTask(controller, ctx, task, final);
    return { decision: "block", reason: "Milestones verified. Run deadlion_verify for final verification against the original campaign baseline." };
  }
}

async function replaceTask(controller, ctx, prior, next) {
  controller.release(ctx, prior);
  controller.tasks.set(controller.session(ctx), next);
  await controller.prepareTask(next, ctx);
}

export async function continueAfterFailure(controller, task, ctx, reason) {
  if (!task.autonomous || !task.refactor) return;
  if (!await deferMilestone(task, reason, ctx)) {
    task.blocker = "Unverified milestone edits remain. Review and restore or verify them before switching milestones.";
    return;
  }
  task.stageDeferred = true;
  await persist(task);
  return advanceMission(controller, task, ctx, `Milestone ${task.refactor.id} deferred: ${reason}`);
}

export async function commitMission(task, report) {
  return withCampaignLock(task.refactorFinal, async () => {
    if (await optional(reservation(task.refactorFinal))) throw new Error("A milestone is active during final verification");
    await saveCampaignFinal(task, report);
  });
}
