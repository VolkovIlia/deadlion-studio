import { spawn } from "node:child_process";

// Fedora process groups include the analyzer's compiler and worker children.
export function execute(argv, { cwd, env = process.env, signal, timeout = 12000, maxBytes = 8 << 20 }) {
  if (signal?.aborted) return Promise.reject(new Error("CANCELLED"));
  if (!(timeout > 0)) return Promise.reject(new Error("analysis budget exhausted"));
  return new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), {
      cwd, env, detached: true, stdio: ["ignore", "pipe", "pipe"],
    });
    let reason;
    let bytes = 0;
    const output = { stdout: [], stderr: [] };
    const stop = message => {
      reason = message;
      if (child.pid) {
        try { process.kill(-child.pid, "SIGKILL"); }
        catch (error) { if (error.code !== "ESRCH") reject(error); }
      }
    };
    const abort = () => stop("CANCELLED");
    const timer = setTimeout(() => stop("analysis timeout"), timeout);
    signal?.addEventListener("abort", abort, { once: true });
    for (const stream of Object.keys(output)) {
      child[stream].on("data", chunk => {
        bytes += chunk.length;
        if (bytes <= maxBytes) output[stream].push(chunk);
        else if (!reason) stop("analysis output limit exceeded");
      });
    }
    child.once("error", reject);
    child.once("close", (code, signum) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      if (reason || signum) reject(new Error(reason ?? signum));
      else resolve({ code, stdout: Buffer.concat(output.stdout).toString(),
        stderr: Buffer.concat(output.stderr).toString() });
    });
  });
}
