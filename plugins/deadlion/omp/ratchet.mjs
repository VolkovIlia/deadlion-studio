import { extname } from "node:path";
import { contains, documentation } from "./coverage.mjs";

const group = (entries, key) => {
  const result = new Map();
  for (const entry of entries) {
    const id = key(entry);
    if (!id) continue;
    if (!result.has(id)) result.set(id, []);
    result.get(id).push(entry);
  }
  return result;
};

const rows = (files, paths) => paths.flatMap(path => {
  const list = files[path]?.functions;
  return Array.isArray(list) ? list.map(item => ({ path, ...item })) :
    Object.entries(list ?? {}).map(([key, lines]) => ({ path, key, name: key, lines }));
});

function compare(issues, name, value, old, limit) {
  if (value > Math.max(old ?? 0, limit))
    issues.push({ name, baseline: old ?? 0, limit, value, status: "FAIL" });
}

function compareFunctions(before, after, paths, issues) {
  const entries = rows(before.files, paths);
  const current = rows(after.files, paths);
  const identity = item => item.path + "\0" + item.key;
  const oldByKey = group(entries, identity);
  const byKey = group(current, identity);
  const matched = new Set();
  const remaining = current.filter(item => {
    const key = identity(item);
    const originals = oldByKey.get(key) ?? [];
    if (originals.length !== 1 || byKey.get(key).length !== 1) return true;
    matched.add(originals[0]);
    compare(issues, item.path + " " + item.name, item.lines, originals[0].lines, before.maxFunction);
    return false;
  });
  const signature = item => item.fingerprint && extname(item.path) + "\0" + item.fingerprint;
  const departed = group(entries.filter(item => !matched.has(item)), signature);
  const arrivals = group(remaining, signature);
  for (const item of remaining) {
    const key = signature(item);
    const choices = departed.get(key) ?? [];
    const prior = choices.length === 1 && arrivals.get(key)?.length === 1 ? choices[0] : undefined;
    if (item.lines > before.maxFunction && !prior &&
        (choices.length > 0 || (oldByKey.get(identity(item))?.length ?? 0) > 1)) {
      issues.push({ name: item.path + " " + item.name, reason: "ambiguous function identity", status: "INCONCLUSIVE" });
    } else compare(issues, item.path + " " + item.name, item.lines, prior?.lines, before.maxFunction);
  }
}

function compareFiles(before, after, paths, issues, tree) {
  const removed = paths.filter(path => before.files[path] && !after.files[path]);
  const moved = group(removed.map(path => ({ path, ...before.files[path] })), file => file.fingerprint);
  const added = group(paths.filter(path => after.files[path] && !before.files[path]).map(path => after.files[path]),
    file => file.fingerprint);
  const removedBytes = new Set(removed.map(path => tree?.baseline.files[path]?.[1]?.[1]).filter(Boolean));
  for (const path of paths) {
    const file = after.files[path];
    if (!file) {
      const current = tree?.current.files[path]?.[1];
      if (current && (before.files[path] || removedBytes.has(current[1]) || !documentation(path) && removed.length))
        issues.push({ name: path, reason: "changed or relocated source is outside structural measurement", status: "INCONCLUSIVE" });
      continue;
    }
    if (file.issue) issues.push({ name: path, reason: file.issue, status: "INCONCLUSIVE" });
    const choices = moved.get(file.fingerprint) ?? [];
    const original = before.files[path] ?? (choices.length === 1 && added.get(file.fingerprint)?.length === 1 &&
      extname(choices[0].path) === extname(path) ? choices[0] : undefined);
    compare(issues, path, file.lines, original?.lines, before.maxFile);
  }
}

export function ratchet(before, after, paths, tree) {
  const issues = [];
  compareFiles(before, after, paths, issues, tree);
  compareFunctions(before, after, paths, issues);
  for (const [name, metric] of Object.entries(after.projects)) {
    if (name !== "." && !paths.some(path => contains(name, path))) continue;
    const prior = before.projects[name];
    const limits = (prior ?? metric).limits;
    compare(issues, name + " SLOC", metric.sloc, prior?.sloc, limits.DL_MAX_SLOC);
    compare(issues, name + " direct dependencies", metric.deps.length, prior?.deps.length, limits.DL_MAX_DEPS);
  }
  return issues;
}
