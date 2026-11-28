import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import performance from '../plugins/deadlion/omp/performance.mjs';
import { resolveTaskInput } from '../plugins/deadlion/omp/task-input.mjs';

async function scenario(t, { moved = false, mode = 'tui', corrupt = false, refactor, pending } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'dl-input-'));
  const cwd = join(root, 'checkout');
  const directory = join(root, 'old');
  await Promise.all([mkdir(cwd), mkdir(directory)]);
  const prevHome = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = root;
  let shutdown;
  t.after(async () => {
    await shutdown?.();
    if (prevHome === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = prevHome;
    await rm(root, { recursive: true, force: true });
  });
  const old = { id: 'old', directory, cwd: moved ? join(root, 'previous') : cwd, state: 'INCOMPLETE',
    policy: { seconds: 1 },
    deadline: 1, analysisMs: 10000, refactor: refactor ? { directory: root } : null,
    last: { reason: 'wall-clock budget exhausted' } };
  if (pending) Object.assign(old, { state: 'AWAITING_APPROVAL', policy: {}, mode: 'Standard', deadline: null,
    analysisMs: null, baselineHash: 'original', executionVersion: 1 });
  const file = join(directory, 'task.json');
  await writeFile(file, JSON.stringify(old));
  const branch = [{ type: 'custom', customType: 'deadlion.engineering.task', data: { id: corrupt ? 'wrong' : old.id, directory } }];
  const hooks = {}, state = { confirmations: 0, aborts: 0, widgets: [], draft: '' };
  performance({ on(name, fn) { hooks[name] = fn; },
    appendEntry(customType, data) { branch.push({ type: 'custom', customType, data }); } });
  const ctx = { mode, cwd, sessionManager: { getSessionId: () => root, getBranch: () => branch },
    abort() { state.aborts++; }, ui: { notify() {}, setWidget(_, rows) { state.widgets.push(rows?.join(' ')); },
      confirm() { state.confirmations++; assert.fail('Deadlion must not open a confirmation'); }, getEditorText() { return state.draft; },
      setEditorText(text) { state.draft = text; } } };
  const prompt = 'Continue the review';
  shutdown = () => hooks.session_shutdown({}, ctx);
  const result = await hooks.before_agent_start({ prompt }, ctx);
  const saved = JSON.parse(await readFile(file, 'utf8'));
  if (!pending) assert.deepEqual(saved, old, 'never renew or rewrite an expired or unavailable task');
  return { state, result, branch, prompt, saved };
}

test('an explicit exhausted budget pauses without a confirmation and retains the draft', async t => {
  const { state, branch, prompt } = await scenario(t);
  assert.equal(state.aborts, 1);
  assert.equal(branch.length, 1);
  assert.equal(state.draft, prompt);
  assert.match(state.widgets.at(-1), /budget exhausted/i);
});

for (const options of [{ mode: 'print', corrupt: true }, { moved: true }, { moved: true, refactor: true }])
  test(`unavailable verification leaves native OMP work available: ${JSON.stringify(options)}`, async t => {
    const { state, branch, result } = await scenario(t, options);
    assert.equal(state.confirmations, 0);
    assert.equal(state.aborts, 0);
    assert.equal(branch.length, 1);
    assert.match(result.message.content, /Continue authorized work/);
  });

test('legacy approval waits resume with the original task and baseline', async t => {
  const { state, saved } = await scenario(t, { pending: true });
  assert.equal(state.aborts, 0);
  assert.equal(saved.id, 'old');
  assert.equal(saved.baselineHash, 'original');
  assert.equal(saved.state, 'IMPLEMENTATION');
});

test('legacy verifier drift permits the next prompt in the same OMP session', async () => {
  const task = { cwd: '/checkout', state: 'BLOCKED', last: { reason: 'verification inputs, analyzer installation or Core changed' } };
  const ctx = { mode: 'tui', cwd: task.cwd, ui: { confirm() { assert.fail('continuing should need no confirmation'); } } };
  const input = await resolveTaskInput(task, ctx, undefined, true, new Set(['BLOCKED']));
  assert.equal(input.selection, 'continue');
});
