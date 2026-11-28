import { persist, resumeTask, save } from './evidence.mjs';
import { exhausted } from './execution.mjs';

export function showTaskStatus(ctx, ...rows) {
  if (ctx.mode === 'tui') ctx.ui?.setWidget?.('deadlion', rows.length ? rows : undefined);
}

export async function outcome(task, ctx) {
  const restart = task.last?.failures?.find(check => check.restartRequired);
  const reason = task.blocker || restart?.reason || task.last?.failures?.[0]?.reason || task.last?.reason;
  const verified = task.state === 'VERIFIED';
  const subject = task.refactor ? 'Deadlion milestone ' + task.refactor.id : 'Deadlion';
  const verdict = task.last?.status === 'PASS' && !verified ? 'NOT VERIFIED' : task.last?.status;
  const summary = `${subject} ${task.state} · ${verdict ?? 'NOT VERIFIED'}`;
  if (verified) showTaskStatus(ctx);
  else showTaskStatus(ctx, summary, reason ?? 'See /deadlion report.');
  await persist(task);
  ctx.ui?.notify([summary, reason, task.last?.receipt ?? task.directory].filter(Boolean).join('\n'),
    verified ? 'info' : 'warning');
  if (process.env.DL_VERDICT_FILE)
    await save(process.env.DL_VERDICT_FILE, { state: task.state, task: task.id, report: task.last,
      mission: task.refactor?.campaign ?? task.missionId, milestone: task.refactor?.id,
      scope: task.refactor ? 'milestone' : 'mission', reason });
}

export function resolveTaskInput(task, ctx, selection, newRequest) {
  if (!task || !newRequest) return { selection };
  const expired = exhausted(task);
  if (task.cwd !== ctx.cwd && selection !== 'new') throw new Error('Stored task does not match this OMP session');
  return { selection: selection ?? 'continue', expired };
}

export function interrupted(task, event) {
  if (task.state === 'INCOMPLETE' || task.state === 'CANCELLED') return true;
  const stop = event.last_assistant_message?.stopReason;
  if (stop === 'error') task.state = 'INCOMPLETE';
  else if (stop === 'aborted' || event.signal?.aborted) task.state = 'CANCELLED';
  else return false;
  return true;
}

export function needsNewTask(task, { milestone, selection, newRequest, nativeGoal }) {
  if (!task || milestone || selection === 'new') return true;
  return newRequest && task.state === 'VERIFIED' && (!nativeGoal || task.nativeGoal !== nativeGoal.id);
}

export function resumeInput(task, input, { newRequest, terminal, nativeGoal }) {
  if (newRequest && (input.expired || terminal.has(task.state))) {
    const sameGoal = nativeGoal && nativeGoal.id === task.nativeGoal;
    resumeTask(task, input.selection ?? (sameGoal ? 'continue' : undefined));
  }
  return task;
}

export async function rejectPrompt(error, ctx, prompt) {
  const reason = error.message;
  showTaskStatus(ctx, 'Deadlion · NOT VERIFIED', reason);
  try {
    if (process.env.DL_VERDICT_FILE) await save(process.env.DL_VERDICT_FILE, { state: 'INCOMPLETE', reason });
  } catch (failure) {
    ctx.ui?.notify("Could not record Deadlion verdict: " + failure.message, "warning");
  }
  if (error.budget) {
    if (prompt && !ctx.ui?.getEditorText?.()) ctx.ui?.setEditorText?.(prompt);
    ctx.abort?.();
  }
  return { message: { customType: 'deadlion.unavailable', display: false,
    content: `Deadlion verification unavailable. ${reason} Continue authorized work using native OMP tools. Keep verification pending.` } };
}
