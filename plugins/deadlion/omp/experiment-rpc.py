"""Keep OMP's RPC input open while native autoresearch runs."""
import json
import os
from pathlib import Path
import subprocess
import sys

from experiment_budget import ExperimentBudget


def request(process, key, text):
    process.stdin.write(json.dumps(dict(id=key, type="prompt", message=text)) + "\n")
    process.stdin.flush()


def events(stream):
    for line in stream:
        try:
            yield json.loads(line)
        except ValueError:
            print(line.rstrip(), file=sys.stderr)


def supervise(directory, limits):
    command = ["omp", "--mode", "rpc", "--offline", "--no-extensions", "--no-judge",
               "--no-spotlight", "-e", str(Path(__file__).with_name("evolution.mjs"))]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    budget = ExperimentBudget(directory, limits)
    logged = 0
    pause_after = int(os.environ.get("DL_PAUSE_AFTER", 0))
    try:
        for event in events(process.stdout):
            stop = budget.observe(event)
            if stop:
                (directory / "completed").write_text(stop + "\n")
                print(stop, flush=True)
                return 2 if stop.startswith("NOT VERIFIED") else 0
            kind = event.get("type")
            if kind == "ready":
                request(process, "enable", "/autoresearch")
            elif kind == "prompt_result" and event.get("id") == "enable":
                request(process, "experiment", f"{limits['goal']}. Set max_iterations={limits['iterations']}. "
                        "Use the fixed workload and independent verifier. Log each result.")
            elif kind == "extension_ui_request" and event.get("method") == "notify":
                print(event.get("message"), flush=True)
            elif kind == "tool_execution_end":
                name = event.get("toolName")
                print(name, "failed" if event.get("isError") else "finished", flush=True)
                if (name == "log_experiment" and not event.get("isError") and
                        len(list(directory.glob("attempt-*"))) >= limits["iterations"]):
                    (directory / "completed").write_text("iteration budget reached\n")
                    return 0
                if name == "log_experiment" and not event.get("isError"):
                    logged += 1
                    if pause_after and logged >= pause_after:
                        print("Paused after a logged experiment", flush=True)
                        return 0
            elif kind == "response" and event.get("success") is False:
                print(event.get("error"), file=sys.stderr)
                return 2
            elif kind == "agent_end" and event.get("messages"):
                last = event["messages"][-1]
                if last.get("stopReason") in ("error", "aborted"):
                    print(last.get("errorMessage", last["stopReason"]), file=sys.stderr)
                    return 2
        return 2
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    directory = Path(os.environ["DL_EXPERIMENT"])
    sys.exit(supervise(directory, json.loads((directory / "limits.json").read_text())))
