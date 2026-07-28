import json
from pathlib import Path

from nova_v12.eval.tasks import validate_tasks
from nova_v12.inference.protocol import parse_agent_action, parse_patch_response


def test_packaged_tasks_validate():
    root = Path(__file__).resolve().parents[1]
    count, errors = validate_tasks(root / "eval" / "tasks")
    assert count >= 5
    assert not errors


def test_protocol_parsers():
    action = parse_agent_action(json.dumps({"tool": "read_file", "args": {"path": "a.py"}}))
    assert action["tool"] == "read_file"
    patch = parse_patch_response(
        json.dumps(
            {
                "status": "patch",
                "operations": [
                    {"action": "replace", "path": "a.py", "search": "x", "replace": "y"}
                ],
            }
        )
    )
    assert patch["status"] == "patch"
