import re
with open("tests/test_long_horizon_qualification.py", "r") as f:
    content = f.read()

patch = """
    from nexus.sandbox import CommandResult, SandboxBackend
    import nexus.process_gateway
    agent_commands = []
    
    def fake_gateway_run(req):
        command = " ".join(req.command)
        if "nexus" in command:
            agent_commands.append(command)
            index = len(agent_commands)
            status = "FAILED" if index == 1 else "VERIFIED"
            import json
            payload = {
                "session_id": "session",
                "run": {
                    "turn_id": f"turn-{index:04d}",
                    "status": status,
                    "outcome": status,
                    "metadata": {},
                },
            }
            return CommandResult(
                argv=list(req.command),
                cwd=str(req.workspace),
                backend=SandboxBackend.RESTRICTED,
                success=index != 1,
                exit_code=2 if index == 1 else 0,
                stdout=json.dumps(payload),
                stderr="",
                timed_out=False
            )
        return CommandResult(
            argv=list(req.command),
            cwd=str(req.workspace),
            backend=SandboxBackend.RESTRICTED,
            success=True,
            exit_code=0,
            stdout="ok\\n",
            stderr="",
            timed_out=False
        )
    monkeypatch.setattr(nexus.process_gateway.ProcessExecutionGateway, "run", fake_gateway_run)
"""

# Find where fake_run is defined and replace it entirely up to where it's mocked
start_marker = "    def fake_run(command, **kwargs):"
end_marker = "    result = BenchmarkRunner(BenchmarkSuite.load(manifest)).run().results[0]"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

new_content = content[:start_idx] + patch + "\n" + content[end_idx:]

with open("tests/test_long_horizon_qualification.py", "w") as f:
    f.write(new_content)
