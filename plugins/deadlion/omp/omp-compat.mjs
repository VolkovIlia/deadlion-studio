const verified = new Map([
  ["omp/19.2.1", { core: "VERIFIED", lifecycle: "VERIFIED", rpc: "VERIFIED",
    lsp: "PARTIALLY VERIFIED", subagents: "VERIFIED", evolution: "VERIFIED" }],
  ["omp/19.2.0", { core: "VERIFIED", lifecycle: "VERIFIED", rpc: "VERIFIED",
    lsp: "PARTIALLY VERIFIED", subagents: "VERIFIED", evolution: "VERIFIED" }],
]);

export function compatibility(version) {
  return verified.get(version) ?? { core: "NOT VERIFIED", lifecycle: "NOT VERIFIED", rpc: "NOT VERIFIED",
    lsp: "NOT VERIFIED", subagents: "NOT VERIFIED", evolution: "NOT VERIFIED" };
}

export function lifecycleContext(pi, ctx) {
  return typeof pi.appendEntry === "function" && typeof ctx.abort === "function" &&
    typeof ctx.sessionManager?.getSessionId === "function" && typeof ctx.sessionManager?.getBranch === "function";
}
