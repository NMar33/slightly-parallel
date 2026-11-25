"""Script the full core against the real Codex CLI, without provider requests."""

import json

from core_mcp import Guard


class CoreModel:
    def __init__(self, plan, rules, *, workspace_shell=False):
        self.plan = plan
        self.rules = rules
        self.workspace_shell = workspace_shell
        self.sent_shell = set()

    def policy_name(self):
        return json.loads(self.plan.policy.read_text(encoding="utf-8"))["name"]

    def __call__(self, items, tools):
        policy = json.loads(self.plan.policy.read_text(encoding="utf-8"))
        turn = policy["turn"]
        if not any(item.get("role") == "user" for item in items):
            return None
        for shell in policy["shell"]:
            if (turn, shell) not in self.sent_shell:
                self.sent_shell.add((turn, shell))
                return self._shell(tools, shell)
        guard = Guard(self.plan.policy, self.plan.trace, None, self.rules)
        events = []
        if self.plan.trace.exists():
            events = [row for line in self.plan.trace.read_text(encoding="utf-8").rpartition("\n")[0].splitlines()
                      if (row := json.loads(line))["turn"] == turn]
        if events and events[-1]["result"] != "accepted":
            return None
        if len(events) == len(policy["calls"]):
            return None
        if events:
            guard.counters = events[-1]["counters"]
            guard.scan_id = events[-1]["scan_id"]
        name, template = policy["calls"][len(events)]
        method = next(tool for tool in tools if tool.startswith("mcp__slightly_parallel_") and tool.endswith("_" + name))
        return method, guard._arguments(template, policy["rule"])

    def _shell(self, tools, command):
        name = next(tool for tool in tools if tool in ("exec_command", "functions_exec_command",
                                                       "shell_command", "functions_shell_command"))
        arguments = {"command" if name.endswith("shell_command") else "cmd": command}
        if not self.workspace_shell:
            arguments.update(sandbox_permissions="require_escalated", justification="Write the calculator fixture.")
        return name, arguments
