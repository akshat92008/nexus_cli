#!/usr/bin/env python3
"""
NexusAI — Hosted + Local Coding Agent CLI

Usage:
    nexus                          Start interactive mode with default model
    nexus --model kimi             Start with a specific model
    nexus --web                    Start the web interface
    nexus "build a flask app"      Run a single prompt and exit
    nexus --list-models            Show all available models
"""

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from nexus import __version__, ui
from nexus.agent import Agent
from nexus.doctor import run_doctor
from nexus.memory import ConversationMemory
from nexus.models import DEFAULT_MODEL, resolve_model
from nexus.policy import get_mode_policy
from nexus.run_catalog import RunCatalog
from nexus.tools import get_history, tool_get_project_structure


def parse_args():
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="NexusAI — Hosted NVIDIA + Local Nova Coding Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexus                              Interactive mode (default: GLM 5.2)
  nexus --model glm-5.2              Use GLM 5.2
  nexus --model kimi                 Use Kimi as Ceiling, Nova Codex v11 as Intern
  nexus --model nova_codex           Use local Nova Codex v11 directly with automatic guardrails
  nexus --web                        Launch web interface (Cursor-like UI)
  nexus --web --port 8080            Web interface on custom port
  nexus "create a REST API in Go"    Single prompt mode
  nexus --list-models                List all available models

Environment:
  NVIDIA_API_KEY                     Your NVIDIA API key (from build.nvidia.com)
  GROQ_API_KEY                       Optional hosted fallback
  OPENROUTER_API_KEY                 Optional hosted fallback
  Ollama                             Required for Nova Intern (nova_codex model)
        """,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Single prompt to run (omit for interactive mode)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"NexusAI {__version__}",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run installation and backend diagnostics, then exit",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=os.environ.get("NEXUS_MODEL", DEFAULT_MODEL),
        help=f"Model to use (default: {DEFAULT_MODEL}). Use --list-models to see all.",
    )
    parser.add_argument(
        "--model-id",
        default=os.environ.get("NEXUS_MODEL_ID"),
        help="Override the provider model ID; required for --model custom",
    )
    parser.add_argument(
        "--api-key",
        "-k",
        help="Hosted provider API key (prefer an environment variable to avoid shell history)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("NEXUS_OPENAI_BASE_URL"),
        help="Custom OpenAI-compatible base URL",
    )
    parser.add_argument(
        "--working-dir",
        "-d",
        help="Working directory (default: current directory)",
    )
    parser.add_argument(
        "--list-models",
        "-l",
        action="store_true",
        help="List all available models and exit",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable tool calling (pure chat mode)",
    )
    parser.add_argument(
        "--local-intern",
        choices=("off", "auto", "required"),
        default=os.environ.get("NEXUS_LOCAL_INTERN", "off"),
        help=(
            "Use Nova as an optional local intern for hosted coding tasks: "
            "off, auto when available, or required (default: off)"
        ),
    )
    parser.add_argument(
        "--enable-nova-fallback",
        action="store_true",
        help="Allow hosted-provider failures to fall back to local Nova when available",
    )
    parser.add_argument(
        "--enable-plugins",
        action="store_true",
        help="Load explicitly trusted local plugins in isolated workers",
    )
    parser.add_argument(
        "--system",
        "-s",
        help="Custom system prompt",
    )
    parser.add_argument(
        "--web",
        "-w",
        action="store_true",
        help="Launch the web interface instead of CLI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Port for web interface (default: 3000)",
    )
    parser.add_argument(
        "--resume",
        "-r",
        help="Resume a previous conversation by ID",
    )
    parser.add_argument(
        "--resume-run",
        help="Continue an interrupted durable run from its latest checkpoint",
    )
    parser.add_argument(
        "--continue",
        dest="continue_last",
        action="store_true",
        help="Resume the most recent conversation for this directory",
    )
    parser.add_argument(
        "--print",
        "-p",
        dest="print_mode",
        action="store_true",
        help="Run non-interactively and exit",
    )
    parser.add_argument(
        "--confirm-danger",
        action="store_true",
        help="Confirm dangerous operations without prompting",
    )
    parser.add_argument(
        "--output-format",
        "--output",
        dest="output_format",
        choices=("text", "json", "jsonl", "stream-json"),
        default="text",
    )
    parser.add_argument("--max-turns", type=int, default=50)
    parser.add_argument(
        "--permission-mode", choices=("default", "acceptEdits", "plan"), default="default"
    )
    parser.add_argument(
        "--mode",
        choices=(
            "plan",
            "review",
            "workspace",
            "autonomous",
            "local-only",
            "quality",
            "budget",
            "ci",
        ),
        default="review",
        help=(
            "Operational policy preset (default: review). "
            "Modes and isolation requirements: "
            "plan — read-only, no OS sandbox needed; "
            "review — edits require confirmation, no OS sandbox needed; "
            "workspace — Git-isolated worktree, native sandbox required; "
            "autonomous — hands-free, native sandbox required (bubblewrap on Linux); "
            "local-only — Nova only, native sandbox required; "
            "quality — maximum verification, review-level isolation; "
            "budget — cost-capped autonomous, native sandbox required; "
            "ci — non-interactive JSON output, native sandbox required. "
            "Run 'nexus --doctor' to check your sandbox status."
        ),
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Alias for --mode local-only",
    )
    parser.add_argument(
        "--prefer-cheap",
        action="store_true",
        help="Alias for --mode budget",
    )
    parser.add_argument(
        "--quality",
        choices=("balanced", "maximum"),
        help="Use maximum-quality planning/review when set to maximum",
    )
    parser.add_argument("--allowed-tools", nargs="*", default=[])
    parser.add_argument("--disallowed-tools", nargs="*", default=[])
    parser.add_argument(
        "--add-dir", action="append", default=[], help="Authorize an additional existing directory"
    )
    parser.add_argument(
        "--workspace",
        action="store_true",
        help="Run in a dedicated Git branch/worktree instead of the source checkout",
    )
    parser.add_argument(
        "--no-workspace",
        action="store_true",
        help="Explicitly disable the default isolated worktree/copy",
    )
    parser.add_argument(
        "--max-hosted-calls",
        type=int,
        help="Hard ceiling for logical hosted model calls in each request run",
    )
    parser.add_argument(
        "--max-provider-attempts",
        type=int,
        help="Hard ceiling for physical provider HTTP attempts, including retries/fallbacks",
    )
    parser.add_argument(
        "--max-prompt-tokens",
        type=int,
        help="Hard ceiling for provider-reported prompt tokens",
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        help="Hard ceiling for provider-reported completion tokens",
    )
    parser.add_argument(
        "--max-cost-usd",
        "--max-cost",
        dest="max_cost_usd",
        type=float,
        help="Hard hosted-cost ceiling; requires explicit token prices",
    )
    parser.add_argument(
        "--input-price-per-million",
        type=float,
        help="Provider input price used for cost accounting",
    )
    parser.add_argument(
        "--output-price-per-million",
        type=float,
        help="Provider output price used for cost accounting",
    )
    return parser.parse_args()


def _normalize_subcommand_argv() -> None:
    """Support the documented command-oriented UX without breaking legacy flags."""
    if len(sys.argv) < 2:
        return
    command = sys.argv[1]
    if command == "run":
        rest = sys.argv[2:]
        # Handle `nexus run --help` cleanly — argparse will print help and
        # exit 0 when it sees --help in the normalized argv list.
        if "--help" in rest or "-h" in rest:
            # Rebuild argv so the main parser sees --help
            sys.argv = [sys.argv[0], "--help"]
            return
        prompt = ""
        if "--prompt" in rest:
            index = rest.index("--prompt")
            if index + 1 >= len(rest):
                # Argparse will raise a clean error; just propagate.
                raise SystemExit("nexus run --prompt requires a value")
            prompt = rest[index + 1]
            del rest[index : index + 2]
        elif rest and not rest[0].startswith("-"):
            prompt = rest.pop(0)
        if not prompt:
            # Exit 0 with usage — not an error
            print(
                "Usage: nexus run <goal> [options]\n"
                "       nexus run --prompt <goal> [options]\n\n"
                "Options:\n"
                "  --mode <mode>       plan|review|workspace|autonomous|… (default: review)\n"
                "  --max-turns N       Maximum agent turns (default: 50)\n"
                "  --output-format F   text|json|jsonl|stream-json (default: text)\n"
                "  --confirm-danger    Confirm dangerous operations without prompting\n"
                "  --model <key>       Model to use (see nexus --list-models)\n"
                "  --working-dir DIR   Working directory (default: cwd)\n\n"
                "Run 'nexus --help' for the full option reference."
            )
            raise SystemExit(0)
        if "--print" not in rest and "-p" not in rest:
            rest.append("--print")
        sys.argv = [sys.argv[0], *rest, prompt]
    elif command == "resume":
        run_id = sys.argv[2] if len(sys.argv) > 2 else ""
        catalog = RunCatalog()
        try:
            reference = catalog.resolve(run_id)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        normalized_id = f"{reference.parent.name}/{reference.name}"
        sys.argv = [sys.argv[0], "--resume-run", normalized_id, *sys.argv[3:]]


def _handle_workspace_commands() -> bool:
    """Implementation for managing Git and non-Git isolated copies."""
    if len(sys.argv) < 2 or sys.argv[1] != "workspace":
        return False
    if len(sys.argv) < 3 or sys.argv[2] not in {"list", "status", "diff", "apply", "discard"}:
        print("Usage: nexus workspace {list|status|diff|apply|discard} [session_id]")
        return True

    command = sys.argv[2]
    from nexus.workspace import WorkspaceManager

    manager = WorkspaceManager()

    if command == "list":
        worktrees = manager.list_worktrees()
        if not worktrees:
            print("No active workspaces.")
        else:
            for w in worktrees:
                print(
                    f"[{w.created_at}] {Path(w.path).name} - {w.backend} - {w.branch or 'N/A'} (Source: {w.source_repository})"
                )
        return True

    session_id = sys.argv[3] if len(sys.argv) > 3 else None
    if not session_id:
        cwd = os.getcwd()
        worktrees = manager.list_worktrees()
        worktrees = [w for w in worktrees if w.source_repository == cwd]
        if not worktrees:
            print("No active workspaces for current directory.")
            return True
        session = manager.resolve_worktree(Path(worktrees[0].path).name)
    else:
        session = manager.resolve_worktree(session_id)

    if not session or not session.info:
        print("Workspace not found.")
        return True

    if command == "status":
        print(json.dumps(session.status(), indent=2))
    elif command == "diff":
        diff_text = session.diff()
        if diff_text:
            print(diff_text)
        else:
            print("No changes.")
    elif command == "apply":
        try:
            session.apply()
            from nexus.ui import print_success

            print_success("Workspace changes applied successfully.")
        except ImportError as e:
            from nexus.ui import print_error

            print_error(f"Apply failed: {e}")
    elif command == "discard":
        session.discard()
        from nexus.ui import print_success

        print_success("Workspace discarded.")

    return True


def _handle_run_management() -> bool:
    """Handle durable run inspection commands before model initialization."""
    if len(sys.argv) < 2 or sys.argv[1] not in {
        "runs",
        "inspect",
        "replay",
        "rollback",
    }:
        return False
    command = sys.argv[1]
    catalog = RunCatalog()
    if command == "runs":
        working_dir = os.getcwd()
        records = catalog.list(working_dir=working_dir, limit=100)
        if "--json" in sys.argv[2:]:
            print(json.dumps([item.__dict__ for item in records], indent=2))
        elif not records:
            print("No durable Nexus runs exist for this directory.")
        else:
            for item in records:
                print(f"{item.session_id}/{item.turn_id}  {item.status:<20} {item.request[:80]}")
        return True

    run_id = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        if command == "inspect":
            print(json.dumps(catalog.inspect(run_id), indent=2))
        elif command == "replay":
            for event in catalog.replay(run_id):
                print(json.dumps(event, ensure_ascii=False))
        else:
            from nexus.recovery import RollbackManager

            success, detail = RollbackManager.rollback(run_id)
            if not success:
                raise RuntimeError(detail)
            print(detail)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return True


def _handle_generate_dashboard() -> bool:
    """Resolve ``nexus generate-dashboard --input <json> --output <html_path>``."""
    if len(sys.argv) < 2 or sys.argv[1] != "generate-dashboard":
        return False
    import argparse

    parser = argparse.ArgumentParser(prog="nexus generate-dashboard")
    parser.add_argument("--input", required=True, help="Path to benchmark-result JSON")
    parser.add_argument("--output", required=True, help="Path to write the HTML dashboard")
    args = parser.parse_args(sys.argv[2:])

    from nexus.dashboard import RegressionDashboard

    try:
        RegressionDashboard.generate(args.input, args.output)
        from nexus.ui import print_success

        print_success(f"Dashboard generated successfully at {args.output}")
    except ImportError as e:
        from nexus.ui import print_error

        print_error(f"Failed to generate dashboard: {e}")
        sys.exit(1)
    return True


def _handle_benchmark() -> bool:
    """Run or validate a versioned public benchmark manifest."""
    if len(sys.argv) < 2 or sys.argv[1] != "benchmark":
        return False
    benchmark_parser = argparse.ArgumentParser(
        prog="nexus benchmark",
        description="Run reproducible Nexus tasks in disposable repository copies.",
    )
    benchmark_parser.add_argument(
        "--manifest",
        required=True,
        help="Path to a nexus.benchmark.v1 or nexus.benchmark.v2 JSON manifest",
    )
    benchmark_parser.add_argument(
        "--output",
        help="Optional path for the versioned JSON result",
    )
    benchmark_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the manifest and repositories without invoking a model",
    )
    benchmark_parser.add_argument(
        "--artifact-dir",
        help="Preserve redacted per-attempt evidence under this directory",
    )
    benchmark_parser.add_argument(
        "--keep-workspaces",
        action="store_true",
        help="Keep isolated benchmark workspaces for forensic inspection",
    )
    benchmark_args = benchmark_parser.parse_args(sys.argv[2:])
    from nexus.benchmark import BenchmarkRunner, BenchmarkSuite

    try:
        suite = BenchmarkSuite.load(benchmark_args.manifest)
        report = BenchmarkRunner(
            suite,
            artifact_root=benchmark_args.artifact_dir,
            keep_workspaces=benchmark_args.keep_workspaces,
        ).run(dry_run=benchmark_args.dry_run)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    payload = report.to_dict()
    rendered = json.dumps(payload, indent=2)
    if benchmark_args.output:
        output_path = Path(benchmark_args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    # A dry-run is a release gate, not a best-effort preview. Missing fixture
    # repositories and other blocked tasks must fail with a non-zero status.
    if payload["summary"]["failed"]:
        raise SystemExit(2)
    return True


def _solve_issue_prompt() -> bool:
    """Resolve ``nexus solve-issue <number>`` through the authenticated gh CLI."""
    if len(sys.argv) < 2 or sys.argv[1] != "solve-issue":
        return False
    if len(sys.argv) < 3 or not sys.argv[2].isdigit():
        raise SystemExit("Usage: nexus solve-issue <issue-number> [options]")
    issue_number = sys.argv[2]

    try:
        from nexus.github import GitHubIntegration

        issue = GitHubIntegration.view_issue(issue_number)
    except ImportError as exc:
        raise SystemExit(str(exc)) from exc

    if not issue:
        raise SystemExit(f"Issue #{issue_number} not found or could not be parsed.")

    comments = "\\n".join(
        f"- {item.get('author', {}).get('login', 'unknown')}: {item.get('body', '')}"
        for item in issue.get("comments", [])
    )
    prompt = (
        f"Solve GitHub issue #{issue.get('number')}: {issue.get('title')}\\n\\n"
        f"{issue.get('body', '')}\\n\\nDiscussion:\\n{comments or '(none)'}\\n\\n"
        "Reproduce the issue, implement the smallest correct fix, add regression tests, "
        "and run deterministic verification. When the tests pass, use the github_create_pr "
        "tool to open a pull request for this issue."
    )
    rest = sys.argv[3:]
    if "--mode" not in rest:
        rest.extend(["--mode", "autonomous"])
    if "--print" not in rest and "-p" not in rest:
        rest.append("--print")
    sys.argv = [sys.argv[0], *rest, prompt]
    return True


def handle_slash_command(cmd: str, agent: Agent) -> bool:
    """Handle slash commands. Returns True if the command was handled."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/exit", "/quit", "/q"):
        ui.print_info("Goodbye! 👋")
        sys.exit(0)

    elif command == "/help":
        ui.print_help()

    elif command == "/models":
        if arg:
            # User typed "/models <name>" — treat as model switch
            if agent.set_model(arg.strip()):
                ui.print_model_info(agent.model_key, agent.model_cfg)
            else:
                ui.print_error(f"Unknown model: '{arg}'. Use /models to see available options.")
        else:
            ui.print_models_table()

    elif command == "/model":
        if not arg:
            ui.print_error("Usage: /model <name>  (e.g., /model kimi or /model nova_codex)")
            return True
        if agent.set_model(arg.strip()):
            ui.print_model_info(agent.model_key, agent.model_cfg)
        else:
            ui.print_error(f"Unknown model: '{arg}'. Use /models to see available options.")

    elif command.startswith("/model"):
        # Handle typos like "/modelglm-5.2" or "/modelsdeepseek-v4"
        model_name = command.replace("/models", "").replace("/model", "").strip()
        if model_name:
            if agent.set_model(model_name):
                ui.print_model_info(agent.model_key, agent.model_cfg)
            else:
                ui.print_error(
                    f"Unknown model: '{model_name}'. Use /models to see available options."
                )
        else:
            ui.print_models_table()

    elif command == "/clear":
        agent.clear_history()
        ui.print_success("Conversation history cleared.")

    elif command == "/reset":
        agent.clear_history()
        os.system("clear" if os.name != "nt" else "cls")
        ui.print_banner()
        ui.print_model_info(agent.model_key, agent.model_cfg)
        ui.print_success("Session reset.")

    elif command == "/project":
        tree = tool_get_project_structure(agent.working_dir)
        ui.console.print(tree)

    elif command == "/cost":
        ui.print_token_usage(
            agent.total_prompt_tokens,
            agent.total_completion_tokens,
            agent.total_prompt_tokens + agent.total_completion_tokens,
        )
        ui.console.print(agent.get_cost_dashboard())

    elif command == "/run-status":
        ui.console.print(agent.get_run_status())

    elif command == "/rollback-run":
        success, message = agent.rollback_current_run()
        ui.print_tool_result(message, success)

    elif command == "/system":
        if not arg:
            ui.print_info(f"Current system prompt:\n{agent.system_prompt[:500]}...")
            return True
        agent.set_system_prompt(arg)
        ui.print_success("System prompt updated.")

    elif command == "/save":
        if not arg:
            arg = f"nexus_conversation_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        agent.save_conversation(arg)

    elif command == "/multi":
        text = ui.get_multiline_input()
        if text.strip():
            agent.run(text)

    elif command == "/run":
        if not arg:
            ui.print_error("Usage: /run <shell command>")
        else:
            result, success = agent._execute_tool_with_safety(
                "run_command", {"command": arg, "cwd": agent.working_dir}
            )
            ui.print_tool_result(result, success)

    # ─── NEW COMMANDS ────────────────────────────────────────────────

    elif command == "/undo":
        history = get_history()
        success, msg = history.undo_changes(int(arg) if arg.strip().isdigit() else 1)
        if success:
            ui.print_success(msg)
        else:
            ui.print_error(msg)

    elif command == "/diff":
        history = get_history()
        diff = history.get_last_diff()
        if diff:
            from rich.syntax import Syntax

            ui.console.print(Syntax(diff, "diff", theme="monokai", line_numbers=False))
        else:
            ui.print_info("No file changes to show.")

    elif command == "/changes":
        history = get_history()
        summary = history.get_change_summary()
        ui.console.print(summary)

    elif command == "/confirm":
        result, success = agent.confirm_pending_operation(arg)
        ui.print_tool_result(result, success)

    elif command == "/cancel":
        result, success = agent.cancel_pending_operation(arg)
        ui.print_tool_result(result, success)

    elif command == "/apply":
        result, success = agent.apply_pending_edit(arg)
        ui.print_tool_result(result, success)

    elif command == "/reject":
        result, success = agent.reject_pending_edit(arg)
        ui.print_tool_result(result, success)

    elif command == "/pending":
        ui.console.print(agent.pending_edits_summary())

    elif command == "/edit-pending":
        edit_parts = arg.split(maxsplit=1)
        if len(edit_parts) != 2:
            ui.print_error("Usage: /edit-pending <edit-id> <replacement-file>")
        else:
            result, success = agent.replace_pending_edit(edit_parts[0], edit_parts[1])
            ui.print_tool_result(result, success)

    elif command == "/history":
        memory = ConversationMemory()
        convs = memory.list_conversations(limit=15)
        if not convs:
            ui.print_info("No saved conversations.")
            return True
        ui.print_conversation_list(convs)

    elif command == "/resume":
        if not arg:
            ui.print_error("Usage: /resume <conversation_id>")
            return True
        if agent.load_conversation(arg.strip()):
            ui.print_success(f"Resumed conversation: {arg.strip()}")
            ui.print_info(
                f"Loaded {len(agent.messages)} messages. Model: {agent.model_cfg['name']}"
            )
        else:
            ui.print_error(f"Could not find conversation: {arg}")

    elif command == "/compact":
        removed = agent.compact_conversation()
        if removed > 0:
            ui.print_success(
                f"Compacted conversation: removed {removed} old messages, keeping recent context."
            )
        else:
            ui.print_info("Conversation is already compact.")

    elif command == "/git":
        from nexus.tools import tool_git_status

        result = tool_git_status(agent.working_dir)
        ui.console.print(result)

    elif command == "/tools":
        ui.print_tools_table()

    # ─── ADDED EXTENSION COMMANDS ────────────────────────────────────

    elif command == "/skills":
        ui.console.print(agent.skills.get_skill_summary())

    elif command == "/hooks":
        ui.console.print(agent.hooks.get_summary())

    elif command == "/subagent":
        if not arg:
            ui.print_error(
                "Usage: /subagent <template> <task>  (e.g., /subagent security Scan for hardcoded passwords)"
            )
            return True
        sub_parts = arg.strip().split(maxsplit=1)
        if len(sub_parts) < 2:
            ui.print_error("Usage: /subagent <template> <task>")
            return True
        template, task = sub_parts[0], sub_parts[1]
        report = agent.spawn_subagent(template, task)
        ui.console.print(report)

    elif command == "/verify":
        if not arg or arg.strip().isdigit() or arg.strip().startswith("evidence"):
            count_text = arg.replace("evidence", "").strip() if arg else ""
            report = agent.verify_evidence(int(count_text) if count_text.isdigit() else 10)
        else:
            checks = None if arg.strip() == "project" else arg.strip().split()
            report = agent.run_verification(checks)
        ui.console.print(report)

    elif command in ("/rewind",):
        history = get_history()
        success, msg = history.undo_changes(int(arg) if arg.strip().isdigit() else 1)
        ui.print_tool_result(msg, success)

    elif command in ("/permissions", "/mode"):
        if not arg:
            ui.print_info(f"Permission mode: {agent.permission_mode}")
        elif arg in ("default", "acceptEdits", "plan"):
            agent.permission_mode = arg
            ui.print_success(f"Permission mode set to {arg}")
        else:
            ui.print_error("Use: /permissions default|acceptEdits|plan")

    elif command == "/trust":
        trust_parts = arg.split(maxsplit=1)
        if not trust_parts or not trust_parts[0]:
            ui.console.print(agent.get_trust_summary())
        elif len(trust_parts) == 2 and trust_parts[0] in ("approve", "reject"):
            decision = (
                agent.trust.approve(trust_parts[1])
                if trust_parts[0] == "approve"
                else agent.trust.reject(trust_parts[1])
            )
            agent.project_mem.reload()
            agent._load_rules_and_preferences()
            agent._update_system_prompt()
            ui.print_success(
                f"{trust_parts[0].title()}d exact config digest: {decision.path} {decision.digest}"
            )
        else:
            ui.print_error("Usage: /trust [approve|reject] <path>")

    elif command == "/init":
        path = agent.project_mem.create_default_rules()
        ui.print_info(
            f"Created {path}. Review it, then run /trust approve {path} before Nexus loads it."
        )

    elif command == "/context":
        ui.console.print(agent.context_mgr.get_architecture_context())
        ui.console.print(agent.context_mgr.get_relevant_context())

    elif command == "/plan":
        agent.permission_mode = "plan"
        ui.print_success("Entered read-only plan mode.")

    elif command == "/mcp":
        ui.console.print(agent.mcp.get_summary())

    elif command == "/plugins":
        if not agent.plugin_loader.plugins:
            ui.print_info("No plugins loaded.")
        else:
            ui.console.print(f"🔌 Plugins ({len(agent.plugin_loader.plugins)} loaded)")
            for name, plugin in agent.plugin_loader.plugins.items():
                ui.console.print(f"  🟢 {name} (v{plugin.version}) — {plugin.description}")

    elif command == "/web":
        port = int(arg.strip()) if arg.strip().isdigit() else 3000
        api_key = agent.client.api_key if agent.client else ""
        start_background_web_server(api_key, agent.model_key, port, agent.working_dir)
        ui.print_success(f"Web UI server started in background at http://localhost:{port}")

    elif command == "/rules":
        rules = agent.project_mem.load_rules()
        ui.console.print(f"📋 Project Rules ({agent.working_dir}/NEXUS.md):")
        ui.console.print(f"  Build command: {rules.build_command or 'None'}")
        ui.console.print(f"  Test command:  {rules.test_command or 'None'}")
        ui.console.print(f"  Lint command:  {rules.lint_command or 'None'}")
        ui.console.print(f"  Format command:{rules.format_command or 'None'}")
        if rules.conventions:
            ui.console.print("\nRules:")
            for rule in rules.conventions:
                ui.console.print(f"  • {rule}")

    else:
        ui.print_error(f"Unknown command: {command}. Type /help for available commands.")

    return True


def run_interactive(agent: Agent):
    """Run the interactive REPL loop."""
    ui.print_banner()
    ui.print_model_info(agent.model_key, agent.model_cfg)
    if getattr(agent, "worktree", None) and agent.worktree.info:
        ui.console.print(f"\n  [bold green]Workspace Active:[/] {agent.worktree.info.path}")
        if agent.worktree.info.branch:
            ui.console.print(f"  [bold green]Branch:[/] {agent.worktree.info.branch}")
    ui.console.print(f"\n  [{ui.DIM}]Type your request, or /help for commands. /exit to quit.[/]\n")

    while True:
        try:
            user_input = ui.get_prompt(agent.model_cfg["name"])

            if not user_input.strip():
                continue

            # Handle slash commands
            if user_input.strip().startswith("/"):
                handle_slash_command(user_input.strip(), agent)
                continue

            if user_input.lstrip().startswith("!"):
                command = user_input.lstrip()[1:].strip()
                try:
                    argv = shlex.split(command, posix=True)
                except ValueError as e:
                    ui.print_error(f"Invalid command: {e}")
                    continue
                result, success = agent._execute_tool_with_safety(
                    "run_process", 
                    {"argv": argv, "cwd": agent.working_dir},
                    _user_initiated=True
                )
                ui.print_tool_result(result, success)
                continue

            # Run the agent
            agent.run(user_input)

        except KeyboardInterrupt:
            ui.console.print(f"\n[{ui.DIM}]Ctrl+C — type /exit to quit[/]")
            continue
        except EOFError:
            ui.print_info("Goodbye! 👋")
            break


def run_web(
    api_key: str,
    model: str,
    port: int,
    working_dir: str | None,
    model_id_override: str | None = None,
    local_intern_mode: str = "off",
    enable_nova_fallback: bool = False,
    plugins_enabled: bool = False,
    tools_enabled: bool = True,
):
    """Launch the web interface."""
    try:
        import uvicorn

        from nexus.webapp.server import create_app

        ui.print_banner()
        ui.console.print(
            f"  [bold {ui.GREEN}]🌐 Web Interface[/] starting on [bold {ui.CYAN}]http://localhost:{port}[/]\n"
            f"  [{ui.DIM}]Press Ctrl+C to stop[/]\n"
        )

        app = create_app(
            api_key=api_key,
            model=model,
            working_dir=working_dir,
            model_id_override=model_id_override,
            local_intern_mode=local_intern_mode,
            enable_nova_fallback=enable_nova_fallback,
            plugins_enabled=plugins_enabled,
            tools_enabled=tools_enabled,
        )
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

    except ImportError as e:
        ui.print_error(f"Web dependencies not installed: {e}")
        ui.print_info("Run: pip install starlette uvicorn websockets")
        sys.exit(1)


def start_background_web_server(api_key: str, model: str, port: int, working_dir: str | None):
    """Start the web server in a daemon thread and automatically open the default browser."""
    import threading
    import time
    import webbrowser

    import uvicorn

    from nexus.webapp.server import create_app

    def _run():
        try:
            app = create_app(api_key=api_key, model=model, working_dir=working_dir)
            # Run uvicorn quietly (log_level="error") to avoid cluttered CLI printouts
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
        except (OSError, RuntimeError):
            pass  # Fail silently if port is already bound by another instance

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # Open the browser automatically after the server binds
    def _open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(f"http://localhost:{port}")
        except OSError:
            pass

    threading.Thread(target=_open_browser, daemon=True).start()


def non_interactive_exit_code(content: str, events: list[dict]) -> int:
    """Return a machine-meaningful status for one-shot CLI execution."""
    if any(
        event.get("type") == "tool_call" and not event.get("success", False) for event in events
    ):
        return 2
    lowered = (content or "").strip().lower()
    failure_markers = (
        "nova backend error:",
        "nova guardrails blocked",
        "nova guardrails rejected",
        "nexus ai provider failover error",
        "❌",
    )
    if lowered.startswith(("error:", "blocked:", "failed:")):
        return 2
    return 2 if any(marker in lowered for marker in failure_markers) else 0


def _close_and_exit(agent: Agent, exit_code: int) -> None:
    """Release session-owned resources before terminating the CLI process."""

    agent.close(discard_workspace=not getattr(agent, "keep_workspace", False))
    raise SystemExit(exit_code)


def _configure_output_streams(streams=None) -> None:
    """Use UTF-8 for redirected Windows output and other legacy locales."""

    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (LookupError, OSError, ValueError):
            pass


def main():
    _configure_output_streams()
    if _handle_run_management():
        return
    if _handle_workspace_commands():
        return
    if _handle_generate_dashboard():
        return
    if _handle_benchmark():
        return
    _solve_issue_prompt()
    _normalize_subcommand_argv()
    args = parse_args()

    resume_snapshot = None
    if args.resume_run:
        try:
            resume_snapshot = RunCatalog().inspect(args.resume_run)
        except FileNotFoundError as exc:
            ui.print_error(str(exc))
            sys.exit(1)
        request_record = resume_snapshot.get("request", {})
        args.working_dir = request_record.get("working_dir") or args.working_dir
        metadata = request_record.get("metadata", {})
        if metadata.get("model"):
            args.model = metadata["model"]
        if metadata.get("permission_mode") in {"default", "acceptEdits", "plan"}:
            args.permission_mode = metadata["permission_mode"]

    if args.local_only:
        args.mode = "local-only"
    elif args.prefer_cheap:
        args.mode = "budget"
    elif args.quality == "maximum":
        args.mode = "quality"

    mode_permissions = {
        "plan": "plan",
        "review": "default",
        "workspace": "acceptEdits",
        "autonomous": "acceptEdits",
        "local-only": "acceptEdits",
        "quality": "default",
        "budget": "acceptEdits",
        "ci": "acceptEdits",
    }
    if args.permission_mode == "default":
        args.permission_mode = mode_permissions[args.mode]

    if args.mode == "local-only" or args.mode == "budget":
        args.model = "nova_codex"

    if args.mode == "budget":
        if args.max_cost_usd is None:
            args.max_cost_usd = 0.10
    elif args.mode == "quality":
        args.max_turns = max(args.max_turns, 20)
    elif args.mode == "ci":
        args.print_mode = True
        if args.output_format == "text":
            args.output_format = "json"

    invalid_dirs = [item for item in args.add_dir if not Path(item).expanduser().is_dir()]
    if invalid_dirs:
        ui.print_error("Additional directories do not exist: " + ", ".join(invalid_dirs))
        sys.exit(1)

    # List models and exit
    if args.list_models:
        ui.print_models_table()
        sys.exit(0)

    # Direct command mode (runs before model preflight).
    # Direct commands use plan-mode policy which does NOT require OS isolation.
    # Dangerous operations are still gated by the safety layer's confirmation
    # mechanism; isolation is not the protection for user-typed commands.
    if args.prompt and args.prompt.lstrip().startswith("!"):
        try:
            command = args.prompt.lstrip()[1:].strip()
            argv = shlex.split(command, posix=True)
            # Override: use plan-mode policy (no require_os_isolation) so that
            # a simple `!echo hello` works without a native sandbox binary.
            # The effective mode from the user's --mode flag is preserved in
            # the output metadata so callers can inspect it.
            _mode_policy = get_mode_policy("plan")
            agent = Agent(
                api_key="offline-direct-command",
                model_key="custom",
                model_id_override="offline/direct",
                working_dir=args.working_dir,
                mode_policy=_mode_policy,
                permission_mode=args.permission_mode,
                workspace_isolation=False,
                tools_enabled=False,
                plugins_enabled=False,
            )
            result, success = agent._execute_tool_with_safety(
                "run_process", {"argv": argv, "cwd": agent.working_dir},
                _user_initiated=True,
                _user_confirmed=args.confirm_danger
            )
            if not args.confirm_danger and "⏸️ PENDING_CONFIRMATION" in result:
                result = (
                    f"⏸️ PENDING_CONFIRMATION: Dangerous command detected.\n"
                    f"Run with --confirm-danger to execute this exact command: {args.prompt}"
                )
            if args.output_format in ("json", "jsonl", "stream-json"):
                print(
                    json.dumps(
                        {
                            "type": "tool_call",
                            "name": "run_process",
                            "result": result,
                            "success": success,
                        }
                    )
                )
            else:
                print(result)
            _close_and_exit(agent, 0 if success else 2)
        except (LookupError, TypeError, ValueError) as exc:
            ui.print_error(str(exc))
            sys.exit(2)

    if args.doctor:
        model_cfg = resolve_model(args.model) or {}
        success, report = run_doctor(
            working_dir=args.working_dir,
            nova_model=model_cfg.get("ollama_model", "nova_codex"),
            mode=args.mode,
        )
        print(report)
        sys.exit(0 if success else 2)

    # Validate model
    model_cfg = resolve_model(args.model)
    if not model_cfg:
        ui.print_error(f"Unknown model: '{args.model}'")
        ui.print_info("Available models:")
        ui.print_models_table()
        sys.exit(1)

    from nexus.api import _load_env_file

    _load_env_file()
    api_key = args.api_key or os.environ.get("NVIDIA_API_KEY")
    has_hosted_key = bool(
        api_key
        or os.environ.get("NEXUS_OPENAI_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )
    is_local_nova = model_cfg.get("backend") == "nova"
    if not has_hosted_key and not is_local_nova:
        ui.console.print()
        ui.print_error("No usable hosted-provider credential found!")
        ui.console.print(
            f"\n  [{ui.WHITE}]For NVIDIA, get an API key from:[/] "
            f"[bold {ui.CYAN}]https://build.nvidia.com[/]\n"
            f"\n  [{ui.WHITE}]Then set one of:[/]"
            f"\n    [bold {ui.GREEN}]export NVIDIA_API_KEY=nvapi-your-key-here[/]"
            f"\n    [bold {ui.GREEN}]export GROQ_API_KEY=gsk-your-key-here[/]"
            f"\n    [bold {ui.GREEN}]export OPENROUTER_API_KEY=sk-or-your-key-here[/]"
            f"\n\n  [{ui.WHITE}]For a custom OpenAI-compatible endpoint:[/]"
            f"\n    [bold {ui.GREEN}]export NEXUS_OPENAI_BASE_URL=https://provider.example/v1[/]"
            f"\n    [bold {ui.GREEN}]export NEXUS_OPENAI_API_KEY=your-key[/]"
            f"\n    [bold {ui.GREEN}]nexus --model custom --model-id provider/model[/]\n"
        )
        sys.exit(1)

    from nexus.preflight import probe_model

    selected_probe = probe_model(model_cfg, model_name=args.model)
    if not selected_probe.ready:
        ui.print_error(selected_probe.detail)
        for action in selected_probe.remediation:
            ui.print_info(action)
        sys.exit(2)

    # Web mode
    if args.web:
        run_web(
            api_key,
            args.model,
            args.port,
            args.working_dir,
            model_id_override=args.model_id,
            local_intern_mode=args.local_intern,
            enable_nova_fallback=args.enable_nova_fallback,
            plugins_enabled=args.enable_plugins,
            tools_enabled=not args.no_tools,
        )
        return

    # Disable tools if requested
    if args.no_tools:
        model_cfg["supports_tools"] = False

    # Create agent
    try:
        _mode_policy = get_mode_policy(args.mode)
        working_dir_path = Path(args.working_dir or os.getcwd()).resolve()
        is_git_repo = (working_dir_path / ".git").exists()
        automatic_workspace = _mode_policy.may_edit and not args.resume_run and is_git_repo
        agent = Agent(
            api_key=api_key,
            model_key=args.model,
            working_dir=args.working_dir,
            mode_policy=_mode_policy,
            permission_mode=args.permission_mode,
            allowed_tools=args.allowed_tools,
            disallowed_tools=args.disallowed_tools,
            additional_dirs=args.add_dir,
            max_turns=args.max_turns,
            workspace_isolation=((args.workspace or automatic_workspace) and not args.no_workspace),
            max_hosted_calls=args.max_hosted_calls,
            max_provider_attempts=args.max_provider_attempts,
            max_prompt_tokens=args.max_prompt_tokens,
            max_completion_tokens=args.max_completion_tokens,
            max_cost_usd=args.max_cost_usd,
            input_price_per_million=args.input_price_per_million,
            output_price_per_million=args.output_price_per_million,
            model_id_override=args.model_id,
            local_intern_mode=args.local_intern,
            enable_nova_fallback=args.enable_nova_fallback,
            plugins_enabled=args.enable_plugins,
            tools_enabled=not args.no_tools,
        )
    except ValueError as e:
        ui.print_error(str(e))
        sys.exit(1)

    # Resume conversation
    if args.continue_last:
        candidates = [
            item
            for item in agent.memory.list_conversations(limit=100)
            if item.get("working_dir") == agent.working_dir
        ]
        if not candidates or not agent.load_conversation(candidates[0]["id"]):
            ui.print_error("No resumable conversation found for this directory.")
            _close_and_exit(agent, 1)
    elif args.resume:
        if agent.load_conversation(args.resume):
            ui.print_success(f"Resumed conversation: {args.resume}")
        else:
            ui.print_error(f"Could not find conversation: {args.resume}")
            _close_and_exit(agent, 1)

    if args.resume_run:
        try:
            content, events = agent.resume_interrupted(args.resume_run)
        except ValueError as exc:
            ui.print_error(str(exc))
            _close_and_exit(agent, 2)
        exit_code = non_interactive_exit_code(content, events)
        final_report = agent.run_ledger.resume_summary().get("final_report", {})
        status = final_report.get("status")
        if status in {"FAILED", "PARTIALLY_VERIFIED", "UNVERIFIED"}:
            exit_code = 2
        elif status in {"AWAITING_APPROVAL", "BLOCKED"}:
            exit_code = 3
        elif status == "VERIFIED":
            exit_code = 0
        if args.output_format in {"json", "jsonl", "stream-json"}:
            print(
                json.dumps(
                    {
                        "success": exit_code == 0,
                        "result": content,
                        "events": events,
                        "session_id": agent.conversation_id,
                        "run": final_report,
                    }
                )
            )
        else:
            print(content)
        _close_and_exit(agent, exit_code)

    # Custom system prompt
    if args.system:
        agent.set_system_prompt(args.system)

    # Single prompt mode
    if args.prompt:
        if args.print_mode or args.output_format != "text":
            content, events = agent.run_non_interactive(args.prompt)
            exit_code = non_interactive_exit_code(content, events)
            final_report = agent.run_ledger.resume_summary().get("final_report", {})
            status = final_report.get("status")
            if status in {"FAILED", "PARTIALLY_VERIFIED", "UNVERIFIED"}:
                exit_code = 2
            elif status in {"AWAITING_APPROVAL", "BLOCKED"}:
                exit_code = 3
            elif status == "VERIFIED":
                exit_code = 0
            if args.output_format == "json":
                print(
                    json.dumps(
                        {
                            "success": exit_code == 0,
                            "result": content,
                            "events": events,
                            "session_id": agent.conversation_id,
                            "run": final_report,
                        }
                    )
                )
            elif args.output_format in {"jsonl", "stream-json"}:
                for event in events:
                    print(json.dumps(event))
                print(
                    json.dumps(
                        {
                            "type": "result",
                            "success": exit_code == 0,
                            "result": content,
                            "session_id": agent.conversation_id,
                            "run": final_report,
                        }
                    )
                )
            else:
                print(content)
                print("\\n")
                try:
                    from nexus.report import FinalReportGenerator

                    final_report_path = agent.run_ledger._require_turn() / "final_report.json"
                    print(FinalReportGenerator.generate(final_report_path))
                except ImportError:
                    pass
            _close_and_exit(agent, exit_code)
        else:
            if getattr(agent, "worktree", None) and agent.worktree.info:
                ui.console.print(f"\n  [bold green]Workspace Active:[/] {agent.worktree.info.path}")
                if agent.worktree.info.branch:
                    ui.console.print(f"  [bold green]Branch:[/] {agent.worktree.info.branch}")
                ui.console.print("")
            agent.run(args.prompt)
            final_report = agent.export_final_report()
            status = final_report.get("status", "UNVERIFIED")
            exit_code = 2
            if status in {"AWAITING_APPROVAL", "BLOCKED"}:
                exit_code = 3
            elif status == "VERIFIED":
                exit_code = 0

            try:
                from nexus.report import FinalReportGenerator

                final_report_path = agent.run_ledger._require_turn() / "final_report.json"
                print("\\n")
                print(FinalReportGenerator.generate(final_report_path))
            except ImportError:
                pass
            _close_and_exit(agent, exit_code)

    # Interactive mode
    try:
        run_interactive(agent)
    finally:
        agent.close(discard_workspace=not getattr(agent, "keep_workspace", False))


if __name__ == "__main__":
    main()
