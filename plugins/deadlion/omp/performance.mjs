import { execFile } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const analyze = fileURLToPath(new URL("../skills/performance/scripts/dl-analyze", import.meta.url));
const run = promisify(execFile);

export default function performance(pi) {
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
      message = stdout.trim();
    } catch (error) {
      message = error.stdout?.trim() || `NOT VERIFIED: ${error.message}`;
    }
    return { content: [...event.content, { type: "text", text: message }] };
  });
}
