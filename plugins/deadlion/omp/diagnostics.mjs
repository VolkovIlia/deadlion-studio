import { timeLeft } from "./execution.mjs";
import { randomUUID } from "node:crypto";
import { lstat, realpath } from "node:fs/promises";
import { join, relative, resolve, sep } from "node:path";
import { execute } from "./process.mjs";
import { save, scripts } from "./evidence.mjs";

export const supported = p => /\.(py|c|cc|cpp|cxx|go|rs|ts|js|java|kt)$/.test(p);

export function scalingSummary(data) {
  if (!data?.scaling) return;
  const scaling = data.scaling;
  return { status: scaling.status, correctness: scaling.correctness, choice: scaling.choice,
    observed: (scaling.models ?? []).filter(row => row.implementation === scaling.choice).slice(0, 2).map(row => {
      const fit = row.metrics.wall_ns;
      return { distribution: row.distribution, metric: "wall_ns", status: fit?.status,
        admissible: fit?.admissible?.slice(0, 5) };
    }), medianRatio: data.median_ratio, interval: data.interval };
}
export function editPaths(event) {
  const input = event.input ?? {};
  const details = event.details ?? {};
  return [...new Set([input.path, input.file_path, ...(input.paths ?? []), details.path,
    ...(details.perFileResults ?? []).map(f => f.path)].filter(p => typeof p === "string"))];
}

export async function regular(root, paths) {
  const files = [];
  for (const path of paths) {
    const absolute = resolve(root, path);
    const name = relative(root, absolute);
    if (name === ".." || name.startsWith(".." + sep)) continue;
    if ((await lstat(absolute).catch(() => null))?.isFile() && await realpath(absolute) === absolute)
      files.push(absolute);
  }
  return files;
}

export async function analyze(files, options, native = false, infer = false, deep = false) {
  const result = await execute([join(scripts, "dl-analyze"), "--json", "--available", ...(deep ? ["--deep"] : []), ...(native ? ["--native"] : []), ...(infer ? ["--infer-cost"] : []),
    "--", ...files], options);
  const report = JSON.parse(result.stdout);
  if (result.code || report.status !== "CHECKED") throw new Error(report.reason || result.stderr || report.status);
  report.diagnostics = report.diagnostics.map(d => {
    let source = "ast-grep";
    if (d.rule === "infer-cost") source = "Infer Cost";
    else if (d.confidence === "native diagnostic") source = ({
      ".kt": "Detekt", ".java": "PMD", ".go": "Staticcheck", ".rs": "Clippy",
      ".ts": "ESLint", ".js": "ESLint",
    })[d.file.slice(d.file.lastIndexOf("."))] ?? "Clang-Tidy";
    else if (/^(PERF|SIM|C901)/.test(d.rule)) source = "Ruff";
    else if (d.file.endsWith(".py")) source = "python_hints";
    source = d.source ?? source;
    return { ...d, source, category: "performance", evidenceLevel: d.confidence === "STATICALLY BOUNDED"
      ? d.confidence : d.confidence === "INCONCLUSIVE" ? "INCONCLUSIVE" : "HEURISTIC",
      range: d.range ?? { startLine: d.line }, provenance: d.provenance?.map(e => ({ ...e, source: e.source === "native" ? source : e.source })) ?? [{ source, rule: d.rule }] };
  });
  return report;
}

export function compact(report, seen) {
  const problems = new Map();
  const key = d => JSON.stringify([d.file, d.line, d.column, d.range, d.explanation, d.rule]);
  for (const d of report.diagnostics) problems.set(key(d), d);
  const fresh = [...problems].filter(([k]) => !seen.has(k));
  const files = new Set(report.filesAnalyzed);
  for (const k of seen) if (files.has(JSON.parse(k)[0]) && !problems.has(k)) seen.delete(k);
  const diagnostics = [];
  for (const [k, d] of fresh.sort((a,b) => Number(b[1].severity === "ERROR") - Number(a[1].severity === "ERROR"))) {
    const item = { file: d.file, line: d.line, rule: d.rule, severity: d.severity,
      explanation: d.explanation.slice(0, 300), typeContext: d.typeContext?.text.slice(0, 240), confirm: d.confirm?.slice(0, 160) };
    if (JSON.stringify([...diagnostics, item]).length > 3000) break;
    diagnostics.push(item);
    seen.add(k);
  }
  return { total: problems.size, new: fresh.length, diagnostics };
}

export async function feedback(task, event, ctx, seen, lookup, signal) {
  const files = await regular(task.root, editPaths(event).map(p => resolve(ctx.cwd, p)).filter(supported));
  if (!files.length) return;
  const report = await analyze(files, { cwd: ctx.cwd, signal, timeout: Math.min(5000, timeLeft(task)) });
  const target = report.diagnostics.find(d => d.semanticTarget);
  if (lookup && target) {
    const before = await realpath(target.file);
    const timeout = AbortSignal.timeout(Math.max(1, Math.min(3000, timeLeft(task))));
    try { target.typeContext = await lookup(ctx.cwd, before, target.semanticTarget, signal ? AbortSignal.any([signal, timeout]) : timeout); }
    catch (error) { target.semanticStatus = "INCONCLUSIVE"; target.semanticReason = error.message; }
  }
  report.filesAnalyzed = files;
  const path = join(task.directory, "analysis-" + randomUUID() + ".json");
  await save(path, report);
  const summary = compact(report, seen);
  if (summary.new) return { content: [...event.content, { type: "text", text: JSON.stringify({ ...summary, report: path }) }] };
}

export function lspObservation(event) {
  if (event.toolName !== "lsp" || event.input?.action !== "diagnostics" || !event.input.file) return;
  const output = event.content.filter(c => c.type === "text").map(c => c.text).join("\n");
  const server = event.details?.serverName;
  const status = server && event.details?.success ? semanticVerdict(server, event.input.file, output) : "INCONCLUSIVE";
  return { source: "omp:lsp", file: event.input.file, server, output,
    status, reason: status === "INCONCLUSIVE" ? "Complete fresh diagnostics are unconfirmed" : undefined };
}

function semanticVerdict(server, file, output) {
  const summary = output.split("\n", 1)[0];
  if (/\b[1-9]\d* errors?\b/.test(summary)) return "FAIL";
  if (file.endsWith(".rs") && /\brust-analyzer\b/.test(server)) return "INCONCLUSIVE";
  if (output.trim() === "OK") return "PASS";
  if (/\d+ (warnings?|info|hints?)\b/.test(summary) &&
      !/unreported|still pending|some servers failed|no (?:fresh|diagnostics) report/i.test(output)) return "WARNING";
  return "INCONCLUSIVE";
}

export function gateFindings(checks, root) {
  const rows = [];
  for (const check of checks) {
    if (check.data?.diagnostics) rows.push(...check.data.diagnostics);
    if (check.name === "Semgrep" && check.data) {
      for (const item of check.data.results) rows.push({ source: "Semgrep", file: resolve(root, item.path),
        line: item.start.line, range: { startLine: item.start.line, startColumn: item.start.col,
          endLine: item.end.line, endColumn: item.end.col, unit: "character" }, rule: item.check_id,
        category: "static", severity: item.extra.severity, evidenceLevel: "HEURISTIC",
        explanation: item.extra.message, confirm: "Review the match against project semantics." });
    }
    if (!["PASS", "NOT APPLICABLE"].includes(check.status) && !check.data?.diagnostics && !check.data?.results) {
      rows.push(checkFinding(check));
    }
  }
  return rows;
}

function checkFinding(check) {
  const semantic = check.name.startsWith("lsp ");
  return { source: check.source ?? check.name, category: semantic ? "semantic" : "verification",
    rule: check.name, file: semantic ? check.name.slice(4) : undefined, status: check.status,
    severity: check.status === "WARNING" ? "WARNING" : "ERROR",
    evidenceLevel: semantic && check.status === "FAIL" ? "SEMANTICALLY CONFIRMED" :
      check.status === "FAIL" ? "EMPIRICALLY CONFIRMED" : "INCONCLUSIVE",
    explanation: check.reason || check.output || check.data?.status || check.status,
    confirm: "Inspect the recorded check and verify the same scope after correction." };
}
