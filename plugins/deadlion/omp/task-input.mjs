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
  const summary = `${subject} ${task.state} · ${task.last?.status ?? 'NOT VERIFIED'}`;
  if (verified) showTaskStatus(ctx);
  else showTaskStatus(ctx, summary, reason ?? 'See /deadlion report.', ['AWAITING_APPROVAL', 'AWAITING_RESTART'].includes(task.state)
    ? 'Independent work can continue in this session.' : 'Send a message to choose the next step.');
  await persist(task);
  ctx.ui?.notify([summary, reason, task.last?.receipt ?? task.directory].filter(Boolean).join('\n'),
    verified ? 'info' : 'warning');
  if (process.env.DL_VERDICT_FILE)
    await save(process.env.DL_VERDICT_FILE, { state: task.state, task: task.id, report: task.last,
      mission: task.refactor?.campaign ?? task.missionId, milestone: task.refactor?.id,
      scope: task.refactor ? 'milestone' : 'mission', reason });
}

export async function confirmNewTask(task, ctx, expired) {
  let reason = `Previous task stopped (${task.state}).`;
  if (task.cwd !== ctx.cwd) reason = 'Working directory changed.';
  else if (expired) reason = 'Previous task budget expired.';
  if (!await ctx.ui?.confirm?.('Deadlion: start a new task?', `${reason}\nSend here with a new budget?`))
    throw new Error(`${reason} New task not started.`);
}

export async function resolveTaskInput(task, ctx, selection, newRequest, terminal) {
  if (!task || !newRequest) return { selection };
  const expired = exhausted(task);
  const moved = task.cwd !== ctx.cwd;
  const legacyVerifier = (task.last?.reason ?? task.last?.failures?.[0]?.reason) === 'verification inputs, analyzer installation or Core changed';
  const recoverable = (['AWAITING_APPROVAL', 'AWAITING_RESTART'].includes(task.state) ||
    task.state === 'BLOCKED' && (task.recovery || legacyVerifier)) && !expired;
  if (needsConfirmation(task, ctx, { selection, expired, moved, recoverable, terminal })) {
    await confirmNewTask(task, ctx, expired);
    return { selection: 'new', expired };
  }
  if (moved && selection !== 'new') throw new Error('Stored task does not match this OMP session');
  return { selection: selection ?? (recoverable ? 'continue' : undefined), expired };
}

function needsConfirmation(task, ctx, { selection, expired, moved, recoverable, terminal }) {
  if (ctx.mode !== 'tui' || task.refactor || selection) return false;
  if (moved) return true;
  if (task.state === 'VERIFIED' || process.env.DL_RESUME_TASK === '1') return false;
  return expired || !recoverable && terminal.has(task.state);
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

export async function rejectPrompt(prompt, error, ctx) {
  showTaskStatus(ctx, 'Deadlion: message not sent', error.message);
  if (!ctx.ui?.getEditorText?.()) ctx.ui?.setEditorText?.(prompt);
  ctx.ui?.notify(error.message, 'error');
  try {
    if (process.env.DL_VERDICT_FILE) await save(process.env.DL_VERDICT_FILE,
      { state: 'INCOMPLETE', reason: error.message });
  } finally {
    ctx.abort?.();
  }
}
