from __future__ import annotations

from typing import Any

from nova_v12.patching import extract_json_object


def parse_agent_action(output: str) -> dict[str, Any]:
    value = extract_json_object(output)
    tool = value.get("tool")
    args = value.get("args")
    if not isinstance(tool, str) or not tool:
        raise ValueError("agent action requires a non-empty tool string")
    if not isinstance(args, dict):
        raise ValueError("agent action requires an args object")
    return {"tool": tool, "args": args}


def parse_patch_response(output: str) -> dict[str, Any]:
    value = extract_json_object(output)
    status = value.get("status", "patch")
    if status not in {"patch", "needs_context", "escalate", "no_change"}:
        raise ValueError(f"unsupported response status: {status}")
    if status == "patch":
        operations = value.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ValueError("patch response requires non-empty operations")
        for operation in operations:
            if not isinstance(operation, dict):
                raise ValueError("each operation must be an object")
            if operation.get("action") not in {"create", "replace", "write"}:
                raise ValueError("unsupported patch operation")
            if not isinstance(operation.get("path"), str):
                raise ValueError("operation path must be a string")
    return value
