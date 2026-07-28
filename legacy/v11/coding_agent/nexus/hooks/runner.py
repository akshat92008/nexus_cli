"""
Hook Runner — executes hooks when lifecycle events fire.

Manages hook registration, ordering by priority, and execution.
"""

import subprocess
from typing import Optional

from nexus.hooks.base import BaseHook, HookEvent, HookType, HookContext, HookResult


class HookRunner:
    """
    Central hook execution engine.

    Manages a registry of hooks and fires them when lifecycle events occur.
    Hooks are executed in priority order (highest first).

    Usage:
        runner = HookRunner()
        runner.register(AutoFormatHook())
        runner.register(AutoLintHook())

        # Fire an event
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
                    )
                elif hook.hook_type == HookType.NOTIFY:
                    result = hook.execute(context)
                else:
                    result = hook.execute(context)

                results.append(result)

                # If any hook blocks, stop processing
                if result.blocked:
                    break

            except Exception as e:
                results.append(HookResult(
                    hook_name=hook.name,
                    event=event,
                    success=False,
                    output=f"Hook error: {e}",
                ))

        return results

    def _execute_shell_hook(self, hook: BaseHook, context: HookContext) -> HookResult:
        """Execute a shell-type hook."""
        command = hook.get_command(context)
        if not command:
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=True,
                output="No command to run",
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.working_dir,
                timeout=30,
            )

            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=result.returncode == 0,
                output=result.stdout + result.stderr,
            )
        except subprocess.TimeoutExpired:
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=False,
                output="Hook command timed out (30s)",
            )
        except Exception as e:
            return HookResult(
                hook_name=hook.name,
                event=context.event,
                success=False,
                output=f"Error: {e}",
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
