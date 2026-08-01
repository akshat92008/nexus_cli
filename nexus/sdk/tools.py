"""
SDK for extending Nexus with custom tools.
"""

import json
from typing import Callable


class BaseTool:
    """Base protocol for a Nexus tool."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    @property
    def parameters(self) -> dict:
        """JSON schema defining the tool parameters."""
        raise NotImplementedError

    def execute(self, **kwargs) -> str:
        raise NotImplementedError

    def to_schema(self) -> dict:
        """Returns the OpenAI-compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class FunctionTool(BaseTool):
    """Wraps an existing python function and a JSON schema into a BaseTool."""

    def __init__(self, schema: dict, func: Callable):
        self._schema = schema
        self._func = func

    @property
    def name(self) -> str:
        return self._schema["function"]["name"]

    @property
    def description(self) -> str:
        return self._schema["function"]["description"]

    @property
    def parameters(self) -> dict:
        return self._schema["function"].get("parameters", {"type": "object", "properties": {}})

    def execute(self, **kwargs) -> str:
        return self._func(**kwargs)


class ToolRegistry:
    """Registry for resolving and executing tools dynamically."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_all_schemas(self) -> list[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict | str) -> tuple[bool, str]:
        """Executes a tool by name, returning (success, result_text)."""
        tool = self.get(name)
        if not tool:
            return False, f"❌ Unknown tool: '{name}' not found in registry."

        args_dict = arguments
        if isinstance(arguments, str):
            try:
                args_dict = json.loads(arguments)
            except json.JSONDecodeError:
                args_dict = {"raw": arguments}

        try:
            result = tool.execute(**args_dict)
            return True, result
        except Exception as e:
            return False, f"❌ Tool '{name}' failed: {e}"
