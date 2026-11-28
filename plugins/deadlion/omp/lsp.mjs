// OMP 19.2.1 version-specific bridge. Load lazily so CLI and Node consumers
// can run without an OMP package installation.
import { lspObservation } from "./diagnostics.mjs";
import { relative, resolve } from "node:path";

export const diagnosticRequest = event =>
  event.toolName === "lsp" && event.input?.action === "diagnostics" && typeof event.input.file === "string";

export function mergeDiagnostic(previous, report) {
  const servers = report.server?.split(/,\s*/) ?? [];
  const prior = previous?.requiredServers ?? (previous?.status === "FAIL" ? previous.server?.split(/,\s*/) ?? [] : []);
  const required = previous?.required || previous?.status === "FAIL";
  if (report.status === "FAIL") return { ...report, required: true, requiredServers: [...new Set([...prior, ...servers])] };
  if (!report.sourceHash || required && (!servers.length ||
      !["PASS", "WARNING"].includes(report.status) || !prior.every(server => servers.includes(server))))
    return previous;
  return { ...report, required, requiredServers: prior };
}

export async function observedDiagnostic(task, event, pending, snapshot) {
  const report = lspObservation(event);
  if (!report) return;
  const source = pending?.task === task.id && pending.file === report.file && pending.source;
  return { ...report, sourceHash: source && source === await snapshot() ? source : undefined };
}

export function saveDiagnostic(task, cwd, report) {
  const file = relative(task.root, resolve(cwd, report.file));
  const previous = task.semantic?.[file];
  const current = mergeDiagnostic(previous, report);
  if (current === previous) return false;
  (task.semantic ??= {})[file] = current;
  return true;
}

async function sessionTool(cwd) {
  const { LspTool } = await import("@oh-my-pi/pi-coding-agent/lsp");
  const { findScopedSettings } = await import("@oh-my-pi/pi-coding-agent/config/settings");
  const settings = findScopedSettings(cwd);
  if (!settings) throw new Error("OMP session settings unavailable");
  return new LspTool({ cwd, settings, lspReadOnly: true });
}

export async function permitsInspection(cwd, input) {
  const tool = await sessionTool(cwd);
  return tool.approval(input) === "read";
}

async function query(cwd, input, signal) {
  return (await sessionTool(cwd)).execute("deadlion-" + input.action, input, signal);
}

export async function hover(cwd, file, target, signal) {
  const input = { action: "hover", file, ...target, timeout: 3 };
  const result = await query(cwd, input, signal);
  if (!result.details?.success || !result.details.serverName) return;
  return { source: result.details.serverName, target, text: result.content.filter(c => c.type === "text").map(c => c.text).join("\n") };
}

export async function diagnostics(cwd, file, signal) {
  const input = { action: "diagnostics", file, timeout: 4 };
  const result = await query(cwd, input, signal);
  return lspObservation({ ...result, input, toolName: "lsp" });
}

export async function servers(cwd) {
  const { discoverStartupLspServers, getLspStatus } = await import("@oh-my-pi/pi-coding-agent/lsp");
  return { configured: discoverStartupLspServers(cwd, "available").map(s => s.name),
    clients: getLspStatus().map(({ name, status }) => ({ name, status })) };
}

export async function activeForFile(cwd, file) {
  const [{ getConfig, getServersForFile }, { getLspStatus }] = await Promise.all([
    import("@oh-my-pi/pi-coding-agent/lsp/config"), import("@oh-my-pi/pi-coding-agent/lsp"),
  ]);
  const clients = getLspStatus().filter(c => c.status === "ready");
  const matching = getServersForFile(getConfig(cwd), file);
  return matching.length > 0 && matching.every(([, config]) =>
    clients.some(client => client.name === config.command));
}
