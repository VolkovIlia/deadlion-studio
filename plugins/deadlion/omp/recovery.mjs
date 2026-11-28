import { digest } from "./evidence.mjs";

const actions = {
  IMPLEMENTATION: ["CORRECT", "DECOMPOSE"],
  VERIFICATION: ["INVESTIGATE", "REPLACE"],
  PERFORMANCE_REGRESSION: ["RECONSIDER", "REPLACE"],
  ARCHITECTURE: ["RECONSIDER", "DECOMPOSE"],
  TOOL: ["INVESTIGATE", "DEFER"],
  ENVIRONMENT: ["INVESTIGATE", "DEFER"],
  PLANNING: ["REPLAN", "DECOMPOSE"],
  RESOURCE: ["VERIFY_WITH_TOOL", "DEFER"],
};

const guidance = {
  CORRECT: "Locate the defect and run the focused check.",
  DECOMPOSE: "Split the failing change into independently verifiable steps.",
  RECONSIDER: "Review complexity, ownership, allocations and the workload. Identify the rejected assumption.",
  REPLACE: "Use a different algorithm, representation or engineering approach supported by the evidence.",
  INVESTIGATE: "Find the root cause and check for an approved way to resolve it. Preserve the oracle.",
  REPLAN: "Review remaining dependencies and decompose or reorder technical work within approved requirements.",
  VERIFY_WITH_TOOL: "Run deadlion_verify for the longer check. Preserve the existing budget and required evidence.",
  DEFER: "Record the blocker and continue an independent milestone if the verified checkout permits it.",
};

function category(failure) {
  const { name = "", reason = "" } = failure;
  if (/timeout|time slice|output limit/i.test(reason)) return "RESOURCE";
  if (/ENOENT|not found|not installed|unavailable|failed to spawn/i.test(reason)) return "TOOL";
  if (/permission denied|ECONNREFUSED|sandbox|dependency unavailable/i.test(reason)) return "ENVIRONMENT";
  if (/performance regression|exceed|resource limit/i.test(reason) || /profile|contract|scaling/.test(name))
    return "PERFORMANCE_REGRESSION";
  if (/structural ratchet|dl-size|dl-budget/.test(name)) return "ARCHITECTURE";
  if (/design|milestone|required constraints|functional verification/.test(name)) return "PLANNING";
  return /lsp|analy[sz]e/.test(name) ? "IMPLEMENTATION" : "VERIFICATION";
}

function distinguish(failure) {
  const reason = failure.reason ?? "";
  return reason.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, "<id>")
    .replace(/\b\d+(?:\.\d+)?(?:ms|s)?\b/g, "#").replace(/\s+/g, " ").trim().slice(0, 240);
}

function observeProgress(report, history) {
  const best = history.best ??= { confirmed: [], deficits: {} };
  const confirmed = new Set(best.confirmed);
  let progress = false;
  for (const check of report.confirmed ?? []) {
    if (!confirmed.has(check)) progress = true;
    confirmed.add(check);
  }
  best.confirmed = [...confirmed];
  for (const [name, value] of Object.entries(report.deficits ?? {})) {
    const prior = best.deficits[name] ?? Infinity;
    if (value >= prior) continue;
    if (Number.isFinite(prior)) progress = true;
    best.deficits[name] = value;
  }
  return progress;
}

export function recoveryDecision(task, report) {
  const failures = report.failures?.length ? report.failures : [{ name: "verification", reason: report.reason }];
  const primary = failures.find(f => f.name !== "verification interrupted") ?? failures[0];
  const cause = category(primary);
  const signature = digest(JSON.stringify(failures.map(f => [f.name, f.status, distinguish(f)]).sort()));
  const history = task.recovery ??= { recent: [], occurrences: {} };
  const previous = history.recent.at(-1);
  const progress = observeProgress(report, history) && !!previous;
  const repeatedState = previous?.source === report.source && previous?.signature === signature;
  const cycle = history.recent.slice(-3).some((entry, index, last) =>
    index < last.length - 1 && entry.source && entry.source === report.source && entry.signature === signature);
  const occurrences = history.occurrences[signature] ?? 0;
  const [initial, alternative] = actions[cause];
  const strategy = progress || occurrences === 0 ? initial : occurrences === 1 ? alternative : "DEFER";
  const record = { cause, strategy, signature, source: report.source, receipt: report.receipt,
    reason: primary.reason || primary.name, confirmed: report.confirmed, deficits: report.deficits,
    progress: Boolean(progress), repeatedState, cycle };
  history.recent = [...history.recent.slice(-7), record];
  if (!Object.hasOwn(history.occurrences, signature) && Object.keys(history.occurrences).length >= 64)
    delete history.occurrences[Object.keys(history.occurrences)[0]];
  history.occurrences[signature] = progress ? 1 : occurrences + 1;
  return record;
}

export function recoveryMessage(task, record) {
  const goal = task.goal ? ` Goal: ${task.goal.slice(0, 240)}.` : "";
  return `Deadlion ${task.last.status} · ${record.cause} · ${record.strategy}. ${record.reason.slice(0, 250)}. ` +
    guidance[record.strategy] + goal + (record.receipt ? " Receipt: " + record.receipt : "");
}

export function awaitsApproval(report) {
  const failures = report.failures ?? [];
  return failures.length > 0 && failures.every(failure => failure.approval);
}
