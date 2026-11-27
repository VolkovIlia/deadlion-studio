"""Account for completed foreground model messages and consecutive discarded runs."""
import json
from pathlib import Path


class ExperimentBudget:
    def __init__(self, directory, limits):
        self.path = Path(directory) / "usage.json"
        self.limits = limits
        self.pending = {}
        self.state = json.loads(self.path.read_text()) if self.path.exists() else dict(tokens=0, rejected=0)

    def observe(self, event):
        kind = event.get("type")
        if kind == "message_end":
            message = event.get("message", {})
            if message.get("role") != "assistant":
                return
            usage = message.get("usage", {}).get("totalTokens")
            if not isinstance(usage, int) or usage < 0:
                return "NOT VERIFIED: missing model token usage" if self.limits["tokens"] else None
            self.state["tokens"] += usage
        elif kind == "tool_execution_start" and event.get("toolName") == "log_experiment":
            self.pending[event["toolCallId"]] = event.get("args", {}).get("status")
            return
        elif kind == "tool_execution_end" and event.get("toolName") == "log_experiment":
            outcome = self.pending.pop(event.get("toolCallId"), None)
            if event.get("isError") or outcome is None:
                return
            self.state["rejected"] = 0 if outcome == "keep" else self.state["rejected"] + 1
        else:
            return
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state))
        temporary.replace(self.path)
        if self.limits["tokens"] and self.state["tokens"] >= self.limits["tokens"]:
            return "reported foreground token budget reached"
        if self.state["rejected"] >= self.limits["patience"]:
            return "no independently verified improvement"
