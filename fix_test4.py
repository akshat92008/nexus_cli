import re

with open("tests/test_cli_coverage.py", "r") as f:
    code = f.read()

code = code.replace(
    'mock_mem.return_value.list_conversations.return_value = ["c1"]',
    'mock_mem.return_value.list_conversations.return_value = [{"id": "c1", "model_name": "x", "message_count": 1, "preview": "p"}]'
)

with open("tests/test_cli_coverage.py", "w") as f:
    f.write(code)
