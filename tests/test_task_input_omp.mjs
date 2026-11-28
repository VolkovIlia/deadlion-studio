import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import performance from '../plugins/deadlion/omp/performance.mjs';

async function scenario(t, { moved = false, accept = true, mode = 'tui', corrupt = false, refactor } = {}) {
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
    deadline: 1, analysisMs: 10000, refactor: refactor ? { directory: root } : null,
    last: { reason: 'wall-clock budget exhausted' } };
  const file = join(directory, 'task.json');
  await writeFile(file, JSON.stringify(old));
  const branch = [{ type: 'custom', customType: 'deadlion.engineering.task', data: { id: corrupt ? 'wrong' : old.id, directory } }];
  const hooks = {}, state = { confirmations: 0, aborts: 0, widgets: [], draft: '' };
  performance({ on(name, fn) { hooks[name] = fn; },
    appendEntry(customType, data) { branch.push({ type: 'custom', customType, data }); } });
  const ctx = { mode, cwd, sessionManager: { getSessionId: () => root, getBranch: () => branch },
    abort() { state.aborts++; }, ui: { notify() {}, setWidget(_, rows) { state.widgets.push(rows?.join(' ')); },
      confirm() { state.confirmations++; return accept; }, getEditorText() { return state.draft; },
      setEditorText(text) { state.draft = text; } } };
  const prompt = 'Continue the review';
  shutdown = () => hooks.session_shutdown({}, ctx);
  const result = await hooks.before_agent_start({ prompt }, ctx);
  assert.deepEqual(JSON.parse(await readFile(file, 'utf8')), old, 'never renew or rewrite the expired task');
  return { state, result, branch, prompt, cwd };
}

for (const moved of [false, true]) test(`confirmed message starts a distinct task (moved=${moved})`, async t => {
  const { result, state, branch, cwd } = await scenario(t, { moved });
  assert.equal(state.confirmations, 1);
  assert.equal(state.aborts, 0);
  assert.ok(result?.message, 'original prompt cleared to proceed to OMP');
  const next = JSON.parse(await readFile(join(branch.at(-1).data.directory, 'task.json'), 'utf8'));
  assert.notEqual(next.id, 'old');
  assert.equal(next.cwd, cwd);
  assert.ok(next.deadline > next.started);
});

test('declining retains the unsent text and shows why work stopped', async t => {
  const { state, branch, prompt } = await scenario(t, { accept: false });
  assert.equal(state.aborts, 1);
  assert.equal(branch.length, 1);
  assert.equal(state.draft, prompt);
  assert.match(state.widgets.at(-1), /not sent/i);
});

for (const options of [{ mode: 'print' }, { moved: true, corrupt: true }, { refactor: true }])
  test(`no renewal on unattended or untrusted restore: ${JSON.stringify(options)}`, async t => {
    const { state, branch } = await scenario(t, options);
    assert.equal(state.confirmations, 0);
    assert.equal(state.aborts, 1);
    assert.equal(branch.length, 1);
  });
