#!/usr/bin/env python3
"""
NexusAI — NVIDIA-Powered Coding Agent CLI

Usage:
    nexus                          Start interactive mode with default model
    nexus --model kimi             Start with a specific model
    nexus --web                    Start the web interface
    nexus "build a flask app"      Run a single prompt and exit
    nexus --list-models            Show all available models
"""

import argparse
import os
import sys

from nexus.agent import Agent
from nexus.models import resolve_model, DEFAULT_MODEL, ALIASES
from nexus import ui
from nexus.tools import tool_get_project_structure
from nexus.history import get_history
from nexus.memory import ConversationMemory


def parse_args():
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="NexusAI — NVIDIA-Powered Coding Agent (Claude Code Alternative)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexus                              Interactive mode (default: DeepSeek V4)
  nexus --model glm-5.2              Use GLM 5.2
  nexus --model kimi                 Use Kimi K2.6
  nexus --web                        Launch web interface (Cursor-like UI)
  nexus --web --port 8080            Web interface on custom port
  nexus "create a REST API in Go"    Single prompt mode
  nexus --list-models                List all available models

Environment:
  NVIDIA_API_KEY                     Your NVIDIA API key (from build.nvidia.com)
        """,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Single prompt to run (omit for interactive mode)",
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"Model to use (default: {DEFAULT_MODEL}). Use --list-models to see all.",
    )
    parser.add_argument(
        "--api-key", "-k",
        help="NVIDIA API key (or set NVIDIA_API_KEY env var)",
    )
    parser.add_argument(
        "--working-dir", "-d",
        help="Working directory (default: current directory)",
    )
    parser.add_argument(
        "--list-models", "-l",
        action="store_true",
        help="List all available models and exit",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable tool calling (pure chat mode)",
    )
    parser.add_argument(
        "--system", "-s",
        help="Custom system prompt",
    )
    parser.add_argument(
        "--web", "-w",
        action="store_true",
        help="Launch the web interface instead of CLI",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=3000,
        help="Port for web interface (default: 3000)",
    )
    parser.add_argument(
        "--resume", "-r",
        help="Resume a previous conversation by ID",
    )
    return parser.parse_args()


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
        ui.print_models_table()

    elif command == "/model":
        if not arg:
            ui.print_error("Usage: /model <name>  (e.g., /model kimi)")
            return True
        if agent.set_model(arg.strip()):
            ui.print_model_info(agent.model_key, agent.model_cfg)
        else:
            ui.print_error(f"Unknown model: '{arg}'. Use /models to see available options.")

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

    # ─── NEW COMMANDS ────────────────────────────────────────────────

    elif command == "/undo":
        history = get_history()
        success, msg = history.undo_last_change()
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
            ui.print_info(f"Loaded {len(agent.messages)} messages. Model: {agent.model_cfg['name']}")
        else:
            ui.print_error(f"Could not find conversation: {arg}")

    elif command == "/compact":
        removed = agent.compact_conversation()
        if removed > 0:
            ui.print_success(f"Compacted conversation: removed {removed} old messages, keeping recent context.")
        else:
            ui.print_info("Conversation is already compact.")

    elif command == "/git":
        from nexus.tools import tool_git_status
        result = tool_git_status(agent.working_dir)
        ui.console.print(result)

    elif command == "/tools":
        ui.print_tools_table()

    else:
        ui.print_error(f"Unknown command: {command}. Type /help for available commands.")

    return True


def run_interactive(agent: Agent):
    """Run the interactive REPL loop."""
    ui.print_banner()
    ui.print_model_info(agent.model_key, agent.model_cfg)
    ui.console.print(
        f"  [{ui.DIM}]Type your request, or /help for commands. /exit to quit.[/]\n"
    )

    while True:
        try:
            user_input = ui.get_prompt(agent.model_cfg["name"])

            if not user_input.strip():
                continue

            # Handle slash commands
            if user_input.strip().startswith("/"):
                handle_slash_command(user_input.strip(), agent)
                continue

            # Run the agent
            agent.run(user_input)

        except KeyboardInterrupt:
            ui.console.print(f"\n[{ui.DIM}]Ctrl+C — type /exit to quit[/]")
            continue
        except EOFError:
            ui.print_info("Goodbye! 👋")
            break


def run_web(api_key: str, model: str, port: int, working_dir: str | None):
    """Launch the web interface."""
    try:
        from nexus.webapp.server import create_app
        import uvicorn

        ui.print_banner()
        ui.console.print(
            f"  [bold {ui.GREEN}]🌐 Web Interface[/] starting on [bold {ui.CYAN}]http://localhost:{port}[/]\n"
            f"  [{ui.DIM}]Press Ctrl+C to stop[/]\n"
        )

        app = create_app(api_key=api_key, model=model, working_dir=working_dir)
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    except ImportError as e:
        ui.print_error(f"Web dependencies not installed: {e}")
        ui.print_info("Run: pip install starlette uvicorn websockets")
        sys.exit(1)


def main():
    args = parse_args()

    # List models and exit
    if args.list_models:
        ui.print_models_table()
        sys.exit(0)

    # Validate model
    model_cfg = resolve_model(args.model)
    if not model_cfg:
        ui.print_error(f"Unknown model: '{args.model}'")
        ui.print_info("Available models:")
        ui.print_models_table()
        sys.exit(1)

    # Determine API key
    api_key = args.api_key or os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        ui.console.print()
        ui.print_error("No NVIDIA API key found!")
        ui.console.print(
            f"\n  [{ui.WHITE}]Get your free API key from:[/] [bold {ui.CYAN}]https://build.nvidia.com[/]\n"
            f"\n  [{ui.WHITE}]Then either:[/]"
            f"\n    [bold {ui.GREEN}]export NVIDIA_API_KEY=nvapi-your-key-here[/]"
            f"\n    [{ui.WHITE}]or run:[/]"
            f"\n    [bold {ui.GREEN}]nexus --api-key nvapi-your-key-here[/]\n"
        )
        sys.exit(1)

    # Web mode
    if args.web:
        run_web(api_key, args.model, args.port, args.working_dir)
        return

    # Disable tools if requested
    if args.no_tools:
        model_cfg["supports_tools"] = False

    # Create agent
    try:
        agent = Agent(
            api_key=api_key,
            model_key=args.model,
            working_dir=args.working_dir,
        )
    except ValueError as e:
        ui.print_error(str(e))
        sys.exit(1)

    # Resume conversation
    if args.resume:
        if agent.load_conversation(args.resume):
            ui.print_success(f"Resumed conversation: {args.resume}")
        else:
            ui.print_error(f"Could not find conversation: {args.resume}")
            sys.exit(1)

    # Custom system prompt
    if args.system:
        agent.set_system_prompt(args.system)

    # Single prompt mode
    if args.prompt:
        agent.run(args.prompt)
        sys.exit(0)

    # Interactive mode
    run_interactive(agent)


if __name__ == "__main__":
    main()
