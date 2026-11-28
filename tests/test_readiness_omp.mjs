import test from "node:test";
import assert from "node:assert/strict";

import { classify } from "../plugins/deadlion/omp/evidence.mjs";

test("intent controls initial mode before topic words", () => {
  for (const prompt of ["Explain the algorithm", "Discuss performance", "Объясни алгоритм", "Исследуй без изменений файлов"]) {
    const route = classify(prompt);
    assert.equal(route.mode, "Standard", prompt);
    assert.equal(route.scope, "read-only", prompt);
  }
  for (const prompt of ["Fix a comment about performance", "Fix README", "Исправь комментарий об алгоритме"])
    assert.equal(classify(prompt).intent, "documentation", prompt);
  for (const prompt of ["Implement a CRUD endpoint", "Replace the search algorithm", "Refactor this function"])
    assert.equal(classify(prompt).mode, "Standard", prompt);
  assert.equal(classify("Optimize the hot loop").mode, "Performance");
  assert.equal(classify("Prove the complexity of the algorithm").scope, "read-only");
  assert.equal(classify("Run Autoresearch").mode, "Evolution");
});

test("scope checks do not transfer a performance result to other components", async () => {
  const { changedArea, coverageFor } = await import("../plugins/deadlion/omp/coverage.mjs");
  const area = changedArea(["parse/main.py", "auth/main.py", "auth/schema.proto"],
    { "parse/pyproject.toml": [], "auth/Cargo.toml": [] });
  const oracle = { status: "PASS", coverage: { type: "oracle", paths: ["parse/main.py"], exact: true } };
  const looseTests = { status: "PASS", coverage: { type: "functional", paths: [] } };
  const compile = { status: "PASS", coverage: { type: "performance", paths: ["."] } };
  assert.deepEqual(coverageFor(area, [oracle, looseTests, compile]).map(row => row.status),
    ["VERIFIED", "NOT VERIFIED", "NOT VERIFIED"]);
  const integration = { status: "PASS", coverage: { type: "functional", paths: ["auth", "parse"] } };
  assert.ok(coverageFor(area, [oracle, integration]).every(row => row.status === "VERIFIED"));
});

test("ratchet and DAG reject worsening limits and conflicting owners", async () => {
  const { parsePlan, ratchet } = await import("../plugins/deadlion/omp/refactor.mjs");
  const section = (id, depends, owners = "") => `### ${id}: Fixture\nFiles: src\nDepends: ${depends}\n` +
    `Change: simplify\nTest: oracle\nVerify: oracle\nOwners: ${owners}\n`;
  assert.throws(() => parsePlan("Status: approved\n" + section("T1", "T2")), /Unknown/);
  assert.throws(() => parsePlan("Status: approved\n" + section("T1", "T2") + section("T2", "T1")), /Cyclic/);
  assert.throws(() => parsePlan("Status: approved\n" + section("T1", "—", "agent=src, peer=src/a")), /Overlapping/);
  const structural = lines => ({ maxFile: 500, maxFunction: 50, files: { "legacy.py": { lines, functions: {} } }, projects: {} });
  assert.deepEqual(ratchet(structural(1800), structural(1200), ["legacy.py"]), []);
  assert.equal(ratchet(structural(1200), structural(1201), ["legacy.py"]).length, 1);
});

test("opaque scans advance past an unchanged prefix of changed paths", async () => {
  const { mkdtemp, writeFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { execute } = await import("../plugins/deadlion/omp/process.mjs");
  const { incremental, snapshot, save } = await import("../plugins/deadlion/omp/evidence.mjs");
  const directory = await mkdtemp(join(tmpdir(), "deadlion-queue-"));
  const root = await mkdtemp(join(tmpdir(), "deadlion-project-"));
  try {
    const git = async (...args) => {
      const result = await execute(["git", ...args], { cwd: root });
      assert.equal(result.code, 0, result.stderr);
    };
    await git("init", "-q");
    await git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "fixture");
    await save(join(directory, "baseline.json"), await snapshot(root));
    for (let i = 0; i < 9; i++) await writeFile(join(root, `f${i}.py`), "x = 1\n");
    const task = { root, directory, deadline: Date.now() + 3000 };
    const first = await incremental(task);
    const second = await incremental(task);
    assert.equal(first.length, 8);
    assert.equal(second[0], join(root, "f8.py"));
  } finally {
    await Promise.all([rm(directory, { recursive: true, force: true }), rm(root, { recursive: true, force: true })]);
  }
});

test("a cancelled process reports cancellation and kills its process group", async () => {
  const { execute } = await import("../plugins/deadlion/omp/process.mjs");
  const controller = new AbortController();
  const running = execute(["sh", "-c", "trap '' TERM; (sleep 5) & wait"], { signal: controller.signal });
  setTimeout(() => controller.abort(), 100);
  await assert.rejects(running, /CANCELLED/);
  await assert.rejects(execute(["/no-such-deadlion-test-executable"], {}), /ENOENT/);
});

test("setup discovers a Makefile without executing it and revokes stale approval", async () => {
  const { mkdtemp, writeFile, lstat, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { save } = await import("../plugins/deadlion/omp/evidence.mjs");
  const { discover, projectPolicy, setup } = await import("../plugins/deadlion/omp/setup.mjs");
  const root = await mkdtemp(join(tmpdir(), "deadlion-setup-"));
  try {
    const marker = join(root, "unexpected");
    const make = join(root, "Makefile");
    await writeFile(make, `SIDE_EFFECT := $(shell touch "${marker}")\ntest:\n\ttrue\n`);
    const home = join(root, ".state");
    const project = await discover(root);
    assert.deepEqual(project.policy.tests, ["make", "test"]);
    assert.deepEqual(await projectPolicy(root, home), {});
    await setup(root, home, project.fingerprint, save);
    assert.equal((await projectPolicy(root, home)).testsScope, undefined);
    assert.equal((await projectPolicy(root, home)).checks, undefined);
    await setup(root, home, project.fingerprint + ' {"1":["src"]}', save);
    assert.deepEqual((await projectPolicy(root, home)).checks[0].scope, ["src"]);
    await writeFile(make, "test:\n\tfalse\n");
    assert.match((await projectPolicy(root, home)).setupIssue, /changed/);
    await assert.rejects(lstat(marker), /ENOENT/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('TAP skip and cancel markers cannot certify a partial suite', async () => {
  const { testResult } = await import('../plugins/deadlion/omp/test-result.mjs');
  assert.deepEqual(testResult(['make', 'test'], '# tests 3\n# pass 2\n# skipped 1', true),
    { source: 'TAP summary', passed: 2, incomplete: true });
  assert.equal(testResult(['npm', 'test'], 'nothing was run', true).passed, 0);
});

test('Ratchet compares measured qualified symbols and rejects copied legacy violations', async () => {
  const { mkdtemp, rm, writeFile } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { execute } = await import('../plugins/deadlion/omp/process.mjs');
  const { structuralMetrics, ratchet } = await import('../plugins/deadlion/omp/refactor.mjs');
  const root = await mkdtemp(join(tmpdir(), 'deadlion-ratchet-'));
  try {
    assert.equal((await execute(['git', 'init', '-q'], { cwd: root })).code, 0);
    const file = join(root, 'legacy.py');
    const body = '    async def action(self):\n        def inner():\n            return 1\n' +
      '        value = inner()\n'.repeat(12) + '        return value\n';
    const a = 'class A:\n' + body;
    const b = 'class B:\n    def action(self):\n        return 2\n';
    const options = { env: { ...process.env, DL_MAX_FUNC: '5' } };
    await writeFile(file, a + b);
    const before = await structuralMetrics(root, options);
    assert.deepEqual(before.files['legacy.py'].functions.map(item => item.name), ['A.action', 'A.action.inner', 'B.action']);
    await writeFile(file, 'def new():\n    return 0\n' + b + a);
    assert.deepEqual(ratchet(before, await structuralMetrics(root, options), ['legacy.py']), []);
    await writeFile(file, a.replace('def action', 'def renamed') + b);
    assert.deepEqual(ratchet(before, await structuralMetrics(root, options), ['legacy.py']), []);
    await writeFile(join(root, 'moved.py'), a);
    await writeFile(file, b);
    assert.deepEqual(ratchet(before, await structuralMetrics(root, options), ['legacy.py', 'moved.py']), []);
    await writeFile(file, a + b);
    assert.ok(ratchet(before, await structuralMetrics(root, options), ['legacy.py', 'moved.py']).some(issue => issue.status === 'FAIL'));
    await writeFile(file, a.replace('        return value', '        result = value\n        return result') + b);
    assert.ok(ratchet(before, await structuralMetrics(root, options), ['legacy.py']).some(issue => issue.name.includes('A.action')));
    await writeFile(file, a.replace('        value = inner()\n', '') + b);
    assert.deepEqual(ratchet(before, await structuralMetrics(root, options), ['legacy.py']), []);
    const movedOutside = { baseline: { files: { 'legacy.py': [null, [0, 'same']] } },
      current: { files: { 'docs/legacy.txt': [null, [0, 'same']] } } };
    await writeFile(file, '');
    assert.ok(ratchet(before, { ...before, files: {} }, ['legacy.py', 'docs/legacy.txt'], movedOutside)
      .some(issue => issue.status === 'INCONCLUSIVE'));
    assert.ok(ratchet({ ...before, projects: { '.': { sloc: 0, deps: ['a'], limits: { DL_MAX_DEPS: 1 } } } },
      { ...before, projects: { '.': { sloc: 0, deps: ['a', 'b'] } } }, ['legacy.py'])
      .some(issue => issue.name.includes('direct dependencies')));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('Semgrep requires a confirmed applicable rule and nonempty requested scope', async () => {
  const { checkSemgrep } = await import('../plugins/deadlion/omp/semgrep.mjs');
  const report = { results: [], errors: [], paths: { scanned: ['Example.kt'] } };
  const task = { policy: {}, root: '/project', semgrep: { source: 'same', data: report } };
  const run = files => checkSemgrep(task, files, 'same', {});
  assert.equal((await run(['/project/Example.kt'])).status, 'NOT VERIFIED');
  report.time = { rules: ['fixture'], targets: [{ path: 'Example.kt', match_times: [0.001] }] };
  assert.equal((await run([])).status, 'NOT VERIFIED');
  assert.equal((await run(['/project/Example.kt'])).status, 'PASS');
});

test('a measured source with unavailable Lizard leaves Ratchet inconclusive', async () => {
  const { mkdtemp, rm, writeFile } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { fileURLToPath } = await import('node:url');
  const { execute } = await import('../plugins/deadlion/omp/process.mjs');
  const { ratchet } = await import('../plugins/deadlion/omp/ratchet.mjs');
  const root = await mkdtemp(join(tmpdir(), 'deadlion-no-lizard-'));
  try {
    const options = { cwd: root };
    assert.equal((await execute(['git', 'init', '-q'], options)).code, 0);
    await writeFile(join(root, 'test.cc'), 'int f() { return 2; }\n');
    const script = fileURLToPath(new URL('../plugins/deadlion/omp/structural.py', import.meta.url));
    const result = await execute(['python3', '-I', '-S', script], options);
    assert.equal(result.code, 0, result.stderr);
    const measured = JSON.parse(result.stdout);
    assert.equal(measured.files['test.cc'].issue, 'Lizard unavailable');
    assert.ok(ratchet(measured, measured, ['test.cc']).some(issue => issue.status === 'INCONCLUSIVE'));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('installed Semgrep distinguishes an applicable Kotlin rule from a Python-only ruleset', async t => {
  const { mkdtemp, rm, writeFile } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { execute } = await import('../plugins/deadlion/omp/process.mjs');
  const { checkSemgrep } = await import('../plugins/deadlion/omp/semgrep.mjs');
  const { digest } = await import('../plugins/deadlion/omp/evidence.mjs');
  const binary = await execute(['which', 'semgrep'], {});
  if (binary.code) return t.skip('Semgrep unavailable');
  const root = await mkdtemp(join(tmpdir(), 'deadlion-semgrep-'));
  try {
    const file = join(root, 'Fixture.kt');
    const config = join(root, 'rules.yml');
    await writeFile(file, 'fun answer(): Int = fixtureCall()\n');
    const verify = async language => {
      const rules = `rules:\n  - id: fixture-rule\n    languages: [${language}]\n` +
        '    severity: WARNING\n    message: Fixture call\n    pattern: fixtureCall()\n';
      await writeFile(config, rules);
      return checkSemgrep({ root, policy: { native: true, semgrepConfig: config }, semgrepConfigHash: digest(rules) },
        [file], 'fixture', { cwd: root, timeout: 10000 });
    };
    assert.equal((await verify('kotlin')).status, 'WARNING');
    assert.equal((await verify('python')).status, 'NOT VERIFIED');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('build boundaries, removed components and renamed paths retain scoped obligations', async () => {
  const { changedArea, coverageFor } = await import('../plugins/deadlion/omp/coverage.mjs');
  const records = { 'old/package.json': [], 'new/pom.xml': [], 'new/nested/pyproject.toml': [] };
  const paths = ['old/removed.js', 'new/nested/introduced.py', 'new/gradle.properties'];
  const report = coverageFor(changedArea(paths, records), [
    { status: 'PASS', coverage: { type: 'functional', paths: ['new'] } },
  ]);
  assert.deepEqual(report.map(item => item.status), ['NOT VERIFIED', 'VERIFIED', 'NOT VERIFIED']);
  assert.deepEqual(report[2].affectedComponents, ['new', 'new/nested', 'old']);
});

test('Lizard distinguishes C++ overloads when their order changes', async t => {
  const { mkdtemp, rm, writeFile } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { execute } = await import('../plugins/deadlion/omp/process.mjs');
  const { structuralMetrics, ratchet } = await import('../plugins/deadlion/omp/refactor.mjs');
  const root = await mkdtemp(join(tmpdir(), 'deadlion-overloads-'));
  try {
    assert.equal((await execute(['git', 'init', '-q'], { cwd: root })).code, 0);
    const options = { env: { ...process.env, DL_MAX_FUNC: '3' } };
    const overload = 'int f(int x) {\n' + '  x += 1;\n'.repeat(9) + '  return x;\n}\n';
    const other = 'int f(double x) { return (int)x; }\n';
    const path = join(root, 'fixture.cpp');
    const write = body => writeFile(path, 'struct Obj {\n' + body + '};\n');
    await write(overload + other);
    const before = await structuralMetrics(root, options);
    if (!before.lizard) return t.skip('Lizard unavailable');
    assert.equal(new Set(before.files['fixture.cpp'].functions.map(item => item.key)).size, 2);
    await write(other + overload);
    assert.deepEqual(ratchet(before, await structuralMetrics(root, options), ['fixture.cpp']), []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('scoped refactoring tools reject symlink traversal outside the owner directory', async () => {
  const { mkdir, mkdtemp, realpath, rm, symlink } = await import('node:fs/promises');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');
  const { authorizeRefactorTool } = await import('../plugins/deadlion/omp/refactor.mjs');
  const directory = await mkdtemp(join(tmpdir(), 'deadlion-symlink-'));
  try {
    const root = await realpath(directory);
    await mkdir(join(root, 'allowed'));
    await mkdir(join(root, 'unassigned'));
    await symlink(join(root, 'unassigned'), join(root, 'allowed', 'escape'));
    const task = { root, refactor: { step: { scope: ['allowed'], owners: { worker: ['allowed'] } } } };
    const ctx = { cwd: root, agent: { kind: 'sub', name: 'worker' } };
    const event = { toolName: 'write' };
    assert.equal(await authorizeRefactorTool(task, event, ctx, ['allowed/new.py']), undefined);
    assert.match(await authorizeRefactorTool(task, event, ctx, ['allowed/escape/new.py']), /symlink/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
