import { join, resolve } from "node:path";
import { read, scripts } from "./evidence.mjs";
import { execute } from "./process.mjs";
import { editPaths } from "./diagnostics.mjs";
import { permitsInspection } from "./lsp.mjs";

export async function design(task) {
  if (task.mode === "Standard" && !task.contract) return;
  if (task.contractIssue) return task.contractIssue;
  const baseline = await read(join(task.directory, "baseline.json"));
  const contracts = Object.keys(baseline.files).filter(p => /^\.performance\/.*\/contract\.json$/.test(p));
  const path = task.approved ?? (contracts.length === 1 && resolve(task.root, contracts[0]));
  if (!path) return "Provide an approved performance contract with alternatives, verification workload and baseline.";
  const result = await execute([join(scripts, "dl-contract"), path], { cwd: task.cwd, timeout: 4000 });
  if (result.code) return "dl-contract: " + result.stdout.slice(0, 350);
  const contract = await read(path);
  if (!contract.benchmark?.baseline) return "The approved contract needs an executable baseline.";
  if (task.mode === "Research" && (!contract.scaling || !contract.computational_model))
    return "Research requires a computational model and scaling workload.";
  if (!task.baselineReceipt) return "Run deadlion_verify before implementation to measure the approved baseline.";
  if (task.mode === "Evolution" && !task.experiment) return "Use dl-evolve with a bounded experiment and independent evaluator.";
}

export async function permitsDesignTool(event, ctx) {
  if (["read", "grep", "find", "ls", "deadlion_verify"].includes(event.toolName)) return true;
  if (event.toolName === "lsp") return permitsInspection(ctx.cwd, event.input).catch(() => false);
  const paths = editPaths(event);
  return ["edit", "write"].includes(event.toolName) && paths.length > 0 && paths.every(p => p.endsWith(".md"));
}
