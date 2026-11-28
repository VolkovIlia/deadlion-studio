const fields = { seconds: "deadline", analysisSeconds: "analysisMs", tokens: "tokenLimit", operationSeconds: "operationMs" };

export function limit(value) {
  return value ?? Infinity;
}

export function integer(value, name, minimum = 1) {
  if (!Number.isSafeInteger(value) || value < minimum || value > Math.floor(Number.MAX_SAFE_INTEGER / 1000))
    throw new Error("Invalid limit for " + name);
  return value;
}

export function executionLimits(policy, now = Date.now()) {
  const limits = { deadline: null, analysisMs: null, tokenLimit: null, operationMs: null, maxCorrections: null };
  for (const [field, key] of Object.entries(fields))
    if (policy[field] !== undefined) limits[key] = budgetValue(field, integer(policy[field], field), now);
  if (policy.maxCorrections !== undefined) limits.maxCorrections = integer(policy.maxCorrections, "maxCorrections", 0);
  return limits;
}

function budgetValue(field, amount, now) {
  if (amount === null || field === "tokens") return amount;
  return field === "seconds" ? now + amount * 1000 : amount * 1000;
}

export function migrateExecution(task) {
  if (task.executionVersion === 1) return task;
  const defaults = executionLimits(task.policy, task.started);
  for (const [field, key] of Object.entries({ ...fields, maxCorrections: "maxCorrections" })) {
    task[key] = task.policy[field] === undefined ? null : task[key] ?? defaults[key];
  }
  task.executionVersion = 1;
  return task;
}

export function tokensUsed(task) {
  const { input = 0, cached = 0, output = 0 } = task.usage ?? {};
  return input + cached + output;
}

export function exhausted(task, now = Date.now()) {
  if (limit(task.deadline) <= now) return "wall-clock budget exhausted";
  if (limit(task.analysisMs) <= 0) return "analysis budget exhausted";
  if (tokensUsed(task) >= limit(task.tokenLimit)) return "token budget exhausted";
}

export function timeLeft(task, now = Date.now()) {
  return Math.min(limit(task.deadline) - now, limit(task.analysisMs));
}

export function chargeAnalysis(task, started, now = Date.now()) {
  if (task.analysisMs != null) task.analysisMs = Math.max(0, task.analysisMs - (now - started));
}

export function operationTimeout(task) {
  return task.operationMs ?? (task.policy.operationSeconds ?? 120) * 1000;
}

export function updateBudget(task, command, now = Date.now()) {
  const [field, value, ...extra] = command.trim().split(/\s+/);
  if (!Object.hasOwn(fields, field) || !value || extra.length)
    throw new Error("Use /deadlion budget seconds|analysisSeconds|tokens|operationSeconds <integer|unlimited>");
  const key = fields[field];
  const before = task[key];
  const amount = value === "unlimited" ? null : integer(Number(value), field);
  if (field === "operationSeconds" && amount === null) throw new Error("An operation timeout must be finite");
  task[key] = budgetValue(field, amount, now);
  const change = { at: now, field, key, before, after: task[key] };
  (task.budgetChanges ??= []).push(change);
  return change;
}

export function budgetStatus(task, now = Date.now()) {
  const seconds = ms => ms == null ? "unlimited" : Math.max(0, Math.ceil(ms / 1000)) + " s";
  return `Task time ${seconds(task.deadline == null ? null : task.deadline - now)} · analysis ${seconds(task.analysisMs)} · tokens ${tokensUsed(task)}/${task.tokenLimit ?? "unlimited"}`;
}

export function executionSnapshot(task) {
  return { deadline: task.deadline, analysisMs: task.analysisMs, tokenLimit: task.tokenLimit, usage: { ...task.usage },
    operationMs: task.operationMs, budgetChanges: task.budgetChanges ?? [] };
}

export function chargeTokens(task, usage) {
  if (task.tokenLimit && !(usage?.totalTokens > 0)) return "provider token usage unavailable";
  if (usage) {
    task.usage.reported = !!usage.totalTokens;
    task.usage.input += usage.input ?? 0;
    task.usage.cached += (usage.cacheRead ?? 0) + (usage.cacheWrite ?? 0);
    task.usage.output += usage.output ?? 0;
  }
  return exhausted(task);
}
