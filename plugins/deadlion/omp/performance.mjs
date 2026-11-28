import { randomUUID } from "node:crypto";
import { commands } from "./commands.mjs";
import { join } from "node:path";
import { incremental, openTask, persist, read, restoreTask, resumeTask, save, stateHome } from "./evidence.mjs";
import { editPaths, feedback } from "./diagnostics.mjs";
import { diagnosticRequest, diagnostics, hover, observedDiagnostic, saveDiagnostic } from "./lsp.mjs";
import { design, permitsDesignTool } from "./design.mjs";
import { semgrepResult } from "./semgrep.mjs";
import { verify, verifyToolInputs } from "./gate.mjs";
import { lifecycleContext } from "./omp-compat.mjs";
import { authorizeRefactorTool, bindMilestone, completeMilestone, milestonePrompt, refactorCommand } from "./refactor.mjs";
import { activateMilestone, loadReservedTask, parkMilestone, saveMissionBudget } from "./refactor-state.mjs";
import { interrupted, needsNewTask, outcome, rejectPrompt, resolveTaskInput, resumeInput, showTaskStatus } from "./task-input.mjs";
import { budgetStatus, chargeAnalysis, chargeTokens, exhausted, limit, migrateExecution, timeLeft, updateBudget } from "./execution.mjs";
import { advisory, recoveryDecision, recoveryMessage } from "./recovery.mjs";
import { advanceMission, commitMission, continueAfterFailure } from "./mission.mjs";
import { hashTree, measureBaseline, registerVerifier, reusableReceipt } from "./task-verification.mjs";
import { captureImportCheck, startImportCheck } from "./import-evidence.mjs";
// Across OMP factory instances, share only unambiguous parent identities.
const owners = new Map();
const delegates = new WeakMap();
function locateParent(ctx) {
  const matches = [...owners.values()].filter(o => o.agent === ctx.agent.parentId && (o.cwd === ctx.cwd || o.task.refactor));
  return matches.length === 1 ? matches[0].task : undefined;
}

const entry = "deadlion.engineering.task", transitionEntry = "deadlion.engineering.transition";
const terminal = new Set(["VERIFIED", "BLOCKED", "AWAITING_APPROVAL", "AWAITING_RESTART", "CANCELLED", "INCOMPLETE"]);
class EngineeringSession {
  constructor(pi) {
    this.pi = pi;
  }

  tasks = new Map();
  unavailable = new Set();
  pendingLsp = new Map();
  lastScan = new Map();
  timers = new Map();
  verified = new Map();
  seen = new Map();
  active = new Map();
  selections = new Map();
  nativeGoals = new Map();
  session(ctx) { return ctx.sessionManager?.getSessionId() ?? ctx.cwd; }

  async taskFor(ctx, prompt = "", newRequest = false, existingOnly = false) {
    const key = this.session(ctx);
    if (!newRequest && !existingOnly && this.unavailable.has(key)) return;
    const prior = this.tasks.get(key);
    const recorded = newRequest && ctx.sessionManager?.getBranch().filter(e =>
      e.type === "custom" && e.customType === transitionEntry).at(-1);
    const selection = newRequest ? this.selections.get(key) ?? recorded?.data?.command : undefined;
    if (selection) {
      this.selections.delete(key);
      this.pi.appendEntry?.(transitionEntry, { command: null });
    }
    const pending = this.loadTask(ctx, { prior, selection, newRequest, existingOnly, prompt });
    this.tasks.set(key, pending);
    try {
      const task = await pending;
      if (this.tasks.get(key) === pending) {
        if (task) this.tasks.set(key, task);
        else this.tasks.delete(key);
      }
      return task;
    } catch (error) {
      if (this.tasks.get(key) === pending) {
        if (prior) this.tasks.set(key, prior);
        else this.tasks.delete(key);
      }
      throw error;
    }
  }

  async loadTask(ctx, { prior, selection, newRequest, existingOnly, prompt }) {
    const transition = selection?.split(" ", 1)[0];
    if (transition === "recover") return this.resumeReserved(ctx, selection.slice(8));
    const interactive = newRequest && ctx.mode === "tui";
    const task = await prior ?? await restoreTask(ctx, entry, { allowMoved: interactive });
    if (existingOnly) return task;
    const milestone = ["milestone", "campaign"].includes(transition) ? selection.split(" ")[1] : undefined;
    const input = resolveTaskInput(task, ctx, selection, newRequest);
    const nativeGoal = this.nativeGoals.get(this.session(ctx));
    if (needsNewTask(task, { milestone, selection: input.selection, newRequest, nativeGoal })) {
      if (task?.refactor && !terminal.has(task.state))
        throw new Error("Stop or finish the active refactoring milestone before starting another task");
      if (task) this.release(ctx, task);
      return this.createTask(ctx, prompt, milestone, transition === "campaign");
    }
    return resumeInput(task, input, { newRequest, terminal, nativeGoal });
  }

  async resumeReserved(ctx, id) {
    const task = migrateExecution(await loadReservedTask(ctx, join(stateHome(), id), id));
    resumeTask(task, "resume");
    await activateMilestone(ctx, task);
    this.rememberTask(task);
    return task;
  }

  async createTask(ctx, prompt, milestone, autonomous = false, signal = this.signal(ctx)) {
    const created = await openTask(ctx, prompt);
    if (milestone) {
      created.autonomous = autonomous;
      created.refactor = await bindMilestone(ctx, milestone, created, signal);
      await persist(created);
    }
    this.rememberTask(created);
    return created;
  }

  rememberTask(task) { this.pi.appendEntry?.(entry, { directory: task.directory, id: task.id }); }
  release(ctx, task) {
    const key = this.session(ctx);
    clearTimeout(this.timers.get(key));
    this.timers.delete(key);
    this.active.get(key)?.abort();
    this.active.delete(key);
    owners.delete(key);
    if (!task) return;
    this.lastScan.delete(task.id);
    this.verified.delete(task.id);
    this.seen.delete(task.id);
    delegates.delete(task);
    for (const [id, pending] of this.pendingLsp) if (pending.task === task.id) this.pendingLsp.delete(id);
  }

  async transition(command, ctx) {
    const key = this.session(ctx);
    if (command === "refactor" || command.startsWith("refactor ")) {
      const check = async task => {
        task.enforcement = lifecycleContext(this.pi, ctx);
        return verify(task, this.signal(ctx), Infinity, this.semanticProbe(task));
      };
      return refactorCommand(command, ctx, check, value => this.select(key, value), verifyToolInputs, this.signal(ctx));
    }
    const task = await this.taskFor(ctx, "", false, true);
    if (command === "budget" || command.startsWith("budget ")) return this.changeBudget(task, key, command);
    if (command === "stop") {
      if (task && !terminal.has(task.state)) {
        task.state = "INCOMPLETE";
        task.last = { status: "NOT VERIFIED", reason: "Stopped by the operator" };
        this.release(ctx, task);
        ctx.abort?.();
        await outcome(task, ctx);
        await parkMilestone(task);
      }
      return "Engineering task stopped.";
    }
    if (command === "retry") {
      if (!task) throw new Error("No engineering task to retry");
      const report = await this.fullCheck(task, undefined, ctx);
      task.last = report;
      await persist(task);
      return `${report.status} · ${report.receipt}`;
    }
    if (command !== "new" && !task) throw new Error("No engineering task to " + command);
    this.select(key, command);
    return `Next prompt will ${command === "new" ? "start a new task" : command + " the task"}.`;
  }

  async changeBudget(task, key, command) {
    if (!task) throw new Error("No engineering task to budget");
    if (command === "budget") return budgetStatus(task);
    if (this.active.has(key)) throw new Error("Stop the active turn before changing its budget");
    const updated = { ...task, budgetChanges: [...task.budgetChanges ?? []] };
    const change = updateBudget(updated, command.slice(7));
    await saveMissionBudget(updated, change);
    Object.assign(task, updated);
    await persist(task);
    return `${task.id} · ${budgetStatus(task)}`;
  }

  select(key, command) {
    this.selections.set(key, command);
    this.pi.appendEntry?.(transitionEntry, { command });
  }

  semanticProbe(task) { return this.pi.getActiveTools?.().includes("lsp") &&
    (task.policy.trustProject || task.policy.requireLsp || task.policy.native) ? diagnostics : undefined; }

  signal(ctx, signal) {
    const current = ctx && this.active.get(this.session(ctx))?.signal;
    return current && signal ? AbortSignal.any([current, signal]) : current ?? signal;
  }
  async fullCheck(task, signal, ctx) {
    this.verified.delete(task.id);
    signal = this.signal(ctx, signal);
    const reason = exhausted(task);
    if (reason) throw new Error(reason);
    const baseline = task.designIssue?.startsWith("Run deadlion_verify") && !task.baselineReceipt;
    if (baseline) return measureBaseline(task, signal);
    const report = await verify(task, signal, Infinity, this.semanticProbe(task));
    task.last = report;
    task.receipts.push(report.receipt);
    if (report.status === "PASS") this.verified.set(task.id, report);
    await persist(task);
    return report;
  }

  async before_agent_start(event, ctx) {
    if (ctx.agent?.kind === "sub") return;
    const key = this.session(ctx);
    this.unavailable.delete(key);
    showTaskStatus(ctx, "Deadlion: preparing request…");
    let task;
    try {
      const nativeGoal = this.nativeGoals.get(this.session(ctx));
      task = await this.taskFor(ctx, nativeGoal?.objective ?? event.prompt, true);
      if (nativeGoal && !task.nativeGoal) task.nativeGoal = nativeGoal.id;
      if (task.refactor) await activateMilestone(ctx, task);
      await this.prepareTask(task, ctx);
    } catch (error) {
      this.unavailable.add(key);
      this.release(ctx, task);
      return rejectPrompt(error, ctx, event.prompt);
    }
    const skills = task.mode === "Standard" ? "workflow, unix-design, build and verify" :
      "workflow, unix-design, decompose, write-plan, performance, build and verify";
    return { message: { customType: "deadlion.policy", display: false,
      content: `Deadlion ${task.mode} (${task.kind}). Correctness, safety and approved resource limits take priority over simplicity. ` +
      `Use applicable ${skills} skills. Check algorithm, data structures, repeated work, allocations and invariants. ` +
      "Use the autonomous OMP workflow. Update technical plans yourself. Run deadlion_verify, resolve failures and deliver the verified result for review. " +
      (task.designIssue ?? "Supply executable evidence.") + " " + milestonePrompt(task.refactor?.step) } };
  }

  async prepareTask(task, ctx) {
    delete task.blocker;
    const key = this.session(ctx);
    task.enforcement = lifecycleContext(this.pi, ctx);
    if (!this.active.has(key)) this.active.set(key, new AbortController());
    const generation = this.active.get(key);
    task.semgrepTools = this.pi.getActiveTools?.().filter(name => /semgrep/i.test(name)) ?? [];
    owners.set(this.session(ctx), { cwd: ctx.cwd, agent: ctx.agent?.id, task, ctx });
    clearTimeout(this.timers.get(key));
    const remaining = limit(task.deadline) - Date.now();
    if (remaining <= 2 ** 31 - 1) {
      const timer = setTimeout(async () => {
        if (this.active.get(key) !== generation || terminal.has(task.state)) return;
        generation.abort();
        await this.pauseForBudget(task, ctx, "wall-clock budget exhausted");
      }, Math.max(1, remaining));
      timer.unref();
      this.timers.set(key, timer);
    }
    task.designIssue = await design(task);
    task.state = task.designIssue ? "DESIGN" : "IMPLEMENTATION";
    await persist(task);
    showTaskStatus(ctx, "Deadlion: working…");
  }

  async tool_call(event, ctx) {
    let task;
    try { task = ctx.agent?.kind === "sub" ? locateParent(ctx) : await this.taskFor(ctx); }
    catch (error) { return { additionalContext: "Deadlion verification unavailable: " + error.message }; }
    if (!task) return;
    const reason = exhausted(task);
    if (reason) return { block: true, reason };
    if (task.refactor) {
      const reason = await authorizeRefactorTool(task, event, ctx, editPaths(event));
      if (reason) return { block: true, reason };
    }
    if (task.designIssue && !await permitsDesignTool(event, ctx))
      return task.designIssue.startsWith("Run deadlion_verify") ? { block: true, reason: task.designIssue } :
        { additionalContext: task.designIssue };
    await startImportCheck(task, event, ctx);
    if (task.semgrepTools?.includes(event.toolName))
      this.pendingLsp.set(event.toolCallId, { task: task.id, source: await hashTree(task) });
    if (ctx.agent?.kind !== "sub" && diagnosticRequest(event)) {
      const source = await this.diagnosticSnapshot(task, ctx);
      if (source) this.pendingLsp.set(event.toolCallId, { task: task.id, source, file: event.input.file });
    }
  }

  async before_subagent_spawn(event, ctx) {
    const task = ctx.agent?.kind === "sub" ? locateParent(ctx) : await this.taskFor(ctx, "", false, true);
    if (!task?.refactor) return;
    const scopes = task.refactor.step.owners;
    if (!delegates.has(task)) delegates.set(task, new Set());
    const delegated = delegates.get(task);
    if (ctx.agent?.kind === "sub" || !Object.hasOwn(scopes, event.agent) || delegated.has(event.agent))
      return { block: true, reason: "Milestone requires a unique subagent with an assigned scope" };
    delegated.add(event.agent);
  }

  async tool_result(event, ctx) {
    const sub = ctx.agent?.kind === "sub";
    const task = sub ? locateParent(ctx) : await this.taskFor(ctx);
    if (!task) return;
    if (sub) await save(join(task.directory, "sub-" + randomUUID() + ".json"), {
      agent: ctx.agent, tool: event.toolName, paths: editPaths(event), error: event.isError });

    if (!sub) {
      await captureImportCheck(task, event);
      await this.collectSemantic(task, event, ctx);
    }
    if (!["edit", "write"].includes(event.toolName)) {
      event = await this.opaqueEdit(task, event, ctx);
      if (!event) return;
    }
    await this.writethrough(task, event, ctx, sub);
    if (!this.seen.has(task.id)) this.seen.set(task.id, new Set());
    const started = Date.now();
    if (timeLeft(task, started) <= 0) return;
    try { return await feedback(task, event, ctx, this.seen.get(task.id), this.semanticProbe(task) && hover, this.signal(ctx)); }
    catch (error) { return { additionalContext: "Deadlion incremental analysis NOT VERIFIED: " + error.message }; }
    finally { chargeAnalysis(task, started); }
  }

  async opaqueEdit(task, event, ctx) {
    if (!["bash", "eval", "python", "patch", "task"].includes(event.toolName) ||
        timeLeft(task) < 2000 || Date.now() - (this.lastScan.get(task.id) ?? 0) < 1500) return;
    this.lastScan.set(task.id, Date.now());
    let paths;
    try { paths = await incremental(task, this.signal(ctx)); }
    catch { return; } // The final gate reconciles the full tree.
    return { ...event, input: { paths } };
  }

  async writethrough(task, event, ctx, sub) {
    const perFile = event.details?.perFileResults ?? [event.details ?? {}];
    for (const item of perFile) {
      const path = item.path ?? event.input.path;
      if (item.diagnostics && path) {
        const evidence = { file: path, ...item.diagnostics };
        await save(join(task.directory, "lsp-" + randomUUID() + ".json"), evidence);
        if (!sub && item.diagnostics.errored) await this.recordDiagnostic(task, ctx,
          { ...evidence, status: "FAIL", output: item.diagnostics.messages, source: "omp:writethrough" });
      }
    }
  }

  async turn_end(event, ctx) {
    const sub = ctx.agent?.kind === "sub";
    const task = sub ? locateParent(ctx) : await this.tasks.get(this.session(ctx));
    if (!task || terminal.has(task.state)) return;
    const reason = chargeTokens(task, event.message?.usage);
    if (reason) {
      const parent = sub && [...owners.values()].find(owner => owner.task === task)?.ctx;
      return this.pauseForBudget(task, parent || ctx, reason);
    }
    await persist(task);
  }

  async pauseForBudget(task, ctx, reason) {
    task.state = "INCOMPLETE";
    task.last = { status: "NOT VERIFIED", reason };
    try { await outcome(task, ctx); } finally { ctx.abort?.(); }
  }

  async agent_end(event, ctx) {
    if (event.willContinue) return;
    if (ctx.agent?.kind === "sub") {
      const parent = locateParent(ctx);
      if (parent) delegates.get(parent)?.delete(ctx.agent.name);
      return;
    }
    const task = await this.tasks.get(this.session(ctx));
    const last = event.messages?.filter(m => m.role === "assistant").at(-1);
    if (!task || terminal.has(task.state) || !["aborted","error"].includes(last?.stopReason)) return;
    task.state = last.stopReason === "aborted" ? "CANCELLED" : "INCOMPLETE";
    await outcome(task, ctx);
  }

  async session_shutdown(_event, ctx) {
    const key = this.session(ctx);
    const task = await this.tasks.get(key);
    this.release(ctx, task);
    this.tasks.delete(key);
    this.unavailable.delete(key);
    this.selections.delete(key);
    this.nativeGoals.delete(key);
    await parkMilestone(task);
    if (task && !terminal.has(task.state)) await persist(task);
  }

  goal_updated(event, ctx) {
    const key = this.session(ctx);
    if (event.goal?.status === "active") this.nativeGoals.set(key, event.goal);
    else this.nativeGoals.delete(key);
  }

  async session_stop(event, ctx) {
    if (ctx.agent?.kind === "sub" || this.unavailable.has(this.session(ctx))) return;
    let task;
    try {
      task = await this.taskFor(ctx, "", false, !!ctx.sessionManager);
      if (!task) throw new Error("session has no recorded task baseline");
      if (interrupted(task, event)) return await outcome(task, ctx);
      task.last = await this.finalEvidence(task, this.signal(ctx, event.signal));
      task.receipts.push(task.last.receipt);
      if (interrupted(task, event)) return await outcome(task, ctx);
      if (task.last.status === "PASS") return await this.acceptVerification(task, ctx, this.signal(ctx, event.signal));
      return await this.correction(task, event, ctx);
    } catch (error) {
      await this.failStop(task, ctx, event, error);
    } finally {
      if (task && this.tasks.get(this.session(ctx)) === task && terminal.has(task.state)) {
        this.release(ctx, task);
        await parkMilestone(task);
      }
    }
  }

  async acceptVerification(task, ctx, signal) {
    if (task.refactor) await completeMilestone(task, task.last);
    if (task.refactorFinal) await commitMission(task, task.last);
    if (task.refactor && task.autonomous) return this.afterMilestone(task, ctx, signal);
    task.state = "VERIFIED";
    return outcome(task, ctx);
  }

  async afterMilestone(task, ctx, signal) {
    task.state = "RECOVERING";
    await outcome(task, ctx);
    const next = await advanceMission(this, task, ctx, "Verified milestone " + task.refactor.id, signal);
    if (next) return advisory(next);
    task.state = "INCOMPLETE";
    task.blocker = "No independent ready milestones. Deferred requirements remain open.";
    await outcome(task, ctx);
  }

  async failStop(task, ctx, event, error) {
    if (task) {
      if (!["CANCELLED", "INCOMPLETE"].includes(task.state)) task.state = event.signal?.aborted ? "CANCELLED" : "INCOMPLETE";
      task.last = { status: "NOT VERIFIED", reason: error.message };
      await outcome(task, ctx);
    } else {
      await rejectPrompt(error, ctx);
    }
  }

  async finalEvidence(task, signal) {
    const previous = this.verified.get(task.id);
    this.verified.delete(task.id);
    if (!exhausted(task) && await reusableReceipt(task, previous, signal)) return previous;
    return verify(task, signal, 20000, this.semanticProbe(task));
  }

  async collectSemantic(task, event, ctx) {
    const pending = this.pendingLsp.get(event.toolCallId);
    this.pendingLsp.delete(event.toolCallId);
    if (pending?.task === task.id && task.semgrepTools?.includes(event.toolName)) {
      const data = semgrepResult(event);
      const { source } = pending;
      if (data && source === await hashTree(task)) {
        task.semgrep = { source, data };
        await persist(task);
      }
    }
    const report = await observedDiagnostic(task, event, pending, () => this.diagnosticSnapshot(task, ctx));
    if (report) await this.recordDiagnostic(task, ctx, report);
  }

  diagnosticSnapshot(task, ctx) {
    return hashTree(task, { timeout: Math.min(3000, timeLeft(task)), signal: this.signal(ctx) }).catch(() => undefined);
  }

  async recordDiagnostic(task, ctx, report) {
    if (!saveDiagnostic(task, ctx.cwd, report)) return;
    this.verified.delete(task.id);
    await persist(task);
  }
  async correction(task, event, ctx) {
    const canContinue = !event.signal?.aborted && !exhausted(task);
    if (canContinue && task.last.failures?.some(check => check.restartRequired)) {
      task.state = "AWAITING_RESTART";
      return outcome(task, ctx);
    }
    const recovery = recoveryDecision(task, task.last);
    const semantic = task.last.failures?.some(check => check.name.startsWith("lsp "));
    if (!canContinue || task.corrections >= limit(task.maxCorrections) ||
        (recovery.repeatedState && !semantic) || recovery.cycle || recovery.strategy === "DEFER") {
      task.state = event.signal?.aborted ? "CANCELLED" : "INCOMPLETE";
      const next = canContinue && await continueAfterFailure(this, task, ctx, recovery.reason, this.signal(ctx, event.signal));
      await outcome(task, ctx);
      if (next) return advisory(next);
      return;
    }
    task.corrections++;
    task.state = "RECOVERING";
    await outcome(task, ctx);
    return advisory(recoveryMessage(task, recovery));
  }
}

export default function performance(pi) {
  const controller = new EngineeringSession(pi);
  registerVerifier(pi, controller);
  pi.on("before_agent_start", controller.before_agent_start.bind(controller));
  pi.on("goal_updated", controller.goal_updated.bind(controller));
  pi.on("tool_call", controller.tool_call.bind(controller));
  pi.on("before_subagent_spawn", controller.before_subagent_spawn.bind(controller));
  pi.on("tool_result", controller.tool_result.bind(controller));
  pi.on("turn_end", controller.turn_end.bind(controller));
  pi.on("agent_end", controller.agent_end.bind(controller));
  pi.on("session_shutdown", controller.session_shutdown.bind(controller));
  pi.on("session_stop", controller.session_stop.bind(controller));
  commands(pi, controller.taskFor.bind(controller), controller.fullCheck.bind(controller), controller.transition.bind(controller));
}
