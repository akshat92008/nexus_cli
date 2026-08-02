import re

with open("tests/test_cli_coverage.py", "r") as f:
    code = f.read()

code = code.replace('agent = MockAgent.return_value', 'agent = MockAgent.return_value\n        agent.total_prompt_tokens = 10\n        agent.total_completion_tokens = 20')

with open("tests/test_cli_coverage.py", "w") as f:
    f.write(code)
