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
    assert.deepEqual((await projectPolicy(root, home)).testsScope, ["."]);
    await writeFile(make, "test:\n\tfalse\n");
    assert.match((await projectPolicy(root, home)).setupIssue, /changed/);
    await assert.rejects(lstat(marker), /ENOENT/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
