import re

with open("tests/test_agent_services.py", "r") as f:
    code = f.read()

code = code.replace("        _run_finalizer.finish=lambda *a, **kw: {\"status\": \"VERIFIED\"},\n", "")

# Now we need to add it after `agent = MagicMock(...)`
# We'll search for `return agent` inside `def _mock_agent(tmp_path: Path):` and replace with `agent._run_finalizer = MagicMock(); agent._run_finalizer.finish = lambda *a, **kw: {"status": "VERIFIED"}; return agent`

code = code.replace("    return agent", "    agent._run_finalizer = MagicMock()\n    agent._run_finalizer.finish = lambda *a, **kw: {\"status\": \"VERIFIED\"}\n    return agent")

with open("tests/test_agent_services.py", "w") as f:
    f.write(code)

