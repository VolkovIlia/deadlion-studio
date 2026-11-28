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

MANIFESTS = {"Cargo.toml", "package.json", "go.mod", "pyproject.toml", "pom.xml",
             "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "Makefile",
             "requirements.txt", "pytest.ini", "setup.cfg", "gradlew"}
LSP_CONFIG = {prefix + "lsp." + suffix for prefix in ("", ".") for suffix in ("json", "yml", "yaml")}
CONFIG = MANIFESTS | LSP_CONFIG | {"Cargo.lock", "go.sum", "package-lock.json", "pnpm-lock.yaml", "uv.lock",
                      "ruff.toml", ".ruff.toml", ".clang-tidy", "compile_commands.json",
                      "detekt.yml", "detekt.yaml", "tsconfig.json", ".eslintrc", ".gitattributes",
                      "gradle-wrapper.properties", "gradle.properties", ".gitignore"}
LANGUAGES = {".rs": "Rust", ".py": "Python", ".go": "Go", ".c": "C", ".cpp": "C++", ".cc": "C++",
             ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".ts": "TypeScript",
             ".tsx": "TypeScript", ".js": "JavaScript", ".mjs": "JavaScript"}


def identity(path):
    stat = Path(path).stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_ctime_ns]


def inventory(venv, root=None):
    result = {}
    root = root or Path.cwd()
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
    commands = [(policy.get("tests"), root), ((policy.get("profile") or {}).get("argv"), root)]
    commands.extend((step["argv"], root / step.get("cwd", ".")) for step in policy.get("checks", []))
    for argv, cwd in commands:
        if not argv:
            continue
        command = shutil.which(str(cwd / argv[0])) if "/" in argv[0] else shutil.which(argv[0])
        paths = [Path(p) for p in argv[1:] if os.path.isabs(p) and not Path(p).is_relative_to(root)]
        if len(argv) > 1 and Path(argv[0]).name in {"python", "python3", "node", "bash", "sh", "ruby"} and not argv[1].startswith("-"):
            paths.append(cwd / argv[1])
        if command:
            paths.append(Path(command).absolute())
        for path in paths:
            if path.is_file():
                inputs[str(path)] = identity(path)
    db = os.getenv("DL_COMPILE_COMMANDS")
    if db:
        inputs[db] = hashlib.sha256(Path(db).read_bytes()).hexdigest()
    config_roots = [root / name for name in (".", ".omp", ".pi", ".claude")]
    config_roots.extend(Path.home() / name for name in (".", ".omp/agent", ".pi/agent", ".claude"))
    if profile := os.getenv("PI_CODING_AGENT_DIR"):
        config_roots.append(Path(profile))
    configs = {folder / name for folder in config_roots for name in LSP_CONFIG}
    configs.update(root / name for name in ("compile_commands.json", "build/compile_commands.json"))
    for path in sorted(configs):
        if path.is_file():
            with path.open("rb") as handle:
                inputs[str(path)] = hashlib.file_digest(handle, "sha256").hexdigest()
    for name in policy.get("verificationInputs", []):
        path = root / name
        if path.resolve() != path or not path.exists():
            raise ValueError(f"verification input unavailable or a symlink: {name}")
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for item in files:
            if item.is_symlink():
                raise ValueError(f"symlink in verification inputs: {item}")
            if item.is_file():
                with item.open("rb") as handle:
                    inputs[str(item)] = hashlib.file_digest(handle, "sha256").hexdigest()
    return inputs


def project_files():
    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True)
    if probe.returncode == 0:
        root = Path(os.fsdecode(probe.stdout).rstrip("\n")).resolve()
        status = subprocess.check_output(["git", "--no-optional-locks", "status", "--porcelain=v1", "-z"], cwd=root)
        paths = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root)
        return root, True, bool(status), sorted(set(map(os.fsdecode, filter(None, paths.split(b"\0")))))
    root = Path.cwd().resolve()
    names = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "target", "build", "__pycache__"}]
        names.extend(str((Path(folder) / file).relative_to(root)) for file in files)
    return root, False, False, sorted(names)


def test_command(root, paths, manifests):
    if "Makefile" in manifests and any(row.startswith("test:") for row in (root / "Makefile").read_text(errors="replace").splitlines()):
        return ["make", "test"]
    if "Cargo.toml" in manifests:
        return ["cargo", "test", "--workspace", "--offline"]
    if "go.mod" in manifests:
        return ["go", "test", "-count=1", "-json", "./..."]
    if "package.json" in manifests and json.loads((root / "package.json").read_bytes()).get("scripts", {}).get("test"):
        return ["npm", "test"]
    if "gradlew" in manifests:
        return ["./gradlew", "--offline", "test"]
    if "pom.xml" in manifests:
        return ["mvn", "--offline", "test"]
    if any(Path(path).name.startswith("test_") and path.endswith(".py") for path in paths):
        return ["python3", "-m", "pytest", "-q"]


def discover():
    root, git, dirty, names = project_files()
    paths = [Path(name) for name in names]
    configs = [p for p in paths if p.name in CONFIG or p.parts[0] in {".omp", ".performance"} or
               p.name.startswith(("eslint.config.", ".eslintrc."))]
    approved = {}
    for path in configs:
        item = root / path
        if item.resolve() == item and item.is_file() and item.stat().st_size <= 4 << 20:
            with item.open("rb") as handle:
                approved[str(path)] = hashlib.file_digest(handle, "sha256").hexdigest()
    manifests = [p for p in approved if Path(p).name in MANIFESTS]
    suites = discover_tests(root, paths, manifests)
    tests = next((suite["argv"] for suite in suites if suite["cwd"] == "."), None)
    tools = [name for name, info in inventory(".venv", root).items() if info["status"] == "installed"]
    policy = {"trustProject": True, "native": True, "verificationInputs": list(approved)} if approved else {
        "trustProject": True, "native": True}
    if tests:
        policy["tests"] = tests
    fingerprint = hashlib.sha256(json.dumps([str(root), policy, approved, suites], sort_keys=True).encode()).hexdigest()
    return dict(root=str(root), git=git, dirty=dirty, manifests=manifests, tools=tools, policy=policy,
                languages=sorted({LANGUAGES[p.suffix] for p in paths if p.suffix in LANGUAGES}),
                components=sorted({str(Path(p).parent) for p in manifests}), fingerprint=fingerprint, suites=suites,
                benchmarks=[p for p in names if "benchmark" in p or "/benches/" in p][:40],
                contracts=[p for p in approved if p.startswith(".performance/") and p.endswith("/contract.json")],
                generated=[p for p in names if "generated" in p.split("/")][:40])


def discover_tests(root, paths, manifests):
    by_directory = {}
    python_tests = set()
    for name in manifests:
        path = Path(name)
        by_directory.setdefault(path.parent, []).append(path.name)
    directories = set(by_directory)
    directories.add(Path("."))
    for path in paths:
        if path.suffix == ".py" and path.name.startswith("test_"):
            python_tests.add(next((parent for parent in path.parents if parent in directories), Path(".")))
    suites = []
    for directory in sorted(directories):
        markers = by_directory.get(directory, [])
        command = test_command(root / directory, ["test_fixture.py"] if directory in python_tests else [], markers)
        if command:
            suites.append(dict(id=str(len(suites) + 1), argv=command, cwd=str(directory),
                               proposedScope=[str(directory)] if directory != Path(".") else [],
                               reason=", ".join(markers) or "Python test filenames"))
    return suites


if __name__ == "__main__":
    if sys.argv[1:] == ["--discover"]:
        print(json.dumps(discover()))
        sys.exit(0)
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
