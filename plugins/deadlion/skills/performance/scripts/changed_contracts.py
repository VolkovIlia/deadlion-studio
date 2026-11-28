"""Select tracked, approved performance contracts for the working-tree changes."""

import json
import os
from pathlib import Path
import subprocess
import tempfile


def git(*args, cwd=None):
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=cwd)


def files(data):
    return set(map(os.fsdecode, filter(None, data.split(b"\0"))))


def check():
    where = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True)
    if where.returncode:
        return {"status": "NOT APPLICABLE"}
    root = Path(os.fsdecode(where.stdout).rstrip("\n"))
    revision = approved_revision(root)
    if revision is None:
        return {"status": "NOT APPLICABLE"}
    approved = sorted(
        p
        for p in files(
            git(
                "ls-tree",
                "-rz",
                "--name-only",
                revision,
                "--",
                ".performance",
                cwd=root,
            )
        )
        if Path(p).name == "contract.json"
    )
    if not approved:
        return {"status": "NOT APPLICABLE"}
    selected = selected_contracts(root, revision, approved, changed_paths(root, revision))
    if not selected:
        return {"status": "NOT APPLICABLE"}
    return evaluate(root, revision, selected)


def approved_revision(root):
    resolved = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            os.getenv("DL_PERF_BASE", "HEAD") + "^{commit}",
        ],
        cwd=root,
        capture_output=True,
    )
    if resolved.returncode:
        if (
            "DL_PERF_BASE" not in os.environ
            and not subprocess.run(
                ["git", "for-each-ref", "--count=1"],
                cwd=root,
                capture_output=True,
                check=True,
            ).stdout
        ):
            return None
        raise ValueError("approved base revision unavailable")
    return resolved.stdout.decode().strip()


def changed_paths(root, revision):
    changed = files(
        git("diff", "--no-renames", "--name-only", "-z", revision, "--", cwd=root)
    )
    changed |= files(git("ls-files", "--others", "--exclude-standard", "-z", cwd=root))
    changed |= files(git("diff", "--cached", "--no-renames", "--name-only", "-z", revision, "--", cwd=root))
    return changed


def selected_contracts(root, revision, approved, changed):
    project_scope = os.environ.get("DL_PERF_PROJECT_SCOPE") == "1"
    selected = []
    for path in approved:
        c = json.loads(git("show", revision + ":" + path, cwd=root))
        directory = Path(path).parent
        impl = Path(c["benchmark"].get("candidate_root", directory))
        if (
            impl.is_absolute()
            or ".." in impl.parts
            or (root / impl).resolve() != root / impl
        ):
            raise ValueError("invalid candidate_root")
        names = c["benchmark"].get("candidate_files")
        if names is None:
            names = [
                arg
                for arg in c["benchmark"]["candidate"]
                if not Path(arg).is_absolute() and ".." not in Path(arg).parts
            ]
        if s := c.get("scaling"):
            names = [*names, *s["implementations"][c["choice"]]["files"]]
        if project_scope or any(Path(f).is_relative_to(directory) for f in changed) or changed & {
            str(impl / f) for f in names
        }:
            if not (root / path).is_file():
                raise ValueError(f"approved contract removed: {path}")
            selected.append((path, root / impl))
    return selected


def evaluate(root, revision, selected):
    reports = []
    with tempfile.TemporaryDirectory() as tmp:
        with tempfile.TemporaryFile() as archive:
            subprocess.run(
                ["git", "archive", revision], cwd=root, stdout=archive, check=True
            )
            archive.seek(0)
            subprocess.run(["tar", "-x", "-C", tmp], stdin=archive, check=True)
        gate = Path(__file__).with_name("dl-perf-gate")
        for path, impl in selected:
            r = subprocess.run(
                [gate, Path(tmp) / path, "--candidate-dir", impl, "--isolated"],
                capture_output=True,
                text=True,
            )
            result = json.loads(r.stdout)
            contract = json.loads((Path(tmp) / path).read_bytes())
            result["scope"] = {
                "contract": path,
                "candidate_root": str(impl.relative_to(root)),
                "candidate_files": contract["benchmark"].get("candidate_files"),
                "workload": contract["workload"],
            }
            reports.append(result)
            if r.returncode:
                return dict(
                    status=result["status"],
                    approved_revision=revision,
                    contracts=reports,
                )
    return dict(status="VERIFIED", approved_revision=revision, contracts=reports)
