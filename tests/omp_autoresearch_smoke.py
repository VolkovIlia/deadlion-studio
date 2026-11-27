"""Run OMP's real autoresearch lifecycle against a local scripted transport."""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
CALLS = [
    ("init_experiment", dict(name="smoke", primary_metric="cost", max_iterations=2)),
    ("candidate_shell", dict(command="printf 'good\\n' > candidate")),
    ("run_experiment", dict(timeout_seconds=5)),
    ("log_experiment", dict(status="keep", metric=1, description="good")),
    ("candidate_shell", dict(command="printf 'bad\\n' > candidate")),
    ("run_experiment", dict(timeout_seconds=5)),
    ("log_experiment", dict(status="keep", metric=0, description="invalid")),
    ("log_experiment", dict(status="discard", metric=0, description="rejected by oracle")),
]


class Transport(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        interactive = bool(request.get("tools"))
        index = self.server.calls
        if interactive:
            self.server.calls += 1
        if interactive and index < len(CALLS):
            name, args = CALLS[index]
            if name=="run_experiment" and self.server.contracts:
                args = dict(timeout_seconds=45)
            if index==3 and self.server.contracts:
                observed = json.dumps(request["messages"][-1])
                values = re.findall(r"METRIC cost=([0-9.eE+-]+)",observed)
                if not values:
                    raise ValueError("Missing measured cost in tool result: "+observed[-1200:])
                args = {**args,"metric":float(values[-1])}
            delta = dict(role="assistant", tool_calls=[dict(index=0, id=f"call_{index}", type="function",
                         function=dict(name=name, arguments=json.dumps(args)))])
            finish = "tool_calls"
        else:
            delta, finish = dict(role="assistant", content="Finished."), "stop"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for payload, reason in [(delta, None), ({}, finish)]:
            chunk = dict(id=f"r{index}", object="chat.completion.chunk", created=1,
                         model=request["model"], choices=[dict(index=0, delta=payload, finish_reason=reason)])
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *args):
        pass


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args], text=True).strip()


def setup(directory, port):
    profile = directory / "profile"
    profile.mkdir()
    (profile / "models.yml").write_text(f"""providers:
  fixture:
    baseUrl: http://127.0.0.1:{port}/v1
    api: openai-completions
    apiKey: FIXTURE_API_KEY
    models:
      - id: local-smoke
        name: local-smoke
        contextWindow: 120000
        maxTokens: 2048
""")
    (profile / "config.yml").write_text("modelRoles:\n  default: fixture/local-smoke\n")
    repo = directory / "source"
    repo.mkdir()
    git(repo, "init", "-qb", "main")
    (repo / "candidate").write_text("baseline\n")
    (repo / "check").write_text("""#!/bin/sh
test "$(cat candidate)" = good || exit 1
echo '{"status":"VERIFIED","interval":[1,1]}'
""")
    (repo / "autoresearch.sh").write_text("#!/bin/sh\necho 'METRIC cost=1'\n")
    for name in ("check", "autoresearch.sh"):
        (repo / name).chmod(0o755)
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Smoke", "-c", "user.email=smoke@example.invalid",
        "commit", "-qm", "fixture")
    return profile, repo


def main():
    with tempfile.TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), Transport) as server:
        directory = Path(tmp)
        server.calls = 0
        server.contracts = "--contracts" in sys.argv
        threading.Thread(target=server.serve_forever, daemon=True).start()
        profile, source = setup(directory, server.server_port)
        workspace = directory / "experiment"
        env = {**os.environ, "PI_CODING_AGENT_DIR": str(profile), "FIXTURE_API_KEY": "unused",
               "GIT_AUTHOR_NAME": "Smoke", "GIT_COMMITTER_NAME": "Smoke",
               "GIT_AUTHOR_EMAIL": "smoke@example.invalid", "GIT_COMMITTER_EMAIL": "smoke@example.invalid"}
        verifier_args = ["--check",source/"check"]
        if server.contracts:
            verifier_args = []
            record=json.loads((ROOT/"plugins/deadlion/evals/indexed-membership/contract.json").read_bytes())
            record["benchmark"] = dict(baseline=["sh","-c","sleep .03; echo good"],
                                       candidate=["cat","candidate"],expected="expected")
            record["budget"] = {"max_wall_ratio":1}
            for name,flag in (("train","--contract"),("holdout","--holdout-contract")):
                trusted=directory/name
                trusted.mkdir()
                (trusted/"input").write_text(name)
                (trusted/"expected").write_text("good\n")
                (trusted/"generate.py").write_text(
                    "import json,sys\nr=json.load(sys.stdin)\n"
                    + f"print(json.dumps(dict(input={name!r}+str(r),expected='good\\n')))\n")
                record["scaling"] = dict(dimensions={"n":[2,4,8,16,32,64]},distributions=["fixed"],
                    generator=["python3","generate.py"],implementations={
                        "scan":{"argv":record["benchmark"]["baseline"],"files":[]},
                        "index":{"argv":record["benchmark"]["candidate"],"files":["candidate"]}},
                    model_tolerance=.2,models=["constant","linear"],min_repetitions=9,
                    requirements=[dict(implementation="index",metric="peak_rss_kib",max=65536)],
                    limits=dict(seconds=25,memory_mib=96,max_points=6))
                (trusted/"contract.json").write_text(json.dumps(record))
                verifier_args.extend([flag,trusted/"contract.json"])
        run = subprocess.run([ROOT / "plugins/deadlion/omp/dl-evolve", workspace,
                              "--goal", "Smoke test", "--iterations", "2", "--seconds", "55",
                              *verifier_args, "--pause-after", "1"], cwd=source, capture_output=True,
                             text=True, timeout=70, env=env)
        assert run.returncode == 0 and (workspace / "repo/candidate").read_text() == "good\n", run.stderr
        assert len(list(workspace.glob("attempt-*"))) == 1
        server.calls = 4
        run = subprocess.run([ROOT / "plugins/deadlion/omp/dl-evolve", workspace, "--resume"],
                             cwd=source, capture_output=True, text=True, timeout=65, env=env)
        print(f"OMP resume exit {run.returncode}, local response position {server.calls}")
        if run.returncode or server.calls < len(CALLS):
            print("attempts", len(list(workspace.glob("attempt-*"))))
            for path in (workspace / "history").rglob("*.db"):
                with sqlite3.connect(path) as db:
                    print(db.execute("SELECT status, description FROM runs ORDER BY id").fetchall())
            raise RuntimeError((run.stdout + run.stderr)[-2400:])
        assert git(source, "status", "--porcelain") == ""
        assert git(source, "branch", "--show-current") == "main"
        assert (workspace / "repo/candidate").read_text() == "good\n"
        assert len(list(workspace.glob("attempt-*"))) == 2
        databases = [p for p in (workspace / "history").rglob("*") if p.is_file()
                     and p.read_bytes()[:16] == b"SQLite format 3\x00"]
        with sqlite3.connect(databases[0]) as db:
            statuses = db.execute("SELECT status FROM runs ORDER BY id").fetchall()
        assert statuses == [("keep",), ("discard",)], statuses
        print("Verified keep, pause, resume, rejection, discard, attempt accounting and original source tree.")


if __name__ == "__main__":
    main()
