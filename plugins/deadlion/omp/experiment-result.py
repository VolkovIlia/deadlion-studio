"""Read the most recent kept OMP run from this experiment's own history."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def accepted(directory):
    keeps = []
    for db in (directory / "history").rglob("*.db"):
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as con:
            if con.execute("select 1 from sqlite_master where name='runs'").fetchone():
                keeps.extend(con.execute(
                    "select completed_at, commit_hash from runs where status='keep' and commit_hash is not null"
                ))
    if not keeps:
        raise ValueError("no independently accepted keep in experiment ledger")
    _, commit = max(keeps)
    spec = json.loads((directory / "limits.json").read_bytes())
    files = {}
    for name in spec["candidate_files"]:
        data = subprocess.check_output(["git", "show", commit + ":" + name], cwd=directory / "repo")
        files[name] = hashlib.sha256(data).hexdigest()
    return dict(commit=commit, files=files)


if __name__ == "__main__":
    print(json.dumps(accepted(Path(sys.argv[1]).resolve())))
