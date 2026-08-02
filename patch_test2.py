import re
with open("tests/test_long_horizon_qualification.py", "r") as f:
    content = f.read()

patch = """
    from nexus.sandbox import CommandResult, SandboxBackend
    import nexus.process_gateway
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
    monkeypatch.setattr(nexus.process_gateway.ProcessExecutionGateway, "run", fake_gateway_run)
"""

content = content.replace(
    '    monkeypatch.setattr("nexus.benchmark.ProcessExecutionGateway.run", fake_gateway_run)',
    patch
)

with open("tests/test_long_horizon_qualification.py", "w") as f:
    f.write(content)
