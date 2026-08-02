import re
with open("tests/test_long_horizon_qualification.py", "r") as f:
    content = f.read()

# We need to add the mock for ProcessExecutionGateway.run
patch = """
    from nexus.sandbox import CommandResult, SandboxBackend
    def fake_gateway_run(req):
        return CommandResult(
            argv=list(req.command),
            cwd=str(req.workspace),
            backend=SandboxBackend.RESTRICTED,
            success=True,
            exit_code=0,
            stdout="ok\\n",
            stderr="",
        )
    monkeypatch.setattr("nexus.benchmark.ProcessExecutionGateway.run", fake_gateway_run)
"""

# Insert it before monkeypatch.setattr("nexus.benchmark.subprocess.run", fake_run)
content = content.replace(
    '    monkeypatch.setattr("nexus.benchmark.subprocess.run", fake_run)',
    patch + '\n    monkeypatch.setattr("nexus.benchmark.subprocess.run", fake_run)'
)

with open("tests/test_long_horizon_qualification.py", "w") as f:
    f.write(content)
