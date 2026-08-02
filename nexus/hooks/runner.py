"""
Hook Runner — executes hooks when lifecycle events fire.

Security:
  - All shell hooks are executed with shell=False
  - File paths in commands are validated against the workspace root
  - Hook failures produce structured diagnostics
  - Formatter or validator failure is visible to the parent operation
"""

import logging
import subprocess

from nexus.hooks.base import (
    BaseHook,
    HookContext,
    HookEvent,
    HookFailurePolicy,
    HookResult,
    HookType,
    validate_hook_path,
)

logger = logging.getLogger(__name__)


class HookRunner:
    """
    Central hook execution engine.

    Manages a registry of hooks and fires them when lifecycle events occur.
    Hooks are executed in priority order (highest first).

    Usage::

        runner = HookRunner("/path/to/workspace")
        runner.register(AutoFormatHook())
        runner.register(AutoLintHook())

        results = runner.fire(HookEvent.AFTER_FILE_EDIT, HookContext(
            event=HookEvent.AFTER_FILE_EDIT,
            file_path="/path/to/file.py",
        ))

        for result in results:
            if result.blocked:
                # Operation was blocked by a hook
                pass
    """

    def __init__(self, working_dir: str = ""):
        self.working_dir = working_dir
        self._hooks: list[BaseHook] = []

    def register(self, hook: BaseHook):
        """Register a hook."""
        self._hooks.append(hook)
        # Re-sort by priority (highest first)
        self._hooks.sort(key=lambda h: h.priority, reverse=True)

    def unregister(self, name: str):
        """Unregister a hook by name."""
        self._hooks = [h for h in self._hooks if h.name != name]

    def enable(self, name: str) -> bool:
        """Enable a hook."""
        for hook in self._hooks:
            if hook.name == name:
                hook.enabled = True
                return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a hook."""
        for hook in self._hooks:
            if hook.name == name:
                hook.enabled = False
                return True
        return False

    def fire(self, event: HookEvent, context: HookContext | None = None) -> list[HookResult]:
        """
        Fire all hooks registered for a given event.

        Args:
            event: The lifecycle event that occurred
            context: Context about the event

        Returns:
            List of HookResults from each hook that fired
        """
        if context is None:
            context = HookContext(event=event)
        context.event = event

        # Inject workspace root for path validation
        if not context.workspace_root and self.working_dir:
            context.workspace_root = self.working_dir

        results = []
        for hook in self._hooks:
            if not hook.should_fire(context):
                continue

            try:
                if hook.hook_type == HookType.SHELL:
                    result = self._execute_shell_hook(hook, context)
                elif hook.hook_type == HookType.BLOCK:
                    result = HookResult(
                        hook_name=hook.name,
                        event=event,
                        success=True,
                        blocked=True,
                        output=f"Operation blocked by hook: {hook.name}",
                        failure_policy=hook.failure_policy,
                    )
                elif hook.hook_type == HookType.NOTIFY:
                    result = hook.execute(context)
                else:
                    result = hook.execute(context)

                results.append(result)

                # If any hook blocks, stop processing
                if result.blocked:
                    break

            except (OSError, ValueError) as e:
                logger.warning(
                    "Hook %s failed with error: %s (event=%s)",
                    hook.name,
                    e,
                    event.value,
                )
                results.append(
                    HookResult(
                        hook_name=hook.name,
                        event=event,
                        success=False,
                        output=f"Hook error: {e}",
                        failure_policy=hook.failure_policy,
                    )
                )

        return results

    def _execute_shell_hook(self, hook: BaseHook, context: HookContext) -> HookResult:
        """Execute a shell-type hook with path validation and sandbox enforcement."""
        command = hook.get_command(context)
        if not command:
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=True,
                output="No command to run",
                failure_policy=hook.failure_policy,
            )

        # SECURITY: Validate that command is a list (argv), not a string
        if isinstance(command, str):
            logger.error(
                "Hook %s returned a string command instead of argv list. "
                "This is a security violation. Command rejected.",
                hook.name,
            )
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=False,
                output="Hook returned a shell string instead of argv list (security violation)",
                failure_policy=HookFailurePolicy.BLOCK,
            )

        # SECURITY: Validate file paths in the command against the workspace
        if context.workspace_root:
            for arg in command[1:]:  # Skip the executable itself
                # Check if the arg looks like a file path
                if "/" in arg or arg.startswith("."):
                    if not validate_hook_path(arg, context.workspace_root):
                        logger.warning(
                            "Hook %s references path outside workspace: %s",
                            hook.name,
                            arg,
                        )
                        return HookResult(
                            hook_name=hook.name,
                            event=context.event,
                            success=False,
                            output=f"Path outside workspace rejected: {arg}",
                            failure_policy=HookFailurePolicy.BLOCK,
                        )

        cwd = self.working_dir or None
        try:
            result = subprocess.run(
                command,
                shell=False,  # SECURITY: Never use shell=True
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=30,
            )

            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=result.returncode == 0,
                output=result.stdout + result.stderr,
                failure_policy=hook.failure_policy,
            )
        except subprocess.TimeoutExpired:
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=False,
                output="Hook command timed out (30s)",
                failure_policy=hook.failure_policy,
            )
        except FileNotFoundError as e:
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=False,
                output=f"Command not found: {e}",
                failure_policy=hook.failure_policy,
            )
        except OSError as e:
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=False,
                output=f"OS Error: {e}",
                failure_policy=hook.failure_policy,
            )

    def is_blocked(self, event: HookEvent, context: HookContext | None = None) -> bool:
        """Check if an event would be blocked by any hook."""
        results = self.fire(event, context)
        return any(r.blocked for r in results)

    def list_hooks(self) -> list[dict]:
        """List all registered hooks."""
        return [h.to_dict() for h in self._hooks]

    def list_active(self) -> list[dict]:
        """List only enabled hooks."""
        return [h.to_dict() for h in self._hooks if h.enabled]

    def get_hooks_for_event(self, event: HookEvent) -> list[BaseHook]:
        """Get all hooks registered for a specific event."""
        return [h for h in self._hooks if event in h.events and h.enabled]

    def get_summary(self) -> str:
        """Human-readable summary of registered hooks."""
        lines = [f"⚡ Hooks ({len(self._hooks)} registered)"]
        for hook in self._hooks:
            status = "🟢" if hook.enabled else "🔴"
            events = ", ".join(e.value for e in hook.events)
            lines.append(f"  {status} {hook.name} [{hook.hook_type.value}] → {events}")
        return "\n".join(lines)
