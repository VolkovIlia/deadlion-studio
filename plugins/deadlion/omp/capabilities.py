"""Inspect analyzer locations without launching project-owned executables."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

NAMES = ("omp", "python3", "ruff", "ast-grep", "semgrep", "clangd", "clang-tidy", "infer",
         "cargo", "rust-analyzer", "cargo-clippy", "staticcheck", "gopls", "jdtls", "pmd",
         "kotlin-language-server", "kotlin-lsp", "pylsp", "detekt", "eslint", "typescript-language-server", "pyright-langserver",
         "perf", "memray", "heaptrack", "scalene", "valgrind", "jfr", "bwrap")


def identity(path):
    stat = Path(path).stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_ctime_ns]


def inventory(venv):
    result = {}
    root = Path.cwd()
    for name in NAMES:
        path = shutil.which(name)
        local = [root / venv / "bin" / name, root / "node_modules/.bin" / name]
        candidates = [str(p) for p in local if p.is_file() and os.access(p, os.X_OK)]
        item = dict(status="installed" if path or candidates else "unavailable",
                    path=path, project={p: identity(p) for p in candidates})
        if path:
            item["identity"] = identity(path)
        result[name] = item
    return result


def approval_inputs(policy):
    inputs = {}
    root = Path.cwd()
    commands = [policy.get("tests"), (policy.get("profile") or {}).get("argv")]
    commands.extend(step["argv"] for step in policy.get("checks", []))
    for argv in commands:
        if not argv:
            continue
        command = shutil.which(argv[0])
        paths = [Path(p) for p in argv[1:] if os.path.isabs(p)]
        if command:
            paths.append(Path(command).absolute())
        for path in paths:
            if not path.is_relative_to(root) and path.is_file():
                inputs[str(path)] = identity(path)
    db = os.getenv("DL_COMPILE_COMMANDS")
    if db:
        inputs[db] = hashlib.sha256(Path(db).read_bytes()).hexdigest()
    return inputs


if __name__ == "__main__":
    core = Path(__file__).resolve().parents[1] / "skills"
    h = hashlib.sha256()
    for parent in ("performance", "suckless-code"):
        for path in sorted((core / parent).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                h.update(str(path.relative_to(core)).encode() + b"\0" + path.read_bytes())
    integration = hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parent.iterdir()):
        if path.is_file():
            integration.update(path.name.encode() + b"\0" + path.read_bytes())
    binary = shutil.which("omp")
    version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=2).stdout.strip() if binary else None
    policy = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(dict(core=h.hexdigest(), integration=integration.hexdigest(), inputs=approval_inputs(policy),
                          tools=inventory(policy.get("projectVenv", ".venv")),
                          omp=version)))
