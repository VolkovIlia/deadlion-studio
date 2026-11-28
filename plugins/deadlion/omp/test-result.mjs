import { basename } from "node:path";

export function testResult(argv, output, requireCount = false) {
  const command = basename(argv[0]);
  const pytest = /^(?:py\.test|pytest)(?:-[\d.]+)?$/.test(command) ||
    /^(?:python|pypy)/.test(command) && argv.includes("-m") && argv.includes("pytest");
  const text = output.replace(/\x1b\[[\d;]*m/g, "");
  if (/^(?:true|echo|printf|:)$/.test(command)) return { source: "no-op", passed: 0, incomplete: true };
  if (command === "go" && argv.includes("-json")) return goSummary(text);
  if (/^# (?:tests|pass) \d+/m.test(text)) return tapSummary(text);
  if (!requireCount && !pytest && command !== "cargo" && !/\bTests(?: run)?:/.test(text) && command !== "go")
    return { source: "operator-attested", incomplete: false };
  return runnerSummary(text);
}

function tapSummary(text) {
  const count = name => [...text.matchAll(new RegExp("^# " + name + " (\\d+)", "gm"))]
    .reduce((total, [, value]) => total + Number(value), 0);
  return { source: "TAP summary", passed: count("pass"),
    incomplete: count("skip(?:ped)?") + count("todo") + count("fail") + count("cancelled") > 0 };
}

function runnerSummary(text) {
  const passed = [...text.matchAll(/\b(\d+) passed\b/g)].reduce((sum, match) => sum + Number(match[1]), 0);
  const goPackages = [...text.matchAll(/^ok\s+\S+\s+[\d.]+s/gm)].length;
  const maven = [...text.matchAll(/Tests run: (\d+), Failures: 0, Errors: 0, Skipped: 0/g)];
  return { source: "runner summary", passed: passed + goPackages + maven.reduce((sum, match) => sum + Number(match[1]), 0),
    incomplete: /\b[1-9]\d* (?:skipped|ignored|deselected|filtered out|xfailed|xpassed|failed|errors?)\b|Skipped: [1-9]|^ok\s+\S+\s+\(cached\)/im.test(text) };
}

function goSummary(text) {
  let passed = 0;
  let incomplete = false;
  for (const line of text.split("\n")) {
    if (!line.startsWith("{")) continue;
    let event;
    try { event = JSON.parse(line); } catch { return { source: "Go JSON", passed, incomplete: true }; }
    if (event.Test && event.Action === "pass") passed++;
    if (event.Test && event.Action === "skip" || event.Action === "fail") incomplete = true;
  }
  return { source: "Go JSON", passed, incomplete };
}
