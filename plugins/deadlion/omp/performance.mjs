import { execFile } from "node:child_process";
import { resolve, join } from "node:path";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const analyze = fileURLToPath(new URL("../skills/performance/scripts/dl-analyze", import.meta.url));
const run = promisify(execFile);

export default function performance(pi) {
  const contract = process.env.DL_PERF_CONTRACT;
  pi.on("session_stop", async (_event, ctx) => {
    let evidence;
    try {
      const gate = resolve(analyze, "../dl-perf-gate");
      const directory = resolve(ctx.cwd, process.env.DL_PERF_CANDIDATE_DIR || ".");
      const args = contract ? [resolve(contract), "--isolated", "--candidate-dir", directory] : ["--changed"];
      const { stdout } = await run(gate, args,
        { cwd: ctx.cwd, timeout: 86400000, maxBuffer: 16 * 1024 * 1024 });
      if (JSON.parse(stdout).status === "NOT APPLICABLE" && !contract) return;
      evidence = join(await mkdtemp(join(tmpdir(),"dl-verification-")),"gate.json");
      await writeFile(evidence, stdout);
      if (JSON.parse(stdout).status === "VERIFIED") return;
    } catch (error) {
      evidence ??= join(await mkdtemp(join(tmpdir(),"dl-verification-")),"gate.json");
      let reason = error.code;
      try { reason = JSON.parse(error.stdout).status; } catch {}
      await writeFile(evidence, error.stdout || JSON.stringify({status:"NOT VERIFIED",reason:String(reason)}));
      return { decision: "block", reason: `Required performance gate: ${reason}. Evidence at ${evidence}.` };
    }
    return { decision: "block", reason: "Required performance gate lacks verified evidence." };
  });
  pi.on("tool_result", async (event, ctx) => {
    if (event.isError || !["edit", "write"].includes(event.toolName)) return;
    const paths = event.input.paths ?? [event.input.path ?? event.input.file_path];
    if (!Array.isArray(paths)) return;
    const sources = paths.filter(p => typeof p === "string" && /\.(py|c|cc|cpp|cxx|go|rs|ts|js|java|kt)$/.test(p));
    if (!sources.length) return;
    let message;
    try {
      const files = sources.map(p => resolve(ctx.cwd, p));
      const { stdout } = await run(analyze, ["--json", "--", ...files], { cwd: ctx.cwd, timeout: 60000 });
      const report = JSON.parse(stdout);
      if (!report.diagnostics.length) return;
      const findings = report.diagnostics.slice(0, 5);
      message = JSON.stringify({ total: report.diagnostics.length, diagnostics: findings }).slice(0, 4096);
    } catch (error) {
      message = error.stdout?.trim().slice(0, 512) || `NOT VERIFIED: ${error.message}`;
    }
    return { content: [...event.content, { type: "text", text: message }] };
  });
}
