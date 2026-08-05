import argparse
import json
import os
import shlex
import sys
from dataclasses import asdict
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
        "--routing-mode",
        choices=("cheapest", "private", "fastest", "balanced", "strongest", "manual"),
        default="balanced",
        help="Model portfolio routing mode (default: balanced)",
    )
    parser.add_argument(
        "--budget-inr",
        type=float,
        help="Hard per-run budget ceiling in INR (e.g. --budget-inr 20)",
    )
    parser.add_argument(
        "--ask-before-frontier",
        action="store_true",
        help="Require user approval before escalating to a frontier tier model",
    )
    parser.add_argument(
        "--mode",
        help=(
            "Operational policy preset (default: review). "
            "Modes and isolation requirements: "
            "plan — read-only, no OS sandbox needed; "
            "review — edits require confirmation, native sandbox required for commands; "
            "workspace — Git-isolated worktree, native sandbox required; "
            "autonomous — hands-free, native sandbox required (bubblewrap on Linux); "
            "local-only — Nova only, native sandbox required; "
            "quality — maximum verification, native sandbox required; "
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
        "--keep-workspace",
        action="store_true",
        help="Retain the isolated workspace after Nexus exits for inspection or manual apply",
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

