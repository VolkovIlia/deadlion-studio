import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { digest } from "./evidence.mjs";
import { execute } from "./process.mjs";

export function semgrepResult(event) {
  if (!/semgrep/i.test(event.toolName) || event.isError) return;
  for (const content of event.content ?? []) {
    if (content.type !== "text") continue;
    try {
      const value = JSON.parse(content.text);
      if (Array.isArray(value.results) && Array.isArray(value.paths?.scanned)) return value;
    } catch { /* Some MCP tools return prose without coverage metadata. */ }
  }
}

export async function checkSemgrep(task, files, source, options) {
  const name = "Semgrep";
  const config = task.policy.semgrepConfig;
  const available = task.semgrepTools?.length > 0;
  let data = task.semgrep?.source === source && task.semgrep.data;
  if (config && digest(await readFile(config)) !== task.semgrepConfigHash)
    throw new Error("Semgrep configuration changed");
  if (available && config)
    return { name, status: "NOT VERIFIED", reason: "The configured MCP scan does not attest a pinned CLI rule file" };
  if (!data && !available && config && task.policy.native === true) {
    const result = await execute(["semgrep", "scan", "--metrics=off", "--disable-version-check",
      "--json", "--config", config, "--", ...files], options);
    if (result.code) return { name, status: "NOT VERIFIED", reason: result.stderr.slice(-400) };
    data = JSON.parse(result.stdout);
  }
  if (!data) return { name, status: "NOT VERIFIED", reason: "Semgrep scan with matching source and file coverage required" };
  const scanned = new Set(data.paths?.scanned?.map(p => resolve(task.root, p)));
  const complete = !data.errors?.length && files.every(p => scanned.has(p));
  return { name, status: !complete ? "NOT VERIFIED" : data.results.length ? "WARNING" : "PASS", data };
}
