"""Freeze a designated contract and its sibling fixtures before implementation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile


def freeze(root, path, revision, directory):
    path = path.absolute()
    if path.resolve() != path or not path.is_file():
        raise ValueError("approved contract missing or symlinked")
    destination = directory / "approved"
    destination.mkdir()
    if path.is_relative_to(root):
        if not revision:
            raise ValueError("in-project contract needs an approved base revision")
        rel = path.relative_to(root)
        with tempfile.TemporaryFile() as archive:
            subprocess.run(["git", "archive", revision, "--", str(rel.parent)], cwd=root,
                           stdout=archive, check=True)
            archive.seek(0)
            with tarfile.open(fileobj=archive) as tar:
                for member in tar:
                    if member.isreg() or member.isdir():
                        tar.extract(member, destination, filter="data")
        approved = destination / rel
    else:
        # An external contract directory belongs to the approving operator.
        total = 0
        for src in path.parent.rglob("*"):
            if src.is_symlink() or directory.is_relative_to(src):
                raise ValueError("use a dedicated contract directory with regular files")
            dest = destination / src.relative_to(path.parent)
            if src.is_dir():
                dest.mkdir(exist_ok=True, parents=True)
            elif src.is_file():
                dest.parent.mkdir(exist_ok=True, parents=True)
                total += src.stat().st_size
                if total > 256 * 1024 * 1024:
                    raise ValueError("approved fixtures exceed the snapshot limit (256 MiB)")
                shutil.copy2(src, dest)
            else:
                raise ValueError("unsupported contract fixture")
        approved = destination / path.name
    if not approved.is_file():
        raise ValueError("explicit contract absent at approved revision")
    return str(approved)


if __name__ == "__main__":
    print(json.dumps(freeze(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))))
