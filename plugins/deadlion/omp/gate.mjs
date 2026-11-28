import { join, basename, dirname, relative } from "node:path";
import { randomUUID } from "node:crypto";
import { activeForFile } from "./lsp.mjs";
import { checkSemgrep } from "./semgrep.mjs";
import { execute } from "./process.mjs";
import { approvalHash, changes, digest, inventory, limits, read, save, scripts, snapshot } from "./evidence.mjs";
import { analyze, gateFindings, regular, scalingSummary, supported } from "./diagnostics.mjs";

const semanticSource = p => supported(p) || /\.(h|hpp|tsx|jsx|mjs|cjs)$/.test(p);

function semanticStatus(item, required) {
  return !required && ["NOT VERIFIED", "INCONCLUSIVE"].includes(item.status) ? "WARNING" : item.status;
}

async function checkSemantics(task, files, source, checks, options, probe) {
  for (const file of files.filter(semanticSource)) {
    const p = relative(task.root, file);
    let item = task.semantic?.[p];
    const required = task.policy.requireLsp || item?.status === "FAIL";
    const active = probe && !required && await activeForFile(task.cwd, file).catch(() => false);
    if (item?.sourceHash !== source && (required || active) && probe) {
      try {
        const timeout = AbortSignal.timeout(Math.max(1, Math.min(5000, options().timeout)));
        const { signal } = options();
        item = await probe(task.cwd, file, signal ? AbortSignal.any([signal, timeout]) : timeout);
        item.sourceHash = source;
      } catch (error) {
        item = { status: "NOT VERIFIED", sourceHash: source, reason: error.message };
      }
    }
    if (item?.sourceHash === source) checks.push({ name: "lsp " + p, ...item,
      status: semanticStatus(item, required) });
    else if (required) checks.push({ name: "lsp " + p, status: "NOT VERIFIED" });
  }
}

async function checkScope(task, baseline, current, paths, files, options, checks, run) {
  if (task.experiment) {
    const agrees = Object.entries(task.experiment.files).every(([p, sha]) => current.files[p]?.[1]?.[1] === sha);
    checks.push({ name: "accepted Evolution candidate", status: agrees ? "PASS" : "NOT VERIFIED",
      commit: task.experiment.commit });
  }
  const protectedPaths = task.policy.protectedPaths ?? [];
  if (paths.some(p => protectedPaths.some(name => p === name || p.startsWith(name + "/"))))
    checks.push({ name: "approved verification inputs changed", status: "BLOCKED" });
  if (paths.some(p => basename(p) === ".budget" || /^\.performance\/.*\/contract\.json$/.test(p) && baseline.files[p]))
    checks.push({ name: "approved policy changed", status: "BLOCKED" });
  // A test of the working tree cannot certify different bytes staged for commit.
  if (current.git && paths.some(p => JSON.stringify(current.files[p]?.[0]) !== JSON.stringify(baseline.files[p]?.[0]))) {
    const mismatch = await execute(["git", "diff", "--quiet", "--", ...paths], options());
    if (mismatch.code !== 0) checks.push({ name: "index differs from tested files", status: "NOT VERIFIED" });
  }
  await checkSize(task, files, checks, run);
  const budgets = Object.keys(current.files).filter(p => basename(p) === ".budget");
  for (const path of budgets) {
    const scope = dirname(path);
    if (paths.some(p => scope === "." || p.startsWith(scope + "/")))
      await run("dl-budget", [join(limits, "dl-budget"), scope], false);
  }
}

async function checkSize(task, files, checks, run) {
  const exceptions = task.policy.sizeExceptions ?? {};
  const ordinary = files.filter(p => !Object.hasOwn(exceptions, relative(task.root, p)));
  if (ordinary.length) await run("dl-size", [join(limits, "dl-size"), ...ordinary], false);
  for (const file of files.filter(p => Object.hasOwn(exceptions, relative(task.root, p)))) {
    const status = await run("dl-size " + relative(task.root, file), [join(limits, "dl-size"), file], false);
    const check = checks.at(-1);
    check.exception = exceptions[relative(task.root, file)];
    if (status === "FAIL") check.status = "WARNING";
  }
}

async function nativeReview(task, sources, options) {
  const native = task.policy.native === true;
  const deep = task.policy.requiredAnalyzers?.includes("ast-grep") ?? false;
  if (native && task.policy.projectVenv) {
    const venv = join(task.root, task.policy.projectVenv, "bin");
    options.env = { ...process.env, PATH: venv + ":" + process.env.PATH };
  }
  const java = sources.filter(p => p.endsWith(".java"));
  if (!native || !task.policy.requiredAnalyzers?.includes("infer") || !java.length)
    return analyze(sources, options, native, false, deep);
  const report = await analyze(java, options, true, true);
  report.native_tools.infer = "selected";
  const others = sources.filter(p => !p.endsWith(".java"));
  if (others.length) {
    const more = await analyze(others, options, true, false, deep);
    report.diagnostics.push(...more.diagnostics);
    report.checked_tools.push(...more.checked_tools);
    Object.assign(report.native_tools, more.native_tools);
    report.files += more.files;
  }
  return report;
}

async function checkAnalyzers(task, sources, options, checks) {
  if (sources.length) {
    try {
      const data = await nativeReview(task, sources, options());
      const missing = (task.policy.requiredAnalyzers || []).filter(name => name !== "semgrep" && !data.checked_tools.includes(name) &&
        data.native_tools?.[name === "clippy" ? "cargo" : name] !== "selected");
      checks.push({ name: "dl-analyze", status: missing.length ? "NOT VERIFIED" :
        data.diagnostics.length ? "WARNING" : "PASS", missing, data });
    } catch (error) {
      checks.push({ name: "dl-analyze", status: "NOT VERIFIED", reason: error.message });
    }
  }
}

async function checkContracts(task, paths, run) {
  let performance = "NOT APPLICABLE";
  if (task.contract) {
    if (!task.approved) throw new Error(task.contractIssue || "approved contract unavailable");
    const path = task.approved;
    performance = await run("performance contract", [join(scripts, "dl-perf-gate"), path, "--isolated",
      "--candidate-dir", task.candidate], true);
  } else if (task.base && paths.length) {
    performance = await run("approved contracts", [join(scripts, "dl-perf-gate"), "--changed"], true,
      { ...process.env, DL_PERF_BASE: task.base, DL_PERF_PROJECT_SCOPE: paths.some(p => !/\.(md|rst)$/i.test(p)) ? "1" : "0" });
  }
  return performance;
}

export async function verify(task, signal, budget = 20000, probe) {
  const started = Date.now();
  const until = Math.min(task.deadline, started + task.analysisMs, started + budget);
  const options = () => ({ cwd: task.root, signal, timeout: until - Date.now() });
  const checks = [];
  let source;
  let paths = [];
  const run = (...args) => record(checks, options, ...args);
  try {
    const { baseline, current } = await verifiedInputs(task, options());
    source = digest(JSON.stringify(current));
    paths = changes(baseline, current);
    const files = await regular(task.root, paths);
    const sources = files.filter(supported);
    const code = paths.some(p => !/\.(md|rst|txt|png|jpg|svg|ico)$/i.test(p));
    await checkScope(task, baseline, current, paths, files, options, checks, run);
    await checkSemantics(task, files, source, checks, options, probe);
    await checkAnalyzers(task, sources, options, checks);
    if (sources.length && (task.policy.semgrepConfig || task.policy.requiredAnalyzers?.includes("semgrep")))
      checks.push(await checkSemgrep(task, sources, source, options()));
    await checkRequirements(task, paths, code, checks, run);
    if (source !== digest(JSON.stringify(await snapshot(task.cwd, options()))))
      checks.push({ name: "workspace changed during verification", status: "NOT VERIFIED" });
  } catch (error) {
    checks.push({ name: "verification", status: signal?.aborted ? "CANCELLED" : "NOT VERIFIED", reason: error.message });
  }
  task.analysisMs = Math.max(0, task.analysisMs - (Date.now() - started));
  if (signal?.aborted || Date.now() >= task.deadline)
    checks.push({ name: "verification interrupted", status: signal?.aborted ? "CANCELLED" : "BLOCKED" });
  return receiptFor(task, checks, paths, source, started);
}

async function checkRequirements(task, paths, code, checks, run) {
  if (task.policy.profile) {
    const spec = task.policy.profile;
    const argv = [join(scripts, "dl-profile"), ...Object.entries(spec.max ?? {}).flatMap(([k,v]) => ["--max", k + "=" + v]),
      spec.metric, "--", ...spec.argv];
    await run("trusted profile", argv, true);
  }
  if (task.policy.tests) await run("functional tests", task.policy.tests, false);
  for (const step of task.policy.checks ?? []) await run("plan: " + step.name, step.argv, false);
  const performance = await checkContracts(task, paths, run);
  if (task.designIssue) checks.push({ name: "design", status: "BLOCKED", reason: task.designIssue });
  if ((code && !task.policy.tests || task.mode !== "Standard") && performance === "NOT APPLICABLE")
    checks.push({ name: task.mode === "Standard" ? "functional verification" : "approved experimental contract",
      status: "NOT VERIFIED" });
}

async function record(checks, options, name, argv, json, env = process.env) {
  const result = await execute(argv, { ...options(), env });
  let status = result.code === 0 ? "PASS" : result.code === 1 ? "FAIL" : "NOT VERIFIED";
  const data = json ? JSON.parse(result.stdout) : result;
  if (json) status = ({ VERIFIED: "PASS", MEASURED: "PASS", ERROR: "FAIL", "PERFORMANCE REGRESSION": "FAIL" })[data.status] ?? data.status;
  if (!["PASS","FAIL","WARNING","INCONCLUSIVE","NOT APPLICABLE","NOT VERIFIED","BLOCKED","CANCELLED"].includes(status) ||
      result.code && ["PASS","WARNING","NOT APPLICABLE"].includes(status)) status = "NOT VERIFIED";
  checks.push({ name, status, data, reason: result.code ? String(data.reason || result.stderr || data.status || result.stdout).slice(-400) : undefined });
  return status;
}

async function verifiedInputs(task, options) {
  if (task.tools.omp !== "omp/19.2.1") throw new Error("OMP version outside verified compatibility");
  if (JSON.stringify(await inventory(task.root, task.policy)) !== JSON.stringify(task.tools)) throw new Error("verification inputs, analyzer installation or Core changed");
  const baseline = await read(join(task.directory, "baseline.json"));
  if (task.baselineHash !== digest(JSON.stringify(baseline))) throw new Error("baseline receipt changed");
  if (task.approved && task.approvalHash !== await approvalHash(task)) throw new Error("approved fixtures changed");
  const current = await snapshot(task.cwd, options);
  if (baseline.root !== current.root || baseline.git !== current.git) throw new Error("workspace identity changed");
  if (current.git && !task.base && Object.keys(current.files).some(p => p.startsWith(".performance/")))
    throw new Error("approved revision required for project contracts");
  return { baseline, current };
}

async function receiptFor(task, checks, paths, source, started) {
  const failures = checks.filter(c => !["PASS", "WARNING", "NOT APPLICABLE"].includes(c.status));
  const status = failures[0]?.status ?? "PASS";
  const receipt = join(task.directory, "gate-" + randomUUID() + ".json");
  const evidence = { task: task.id, baseline: task.base, policy: task.policy, toolIdentity: digest(JSON.stringify(task.tools)), source, paths, checks, status, diagnostics: gateFindings(checks, task.root),
    elapsedMs: Date.now() - started };
  await save(receipt, evidence);
  const scaling = checks.flatMap(c => (c.data?.contracts ?? [c.data]).map(scalingSummary).filter(Boolean)).slice(0, 2);
  return { receipt, receiptHash: digest(JSON.stringify(evidence)), status, paths, source, scaling, failures: failures.map(c => ({ name:c.name, status:c.status, reason:String(c.reason ?? c.output ?? c.data?.reason ?? "").slice(0, 360) })) };
}
