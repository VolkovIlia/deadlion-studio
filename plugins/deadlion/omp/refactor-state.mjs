import { randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { mkdir, readFile, rename, unlink } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { changes, digest, read, save, snapshot } from "./evidence.mjs";
import { executionSnapshot, migrateExecution } from "./execution.mjs";

export const state = directory => join(directory, "plan-state.json");
export const reservation = directory => join(directory, "active.json");

export async function optional(path) {
  return read(path).catch(error => {
    if (error.code !== "ENOENT") throw error;
  });
}

// The mutex lives beside the campaign so archiving cannot replace its inode.
// flock holds it only while the controller owns the pipe, including on SIGKILL.
export async function withCampaignLock(directory, action) {
  await mkdir(dirname(directory), { recursive: true, mode: 0o700 });
  const child = spawn("flock", ["-w", "4", directory + ".lock", "/bin/sh", "-c",
    'printf "locked\\n"; exec cat >/dev/null'], { stdio: ["pipe", "pipe", "ignore"] });
  const closed = new Promise(resolve => child.once("close", resolve));
  child.stdin.on("error", () => {});
  try {
    await new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("close", () => reject(new Error("Refactoring state is busy or flock is unavailable")));
      child.stdout.once("data", resolve);
    });
    return await action();
  } finally {
    child.stdin.end();
    await closed;
  }
}

async function processStart(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 0) return;
  const line = await readFile("/proc/" + pid + "/stat", "utf8").catch(error => {
    if (error.code !== "ENOENT" && error.code !== "ESRCH") throw error;
  });
  const fields = line?.slice(line.lastIndexOf(")") + 2).split(" ");
  if (fields && !["Z", "X", "x"].includes(fields[0])) return fields[19];
}

async function ownerIdentity(pid = process.pid) {
  return { pid, start: await processStart(pid), boot: (await readFile("/proc/sys/kernel/random/boot_id", "utf8")).trim() };
}

export async function ownerAlive(owner) {
  if (!owner) return false;
  const current = await ownerIdentity(owner.pid);
  return Boolean(current.start && current.start === owner.start && current.boot === owner.boot);
}

export async function activateMilestone(ctx, task) {
  const { directory, campaign } = task.refactor;
  await withCampaignLock(directory, async () => {
    const current = await read(state(directory));
    const active = await read(reservation(directory));
    if (current.id !== campaign || current.status !== "ACTIVE" ||
        active.task !== task.id || active.checkpoint !== task.baselineHash)
      throw new Error("Milestone reservation is no longer current");
    if (active.session !== ctx.sessionManager?.getSessionId())
      throw new Error("Resume the OMP session that owns this milestone");
    const owner = await ownerIdentity();
    if (await ownerAlive(active.owner) && active.owner.pid !== owner.pid)
      throw new Error("Milestone is already running in another OMP process");
    if (active.owner && active.owner.pid !== owner.pid && active.status === "ACTIVE")
      throw new Error("Recover the interrupted milestone before resuming");
    await save(reservation(directory), { ...active, owner, status: "ACTIVE" });
  });
}

export async function parkMilestone(task) {
  if (!task?.refactor) return;
  const { directory } = task.refactor;
  await withCampaignLock(directory, async () => {
    const active = await optional(reservation(directory));
    if (active?.task !== task.id || active.owner?.pid !== process.pid) return;
    const status = task.state === "BLOCKED" ? "FAILED" : "PAUSED";
    const current = await read(state(directory));
    current.execution = executionSnapshot(task);
    await save(state(directory), current);
    await save(reservation(directory), { ...active, owner: null, status });
  });
}

export async function loadReservedTask(ctx, directory, id) {
  if (!/^[a-f0-9-]{36}$/.test(id)) throw new Error("Invalid recovery task identity");
  const task = await read(join(directory, "task.json"));
  if (task.id !== id || task.cwd !== ctx.cwd || task.directory !== directory || !task.refactor)
    throw new Error("Recovered task does not match this OMP checkout");
  return task;
}

export async function checkpoint(directory, current) {
  const tree = current.checkpointPath ? await read(join(directory, current.checkpointPath)) :
    (await read(join(directory, "global.json"))).baseline;
  if (digest(JSON.stringify(tree)) !== current.checkpoint) throw new Error("Checkpoint fingerprint changed");
  return tree;
}

export async function recoverReservation({ directory, root }, operation, ctx, select) {
  return withCampaignLock(directory, async () => {
    const current = await read(state(directory));
    const active = await optional(reservation(directory));
    if (!active) return "No milestone reservation.";
    const before = await checkpoint(directory, current);
    const tree = await snapshot(root);
    const changed = changes(before, tree);
    if (await ownerAlive(active.owner))
      throw new Error("The milestone owner is running. Stop the verification before changing its reservation.");
    if (current.results[active.id]?.task === active.task && current.checkpoint === current.results[active.id].source) {
      if (changed.length) await recordRecovery(directory, active, changed, operation, current.checkpoint, tree);
      await unlink(reservation(directory));
      return "Verified checkpoint retained. Released its obsolete reservation.";
    }
    const conflict = active.checkpoint && active.checkpoint !== current.checkpoint;
    if (operation === "cancel") return cancelReservation(directory, current, active, changed, tree);
    if (conflict) throw new Error("Reservation belongs to a different checkpoint. Cancel it and review the changes.");
    if (active.session !== ctx.sessionManager?.getSessionId())
      throw new Error("Open the owning OMP session to recover it, or cancel its reservation");
    if (!/^[a-f0-9-]{36}$/.test(active.task ?? "")) throw new Error("Invalid saved task identity");
    const task = await read(join(dirname(dirname(directory)), active.task, "task.json"));
    if (task.id !== active.task || task.baselineHash !== current.checkpoint || task.refactor?.campaign !== current.id)
      throw new Error("Saved task is inconsistent. Cancel the reservation and review the checkout.");
    await recordRecovery(directory, active, changed, operation, current.checkpoint, tree);
    await save(reservation(directory), { ...active, owner: null, status: "PAUSED" });
    select("recover " + active.task);
    return "Milestone recovered as PAUSED. Resume to reverify the working tree.";
  });
}

async function cancelReservation(directory, current, active, paths, tree) {
  current.milestones ??= {};
  current.milestones[active.id] = "CANCELLED";
  const saved = /^[a-f0-9-]{36}$/.test(active.task ?? "") &&
    await optional(join(dirname(dirname(directory)), active.task, "task.json")).catch(() => undefined);
  if (saved?.id === active.task && saved.refactor?.campaign === current.id)
    current.execution = executionSnapshot(migrateExecution(saved));
  await recordRecovery(directory, active, paths, "cancel", current.checkpoint, tree);
  await save(state(directory), current);
  await unlink(reservation(directory));
  return paths.length ? "Milestone cancelled. Checkout has unverified changes. Restore the checkpoint before restarting." : "Milestone cancelled.";
}

export async function finalReceiptStatus(current, planHash, source, final, evidence, revalidate) {
  if (current.status !== "COMPLETED" || current.finalPlanHash !== planHash ||
      final?.status !== "PASS" || current.checkpoint !== source || final.source !== source ||
      final.receiptHash !== digest(JSON.stringify(evidence))) return { status: "NOT VERIFIED" };
  try {
    await revalidate();
    return { status: "VERIFIED" };
  } catch (error) { return { status: "NOT VERIFIED", staleInputs: error.message }; }
}

async function recordRecovery(directory, active, paths, operation, checkpointHash, tree) {
  await save(join(directory, "recovery", randomUUID() + ".json"), {
    operation, milestone: active.id, task: active.task, session: active.session, paths,
    status: "NOT VERIFIED", reservedCheckpoint: active.checkpoint, checkpoint: checkpointHash,
    checkout: digest(JSON.stringify(tree)), at: new Date().toISOString(),
  });
}

export async function archiveCampaign({ directory, current }) {
  if (!["COMPLETED", "CANCELLED", "ARCHIVED"].includes(current.status))
    throw new Error("Complete final verification or cancel the campaign before archiving");
  const archive = join(dirname(directory), "history", basename(directory), current.id);
  await mkdir(dirname(archive), { recursive: true, mode: 0o700 });
  const global = await read(join(directory, "global.json"));
  const final = await optional(join(directory, "final-receipt.json"));
  if (global.receipt) await save(join(directory, "receipts", "baseline.json"), await read(global.receipt));
  if (final?.receipt) await save(join(directory, "receipts", "final.json"), await read(final.receipt));
  for (const [id, result] of Object.entries(current.results))
    await save(join(directory, "receipts", id + ".json"), await read(result.receipt));
  await save(state(directory), { ...current, status: "ARCHIVED", archived: new Date().toISOString() });
  await rename(directory, archive);
  return archive;
}

export function readyMilestones(current) {
  if (current.status !== "ACTIVE") return [];
  return Object.values(current.steps).filter(step => !current.results[step.id] &&
    !["DEFERRED", "BLOCKED", "CANCELLED"].includes(current.milestones?.[step.id]) &&
    step.depends.every(id => current.results[id]));
}

export async function deferMilestone(task, reason, ctx) {
  const { directory, id, campaign } = task.refactor;
  return withCampaignLock(directory, async () => {
    const current = await read(state(directory));
    const active = await read(reservation(directory));
    if (active.task !== task.id || current.id !== campaign || current.checkpoint !== task.baselineHash ||
        active.session !== ctx.sessionManager?.getSessionId() || active.owner?.pid !== process.pid)
      throw new Error("Milestone reservation changed");
    const tree = await snapshot(task.root);
    if (digest(JSON.stringify(tree)) !== current.checkpoint) return false;
    current.milestones ??= {};
    current.milestones[id] = "DEFERRED";
    current.execution = executionSnapshot(task);
    await save(join(directory, "milestone-" + id + "-deferred.json"), {
      task: task.id, reason, receipt: task.last?.receipt, checkpoint: current.checkpoint,
    });
    await save(state(directory), current);
    await unlink(reservation(directory));
    return true;
  });
}

export async function saveMissionBudget(task, change) {
  const directory = task.refactor?.directory ?? task.refactorFinal;
  if (!directory) return;
  await withCampaignLock(directory, async () => {
    const current = await read(state(directory));
    const active = await optional(reservation(directory));
    if (await ownerAlive(active?.owner) || active && active.task !== task.id ||
        current.id !== (task.refactor?.campaign ?? task.missionId))
      throw new Error("Campaign ownership changed");
    const previous = current.execution ?? executionSnapshot(task);
    current.execution = { ...previous, [change.key]: change.after,
      budgetChanges: [...previous.budgetChanges ?? [], change] };
    await save(state(directory), current);
    Object.assign(task, current.execution);
  });
}
