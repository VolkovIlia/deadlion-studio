"""Fingerprint the worktree and index independently of the current HEAD."""

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


def git(*args):
    return subprocess.run(["git", "--no-optional-locks", *args], capture_output=True)


def unmanaged(root):
    skip = {".git", ".omp", "__pycache__", "node_modules", ".venv", "target", "build"}
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(set(dirs) - skip)
        for name in files:
            yield str((Path(directory) / name).relative_to(root))


def fingerprint(path):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(mode):
        return ["link", os.readlink(path)]
    if stat.S_ISREG(mode):
        with path.open("rb") as handle:
            return [mode, hashlib.file_digest(handle, "sha256").hexdigest()]
    return ["special", mode]


def snapshot():
    located = git("rev-parse", "--show-toplevel")
    root = Path(os.fsdecode(located.stdout).rstrip("\n")) if not located.returncode else Path.cwd()
    index = {}
    base = None
    if located.returncode:
        names = unmanaged(root)
    else:
        os.chdir(root)
        base = git("rev-parse", "--verify", "HEAD").stdout.decode().strip() or None
        tracked = git("ls-files", "--stage", "-z")
        extra = git("ls-files", "--others", "--exclude-standard", "-z")
        tracked.check_returncode()
        extra.check_returncode()
        for entry in filter(None, tracked.stdout.split(b"\0")):
            info, name = entry.split(b"\t", 1)
            index.setdefault(os.fsdecode(name), []).append(info.decode())
        names = index.keys() | set(map(os.fsdecode, filter(None, extra.stdout.split(b"\0"))))
    records = {}
    for name in names:
        path = root / name
        if path.parent.resolve() != path.parent:
            raise ValueError(f"symlink in parent path: {name}")
        records[name] = [index.get(name), fingerprint(path)]
    return dict(root=str(root), base=base, git=not located.returncode, files=records)


def incremental(directory):
    baseline = json.loads((directory / "baseline.json").read_bytes())
    if not baseline["git"] or not baseline["base"]:
        return []
    root = Path(baseline["root"])
    os.chdir(root)
    changed = git("diff", "--no-renames", "--name-only", "-z", baseline["base"], "--")
    extra = git("ls-files", "--others", "--exclude-standard", "-z")
    changed.check_returncode()
    extra.check_returncode()
    paths = sorted(set(map(os.fsdecode, filter(None, (changed.stdout + extra.stdout).split(b"\0")))))
    result = []
    for name in paths:
        path = root / name
        if path.suffix not in {".py", ".c", ".cpp", ".cc", ".cxx", ".go", ".rs", ".ts", ".js", ".java", ".kt"}:
            continue
        if path.resolve() != path or not path.is_file():
            continue
        original = baseline["files"].get(name)
        if not original or original[1] != fingerprint(path):
            result.append(str(path))
        if len(result) == 8:
            break
    return result


if __name__ == "__main__":
    result = incremental(Path(sys.argv[1])) if len(sys.argv) == 2 else snapshot()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
