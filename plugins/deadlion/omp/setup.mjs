import { createHash } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { execute } from "./process.mjs";

const helper = fileURLToPath(new URL("capabilities.py", import.meta.url));
const hash = value => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const store = (home, root) => join(home, "projects", hash(root) + ".json");

export async function discover(cwd) {
  const result = await execute(["python3", "-I", helper, "--discover"], { cwd, timeout: 5000 });
  if (result.code) throw new Error(result.stderr.trim() || "project discovery failed");
  return JSON.parse(result.stdout);
}

export async function projectPolicy(root, home) {
  const canonical = await realpath(root);
  const stored = await readFile(store(home, canonical), "utf8").catch(error => {
    if (error.code !== "ENOENT") throw error;
  });
  if (!stored) return {};
  const approved = JSON.parse(stored);
  const current = await discover(root);
  if (approved.root !== current.root || approved.fingerprint !== current.fingerprint)
    return { setupIssue: "Project commands or configuration changed. Review /deadlion setup again." };
  return current.policy;
}

export async function setup(cwd, home, approve, save) {
  const project = await discover(cwd);
  const { root, languages, components, git, dirty, manifests, tools, policy, fingerprint } = project;
  const config = process.env.DL_ENGINEERING_POLICY;
  const lines = [
    root,
    `Languages ${languages.join(", ") || "unknown"} · ${components.length} component(s)`,
    `Git ${git ? dirty ? "working tree changed" : "clean" : "unavailable"}`,
    `Manifests ${manifests.slice(0, 10).join(", ") || "none"}`,
    `Available analyzers ${tools.join(", ") || "none"}`,
    `Functional verification ${policy.tests?.join(" ") || "no test command detected"}`,
    "Computer Science and structural analysis enabled. Experimental optimization on demand.",
  ];
  if (config) lines.push("The operator policy remains active: " + config);
  else if (approve && approve === fingerprint) {
    await save(store(home, root), { root, fingerprint });
    lines.push("Approved project-native analyzers, language servers and the test command above.");
  } else if (approve) lines.push("Project discovery changed. Review the new recommendation before approving.");
  else lines.push("Project-native analyzers, language servers and tests may execute project code.");
  if (!config && approve !== fingerprint) lines.push("/deadlion setup approve " + fingerprint);
  return lines.join("\n");
}
