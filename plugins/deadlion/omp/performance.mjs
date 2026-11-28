import { randomUUID } from "node:crypto";
import { commands } from "./commands.mjs";
import { join, relative, resolve } from "node:path";
import { execute } from "./process.mjs";
import { approvalHash, digest, incremental, inventory, openTask, persist, read, save, scripts, snapshot } from "./evidence.mjs";
import { editPaths, feedback, lspObservation, scalingSummary } from "./diagnostics.mjs";
import { diagnostics, hover, permitsInspection } from "./lsp.mjs";
import { semgrepResult } from "./semgrep.mjs";
import { verify } from "./gate.mjs";

// Factories are rebound by OMP. Use a shared lookup only for unambiguous
// parent identities in this process. The main gate always checks disk again.
const owners = new Map();
function locateParent(ctx) {
  const matches = [...owners.values()].filter(o => o.cwd === ctx.cwd && o.agent === ctx.agent.parentId);
  return matches.length === 1 ? matches[0].task : undefined;
}

const entry = "deadlion.engineering.task";
const terminal = new Set(["VERIFIED", "BLOCKED", "CANCELLED", "INCOMPLETE"]);
const hashTree = async task => digest(JSON.stringify(await snapshot(task.cwd)));

async function outcome(task, ctx) {
  await persist(task);
  const message = `Deadlion ${task.state}: ${task.last?.status ?? "NOT VERIFIED"}. ${task.last?.receipt ?? task.directory}`;
  ctx.ui?.notify(message, task.state === "VERIFIED" ? "info" : "warning");
  if (process.env.DL_VERDICT_FILE)
    await save(process.env.DL_VERDICT_FILE, { state: task.state, task: task.id, report: task.last });
}

async function design(task) {
  if (task.mode === "Standard" && !task.contract) return;
  if (task.contractIssue) return task.contractIssue;
  const baseline = await read(join(task.directory, "baseline.json"));
  const contracts = Object.keys(baseline.files).filter(p => /^\.performance\/.*\/contract\.json$/.test(p));
  const path = task.approved ?? (contracts.length === 1 && resolve(task.root, contracts[0]));
  if (!path) return "Provide an approved performance contract with alternatives, verification workload and baseline.";
  const result = await execute([join(scripts, "dl-contract"), path], { cwd: task.cwd, timeout: 4000 });
  if (result.code) return "dl-contract: " + result.stdout.slice(0, 350);
  const contract = await read(path);
  if (!contract.benchmark?.baseline) return "The approved contract needs an executable baseline.";
  if (task.mode === "Research" && (!contract.scaling || !contract.computational_model))
    return "Research requires a computational model and scaling workload.";
  if (!task.baselineReceipt) return "Run deadlion_verify before implementation to measure the approved baseline.";
  if (task.mode === "Evolution" && !task.experiment) return "Use dl-evolve with a bounded experiment and independent evaluator.";
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
  session(ctx) { return ctx.sessionManager?.getSessionId() ?? ctx.cwd; }

  async taskFor(ctx, prompt = "", newRequest = false, existingOnly = false) {
    const key = this.session(ctx);
    let task = await this.tasks.get(key);
    if (!task) {
      const previous = ctx.sessionManager?.getBranch().filter(e => e.type === "custom" && e.customType === entry).at(-1);
      if (previous) task = await read(join(previous.data.directory, "task.json"));
    }
    if (!task && existingOnly) return;
    if (!task || newRequest && task.state === "VERIFIED") {
      const promise = openTask(ctx, prompt);
      this.tasks.set(key, promise);
      task = await promise;
      this.pi.appendEntry?.(entry, { directory: task.directory, id: task.id });
    }
    this.tasks.set(key, task);
    return task;
  }

  semanticProbe() { return this.pi.getActiveTools?.().includes("lsp") ? diagnostics : undefined; }
  async fullCheck(task, signal) {
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
    const report = await verify(task, signal, task.analysisMs, this.semanticProbe());
    if (report.status === "PASS") this.verified.set(task.id, report);
    await persist(task);
    return report;
  }

  async before_agent_start(event, ctx) {
    if (ctx.agent?.kind === "sub") return;
    const task = await this.taskFor(ctx, event.prompt, true);
    task.semgrepTools = this.pi.getActiveTools?.().filter(name => /semgrep/i.test(name)) ?? [];
    owners.set(this.session(ctx), { cwd: ctx.cwd, agent: ctx.agent?.id, task });
    clearTimeout(this.timers.get(this.session(ctx)));
    const timer = setTimeout(async () => {
      if (terminal.has(task.state)) return;
      task.state = "INCOMPLETE";
      task.last = { status: "NOT VERIFIED", reason: "wall-clock budget exhausted" };
      try { await outcome(task, ctx); } finally { ctx.abort?.(); }
    }, Math.max(1, task.deadline - Date.now()));
    timer.unref();
    this.timers.set(this.session(ctx), timer);
    task.designIssue = await design(task);
    task.state = task.designIssue ? "DESIGN" : "IMPLEMENTATION";
    await persist(task);
    const skills = task.mode === "Standard" ? "workflow, unix-design, build and verify" :
      "workflow, unix-design, decompose, write-plan, performance, build and verify";
    return { message: { customType: "deadlion.policy", display: false,
      content: `Deadlion ${task.mode} (${task.kind}). Correctness, safety and approved resource limits take priority over simplicity. ` +
      `Use applicable ${skills} skills. ` + (task.designIssue ?? "Supply executable evidence.") } };
  }

  async tool_call(event, ctx) {
    let task;
    try { task = ctx.agent?.kind === "sub" ? locateParent(ctx) : await this.taskFor(ctx); }
    catch (error) { return { block: true, reason: "Deadlion initialization failed: " + error.message }; }
    if (!task) return;
    if (task.designIssue && !["read", "grep", "find", "ls", "deadlion_verify"].includes(event.toolName)) {
      const paths = editPaths(event);
      const docs = ["edit", "write"].includes(event.toolName) && paths.length && paths.every(p => p.endsWith(".md"));
      const inspect = event.toolName === "lsp" && await permitsInspection(ctx.cwd, event.input).catch(() => false);
      if (!docs && !inspect) return { block: true, reason: task.designIssue };
    }
    if (event.toolName === "lsp" && event.input?.action === "diagnostics" || task.semgrepTools?.includes(event.toolName))
      this.pendingLsp.set(event.toolCallId, await hashTree(task));
  }

  async tool_result(event, ctx) {
    const sub = ctx.agent?.kind === "sub";
    const task = sub ? locateParent(ctx) : await this.taskFor(ctx);
    if (!task) return;
    if (sub) await save(join(task.directory, "sub-" + randomUUID() + ".json"), {
      agent: ctx.agent, tool: event.toolName, paths: editPaths(event), error: event.isError });

    if (!sub) await this.collectSemantic(task, event, ctx);
    const direct = ["edit", "write"].includes(event.toolName);
    if (!direct) {
      if (!["bash", "eval", "python", "patch", "task"].includes(event.toolName) ||
          task.analysisMs < 2000 || Date.now() - (this.lastScan.get(task.id) ?? 0) < 1500) return;
      this.lastScan.set(task.id, Date.now());
      const paths = await incremental(task);
      event = { ...event, input: { paths } };
    }
    await this.writethrough(task, event, ctx, sub);
    if (!this.seen.has(task.id)) this.seen.set(task.id, new Set());
    const started = Date.now();
    if (started >= task.deadline || task.analysisMs <= 0) return;
    try { return await feedback(task, event, ctx, this.seen.get(task.id), this.semanticProbe() && hover); }
    catch (error) { return { additionalContext: "Deadlion incremental analysis NOT VERIFIED: " + error.message }; }
    finally { task.analysisMs = Math.max(0, task.analysisMs - (Date.now() - started)); }
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
          task.semantic[relative(task.root, resolve(ctx.cwd, path))] =
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
    if (ctx.agent?.kind === "sub" || event.willContinue) return;
    const task = await this.tasks.get(this.session(ctx));
    const last = event.messages?.filter(m => m.role === "assistant").at(-1);
    if (!task || terminal.has(task.state) || !["aborted","error"].includes(last?.stopReason)) return;
    task.state = last.stopReason === "aborted" ? "CANCELLED" : "INCOMPLETE";
    await outcome(task, ctx);
  }

  async session_shutdown(_event, ctx) {
    clearTimeout(this.timers.get(this.session(ctx)));
    owners.delete(this.session(ctx));
    const task = await this.tasks.get(this.session(ctx));
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
      task.last = await this.finalEvidence(task, event.signal);
      task.receipts.push(task.last.receipt);
      if (task.state === "INCOMPLETE" || event.signal?.aborted) {
        if (event.signal?.aborted && task.state !== "INCOMPLETE") task.state = "CANCELLED";
        await outcome(task, ctx);
        return;
      }
      if (task.last.status === "PASS") {
        task.state = "VERIFIED";
        await outcome(task, ctx);
        return;
      }
      return await this.correction(task, event, ctx);
    } catch (error) {
      if (task) {
        task.state = "BLOCKED";
        task.last = { status: "NOT VERIFIED", reason: error.message };
        await outcome(task, ctx);
      } else {
        ctx.ui?.notify("Deadlion BLOCKED: " + error.message, "error");
        if (process.env.DL_VERDICT_FILE) await save(process.env.DL_VERDICT_FILE, { state: "BLOCKED", reason: error.message });
      }
      ctx.abort?.();
    }
  }

  async finalEvidence(task, signal) {
    const previous = this.verified.get(task.id);
    this.verified.delete(task.id);
    if (previous && !task.policy.semgrepConfig && Date.now() < task.deadline && previous.source === await hashTree(task) &&
        previous.receiptHash === digest(JSON.stringify(await read(previous.receipt))) &&
        (!task.approved || task.approvalHash === await approvalHash(task)) &&
        JSON.stringify(task.tools) === JSON.stringify(await inventory(task.root, task.policy))) return previous;
    return verify(task, signal, 20000, this.semanticProbe());
  }

  async collectSemantic(task, event, ctx) {
    if (task.semgrepTools?.includes(event.toolName)) {
      const data = semgrepResult(event);
      const source = this.pendingLsp.get(event.toolCallId);
      this.pendingLsp.delete(event.toolCallId);
      if (data && source === await hashTree(task)) {
        task.semgrep = { source, data };
        await persist(task);
      }
    }
    const info = lspObservation(event);
    if (info) {
      const sourceHash = await hashTree(task);
      const file = relative(task.root, resolve(ctx.cwd, info.file));
      if (this.pendingLsp.get(event.toolCallId) === sourceHash) {
        task.semantic ??= {};
        task.semantic[file] = { ...info, sourceHash };
        await persist(task);
      }
      this.pendingLsp.delete(event.toolCallId);
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
      const report = await controller.fullCheck(await controller.taskFor(ctx), signal);
      return { content: [{ type: "text", text: JSON.stringify({ status: report.status, receipt: report.receipt, scaling: report.scaling, failures: report.failures?.slice(0, 5) }) }],
        details: { receipt: report.receipt } };
    },
  });
  pi.on("before_agent_start", controller.before_agent_start.bind(controller));
  pi.on("tool_call", controller.tool_call.bind(controller));
  pi.on("tool_result", controller.tool_result.bind(controller));
  pi.on("turn_end", controller.turn_end.bind(controller));
  pi.on("agent_end", controller.agent_end.bind(controller));
  pi.on("session_shutdown", controller.session_shutdown.bind(controller));
  pi.on("session_stop", controller.session_stop.bind(controller));
  commands(pi, controller.taskFor.bind(controller), controller.fullCheck.bind(controller));
}
