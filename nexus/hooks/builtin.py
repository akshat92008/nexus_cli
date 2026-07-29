"""
Built-in Hooks — auto-format, auto-lint, auto-test, security scan.
"""

from nexus.hooks.base import BaseHook, HookContext, HookEvent, HookResult, HookType


class AutoFormatHook(BaseHook):
    """Auto-format files after editing."""
    name = "auto_format"
    description = "Auto-format files after editing (prettier, black, gofmt)"
    events = [HookEvent.AFTER_FILE_EDIT, HookEvent.AFTER_FILE_CREATE]
    hook_type = HookType.SHELL
    enabled = False  # Disabled by default
    priority = 30

    def get_command(self, context: HookContext) -> list[str]:
        path = context.file_path
        if path.endswith(".py"):
            return ["ruff", "format", path]
        elif path.endswith((".js", ".jsx", ".ts", ".tsx", ".css", ".json", ".md")):
            return ["npx", "prettier", "--write", path]
        elif path.endswith(".go"):
            return ["gofmt", "-w", path]
        elif path.endswith(".rs"):
            return ["rustfmt", path]
        return []


class AutoLintHook(BaseHook):
    """Auto-lint files after editing."""
    name = "auto_lint"
    description = "Run linter after file edits"
    events = [HookEvent.AFTER_FILE_EDIT]
    hook_type = HookType.SHELL
    enabled = False  # Disabled by default
    priority = 25

    def get_command(self, context: HookContext) -> list[str]:
        path = context.file_path
        if path.endswith(".py"):
            return ["ruff", "check", path, "--no-fix"]
        elif path.endswith((".js", ".jsx", ".ts", ".tsx")):
            return ["npx", "eslint", path, "--no-error-on-unmatched-pattern"]
        elif path.endswith(".rs"):
            return ["cargo", "clippy", "--quiet"]
        return []


class PreCommitTestHook(BaseHook):
    """Run tests before committing."""
    name = "pre_commit_test"
    description = "Run tests before git commit"
    events = [HookEvent.BEFORE_COMMIT]
    hook_type = HookType.SHELL
    enabled = False
    priority = 80

    _test_commands = {
        ".py": "python -m pytest -x -q",
        ".js": "npm test",
        ".ts": "npm test",
        ".rs": "cargo test --quiet",
        ".go": "go test ./...",
    }

    def get_command(self, context: HookContext) -> list[str]:
        # Use project-specific test command if available
        if context.metadata.get("test_command"):
            import shlex
            return shlex.split(context.metadata["test_command"])
        # Default: run Python tests (most common for this project)
        return ["python", "-m", "pytest", "-x", "-q"]


class SecurityScanHook(BaseHook):
    """Scan for secrets before pushing."""
    name = "security_scan"
    description = "Scan for hardcoded secrets before git push"
    events = [HookEvent.BEFORE_PUSH]
    hook_type = HookType.BLOCK
    enabled = False
    priority = 90

    def execute(self, context: HookContext) -> HookResult:
        import subprocess
        # Check if git-secrets is installed
        git_secrets_check = subprocess.run(["command", "-v", "git-secrets"], capture_output=True, text=True)
        if git_secrets_check.returncode == 0:
            result = subprocess.run(["git", "secrets", "--scan"], capture_output=True, text=True, cwd=context.metadata.get("working_dir", "."))
            return HookResult(
                hook_name=self.name,
                event=context.event,
                success=result.returncode == 0,
                output=result.stdout + result.stderr,
            )
        else:
            # Fallback naive check
            import re
            import os
            secret_pattern = re.compile(r'password|secret|api_key|private_key', re.IGNORECASE)
            working_dir = context.metadata.get("working_dir", ".")
            found = False
            for root, dirs, files in os.walk(working_dir):
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__"}]
                for file in files:
                    if file.endswith((".py", ".js", ".ts", ".env")):
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                for line in f:
                                    if secret_pattern.search(line):
                                        found = True
                                        break
                        except Exception:
                            pass
            return HookResult(
                hook_name=self.name,
                event=context.event,
                success=not found,
                output="Secrets found!" if found else "No secrets found.",
            )


class NotifyOnErrorHook(BaseHook):
    """Log errors for debugging."""
    name = "notify_on_error"
    description = "Log errors for debugging"
    events = [HookEvent.ON_ERROR]
    hook_type = HookType.NOTIFY
    enabled = True
    priority = 50

    def execute(self, context: HookContext) -> HookResult:
        return HookResult(
            hook_name=self.name,
            event=context.event,
            success=True,
            output=f"Error occurred: {context.error_message}",
        )


class SessionStartHook(BaseHook):
    """Actions to perform when a session starts."""
    name = "session_start"
    description = "Setup actions on session start"
    events = [HookEvent.ON_SESSION_START]
    hook_type = HookType.NOTIFY
    enabled = True
    priority = 10

    def execute(self, context: HookContext) -> HookResult:
        return HookResult(
            hook_name=self.name,
            event=context.event,
            success=True,
            output="Session started",
        )


# ── Built-in hook registry ──────────────────────────────────────────────────

ALL_BUILTIN_HOOKS: list[type[BaseHook]] = [
    AutoFormatHook,
    AutoLintHook,
    PreCommitTestHook,
    SecurityScanHook,
    NotifyOnErrorHook,
    SessionStartHook,
]


def create_builtin_hooks() -> list[BaseHook]:
    """Create instances of all built-in hooks."""
    return [cls() for cls in ALL_BUILTIN_HOOKS]
