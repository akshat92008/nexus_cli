"""
Hook Base — types, events, and base class for lifecycle hooks.
"""

from dataclasses import dataclass, field
from enum import Enum


class HookEvent(str, Enum):
    """Lifecycle events that can trigger hooks."""
    BEFORE_FILE_EDIT = "before_file_edit"
    AFTER_FILE_EDIT = "after_file_edit"
    BEFORE_FILE_CREATE = "before_file_create"
    AFTER_FILE_CREATE = "after_file_create"
    BEFORE_COMMAND = "before_command"
    AFTER_COMMAND = "after_command"
    BEFORE_COMMIT = "before_commit"
    AFTER_COMMIT = "after_commit"
    BEFORE_PUSH = "before_push"
    AFTER_PUSH = "after_push"
    ON_ERROR = "on_error"
    ON_TEST_FAIL = "on_test_fail"
    ON_LINT_FAIL = "on_lint_fail"
    ON_PLAN_START = "on_plan_start"
    ON_PLAN_COMPLETE = "on_plan_complete"
    ON_SESSION_START = "on_session_start"
    ON_SESSION_END = "on_session_end"
    ON_MODEL_SWITCH = "on_model_switch"
    ON_SKILL_ACTIVATE = "on_skill_activate"
    ON_SUBAGENT_COMPLETE = "on_subagent_complete"


class HookType(str, Enum):
    """Types of hook actions."""
    SHELL = "shell"       # Run a shell command
    PROMPT = "prompt"     # Inject a prompt into the agent
    TOOL = "tool"         # Call a specific tool
    NOTIFY = "notify"     # Show a notification
    BLOCK = "block"       # Block the operation


@dataclass
class HookContext:
    """Context passed to hooks when they fire."""
    event: HookEvent
    file_path: str = ""
    file_content: str = ""
    command: str = ""
    command_output: str = ""
    error_message: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class HookResult:
    """Result of a hook execution."""
    hook_name: str
    event: HookEvent
    success: bool
    output: str = ""
    blocked: bool = False  # If True, the triggering operation should be cancelled
    modified_content: str = ""  # If non-empty, use this instead of original content


class BaseHook:
    """
    Base class for hooks. Subclass to create custom hooks.

    Example:
        class AutoFormatHook(BaseHook):
            name = "auto_format"
            events = [HookEvent.AFTER_FILE_EDIT]
            hook_type = HookType.SHELL

            def get_command(self, context: HookContext) -> str:
                if context.file_path.endswith(".py"):
                    return f"ruff format {context.file_path}"
                return ""
    """

    name: str = "base_hook"
    description: str = "Base hook"
    events: list[HookEvent] = []
    hook_type: HookType = HookType.SHELL
    enabled: bool = True
    priority: int = 50  # 0 = lowest, 100 = highest
    file_pattern: str = ""  # Glob pattern to filter by file (e.g., "*.py")

    def should_fire(self, context: HookContext) -> bool:
        """Determine if this hook should fire for the given context."""
        if not self.enabled:
            return False

        if context.event not in self.events:
            return False

        # File pattern matching
        if self.file_pattern and context.file_path:
            import fnmatch
            if not fnmatch.fnmatch(context.file_path, self.file_pattern):
                return False

        return True

    def execute(self, context: HookContext) -> HookResult:
        """
        Execute this hook. Override in subclasses.

        Returns a HookResult indicating success/failure and any modifications.
        """
        return HookResult(
            hook_name=self.name,
            event=context.event,
            success=True,
        )

    def get_command(self, context: HookContext) -> list[str]:
        """For SHELL hooks, return the command to run. Override in subclasses."""
        return []

    def get_prompt(self, context: HookContext) -> str:
        """For PROMPT hooks, return the prompt to inject. Override in subclasses."""
        return ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "events": [e.value for e in self.events],
            "type": self.hook_type.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "file_pattern": self.file_pattern,
        }
