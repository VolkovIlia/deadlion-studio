import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execute } from "./process.mjs";
import { analyze, regular, supported } from "./diagnostics.mjs";
import { approvalHash, changes, inventory, persist, read, save, snapshot } from "./evidence.mjs";
import { servers } from "./lsp.mjs";

async function approvedWorkloads(task) {
  const { train, holdout } = task.workloads;
  for (const workload of [train, holdout])
    if (await approvalHash(workload) !== workload.hash) throw new Error("Approved experiment inputs changed");
  return [train.path, holdout.path];
}

async function evolve(task) {
  const spec = task.policy.evolution;
  if (task.mode !== "Evolution" || !spec?.goal || !Number.isSafeInteger(spec.iterations) ||
      !Number.isSafeInteger(spec.seconds) || !spec.train || !spec.holdout || !spec.files?.length)
    throw new Error("Evolution requires approved train, holdout, files, iterations and seconds.");
  const revision = await execute(["git", "rev-parse", "--verify", "HEAD"], { cwd: task.root });
  if (revision.code || revision.stdout.trim() !== task.base) throw new Error("Experiment requires the approved base checkout.");
  const seconds = Math.min(spec.seconds, Math.floor((task.deadline - Date.now()) / 1000));
  const directory = join(task.directory, "experiment");
  const tool = fileURLToPath(new URL("dl-evolve", import.meta.url));
  const [train, holdout] = await approvedWorkloads(task);
  const result = await execute([tool, directory, "--goal", spec.goal, "--contract", train,
    "--holdout-contract", holdout, "--iterations", String(spec.iterations), "--seconds", String(seconds),
    "--tokens", String(task.tokenLimit ?? 0), ...spec.files.flatMap(file => ["--candidate-file", file])], { cwd: task.root, timeout: seconds * 1000 });
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

export function commands(pi, taskFor, fullCheck) {
  pi.registerCommand?.("deadlion", {
    description: "Engineering status, doctor, mode, analyze, verify, scale, evolve or report",
    handler: async (args, ctx) => {
      const command = args.trim() || "status";
      let data;
      try {
        if (command === "doctor") {
          data = await doctor(ctx.cwd, pi.getActiveTools().includes("lsp"), await taskFor(ctx, "", false, true));
        } else {
          const task = await taskFor(ctx, "", false, true);
          if (!task) { ctx.ui.notify("Deadlion active. No engineering task started.", "info"); return; }
          if (command === "verify" || command === "scale") {
            if (command === "scale" && (!task.approved || !(await read(task.approved)).scaling))
              throw new Error("Select an approved scaling contract with DL_PERF_CONTRACT");
            data = await fullCheck(task);
          } else if (command === "analyze") {
            const paths = changes(await read(join(task.directory, "baseline.json")), await snapshot(ctx.cwd));
            const files = await regular(task.root, paths.filter(supported));
            const report = resolve(task.directory, "analysis.json");
            const result = files.length ? await analyze(files, { cwd: task.cwd, timeout: Math.min(task.analysisMs, task.deadline - Date.now()) },
              task.policy.native === true) : { status: "NOT APPLICABLE", diagnostics: [] };
            await save(report, result);
            data = { status: result.status, diagnostics: result.diagnostics.length, report };
          } else if (command === "evolve") data = await evolve(task);
          else if (["status", "report", "mode"].includes(command))
            data = { mode: task.mode, state: task.state, report: task.last?.receipt, directory: task.directory,
              corrections: task.corrections, usage: task.usage, design: task.designIssue };
          else throw new Error("Use status, doctor, mode, analyze, verify, scale, evolve or report.");
        }
        ctx.ui.notify(JSON.stringify(data), "info");
      } catch (error) { ctx.ui.notify("Deadlion NOT VERIFIED: " + error.message, "error"); }
    },
  });
}

async function doctor(cwd, available, task) {
  const info = await inventory(cwd);
  const checks = task?.last?.receipt ? (await read(task.last.receipt)).checks : [];
  return { integration: "ACTIVE", omp: info.omp, testedVersion: "omp/19.2.1",
    compatible: info.omp === "omp/19.2.1", core: info.core, tools: info.tools,
    lsp: available ? await servers(cwd) : "inactive",
    gate: task?.last?.status ?? "NOT VERIFIED", receipt: task?.last?.receipt,
    checked: checks.map(check => ({ name: check.name, status: check.status })) };
}
