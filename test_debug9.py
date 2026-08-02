import json
import pytest
from pathlib import Path
import subprocess
from types import SimpleNamespace
from nexus.benchmark import BenchmarkRunner, BenchmarkSuite
from nexus.sandbox import SandboxRunner, SandboxBackend

def test_debug(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "verify.py").write_text("print('ok')\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        """{
          "schema_version": "nexus.benchmark.v2",
          "name": "resume-contract",
          "profile": "long-horizon",
          "tasks": [{
            "id": "resume",
            "category": "long-horizon-system",
            "prompt": "Build the entire system",
            "repository": "repo",
            "verification": [["python", "verify.py"]],
            "max_attempts": 2,
            "max_turns_per_attempt": 5
          }]
        }""",
        encoding="utf-8",
    )
    agent_commands = []
    def fake_run(command, **kwargs):
        print(f"fake_run command: {command}")
        if "nexus" in command:
            agent_commands.append(command)
            index = len(agent_commands)
            status = "FAILED" if index == 1 else "VERIFIED"
            payload = {
                "session_id": "session",
                "run": {
                    "turn_id": f"turn-{index:04d}",
                    "status": status,
                    "outcome": status,
                    "metadata": {},
                },
            }
            return subprocess.CompletedProcess(
                command,
                2 if index == 1 else 0,
                stdout=json.dumps(payload).encode("utf-8") if isinstance(json.dumps(payload), str) else json.dumps(payload),
                stderr=b"",
            )
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n", stderr=b"")

    import nexus.benchmark
    import nexus.process_gateway
    from nexus.sandbox import CommandResult
    def fake_gateway_run(req):
        return CommandResult(
            argv=list(req.command),
            cwd=str(req.workspace),
            backend=SandboxBackend.RESTRICTED,
            success=True,
            exit_code=0,
            stdout="ok\n",
            stderr="",
        )
    nexus.benchmark.subprocess.run = fake_run
    nexus.process_gateway.ProcessExecutionGateway.run = fake_gateway_run
    SandboxRunner._backend_cache = SandboxBackend.RESTRICTED
    BenchmarkRunner._preflight = lambda _self: SimpleNamespace(ready=True)

    result = BenchmarkRunner(BenchmarkSuite.load(manifest)).run().results[0]
    print(result)

if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_debug(Path(tmp_dir))
