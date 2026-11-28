import { spawn } from "node:child_process";

function collect(child, limit, overflow) {
  let bytes = 0;
  const buffers = { stdout: [], stderr: [] };
  for (const [stream, output] of Object.entries(buffers)) {
    child[stream].on("data", chunk => {
      bytes += chunk.length;
      if (bytes <= limit) output.push(chunk);
      else overflow();
    });
  }
  return () => Object.fromEntries(Object.entries(buffers).map(([stream, output]) =>
    [stream, Buffer.concat(output).toString()]));
}

function closePipes(child) {
  child.stdout.destroy();
  child.stderr.destroy();
  child.unref();
}

// Fedora process groups include the analyzer's compiler and worker children.
export function execute(argv, { cwd, env = process.env, signal, timeout = 12000, maxBytes = 8 << 20 }) {
  if (signal?.aborted) return Promise.reject(new Error("CANCELLED"));
  if (!(timeout > 0)) return Promise.reject(new Error("analysis budget exhausted"));
  return new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), {
      cwd, env, detached: true, stdio: ["ignore", "pipe", "pipe"],
    });
    let reason;
    let grace;
    let fallback;
    const send = name => {
      if (!child.pid) return;
      try { process.kill(-child.pid, name); }
      catch (error) { if (error.code !== "ESRCH") finish(error); }
    };
    let finished = false;
    function finish(error, code) {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      clearTimeout(grace);
      clearTimeout(fallback);
      signal?.removeEventListener("abort", abort);
      if (error) reject(error);
      else resolve({ code, ...output() });
    }
    const stop = message => {
      if (reason || finished) return;
      reason = message;
      send("SIGTERM");
      if (finished) return;
      grace = setTimeout(() => send("SIGKILL"), 200);
      fallback = setTimeout(() => {
        closePipes(child);
        finish(new Error(reason));
      }, 500);
    };
    const abort = () => stop("CANCELLED");
    const timer = setTimeout(() => stop("analysis timeout"), timeout);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    const output = collect(child, maxBytes, () => stop("analysis output limit exceeded"));
    child.once("error", error => finish(error));
    child.once("close", (code, signum) => {
      if (reason) send("SIGKILL");
      finish(reason || signum ? new Error(reason ?? signum) : undefined, code);
    });
  });
}
