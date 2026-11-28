"""Fingerprint the worktree and index independently of the current HEAD."""

from bisect import bisect_right
import ast
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
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(f"file type changed during snapshot: {path}")
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            after = os.fstat(handle.fileno())
            if (before.st_mode, before.st_size, before.st_ctime_ns) != (after.st_mode, after.st_size, after.st_ctime_ns):
                raise ValueError(f"file changed during snapshot: {path}")
            return [before.st_mode, digest]
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
    parents = set()
    for name in names:
        path = root / name
        parent = path.parent
        if parent not in parents:
            if parent.resolve() != parent:
                raise ValueError(f"symlink in parent path: {name}")
            parents.add(parent)
        records[name] = [index.get(name), fingerprint(path)]
    if any(parent.resolve() != parent for parent in parents):
        raise ValueError("parent path changed during snapshot")
    return dict(root=str(root), base=base, git=not located.returncode, files=records)


def incremental(directory, cursor):
    baseline = json.loads((directory / "baseline.json").read_bytes())
    if not baseline["git"] or not baseline["base"]:
        return {"paths": [], "cursor": ""}
    root = Path(baseline["root"])
    os.chdir(root)
    changed = git("diff", "--no-renames", "--name-only", "-z", baseline["base"], "--")
    extra = git("ls-files", "--others", "--exclude-standard", "-z")
    changed.check_returncode()
    extra.check_returncode()
    paths = sorted(set(map(os.fsdecode, filter(None, (changed.stdout + extra.stdout).split(b"\0")))))
    result = []
    start = bisect_right(paths, cursor)
    for offset in range(len(paths)):
        name = paths[(start + offset) % len(paths)]
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
    return {"paths": result, "cursor": str(Path(result[-1]).relative_to(root)) if result else ""}


def same_python(base, name, expected):
    previous = git("show", f"{base}:{name}")
    path = Path.cwd() / name
    if previous.returncode or path.resolve() != path or hashlib.sha256(previous.stdout).hexdigest() != expected:
        return False
    current = path.read_bytes()
    def header(data):
        return data.partition(b"\n")[0] if data.startswith(b"#!") else b""
    try:
        return header(previous.stdout) == header(current) and ast.dump(ast.parse(previous.stdout, type_comments=True)) == ast.dump(
            ast.parse(current, type_comments=True))
    except (SyntaxError, UnicodeError, ValueError):
        return False


if __name__ == "__main__":
    if sys.argv[1:2] == ["--same-python"]:
        result = same_python(*sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] != "--digest":
        result = incremental(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) == 3 else "")
    else:
        result = snapshot()
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    print(hashlib.sha256((encoded + "\n").encode()).hexdigest() if sys.argv[1:2] == ["--digest"] else encoded)
