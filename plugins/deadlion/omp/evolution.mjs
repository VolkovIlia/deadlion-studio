import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const run = promisify(execFile);

async function verifyCandidate(limits, ctx, metric) {
  try {
    const { stdout } = await run(process.env.DL_HELPER ? "/usr/bin/python3" : limits.check, process.env.DL_HELPER ? ["-I", process.env.DL_HELPER, "verify"] : [], {
      cwd: ctx.cwd, timeout: Math.max(1, limits.deadline - Date.now()),
    });
    const witness = JSON.parse(stdout);
    const bounds = witness.interval;
    if (witness.status !== "VERIFIED" || !Array.isArray(bounds) || bounds.length !== 2 ||
        !bounds.every(Number.isFinite) || !Number.isFinite(metric) ||
        bounds[0] > metric || metric > bounds[1])
      return { block: true, reason: "Claimed metric lacks independent verification" };
  } catch (error) {
    return { block: true, reason: `Independent verifier rejected candidate: ${error.message}` };
  }
  return;
}

// OMP owns candidate generation and its SQLite checkpoints. Slots are consumed
// before dispatch, so a crash cannot silently refund an experiment.
export default function evolution(pi) {
  const directory = process.env.DL_EXPERIMENT;
  if (!directory) throw new Error("DL_EXPERIMENT is required");
  if (process.env.DL_HELPER) pi.registerTool({
    name: "candidate_shell", label: "Candidate shell",
    description: "Read and edit the declared candidate files in /work with an isolated shell.",
    parameters: { type: "object", properties: { command: { type: "string" } }, required: ["command"] },
    async execute(_id, input) {
      const { stdout } = await run("/usr/bin/python3", ["-I", process.env.DL_HELPER, "shell", input.command]);
      return { content: [{ type: "text", text: stdout.slice(0, 4096) }] };
    },
  });
  async function authorize(event, ctx) {
    if (process.env.DL_HELPER && !["init_experiment","run_experiment","log_experiment","candidate_shell"].includes(event.toolName))
      return { block: true, reason: "Use candidate_shell to edit the declared files in /work." };
    if (event.toolName === "log_experiment" && event.input.commit)
      return { block: true, reason: "Verify and commit the current candidate." };
    const keep = event.toolName === "log_experiment" && event.input.status === "keep";
    if (!keep && !["init_experiment", "run_experiment"].includes(event.toolName)) return;
    const limits = JSON.parse(await readFile(join(directory, "limits.json"), "utf8"));
    if (resolve(ctx.cwd) !== join(directory, "repo") || Date.now() >= limits.deadline)
      return { block: true, reason: "Outside experiment directory or time budget" };
    if (keep) return verifyCandidate(limits, ctx, event.input.metric);
    if (event.toolName === "init_experiment") {
      const cap = event.input.max_iterations;
      if (!Number.isSafeInteger(cap) || cap < 1 || cap > limits.iterations)
        return { block: true, reason: `Set max_iterations between 1 and ${limits.iterations}` };
      return;
    }
    for (let i = 1; i <= limits.iterations; i++) {
      const slot = join(directory, "attempt-" + i);
      try {
        await mkdir(slot);
      } catch (error) {
        if (error.code === "EEXIST") continue;
        throw error;
      }
      await writeFile(join(slot, "started"), new Date().toISOString());
      return;
    }
    return { block: true, reason: "Total experiment budget exhausted" };
  }

  let activeCall;
  if (process.env.DL_HELPER) pi.on("tool_result", event => {
    if (activeCall === event.toolCallId) activeCall = undefined;
  });
  pi.on("tool_call", async (event, ctx) => {
    if (!process.env.DL_HELPER) return authorize(event, ctx);
    if (activeCall) return { block: true, reason: "Wait for the current candidate operation." };
    activeCall = event.toolCallId;
    try {
      const verdict = await authorize(event, ctx);
      if (verdict?.block) activeCall = undefined;
      return verdict;
    } catch (error) {
      activeCall = undefined;
      return { block: true, reason: String(error) };
    }
  });
}
