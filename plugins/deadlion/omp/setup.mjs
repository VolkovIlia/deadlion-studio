import { createHash } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { execute } from "./process.mjs";
import { contains, scopeList } from "./coverage.mjs";

const helper = fileURLToPath(new URL("capabilities.py", import.meta.url));
const hash = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const store = (home, root) => join(home, "projects", hash(root) + ".json");

export async function discover(cwd, options = {}) {
  const result = await execute(["python3", "-I", helper, "--discover"],
    { ...options, cwd, timeout: Math.min(options.timeout ?? 5000, 5000) });
  if (result.code) throw new Error(result.stderr.trim() || "project discovery failed");
  return JSON.parse(result.stdout);
}

export async function projectPolicy(root, home, options) {
  const canonical = await realpath(root);
  const stored = await readFile(store(home, canonical), "utf8").catch(error => {
    if (error.code !== "ENOENT") throw error;
  });
  if (!stored) return {};
  const approved = JSON.parse(stored);
  const current = await discover(root, options);
  if (approved.root !== current.root || approved.fingerprint !== current.fingerprint)
    return { setupIssue: "Project commands or configuration changed. Review /deadlion setup again." };
  return { ...setupPolicy(current, approved.scopes ?? {}), setupApproval: hash(stored) };
}

function setupPolicy(project, scopes) {
  const { tests, ...policy } = project.policy;
  const checks = project.suites.filter(suite => Object.hasOwn(scopes, suite.id)).map(suite => ({
    name: "discovered tests " + suite.id, argv: suite.argv, cwd: suite.cwd,
    type: "functional", scope: scopes[suite.id], requireTestCount: true,
  }));
  return checks.length ? { ...policy, checks } : policy;
}

function parseScopes(project, input) {
  const scopes = input ? JSON.parse(input) : {};
  if (!scopes || Array.isArray(scopes) || typeof scopes !== "object")
    throw new Error("Pass approved suite scopes as a JSON object");
  for (const [id, paths] of Object.entries(scopes)) {
    if (!project.suites.some(suite => suite.id === id) || !scopeList(paths))
      throw new Error("Unknown suite or invalid project-relative paths for " + id);
  }
  return scopes;
}

export async function setup(cwd, home, approve, save) {
  const project = await discover(cwd);
  const { root, languages, components, git, dirty, manifests, tools, fingerprint, suites } = project;
  const [, token = "", details = ""] = /^(\S+)(?:\s+(.*))?$/s.exec(approve.trim()) ?? [];
  const config = process.env.DL_ENGINEERING_POLICY;
  const lines = [
    root,
    `Languages ${languages.join(", ") || "unknown"} · ${components.length} component(s)`,
    `Git ${git ? dirty ? "working tree changed" : "clean" : "unavailable"}`,
    `Manifests ${manifests.slice(0, 10).join(", ") || "none"}`,
    `Available analyzers ${tools.join(", ") || "none"}`,
    ...suites.map(suite => `Suite ${suite.id} · ${suite.cwd} · ${suite.argv.join(" ")} · ${suite.reason} · proposed ${suite.proposedScope.join(", ") || "unknown"}`),
    "Functional coverage requires explicit scope approval and a nonempty test result.",
    "Computer Science and structural analysis enabled. Experimental optimization on demand.",
  ];
  if (config) return [...lines, "The operator policy remains active: " + config].join("\n");
  if (token === fingerprint) {
    const scopes = parseScopes(project, details);
    await save(store(home, root), { root, fingerprint, scopes });
    const uncovered = components.filter(component => !Object.values(scopes).flat().some(path => contains(path, component)));
    lines.push("Project-native tools approved. Uncovered components · " + (uncovered.join(", ") || "none declared"));
  } else if (approve) {
    lines.push("Project discovery changed. Review the new recommendation before approving.");
  } else {
    lines.push("Project-native analyzers, language servers and tests may execute project code.",
      "Uncovered components · " + (components.join(", ") || "project"));
  }
  lines.push("/deadlion setup approve " + fingerprint);
  if (suites.length) lines.push('Append a JSON object such as {"1":["frontend"]} to approve test coverage.');
  return lines.join("\n");
}
