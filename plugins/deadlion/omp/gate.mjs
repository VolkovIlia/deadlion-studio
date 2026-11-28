import { join, basename, dirname, relative, resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import { activeForFile } from "./lsp.mjs";
import { checkSemgrep } from "./semgrep.mjs";
import { execute } from "./process.mjs";
import { approvalHash, changes, digest, integrationFingerprint, inventory, limits, read, samePython, save, scripts, snapshot, stateHome } from "./evidence.mjs";
import { projectPolicy } from "./setup.mjs";
import { analyze, gateFindings, regular, scalingSummary, supported } from "./diagnostics.mjs";
import { changedArea, contains, contractCoverage, coverageFor, documentation } from "./coverage.mjs";
import { testResult } from "./test-result.mjs";
import { compatibility } from "./omp-compat.mjs";
import { verifyMilestone } from "./refactor.mjs";
import { chargeAnalysis, operationTimeout, timeLeft } from "./execution.mjs";
import { importEvidence } from "./import-evidence.mjs";
import { borrowedFunctionalChecks, publishFunctionalReceipt } from "./functional-receipts.mjs";

const semanticSource = p => supported(p) || /\.(h|hpp|tsx|jsx|mjs|cjs)$/.test(p);
export const testInput = /(?:^|\/)(?:conftest\.py|pytest\.ini|tests?\/.+|test_[^/]+\.py|[^/]+_test\.go|[^/]+\.(?:spec|test)\.[^/]+)$/i;
const runningIntegration = integrationFingerprint().catch(() => null);

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
      status: semanticStatus(item, required), coverage: { type: "semantic", paths: [p] } });
    else if (required) checks.push({ name: "lsp " + p, status: "NOT VERIFIED" });
  }
}

async function checkScope(task, baseline, current, paths, files, options, checks, run) {
  if (task.experiment) {
    const agrees = Object.entries(task.experiment.files).every(([p, sha]) => current.files[p]?.[1]?.[1] === sha);
    checks.push({ name: "accepted Evolution candidate", status: agrees ? "PASS" : "NOT VERIFIED",
      commit: task.experiment.commit });
  }
  checkProtectedInputs(task, baseline, current, paths, checks);
  // A test of the working tree cannot certify different bytes staged for commit.
  if (current.git && paths.length) await checkIndex(baseline, current, paths, checks, options);
  if (task.refactor || task.refactorFinal) return;
  await checkSize(task, files, checks, run);
  const budgets = Object.keys(current.files).filter(p => basename(p) === ".budget");
  for (const path of budgets) {
    const scope = dirname(path);
    if (paths.some(p => scope === "." || p.startsWith(scope + "/")))
      await run("dl-budget", [join(limits, "dl-budget"), scope], false);
  }
}

async function checkIndex(baseline, current, paths, checks, options) {
  const staged = await execute(["git", "diff", "--cached", "--name-only", "-z"], options());
  if (staged.code) throw new Error("Could not inspect staged paths");
  const index = new Set(staged.stdout.split("\0"));
  const changed = paths.filter(path => index.has(path) ||
    JSON.stringify(current.files[path]?.[0]) !== JSON.stringify(baseline.files[path]?.[0]));
  if (!changed.length) return;
  const worktree = await execute(["git", "diff", "--name-only", "-z"], options());
  if (worktree.code) throw new Error("Could not inspect worktree and index agreement");
  const dirty = new Set(worktree.stdout.split("\0"));
  const mismatch = changed.filter(path => dirty.has(path));
  if (mismatch.length) checks.push({ name: "index differs from tested files", status: "NOT VERIFIED", reason: mismatch.slice(0, 5).join(", ") });
}

function checkProtectedInputs(task, baseline, current, paths, checks) {
  const protectedPaths = [...task.policy.protectedPaths ?? [], ...task.policy.verificationInputs ?? []];
  const modifiedInputs = paths.filter(p => protectedPaths.some(name => contains(name, p)));
  if (modifiedInputs.length)
    checks.push({ name: "approved verification inputs changed", status: "BLOCKED",
      reason: modifiedInputs.join(", "), coverage: { type: "verification-input", paths: modifiedInputs } });
  else if (protectedPaths.length)
    checks.push({ name: "protected verification inputs", status: "PASS",
      coverage: { type: "verification-input", paths: protectedPaths } });
  const changedTests = paths.filter(p => testInput.test(p) && (baseline.files[p] || /(?:conftest\.py|pytest\.ini)$/.test(p)) &&
    (!task.approvedTestRevisions?.[p] || JSON.stringify(task.approvedTestRevisions[p]) !== JSON.stringify(current.files[p]?.[1])));
  if ((task.policy.tests || task.policy.checks?.some(c => c.type === "functional")) &&
      changedTests.length && paths.some(p => !documentation(p) && !testInput.test(p)))
    checks.push({ name: "existing tests changed with production code", status: "NOT VERIFIED",
      reason: "Use a frozen independent oracle for production changes. Changed tests: " + changedTests.slice(0, 5).join(", ") });
  if (paths.some(p => basename(p) === ".budget" || /^\.performance\/.*\/contract\.json$/.test(p) && baseline.files[p]))
    checks.push({ name: "approved policy changed", status: "BLOCKED" });
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
        data.diagnostics.length || data.unavailable_tools?.length ? "WARNING" : "PASS", missing, data,
        coverage: { type: "static", paths: sources.map(path => relative(task.root, path)) },
        reason: missing.length ? "Required analyzer not installed or unsuccessful: " + missing.join(", ") : undefined });
    } catch (error) {
      checks.push({ name: "dl-analyze", status: "NOT VERIFIED", reason: error.message });
    }
  }
}

async function checkContracts(task, paths, checks, run) {
  let performance = "NOT APPLICABLE";
  if (task.contract) {
    if (!task.approved) throw new Error(task.contractIssue || "approved contract unavailable");
    const path = task.approved;
    performance = await run("performance contract", [join(scripts, "dl-perf-gate"), path, "--isolated",
      "--candidate-dir", task.candidate], true);
    const contract = await read(path);
    const coverage = contractCoverage(contract.benchmark, task.candidate, task.root, contract.workload);
    checks.at(-1).coverage = coverage;
    if (performance === "PASS" && checks.at(-1).data.status === "VERIFIED")
      checks.push({ name: "approved workload oracle", status: "PASS", coverage: { ...coverage, type: "oracle",
        invariants: [contract.benchmark.oracle?.kind ?? "exact"] } });
  } else if (projectContracts(task, paths)) {
    performance = await run("approved contracts", [join(scripts, "dl-perf-gate"), "--changed"], true,
      { ...process.env, DL_PERF_BASE: task.base, DL_PERF_PROJECT_SCOPE: task.baselineCapture || paths.some(p => !documentation(p)) ? "1" : "0" });
    for (const report of checks.at(-1).data.contracts ?? []) {
      if (report.status !== "VERIFIED" || !report.scope) continue;
      const { contract, candidate_root, workload } = report.scope;
      const coverage = contractCoverage(report.scope, resolve(task.root, candidate_root), task.root, workload);
      checks.push({ name: "approved workload oracle " + contract, status: "PASS", coverage: { ...coverage, type: "oracle" } });
    }
  }
  return performance;
}

function projectContracts(task, paths) {
  return task.base && (paths.length || task.baselineCapture);
}

export async function verify(task, signal, budget = 20000, probe) {
  const started = Date.now();
  const until = started + Math.min(timeLeft(task, started), budget);
  const options = () => ({ cwd: task.root, signal, timeout: Math.min(operationTimeout(task), until - Date.now()) });
  const checks = [];
  let source;
  let workspaceHash;
  let paths = [];
  let area = [];
  let tools;
  const run = (...args) => record(checks, options, ...args);
  try {
    const initial = await verifiedInputs(task, options());
    const { baseline, current } = initial;
    tools = initial.tools;
    source = digest(JSON.stringify(current));
    workspaceHash = current.fingerprint;
    paths = source === task.baselineHash ? [] : changes(baseline, current);
    area = paths.length ? changedArea(paths, { ...baseline.files, ...current.files }) : [];
    observeRoute(task, paths, area);
    const readOnly = !paths.length && task.route?.readOnly && !task.refactor;
    if (!readOnly) {
      await reviewChanges(task, { baseline, current, paths, area, source, checks, options, probe, run });
      if (!checks.some(check => check.status === "BLOCKED")) {
        if (source !== digest(JSON.stringify(await snapshot(task.cwd, options()))))
          checks.push({ name: "workspace changed during verification", status: "NOT VERIFIED" });
        await verifyToolInputs(task, options());
      }
    }
  } catch (error) {
    checks.push({ name: "verification", status: signal?.aborted ? "CANCELLED" : "NOT VERIFIED", reason: error.message,
      restartRequired: error.restartRequired });
  }
  chargeAnalysis(task, started);
  if (signal?.aborted || Date.now() >= until)
    checks.push({ name: "verification interrupted", status: signal?.aborted ? "CANCELLED" : "BLOCKED",
      reason: signal?.aborted ? "Cancelled" : "Verification time slice elapsed" });
  return receiptFor(task, checks, area, source, workspaceHash, started, tools);
}

function observeRoute(task, paths, area) {
  const changed = area.filter(row => !documentation(row.path));
  if (task.mode === "Standard" && changed.some(row => task.policy.performancePaths?.some(p => contains(p, row.path)))) {
    task.mode = "Performance";
    if (task.route) task.route.mode = task.mode;
  }
  const components = new Set(changed.map(row => row.component));
  if (task.route) {
    task.route.scope = !paths.length ? "read-only" : paths.length === 1 ? "one file" :
      task.route.scope === "project" ? "project" : components.size > 1 ? "multiple components" : "multiple files";
    if (components.size > 1 || changed.some(row => row.interface)) task.route.risk = "high";
    else if (changed.length && task.route.risk === "low") task.route.risk = "medium";
  }
}

async function reviewChanges(task, { baseline, current, paths, area, source, checks, options, probe, run }) {
  const files = await regular(task.root, paths);
  const sources = files.filter(supported);
  await checkScope(task, baseline, current, paths, files, options, checks, run);
  if (checks.some(check => check.status === "BLOCKED")) return;
  await checkSemantics(task, files, source, checks, options, probe);
  await checkAnalyzers(task, sources, options, checks);
  if (sources.length && (task.policy.semgrepConfig || task.policy.requiredAnalyzers?.includes("semgrep"))) {
    const check = await checkSemgrep(task, sources, source, options());
    checks.push({ ...check, coverage: { type: "static", paths: check.data?.paths?.scanned ?? [] } });
  }
  if (task.route?.intent === "documentation" && task.base && paths.length <= 12) {
    for (const path of paths.filter(p => p.endsWith(".py"))) {
      const before = baseline.files[path]?.[1];
      const after = current.files[path]?.[1];
      if (typeof before?.[0] === "number" && before[0] === after?.[0] &&
          await samePython(task, path, before[1], options()))
        checks.push({ name: "unchanged Python syntax " + path, status: "PASS",
          coverage: { type: "functional", exact: true, paths: [path], invariants: ["identical Python AST and shebang"] } });
    }
  }
  const imports = importEvidence(task, area, source);
  if (imports) checks.push(imports);
  await checkRequirements(task, area, { source, workspaceHash: current.fingerprint, checks, run, options });
  await verifyMilestone(task, paths, checks, options(), { baseline, current });
}

async function checkRequirements(task, area, { source, workspaceHash, checks, run, options }) {
  const paths = area.map(row => row.path);
  const code = paths.filter(p => !documentation(p));
  if (!code.length && (task.route?.readOnly || task.route?.intent === "documentation")) return;
  await approvedCommands(task, checks, run, area);
  const performance = await checkContracts(task, paths, checks, run);
  if (task.designIssue) checks.push({ name: "design", status: "BLOCKED", reason: task.designIssue });
  let gap = functionalGap(area, checks);
  if (gap) {
    const scope = { source, workspaceHash, testOnly: code.every(path => testInput.test(path)) };
    checks.push(...await borrowedFunctionalChecks(task, gap.missing, scope, options, verifyToolInputs));
    gap = functionalGap(area, checks);
  }
  if (gap) checks.push(gap);
  if (task.mode !== "Standard" && performance === "NOT APPLICABLE")
    checks.push({ name: "approved experimental contract", status: "NOT VERIFIED" });
}

function functionalGap(area, checks) {
  const missing = coverageFor(area, checks).filter(row => row.status === "NOT VERIFIED");
  if (!missing.length) return;
  return { name: "functional verification", status: "NOT VERIFIED", missing,
    reason: "Establish scoped functional evidence for " +
      missing.slice(0, 5).map(row => row.interface ? row.path + " [" + row.affectedComponents.join(", ") + "]" : row.path).join(", ") };
}

async function approvedCommands(task, checks, run, area) {
  if (task.policy.profile) {
    const spec = task.policy.profile;
    const argv = [join(scripts, "dl-profile"), ...Object.entries(spec.max ?? {}).flatMap(([k,v]) => ["--max", k + "=" + v]),
      spec.metric, "--", ...spec.argv];
    await run("trusted profile", argv, true);
    checks.at(-1).coverage = { type: "resource", workloads: [spec.argv] };
  }
  if (task.policy.tests) {
    await run("functional tests", task.policy.tests, false);
    bindTestEvidence(checks.at(-1), task.policy.tests, task.policy.testsScope ?? []);
  }
  for (const step of task.policy.checks ?? []) {
    if (!neededInMilestone(task, step, area)) continue;
    const cwd = resolve(task.root, step.cwd ?? ".");
    if (await realpath(cwd) !== cwd) throw new Error("Approved test directory changed");
    await run("plan: " + step.name, step.argv, false, process.env, cwd);
    const result = checks.at(-1);
    if (step.type === "functional") bindTestEvidence(result, step.argv, step.scope ?? [], step.requireTestCount);
    else result.coverage = { type: step.type ?? "policy", paths: step.scope ?? [], argv: step.argv };
  }
}

function neededInMilestone(task, check, area) {
  const stage = task.refactor?.step;
  if (!stage || !check.scope || stage.checks.includes("plan: " + check.name)) return true;
  const targets = [...stage.scope, ...area.flatMap(row => row.interface ? row.affectedComponents : [row.path])];
  return check.scope.some(scope => targets.some(path => contains(scope, path) || contains(path, scope)));
}

function bindTestEvidence(check, argv, paths, requireCount) {
  const stats = testResult(argv, check.data.stdout + "\n" + check.data.stderr, requireCount);
  check.coverage = { type: "functional", paths, argv, execution: stats };
  if (check.status === "PASS" && (stats.incomplete || stats.passed === 0)) {
    check.status = "NOT VERIFIED";
    check.reason = "No complete nonempty test run was observed";
  }
}

async function record(checks, options, name, argv, json, env = process.env, cwd) {
  const execution = options();
  let result;
  try { result = await execute(argv, { ...execution, env, cwd: cwd ?? execution.cwd }); }
  catch (error) {
    if (execution.signal?.aborted) throw error;
    checks.push({ name, status: "NOT VERIFIED", data: { stdout: "", stderr: "" }, reason: error.message });
    return "NOT VERIFIED";
  }
  const check = commandEvidence(name, result, json);
  checks.push(check);
  return check.status;
}

function commandEvidence(name, result, json) {
  let status = result.code === 0 ? "PASS" : result.code === 1 ? "FAIL" : "NOT VERIFIED";
  const data = json ? JSON.parse(result.stdout) : result;
  if (json) status = ({ VERIFIED: "PASS", MEASURED: "PASS", ERROR: "FAIL", "PERFORMANCE REGRESSION": "FAIL" })[data.status] ?? data.status;
  if (!["PASS","FAIL","WARNING","INCONCLUSIVE","NOT APPLICABLE","NOT VERIFIED","BLOCKED","CANCELLED"].includes(status) ||
      result.code && ["PASS","WARNING","NOT APPLICABLE"].includes(status)) status = "NOT VERIFIED";
  return { name, status, data, reason: result.code ? String(data.reason || result.stderr || data.status || result.stdout).slice(-400) : undefined };
}

export async function verifyToolInputs(task, options) {
  const tools = await inventory(task.root, task.policy, options);
  if (JSON.stringify({ ...tools, integration: task.tools.integration }) !== JSON.stringify(task.tools))
    throw new Error("verification inputs, analyzer installation or Core changed");
  if (task.approved && task.approvalHash !== await approvalHash(task, options)) throw new Error("approved fixtures changed");
  if (task.policyFile && task.policyHash !== digest(await readFile(task.policyFile)))
    throw new Error("operator policy changed");
  if (!task.policyFile && (task.policy.testsScope || task.policy.setupApproval &&
      task.policy.setupApproval !== (await projectPolicy(task.root, stateHome(), options)).setupApproval))
    throw new Error("Project setup or approved test scope changed. Review /deadlion setup and start a new task.");
  if (task.policy.semgrepConfig && task.semgrepConfigHash !== digest(await readFile(task.policy.semgrepConfig)))
    throw new Error("Semgrep configuration changed");
  if (tools.integration !== await runningIntegration) {
    const error = new Error("Deadlion verifier changed on disk. Continue engineering work and restart OMP in the same session for fresh verification.");
    error.restartRequired = true;
    throw error;
  }
  return tools;
}

async function verifiedInputs(task, options) {
  if (task.enforcement === false || compatibility(task.tools.omp).lifecycle !== "VERIFIED")
    throw new Error("Mandatory OMP lifecycle enforcement is NOT VERIFIED for " + task.tools.omp);
  const tools = await verifyToolInputs(task, options);
  const baseline = await read(join(task.directory, "baseline.json"));
  if (task.baselineHash !== digest(JSON.stringify(baseline))) throw new Error("baseline receipt changed");
  const current = await snapshot(task.cwd, options);
  if (baseline.root !== current.root || baseline.git !== current.git) throw new Error("workspace identity changed");
  if (current.git && !task.base && Object.keys(current.files).some(p => p.startsWith(".performance/")))
    throw new Error("approved revision required for project contracts");
  return { baseline, current, tools };
}

async function receiptFor(task, checks, area, source, workspaceHash, started, tools) {
  const failures = checks.filter(c => !["PASS", "WARNING", "NOT APPLICABLE"].includes(c.status));
  const status = failures[0]?.status ?? "PASS";
  const receipt = join(task.directory, "gate-" + randomUUID() + ".json");
  const paths = area.map(row => row.path);
  const evidence = { version: 2, task: task.id, baseline: task.base, baselineHash: task.baselineHash,
    route: task.route, policy: task.policy, toolIdentity: tools && digest(JSON.stringify(tools)), source, workspaceHash, paths, checks, status,
    integration: { baseline: task.tools.integration, verified: tools?.integration },
    coverage: coverageFor(area, checks), diagnostics: gateFindings(checks, task.root),
    elapsedMs: Date.now() - started };
  const receiptHash = digest(JSON.stringify(evidence));
  await save(receipt, evidence);
  await publishFunctionalReceipt(task, evidence, receipt, receiptHash);
  const scaling = checks.flatMap(c => (c.data?.contracts ?? [c.data]).map(scalingSummary).filter(Boolean)).slice(0, 2);
  return { receipt, receiptHash, status, paths, source, scaling,
    confirmed: checks.filter(c => c.status === "PASS").map(c => c.name), deficits: checkDeficits(failures),
    receiptNotes: checks.filter(c => c.name === "functional receipt unavailable").map(c => c.reason),
    failures: failures.map(c => ({ name:c.name, status:c.status, missing:c.missing?.slice(0, 8), restartRequired:c.restartRequired,
      reason:String(c.reason ?? c.output ?? c.data?.reason ?? "").slice(0, 360) })) };
}

function checkDeficits(failures) {
  const deficits = {};
  for (const { name, data } of failures) {
    for (const item of data?.violations ?? []) {
      if (Number.isFinite(item.value) && Number.isFinite(item.limit))
        deficits[name + " " + item.name] = item.value - Math.max(item.limit, item.baseline ?? 0);
    }
    for (const [metric, budget] of Object.entries(data?.budgets ?? {})) {
      const observed = data.metrics?.[metric];
      if (Number.isFinite(observed) && observed > budget) deficits[name + " " + metric] = observed - budget;
    }
  }
  return deficits;
}
