import { persist, save } from './evidence.mjs';

export function showTaskStatus(ctx, ...rows) {
  if (ctx.mode === 'tui') ctx.ui?.setWidget?.('deadlion', rows.length ? rows : undefined);
}

export async function outcome(task, ctx) {
  const reason = task.last?.failures?.[0]?.reason || task.last?.reason;
  const verified = task.state === 'VERIFIED';
  const summary = `Deadlion ${task.state} · ${task.last?.status ?? 'NOT VERIFIED'}`;
  if (verified) showTaskStatus(ctx);
  else showTaskStatus(ctx, summary, reason ?? 'See /deadlion report.', 'Send a message to choose the next step.');
  await persist(task);
  ctx.ui?.notify([summary, reason, task.last?.receipt ?? task.directory].filter(Boolean).join('\n'),
    verified ? 'info' : 'warning');
  if (process.env.DL_VERDICT_FILE)
    await save(process.env.DL_VERDICT_FILE, { state: task.state, task: task.id, report: task.last });
}

export async function confirmNewTask(task, ctx, expired) {
  let reason = `Previous task stopped (${task.state}).`;
  if (task.cwd !== ctx.cwd) reason = 'Working directory changed.';
  else if (expired) reason = 'Previous task budget expired.';
  if (!await ctx.ui?.confirm?.('Deadlion: start a new task?', `${reason}\nSend here with a new budget?`))
    throw new Error(`${reason} New task not started.`);
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
