import { randomUUID } from "node:crypto";
import { commands } from "./commands.mjs";
import { join, relative, resolve } from "node:path";
import { execute } from "./process.mjs";
import { approvalHash, digest, incremental, openTask, persist, read, restoreTask, resumeTask, save, scripts, snapshot, stateHome } from "./evidence.mjs";
import { editPaths, feedback, lspObservation, scalingSummary } from "./diagnostics.mjs";
import { diagnostics, hover } from "./lsp.mjs";
import { design, permitsDesignTool } from "./design.mjs";
import { semgrepResult } from "./semgrep.mjs";
import { verify, verifyToolInputs } from "./gate.mjs";
import { lifecycleContext } from "./omp-compat.mjs";
import { authorizeRefactorTool, bindMilestone, completeMilestone, milestonePrompt, refactorCommand } from "./refactor.mjs";
import { activateMilestone, loadReservedTask, parkMilestone } from "./refactor-state.mjs";

// Factories are rebound by OMP. Use a shared lookup only for unambiguous
// parent identities in this process. The main gate always checks disk again.
const owners = new Map();
const delegates = new WeakMap();
function locateParent(ctx) {
  const matches = [...owners.values()].filter(o => o.agent === ctx.agent.parentId && (o.cwd === ctx.cwd || o.task.refactor));
  return matches.length === 1 ? matches[0].task : undefined;
}

const entry = "deadlion.engineering.task";
const transitionEntry = "deadlion.engineering.transition";
const terminal = new Set(["VERIFIED", "BLOCKED", "CANCELLED", "INCOMPLETE"]);
const hashTree = async task => digest(JSON.stringify(await snapshot(task.cwd)));

async function outcome(task, ctx) {
  await persist(task);
  const reason = task.last?.failures?.[0]?.reason || task.last?.reason;
  const message = `Deadlion ${task.state} · ${task.last?.status ?? "NOT VERIFIED"}` +
    (reason ? "\n" + reason : "") + "\n" + (task.last?.receipt ?? task.directory);
  ctx.ui?.notify(message, task.state === "VERIFIED" ? "info" : "warning");
  if (process.env.DL_VERDICT_FILE)
    await save(process.env.DL_VERDICT_FILE, { state: task.state, task: task.id, report: task.last });
}

class EngineeringSession {
  constructor(pi) {
    this.pi = pi;
  }

  tasks = new Map();
  pendingLsp = new Map();
  lastScan = new Map();
  timers = new Map();
  verified = new Map();
  seen = new Map();
  active = new Map();
  selections = new Map();
  session(ctx) { return ctx.sessionManager?.getSessionId() ?? ctx.cwd; }

  async taskFor(ctx, prompt = "", newRequest = false, existingOnly = false) {
    const key = this.session(ctx);
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
    if (transition === "recover") {
      const id = selection.slice(8);
      const directory = join(stateHome(), id);
      const task = await loadReservedTask(ctx, directory, id);
      resumeTask(task, "resume");
      await activateMilestone(ctx, task);
      this.pi.appendEntry?.(entry, { directory, id });
      return task;
    }
    const task = await prior ?? await restoreTask(ctx, entry);
    if (existingOnly) return task;
    const milestone = transition === "milestone" ? selection.slice(10) : undefined;
    if (!task || milestone || selection === "new" || newRequest && task.state === "VERIFIED") {
      if (task?.refactor && !terminal.has(task.state))
        throw new Error("Stop or finish the active refactoring milestone before starting another task");
      if (task) this.release(ctx, task);
      return this.createTask(ctx, prompt, milestone);
    }
    if (newRequest && terminal.has(task.state)) resumeTask(task, selection);
    return task;
  }

  async createTask(ctx, prompt, milestone) {
    const created = await openTask(ctx, prompt);
    if (milestone) {
      created.refactor = await bindMilestone(ctx, milestone, created);
      await persist(created);
    }
    this.pi.appendEntry?.(entry, { directory: created.directory, id: created.id });
    return created;
  }
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
        return verify(task, this.signal(ctx), task.analysisMs, this.semanticProbe(task));
      };
      return refactorCommand(command, ctx, check, value => this.select(key, value), verifyToolInputs);
    }
    const task = await this.taskFor(ctx, "", false, true);
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
    signal = this.signal(ctx, signal);
    const baseline = task.designIssue?.startsWith("Run deadlion_verify") && !task.baselineReceipt;
    if (baseline) {
      const original = await read(join(task.directory, "baseline.json"));
      if (task.approvalHash !== await approvalHash(task)) throw new Error("approved fixtures changed");
      const current = await snapshot(task.cwd);
      if (digest(JSON.stringify(original.files)) !== digest(JSON.stringify(current.files)))
        throw new Error("baseline measurement needs the original working tree");
      const started = Date.now();
      let result;
      try {
        result = await execute([join(scripts, "dl-perf-gate"), task.approved, "--isolated",
          "--candidate-dir", task.candidate], { cwd: task.root, signal, timeout: Math.min(task.analysisMs, task.deadline - started) });
      } finally {
        task.analysisMs = Math.max(0, task.analysisMs - (Date.now() - started));
        await persist(task);
      }
      const data = JSON.parse(result.stdout);
      if (digest(JSON.stringify(current)) !== await hashTree(task)) throw new Error("workspace changed during baseline measurement");
      const receipt = join(task.directory, "initial-measurement.json");
      await save(receipt, data);
      if (!["VERIFIED", "PERFORMANCE REGRESSION"].includes(data.status)) throw new Error("baseline: " + data.status);
      task.baselineReceipt = receipt;
      task.designIssue = await design(task);
      await persist(task);
      return { status: data.status, receipt, purpose: "baseline", scaling: scalingSummary(data) };
    }
    const report = await verify(task, signal, task.analysisMs, this.semanticProbe(task));
    if (report.status === "PASS") this.verified.set(task.id, report);
    await persist(task);
    return report;
  }

  async before_agent_start(event, ctx) {
    if (ctx.agent?.kind === "sub") return;
    let task;
    try {
      task = await this.taskFor(ctx, event.prompt, true);
      if (task.refactor) await activateMilestone(ctx, task);
    }
    catch (error) {
      ctx.ui?.notify(error.message, "error");
      if (process.env.DL_VERDICT_FILE) await save(process.env.DL_VERDICT_FILE,
        { state: "INCOMPLETE", reason: error.message });
      ctx.abort?.();
      return;
    }
    const key = this.session(ctx);
    task.enforcement = lifecycleContext(this.pi, ctx);
    if (!this.active.has(key)) this.active.set(key, new AbortController());
    const generation = this.active.get(key);
    task.semgrepTools = this.pi.getActiveTools?.().filter(name => /semgrep/i.test(name)) ?? [];
    owners.set(this.session(ctx), { cwd: ctx.cwd, agent: ctx.agent?.id, task });
    clearTimeout(this.timers.get(key));
    const timer = setTimeout(async () => {
      if (this.active.get(key) !== generation || terminal.has(task.state)) return;
      generation.abort();
      task.state = "INCOMPLETE";
      task.last = { status: "NOT VERIFIED", reason: "wall-clock budget exhausted" };
      try { await outcome(task, ctx); } finally { ctx.abort?.(); }
    }, Math.max(1, task.deadline - Date.now()));
    timer.unref();
    this.timers.set(key, timer);
    task.designIssue = await design(task);
    task.state = task.designIssue ? "DESIGN" : "IMPLEMENTATION";
    await persist(task);
    const skills = task.mode === "Standard" ? "workflow, unix-design, build and verify" :
      "workflow, unix-design, decompose, write-plan, performance, build and verify";
    return { message: { customType: "deadlion.policy", display: false,
      content: `Deadlion ${task.mode} (${task.kind}). Correctness, safety and approved resource limits take priority over simplicity. ` +
      `Use applicable ${skills} skills. Check algorithm, data structures, repeated work, allocations and invariants. ` +
      (task.designIssue ?? "Supply executable evidence.") + " " + milestonePrompt(task.refactor?.step) } };
  }

  async tool_call(event, ctx) {
    let task;
    try { task = ctx.agent?.kind === "sub" ? locateParent(ctx) : await this.taskFor(ctx); }
    catch (error) { return { block: true, reason: "Deadlion initialization failed: " + error.message }; }
    if (!task) return;
    if (task.refactor) {
      const reason = await authorizeRefactorTool(task, event, ctx, editPaths(event));
      if (reason) return { block: true, reason };
    }
    if (event.toolName === "lsp" && !this.semanticProbe(task) && event.input?.action !== "status")
      return { block: true, reason: "Approve project-native language servers with /deadlion setup." };
    if (task.designIssue && !await permitsDesignTool(event, ctx))
      return { block: true, reason: task.designIssue };
    if (task.semgrepTools?.includes(event.toolName))
      this.pendingLsp.set(event.toolCallId, { task: task.id, source: await hashTree(task) });
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

    if (!sub) await this.collectSemantic(task, event, ctx);
    if (!["edit", "write"].includes(event.toolName)) {
      event = await this.opaqueEdit(task, event, ctx);
      if (!event) return;
    }
    await this.writethrough(task, event, ctx, sub);
    if (!this.seen.has(task.id)) this.seen.set(task.id, new Set());
    const started = Date.now();
    if (started >= task.deadline || task.analysisMs <= 0) return;
    try { return await feedback(task, event, ctx, this.seen.get(task.id), this.semanticProbe(task) && hover, this.signal(ctx)); }
    catch (error) { return { additionalContext: "Deadlion incremental analysis NOT VERIFIED: " + error.message }; }
    finally { task.analysisMs = Math.max(0, task.analysisMs - (Date.now() - started)); }
  }

  async opaqueEdit(task, event, ctx) {
    if (!["bash", "eval", "python", "patch", "task"].includes(event.toolName) ||
        task.analysisMs < 2000 || Date.now() - (this.lastScan.get(task.id) ?? 0) < 1500) return;
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
        if (!sub) {
          task.semantic ??= {};
          const file = relative(task.root, resolve(ctx.cwd, path));
          if (!task.semantic[file] || item.diagnostics.errored) task.semantic[file] =
            { status: item.diagnostics.errored ? "FAIL" : "INCONCLUSIVE", server: item.diagnostics.server, output: item.diagnostics.messages, source: "omp:writethrough" };
          await persist(task);
        }
      }
    }
  }

  async turn_end(event, ctx) {
    if (ctx.agent?.kind === "sub") return;
    const task = await this.tasks.get(this.session(ctx));
    if (!task || terminal.has(task.state)) return;
    const usage = event.message?.usage;
    if (task.tokenLimit && (!usage || !(usage.totalTokens > 0))) {
      task.state = "INCOMPLETE";
      task.last = { status: "NOT VERIFIED", reason: "provider token usage unavailable" };
      await outcome(task, ctx);
      ctx.abort();
      return;
    }
    if (usage) {
      task.usage.reported = !!usage.totalTokens;
      task.usage.input += usage.input ?? 0;
      task.usage.cached += (usage.cacheRead ?? 0) + (usage.cacheWrite ?? 0);
      task.usage.output += usage.output ?? 0;
    }
    if (Date.now() >= task.deadline || task.tokenLimit && (task.usage.input + task.usage.cached + task.usage.output) >= task.tokenLimit) {
      task.state = "INCOMPLETE";
      await outcome(task, ctx);
      ctx.abort();
    } else await persist(task);
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
    this.selections.delete(key);
    await parkMilestone(task);
    if (task && !terminal.has(task.state)) await persist(task);
  }

  async session_stop(event, ctx) {
    if (ctx.agent?.kind === "sub") return;
    let task;
    try {
      task = await this.taskFor(ctx, "", false, !!ctx.sessionManager);
      if (!task) throw new Error("session has no recorded task baseline");
      const stop = event.last_assistant_message?.stopReason;
      if (["error", "aborted"].includes(stop)) task.state = stop === "error" ? "INCOMPLETE" : "CANCELLED";
      if (["INCOMPLETE", "CANCELLED"].includes(task.state)) {
        await outcome(task, ctx);
        ctx.abort?.();
        return;
      }
      task.last = await this.finalEvidence(task, this.signal(ctx, event.signal));
      task.receipts.push(task.last.receipt);
      if (["CANCELLED", "INCOMPLETE"].includes(task.state) || event.signal?.aborted) {
        if (event.signal?.aborted && task.state !== "INCOMPLETE") task.state = "CANCELLED";
        await outcome(task, ctx);
        return;
      }
      if (task.last.status === "PASS") {
        if (task.refactor) await completeMilestone(task, task.last);
        task.state = "VERIFIED";
        await outcome(task, ctx);
        return;
      }
      return await this.correction(task, event, ctx);
    } catch (error) {
      await this.failStop(task, ctx, event, error);
      ctx.abort?.();
    } finally {
      if (task && terminal.has(task.state)) {
        this.release(ctx, task);
        await parkMilestone(task);
      }
    }
  }

  async failStop(task, ctx, event, error) {
    if (task) {
      if (!["CANCELLED", "INCOMPLETE"].includes(task.state)) task.state = event.signal?.aborted ? "CANCELLED" : "BLOCKED";
      task.last = { status: "NOT VERIFIED", reason: error.message };
      await outcome(task, ctx);
    } else {
      ctx.ui?.notify("Deadlion BLOCKED: " + error.message, "error");
      if (process.env.DL_VERDICT_FILE) await save(process.env.DL_VERDICT_FILE, { state: "BLOCKED", reason: error.message });
    }
  }

  async finalEvidence(task, signal) {
    const previous = this.verified.get(task.id);
    this.verified.delete(task.id);
    if (!task.refactor && previous && !signal?.aborted && !task.policy.semgrepConfig && Date.now() < task.deadline &&
        previous.source === await hashTree(task) &&
        previous.receiptHash === digest(JSON.stringify(await read(previous.receipt)))) {
      await verifyToolInputs(task, { signal });
      if (!signal?.aborted) return previous;
    }
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
    const info = lspObservation(event);
    if (info) {
      const file = relative(task.root, resolve(ctx.cwd, info.file));
      task.semantic ??= {};
      // Tool diagnostics describe an observation. The gate obtains fresh native
      // diagnostics for required sources or known failures.
      if (task.semantic[file]?.status !== "FAIL" || info.status === "FAIL") task.semantic[file] = info;
      await persist(task);
    }
  }

  async correction(task, event, ctx) {
    const signature = digest(JSON.stringify([task.last.source, task.last.failures.map(f => [f.name, f.status])]));
    const unavailable = task.last.failures.some(f => /ENOENT|not found|missing executable|not installed/i.test(f.reason ?? ""));
    if (unavailable || event.signal?.aborted || task.corrections >= task.maxCorrections ||
        task.previous === signature || task.deadline <= Date.now() || task.analysisMs <= 0) {
      task.state = event.signal?.aborted ? "CANCELLED" : "BLOCKED";
      await outcome(task, ctx);
      ctx.abort?.();
      return;
    }
    task.previous = signature;
    task.corrections++;
    task.state = "DIRTY";
    await persist(task);
    const brief = task.last.failures.slice(0, 5).map(f => ({ name: f.name.slice(0,160), status: f.status, reason: f.reason.slice(0,220) }));
    return { decision: "block", reason: `Deadlion ${task.last.status}: ${JSON.stringify(brief)}. Report: ${task.last.receipt}` };
  }
}

export default function performance(pi) {
  const controller = new EngineeringSession(pi);
  if (pi.registerTool && pi.zod) pi.registerTool({
    name: "deadlion_verify", label: "Deadlion verification", description: "Measure the required baseline or run approved engineering checks.",
    parameters: pi.zod.object({}),
    async execute(_id, _args, signal, _update, ctx) {
      if (ctx.agent.kind === "sub") throw new Error("The main session owns verification.");
      const report = await controller.fullCheck(await controller.taskFor(ctx), signal, ctx);
      return { content: [{ type: "text", text: JSON.stringify({ status: report.status, receipt: report.receipt, scaling: report.scaling, failures: report.failures?.slice(0, 5) }) }],
        details: { receipt: report.receipt } };
    },
  });
  pi.on("before_agent_start", controller.before_agent_start.bind(controller));
  pi.on("tool_call", controller.tool_call.bind(controller));
  pi.on("before_subagent_spawn", controller.before_subagent_spawn.bind(controller));
  pi.on("tool_result", controller.tool_result.bind(controller));
  pi.on("turn_end", controller.turn_end.bind(controller));
  pi.on("agent_end", controller.agent_end.bind(controller));
  pi.on("session_shutdown", controller.session_shutdown.bind(controller));
  pi.on("session_stop", controller.session_stop.bind(controller));
  commands(pi, controller.taskFor.bind(controller), controller.fullCheck.bind(controller), controller.transition.bind(controller));
}
