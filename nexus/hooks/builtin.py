"""
Built-in Hooks — auto-format, auto-lint, auto-test, security scan.
"""

from nexus.hooks.base import BaseHook, HookEvent, HookType, HookContext, HookResult


class AutoFormatHook(BaseHook):
    """Auto-format files after editing."""
    name = "auto_format"
    description = "Auto-format files after editing (prettier, black, gofmt)"
    events = [HookEvent.AFTER_FILE_EDIT, HookEvent.AFTER_FILE_CREATE]
    hook_type = HookType.SHELL
    enabled = False  # Disabled by default
    priority = 30

    def get_command(self, context: HookContext) -> str:
        path = context.file_path
        if path.endswith(".py"):
            return f"ruff format {path} 2>/dev/null || black {path} 2>/dev/null || true"
        elif path.endswith((".js", ".jsx", ".ts", ".tsx", ".css", ".json", ".md")):
            return f"npx prettier --write {path} 2>/dev/null || true"
        elif path.endswith(".go"):
            return f"gofmt -w {path}"
        elif path.endswith(".rs"):
            return f"rustfmt {path} 2>/dev/null || true"
        return ""


class AutoLintHook(BaseHook):
    """Auto-lint files after editing."""
    name = "auto_lint"
    description = "Run linter after file edits"
    events = [HookEvent.AFTER_FILE_EDIT]
    hook_type = HookType.SHELL
    enabled = False  # Disabled by default
    priority = 25

    def get_command(self, context: HookContext) -> str:
        path = context.file_path
        if path.endswith(".py"):
            return f"ruff check {path} --no-fix 2>/dev/null || true"
        elif path.endswith((".js", ".jsx", ".ts", ".tsx")):
            return f"npx eslint {path} --no-error-on-unmatched-pattern 2>/dev/null || true"
        elif path.endswith(".rs"):
            return f"cargo clippy --quiet 2>/dev/null || true"
        return ""


class PreCommitTestHook(BaseHook):
    """Run tests before committing."""
    name = "pre_commit_test"
    description = "Run tests before git commit"
    events = [HookEvent.BEFORE_COMMIT]
    hook_type = HookType.SHELL
    enabled = False
    priority = 80

    _test_commands = {
        ".py": "python -m pytest -x -q 2>/dev/null || true",
        ".js": "npm test -- --passWithNoTests 2>/dev/null || true",
        ".ts": "npm test -- --passWithNoTests 2>/dev/null || true",
        ".rs": "cargo test --quiet 2>/dev/null || true",
        ".go": "go test ./... 2>/dev/null || true",
    }

    def get_command(self, context: HookContext) -> str:
        # Use project-specific test command if available
        if context.metadata.get("test_command"):
            return context.metadata["test_command"]
        # Default: run Python tests (most common for this project)
        return "python -m pytest -x -q 2>/dev/null || true"


class SecurityScanHook(BaseHook):
    """Scan for secrets before pushing."""
    name = "security_scan"
    description = "Scan for hardcoded secrets before git push"
    events = [HookEvent.BEFORE_PUSH]
    hook_type = HookType.SHELL
    enabled = False
    priority = 90

    def get_command(self, context: HookContext) -> str:
        # Use git-secrets or trufflehog if available, otherwise basic grep
        return (
            "git secrets --scan 2>/dev/null || "
            "grep -rn 'password\\|secret\\|api_key\\|private_key' --include='*.py' --include='*.js' --include='*.ts' --include='*.env' . "
            "| grep -v 'node_modules\\|.git\\|__pycache__\\|Binary' "
            "| head -20 || true"
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
