import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import performance from "../plugins/deadlion/omp/performance.mjs";
import evolution from "../plugins/deadlion/omp/evolution.mjs";

test("edit feedback contains a real Ruff diagnostic", async () => {
  const cwd = await mkdtemp(join(tmpdir(), "dl-edit-"));
  await writeFile(join(cwd, "example.py"), "for k, v in table.items():\n    print(v)\n");
  let handler;
  performance({ on(name, fn) { if (name === "tool_result") handler = fn; } });
  const result = await handler({ toolName: "edit", input: { path: "example.py" }, content: [] }, { cwd });
  assert.match(result.content[0].text, /PERF102/);
});

test("a second extension instance sees the consumed iteration", async () => {
  const dir = await mkdtemp(join(tmpdir(), "dl-evolve-"));
  const cwd = join(dir, "repo");
  await mkdir(cwd);
  await writeFile(join(dir, "limits.json"), JSON.stringify({ iterations: 1, deadline: Date.now() + 60000 }));
  process.env.DL_EXPERIMENT = dir;
  function load() {
    let handler;
    evolution({ on(name, fn) { assert.equal(name, "tool_call"); handler = fn; } });
    return handler;
  }
  assert.equal((await load()({ toolName: "init_experiment", input: {} }, { cwd })).block, true);
  assert.equal(await load()({ toolName: "run_experiment" }, { cwd }), undefined);
  assert.equal((await load()({ toolName: "run_experiment" }, { cwd })).block, true);
});

test("independent verifier can reject a keep even with a claimed improvement", async () => {
  const dir = await mkdtemp(join(tmpdir(), "dl-keep-"));
  const cwd = join(dir, "repo");
  await mkdir(cwd);
  await writeFile(join(dir, "limits.json"), JSON.stringify({
    deadline: Date.now() + 30000, check: "/usr/bin/false", iterations: 2,
  }));
  process.env.DL_EXPERIMENT = dir;
  let handler;
  evolution({ on(name, fn) { handler = fn; } });
  const verdict = await handler({ toolName: "log_experiment", input: { status: "keep", metric: 1 } }, { cwd });
  assert.equal(verdict.block, true);
  assert.match(verdict.reason, /verifier rejected/);
});


test("a missing mandatory gate returns diagnostic context through OMP advisory continuation", async () => {
  const cwd = await mkdtemp(join(tmpdir(), "dl-stop-"));
  process.env.DL_PERF_CONTRACT = join(cwd, "missing.json");
  const handlers = {};
  try {
    performance({ on(name, fn) { handlers[name] = fn; } });
    const result = await handlers.session_stop({}, { cwd });
    assert.equal(result.continue, true);
    assert.equal(result.decision, undefined);
    assert.match(result.additionalContext, /NOT VERIFIED/);
  } finally {
    delete process.env.DL_PERF_CONTRACT;
  }
});
