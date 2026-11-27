"""Review diagnostics from installed project-native tools. Run only on trusted projects."""

import json
from pathlib import Path
import shutil
import subprocess


def review(files, coverage):
    jobs = set()
    for file in files:
        specs = {
            ".rs": (("Cargo.toml",), "cargo"),
            ".go": (("go.mod",), "staticcheck"),
            ".java": (("pom.xml", "build.gradle", "build.gradle.kts"), "pmd"),
            ".kt": (("detekt.yml", "config/detekt/detekt.yml"), "detekt"),
        }
        for suffix in (".c", ".cc", ".cpp", ".cxx"):
            specs[suffix] = (("compile_commands.json",), "clang-tidy")
        for suffix in (".ts", ".js"):
            specs[suffix] = (
                ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs"),
                "eslint",
            )
        if file.suffix not in specs:
            continue
        markers, tool = specs[file.suffix]
        hit = next(
            (
                (p, m)
                for p in file.resolve().parents
                for m in markers
                if (p / m).is_file()
            ),
            None,
        )
        if not hit:
            coverage[tool] = coverage.get(tool, "no matching project configuration")
            continue
        root, marker = hit
        local = root / "node_modules/.bin/eslint"
        binary = (
            str(local) if tool == "eslint" and local.is_file() else shutil.which(tool)
        )
        if not binary:
            coverage[tool] = "not installed"
            continue
        coverage[tool] = "selected"
        jobs.add(
            (
                tool,
                binary,
                root,
                marker,
                str(file.resolve()) if tool not in ("staticcheck", "cargo") else "",
            )
        )
    for tool, binary, root, marker, file in sorted(jobs):
        if tool in ("eslint", "pmd", "detekt"):
            yield from project_findings(tool, binary, root, marker, file)
            continue
        if tool == "cargo":
            cmd = [
                "cargo",
                "clippy",
                "--offline",
                "--message-format=json",
                "--",
                "-W",
                "clippy::perf",
            ]
        elif tool == "staticcheck":
            cmd = [tool, "-checks", "SA6*", "-f", "json", "./..."]
        else:
            cmd = [tool, "-p", str(root), "--checks=-*,performance-*", file]
        r = subprocess.run(cmd, cwd=root, timeout=60, capture_output=True, text=True)
        if r.returncode not in ((0, 1) if tool == "staticcheck" else (0,)):
            raise ValueError(f"{tool} failed: {(r.stderr or r.stdout)[-400:]}")
        if tool == "clang-tidy":
            import re

            for path, line, message, rule in re.findall(
                r"^(.+?):(\d+):\d+: warning: (.+) \[(performance-[^\]]+)\]",
                r.stdout,
                re.M,
            ):
                yield diagnostic(path, int(line), rule, message)
            continue
        count = 0
        for line in r.stdout.splitlines():
            item = json.loads(line)
            if tool == "cargo":
                if item.get("reason") != "compiler-message":
                    continue
                msg = item["message"]
                rule = (msg.get("code") or {}).get("code", "")
                if not rule.startswith("clippy::"):
                    continue
                span = next((s for s in msg["spans"] if s["is_primary"]), None)
                if span:
                    yield diagnostic(
                        str(root / span["file_name"]),
                        span["line_start"],
                        rule,
                        msg["message"],
                    )
            else:
                pos = item["location"]
                count += 1
                yield diagnostic(
                    pos["file"], pos["line"], item["code"], item["message"]
                )
        if tool == "staticcheck" and r.returncode and not count:
            raise ValueError("staticcheck produced no diagnostics on failure")


def project_findings(tool, binary, root, marker, file):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "detekt.sarif"
        if tool == "pmd":
            cmd = [
                binary,
                "check",
                "-d",
                file,
                "-R",
                "category/java/performance.xml",
                "-f",
                "json",
                "--no-cache",
            ]
            codes = (0, 4)
        elif tool == "detekt":
            cmd = [
                binary,
                "--input",
                file,
                "--config",
                str(root / marker),
                "--report",
                f"sarif:{report}",
            ]
            codes = (0, 2)
        else:
            cmd = [binary, "--format", "json", file]
            codes = (0, 1)
        result = subprocess.run(
            cmd, cwd=root, timeout=60, capture_output=True, text=True
        )
        if result.returncode not in codes:
            raise ValueError(f"{tool} failed: {(result.stderr or result.stdout)[-400:]}")
        payload = json.loads(report.read_bytes() if tool == "detekt" else result.stdout)
        if tool == "pmd":
            if any(payload.get(k) for k in ("processingErrors", "configurationErrors")):
                raise ValueError("PMD reported an analysis error")
            for item in payload["files"]:
                for d in item["violations"]:
                    yield diagnostic(
                        item["filename"], d["beginline"], d["rule"], d["description"]
                    )
        elif tool == "detekt":
            for run in payload["runs"]:
                for d in run["results"]:
                    if ".performance." not in d["ruleId"]:
                        continue
                    region = d["locations"][0]["physicalLocation"]["region"]
                    yield diagnostic(
                        file, region["startLine"], d["ruleId"], d["message"]["text"]
                    )
        else:
            for item in payload:
                for d in item["messages"]:
                    if d.get("fatal"):
                        raise ValueError(d["message"])
                    if d.get("ruleId"):
                        yield diagnostic(
                            item["filePath"], d["line"], d["ruleId"], d["message"]
                        )


def diagnostic(path, line, rule, message):
    return dict(
        file=path,
        line=line,
        rule=rule,
        explanation=message,
        confidence="native diagnostic",
        severity="INFO",
        confirm="Check semantics and compare the affected workload with dl-perf scale.",
    )


def infer_cost(files):
    """Capture the selected Java sources and read Cost's bounds from this execution."""
    import tempfile

    if not files or any(p.suffix != ".java" for p in files):
        raise ValueError("--infer-cost requires explicit Java sources")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)/"infer-out"
        subprocess.run(["infer","run","--cost-only","--results-dir",str(out),"--","javac",
                        "-proc:none","-d",tmp,*[str(p.resolve()) for p in files]],
                       check=True,capture_output=True,timeout=120)
        report = json.loads((out/"costs-report.json").read_bytes())
    for entry in report:
        cost = entry.get("exec_cost",{})
        human = cost.get("hum",{})
        known = type(cost.get("degree")) is int and cost["degree"]>=0 and bool(human.get("big_o"))
        loc = entry["loc"]
        finding = diagnostic(loc["file"],loc["lnum"],"infer-cost",
                             f"{entry['procedure_id']} {human.get('big_o','unknown')}")
        finding.update(confidence="STATICALLY BOUNDED" if known else "INCONCLUSIVE",
                       computational_model="Infer Cost execution steps on captured Java bytecode",
                       polynomial=human.get("hum_polynomial"),assumptions="Modeled calls and inferred loop bounds")
        yield finding
