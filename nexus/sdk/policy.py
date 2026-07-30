"""
SDK for extending Nexus with custom execution policies.
"""

from typing import Any


class ExecutionPolicy:
    """Base interface for security and execution policies."""
    
    @property
    def name(self) -> str:
        raise NotImplementedError
        
    def check_permissions(self, tool_name: str, args: dict) -> tuple[bool, str | None]:
        """Check if a tool call is permitted by this policy."""
        return True, None
        
    def before_action(self, action: str, kwargs: dict) -> None:
        """Hook called before an action executes."""
        pass
        
    def after_action(self, action: str, kwargs: dict, success: bool, result: Any) -> None:
        """Hook called after an action executes."""
        pass
