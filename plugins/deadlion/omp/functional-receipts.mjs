import { readFile, realpath } from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { coverageFor, scopeList } from "./coverage.mjs";
import { digest, read, save, stateHome } from "./evidence.mjs";
import { testResult } from "./test-result.mjs";

const uuid = "[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}";
const taskName = new RegExp("^" + uuid + "$");
const gateName = new RegExp("^gate-" + uuid + "\\.json$");
const index = source => join(stateHome(), "functional-receipts", source + ".json");
const equal = (left, right) => JSON.stringify(left) === JSON.stringify(right);

function receiptPath(path) {
  const file = resolve(path);
  const directory = dirname(file);
  if (dirname(directory) !== resolve(stateHome()) || !taskName.test(basename(directory)) || !gateName.test(basename(file)))
    throw new Error("Expected a Deadlion gate receipt in the local evidence store.");
  return file;
}

export function attachFunctionalReceipt(task, path) {
  if (!path) throw new Error("Provide the path of the independent Deadlion gate receipt.");
  const receipt = receiptPath(path);
  task.functionalReceipts = [...new Set([receipt, ...task.functionalReceipts ?? []])].slice(0, 8);
}

function directChecks(policy, checks) {
  const approved = new Map((policy.checks ?? []).filter(check => check.type === "functional")
    .map(check => ["plan: " + check.name, check]));
  if (policy.tests) approved.set("functional tests", { argv: policy.tests, scope: policy.testsScope });
  return checks.flatMap(check => {
    const entry = approved.get(check.name);
    if (!entry || check.status !== "PASS" || check.data?.code !== 0 ||
        check.coverage?.type !== "functional" || !scopeList(entry.scope) ||
        !equal(entry.scope, check.coverage.paths) || !equal(entry.argv, check.coverage.argv)) return [];
    const observed = testResult(entry.argv, [check.data.stdout, check.data.stderr].join("\n"), true);
    return Number.isSafeInteger(observed.passed) && observed.passed > 0 && !observed.incomplete ? [check] : [];
  });
}

export async function publishFunctionalReceipt(task, evidence, receipt, receiptHash) {
  if (evidence.status !== "PASS" || !evidence.source || !(task.policyFile || task.policy.setupApproval)) return;
  if (!directChecks(task.policy, evidence.checks).length) return;
  try { await save(index(evidence.source), { receipt, receiptHash }); }
  catch { /* The per-task receipt remains available even when the optional index cannot be written. */ }
}

async function readBoundReceipt(task, reference) {
  const path = receiptPath(reference.receipt);
  const directory = dirname(path);
  const state = join(directory, "task.json");
  if (await realpath(path) !== path || await realpath(state) !== state)
    throw new Error("The receipt or task path resolves through a symlink.");
  const donor = await read(state);
  if (donor.id === task.id || donor.id !== basename(directory) || donor.directory !== directory ||
      donor.root !== task.root || !(donor.policyFile || donor.policy?.setupApproval))
    throw new Error("The receipt needs another task with pinned scoped checks in this checkout.");
  return { donor, path, ...readDonorEvidence(await readFile(path), donor, reference, path) };
}

function readDonorEvidence(bytes, donor, reference, path) {
  const receiptHash = digest(bytes);
  const receipt = JSON.parse(bytes);
  if (path !== donor.last?.receipt || receiptHash !== donor.last?.receiptHash ||
      reference.receiptHash && receiptHash !== reference.receiptHash)
    throw new Error("The receipt is stale or its saved digest changed.");
  if (receipt.version !== 2 || receipt.status !== "PASS" || receipt.task !== donor.id ||
      !equal(receipt.policy, donor.policy) || receipt.baselineHash !== donor.baselineHash)
    throw new Error("The receipt does not bind a passing run to its donor policy and baseline.");
  return { receipt, receiptHash };
}

async function loadDonor(task, reference, scope, options, verifyInputs) {
  const { donor, path, receipt, receiptHash } = await readBoundReceipt(task, reference);
  if (receipt.source !== scope.source || receipt.workspaceHash !== scope.workspaceHash)
    throw new Error("Run the pinned checks in the active checkout. The whole checkout fingerprint differs.");
  if (!scope.testOnly && receipt.baselineHash !== task.baselineHash)
    throw new Error("Production changes require independently verified evidence from the same baseline.");
  const tools = await verifyInputs(donor, options);
  const integration = receipt.integration?.verified;
  if (!integration || ![donor.tools.integration, tools.integration].includes(integration) ||
      receipt.toolIdentity !== digest(JSON.stringify({ ...tools, integration })))
    throw new Error("The recorded verifier inputs no longer match.");
  return { receipt, receiptHash, path, checks: directChecks(donor.policy, receipt.checks) };
}

export async function borrowedFunctionalChecks(task, missing, scope, options, verifyInputs) {
  const automatic = await read(index(scope.source)).catch(() => undefined);
  const references = new Map((task.functionalReceipts ?? []).map(receipt => [receipt, { receipt, explicit: true }]));
  if (automatic?.receipt && !references.has(automatic.receipt)) references.set(automatic.receipt, automatic);
  const checks = [];
  let remaining = missing;
  for (const reference of references.values()) {
    if (!remaining.length) break;
    try {
      const donor = await loadDonor(task, reference, scope, options(), verifyInputs);
      const covered = remaining.filter(row => !row.interface);
      for (const check of donor.checks) {
        const paths = coverageFor(covered, [check]).filter(row => row.status === "VERIFIED").map(row => row.path);
        if (!paths.length) continue;
        checks.push({ name: "scoped functional receipt", status: "PASS", coverage: { type: "functional", exact: true, paths },
          borrowed: { receipt: donor.path, receiptHash: donor.receiptHash, task: donor.receipt.task, check: check.name,
            testOnly: scope.testOnly } });
      }
      remaining = coverageFor(remaining, checks).filter(row => row.status === "NOT VERIFIED");
    } catch (error) {
      if (reference.explicit)
        checks.push({ name: "functional receipt unavailable", status: "WARNING", reason: error.message });
    }
  }
  return checks;
}

export async function revalidateBorrowedChecks(task, evidence, options, verifyInputs) {
  const donors = new Map();
  for (const { borrowed, coverage } of evidence.checks) {
    if (!borrowed) continue;
    const scope = { source: evidence.source, workspaceHash: evidence.workspaceHash, testOnly: borrowed.testOnly };
    if (!donors.has(borrowed.receiptHash))
      donors.set(borrowed.receiptHash, await loadDonor(task, borrowed, scope, options, verifyInputs));
    const donor = donors.get(borrowed.receiptHash);
    const check = donor.checks.find(item => item.name === borrowed.check);
    if (!check || coverageFor(coverage.paths.map(path => ({ path })), [check]).some(row => row.status !== "VERIFIED"))
      throw new Error("The borrowed check no longer covers the recorded paths.");
  }
}
