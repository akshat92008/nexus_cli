import re

with open("tests/test_cli_coverage.py", "r") as f:
    code = f.read()

code = code.replace(
    'agent.total_completion_tokens = 200',
    'agent.total_completion_tokens = 200\n        agent._execute_tool_with_safety.return_value = ("ok", True)'
)

with open("tests/test_cli_coverage.py", "w") as f:
    f.write(code)
