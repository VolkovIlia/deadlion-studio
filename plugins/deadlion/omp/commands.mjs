import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execute } from "./process.mjs";
import { analyze, regular, supported } from "./diagnostics.mjs";
import { approvalHash, changes, inventory, persist, read, save, snapshot, stateHome } from "./evidence.mjs";
import { servers } from "./lsp.mjs";
import { compatibility } from "./omp-compat.mjs";
import { setup } from "./setup.mjs";
import { budgetStatus, exhausted, limit, operationTimeout, timeLeft, tokensUsed } from "./execution.mjs";
import { approveTaskTests } from "./test-approval.mjs";

async function approvedWorkloads(task) {
  const { train, holdout } = task.workloads;
  for (const workload of [train, holdout])
    if (await approvalHash(workload) !== workload.hash) throw new Error("Approved experiment inputs changed");
  return [train.path, holdout.path];
}

function evolutionBudget(task) {
  const spec = task.policy.evolution;
  if (exhausted(task)) throw new Error(exhausted(task));
  if (task.mode !== "Evolution" || !spec?.goal || !Number.isSafeInteger(spec.iterations) ||
      !Number.isSafeInteger(spec.seconds) || !spec.train || !spec.holdout || !spec.files?.length)
    throw new Error("Evolution requires approved train, holdout, files, iterations and seconds.");
  const seconds = Math.min(spec.seconds, Math.floor((limit(task.deadline) - Date.now()) / 1000));
  if (seconds <= 0) throw new Error("No remaining approved Evolution time");
  const tokens = task.tokenLimit == null ? 0 : task.tokenLimit - tokensUsed(task);
  return { spec, seconds, tokens };
}

async function evolve(task) {
  const { spec, seconds, tokens } = evolutionBudget(task);
  const revision = await execute(["git", "rev-parse", "--verify", "HEAD"], { cwd: task.root });
  if (revision.code || revision.stdout.trim() !== task.base) throw new Error("Experiment requires the approved base checkout.");
  const directory = join(task.directory, "experiment");
  const tool = fileURLToPath(new URL("dl-evolve", import.meta.url));
  const [train, holdout] = await approvedWorkloads(task);
  const result = await execute([tool, directory, "--goal", spec.goal, "--contract", train,
    "--holdout-contract", holdout, "--iterations", String(spec.iterations), "--seconds", String(seconds),
    "--tokens", String(tokens),
    ...spec.files.flatMap(file => ["--candidate-file", file])], { cwd: task.root, timeout: seconds * 1000 });
  await save(join(task.directory, "evolution.json"), result);
  if (result.code) throw new Error("Evolution failed. See " + join(task.directory, "evolution.json"));
  const helper = fileURLToPath(new URL("experiment-result.py", import.meta.url));
  const inspected = await execute(["python3", "-I", helper, directory], { cwd: task.root });
  if (inspected.code) throw new Error("No accepted experiment revision. See " + directory);
  task.experiment = JSON.parse(inspected.stdout);
  if (task.baselineReceipt) {
    delete task.designIssue;
    task.state = "IMPLEMENTATION";
  }
  await persist(task);
  return { workspace: directory, commit: task.experiment.commit, import: "requires independent candidate acceptance" };
}

export function commands(pi, taskFor, fullCheck, transition) {
  pi.registerCommand?.("deadlion", {
    description: "Engineering status, setup, doctor, analyze, verify, scale, evolve or report",
    handler: async (args, ctx) => {
      const command = args.trim() || "status";
      try {
        const data = await runCommand(command, ctx, { pi, taskFor, fullCheck, transition });
        ctx.ui.notify(typeof data === "string" ? data : JSON.stringify(data), "info");
      } catch (error) { ctx.ui.notify("Deadlion NOT VERIFIED: " + error.message, "error"); }
    },
  });
}

async function runCommand(command, ctx, { pi, taskFor, fullCheck, transition }) {
  if (command === "setup" || command.startsWith("setup approve "))
    return setup(ctx.cwd, stateHome(), command.slice(14), save);
  if (["new", "resume", "continue", "retry", "stop", "budget", "refactor"].includes(command) || /^(?:budget|refactor) /.test(command))
    return transition(command, ctx);
  const task = await taskFor(ctx, "", false, true);
  if (command === "doctor") return doctor(ctx.cwd, pi.getActiveTools().includes("lsp"), task);
  if (!task) return "Deadlion active. No engineering task started.";
  if (command.startsWith("approve-tests ")) return approveTaskTests(task, ctx, command.slice(14));
  return taskCommand(command, ctx, task, fullCheck);
}

async function taskCommand(command, ctx, task, fullCheck) {
  switch (command) {
    case "verify": return fullCheck(task, undefined, ctx);
    case "scale":
      if (!task.approved || !(await read(task.approved)).scaling)
        throw new Error("Select an approved scaling contract with DL_PERF_CONTRACT");
      return fullCheck(task, undefined, ctx);
    case "analyze": return analyzeChanges(task);
    case "evolve": return evolve(task);
    case "report": return task.last?.receipt ?? task.directory;
    case "mode": return `${task.mode} · ${task.route?.intent ?? task.kind}`;
    case "status": return currentStatus(task);
    default: throw new Error("Use setup, status, doctor, mode, analyze, verify, scale, evolve or report.");
  }
}

async function analyzeChanges(task) {
  const paths = changes(await read(join(task.directory, "baseline.json")), await snapshot(task.cwd));
  const files = await regular(task.root, paths.filter(supported));
  const report = resolve(task.directory, "analysis.json");
  const result = files.length ? await analyze(files, { cwd: task.cwd, timeout: Math.min(operationTimeout(task), timeLeft(task)) },
    task.policy.native === true) : { status: "NOT APPLICABLE", diagnostics: [] };
  await save(report, result);
  return { status: result.status, diagnostics: result.diagnostics.length, report };
}

function currentStatus(task) {
  const latest = task.recovery?.recent.at(-1);
  return [
    `Mission ${task.refactor?.campaign ?? task.missionId ?? task.id} · ${task.state} · ${task.mode}`,
    task.goal && `Goal ${task.goal.slice(0, 240)}`,
    task.refactor && `Milestone ${task.refactor.id} · ${task.refactor.step.title}`,
    `Verification ${task.last?.status ?? "pending"} · ${budgetStatus(task)}`,
    latest && `Recovery ${latest.cause} · ${latest.strategy}`,
    task.designIssue ?? task.policy.setupIssue ?? task.last?.failures?.[0]?.reason,
    task.last?.receipt,
  ].filter(Boolean).join("\n");
}

async function doctor(cwd, available, task) {
  const info = await inventory(cwd);
  const checks = task?.last?.receipt ? (await read(task.last.receipt)).checks : [];
  return { integration: "ACTIVE", omp: info.omp, capabilities: compatibility(info.omp), core: info.core, tools: info.tools,
    lsp: available ? await servers(cwd).catch(() => "NOT VERIFIED") : "inactive",
    gate: task?.last?.status ?? "NOT VERIFIED", receipt: task?.last?.receipt,
    checked: checks.map(check => ({ name: check.name, status: check.status })) };
}
