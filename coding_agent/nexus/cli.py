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
import sys
from pathlib import Path

from nexus.agent import Agent
from nexus.models import resolve_model, DEFAULT_MODEL, ALIASES
from nexus import ui
from nexus.tools import tool_get_project_structure
from nexus.history import get_history
from nexus.memory import ConversationMemory


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
  Ollama                             Required for Nova Intern (nova_codex model)
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
        "--port",
        type=int,
        default=3000,
        help="Port for web interface (default: 3000)",
    )
    parser.add_argument(
        "--resume", "-r",
        help="Resume a previous conversation by ID",
    )
    parser.add_argument("--continue", dest="continue_last", action="store_true", help="Resume the most recent conversation for this directory")
    parser.add_argument("--print", "-p", dest="print_mode", action="store_true", help="Run non-interactively and exit")
    parser.add_argument("--output-format", choices=("text", "json", "stream-json"), default="text")
    parser.add_argument("--max-turns", type=int, default=50)
    parser.add_argument("--permission-mode", choices=("default", "acceptEdits", "plan"), default="default")
    parser.add_argument("--allowed-tools", nargs="*", default=[])
    parser.add_argument("--disallowed-tools", nargs="*", default=[])
    parser.add_argument("--add-dir", action="append", default=[], help="Authorize an additional existing directory")
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
                ui.print_error(f"Unknown model: '{model_name}'. Use /models to see available options.")
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
            result, success = agent._execute_tool_with_safety("run_command", {"command": arg, "cwd": agent.working_dir})
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

    # ─── ADDED EXTENSION COMMANDS ────────────────────────────────────

    elif command == "/skills":
        ui.console.print(agent.skills.get_skill_summary())

    elif command == "/hooks":
        ui.console.print(agent.hooks.get_summary())

    elif command == "/subagent":
        if not arg:
            ui.print_error("Usage: /subagent <template> <task>  (e.g., /subagent security Scan for hardcoded passwords)")
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
            decision = agent.trust.approve(trust_parts[1]) if trust_parts[0] == "approve" else agent.trust.reject(trust_parts[1])
            agent.project_mem.reload()
            agent._load_rules_and_preferences()
            agent._update_system_prompt()
            ui.print_success(f"{trust_parts[0].title()}d exact config digest: {decision.path} {decision.digest}")
        else:
            ui.print_error("Usage: /trust [approve|reject] <path>")

    elif command == "/init":
        path = agent.project_mem.create_default_rules()
        ui.print_info(f"Created {path}. Review it, then run /trust approve {path} before Nexus loads it.")

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
        if rules.rules:
            ui.console.print("\nRules:")
            for rule in rules.rules:
                ui.console.print(f"  • {rule}")

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

            if user_input.lstrip().startswith("!"):
                command = user_input.lstrip()[1:].strip()
                result, success = agent._execute_tool_with_safety(
                    "run_command", {"command": command, "cwd": agent.working_dir}
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


def start_background_web_server(api_key: str, model: str, port: int, working_dir: str | None):
    """Start the web server in a daemon thread and automatically open the default browser."""
    import threading
    import time
    import webbrowser
    from nexus.webapp.server import create_app
    import uvicorn

    def _run():
        try:
            app = create_app(api_key=api_key, model=model, working_dir=working_dir)
            # Run uvicorn quietly (log_level="error") to avoid cluttered CLI printouts
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
        except Exception:
            pass  # Fail silently if port is already bound by another instance

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # Open the browser automatically after the server binds
    def _open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    threading.Thread(target=_open_browser, daemon=True).start()


def main():
    args = parse_args()

    invalid_dirs = [item for item in args.add_dir if not Path(item).expanduser().is_dir()]
    if invalid_dirs:
        ui.print_error("Additional directories do not exist: " + ", ".join(invalid_dirs))
        sys.exit(1)

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
    from nexus.api import _load_env_file
    _load_env_file()
    api_key = args.api_key or os.environ.get("NVIDIA_API_KEY")
    is_local_nova = model_cfg.get("backend") == "nova"
    if not api_key and not is_local_nova:
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
            permission_mode=args.permission_mode,
            allowed_tools=args.allowed_tools,
            disallowed_tools=args.disallowed_tools,
            additional_dirs=args.add_dir,
            max_turns=args.max_turns,
        )
    except ValueError as e:
        ui.print_error(str(e))
        sys.exit(1)

    # Resume conversation
    if args.continue_last:
        candidates = [item for item in agent.memory.list_conversations(limit=100) if item.get("working_dir") == agent.working_dir]
        if not candidates or not agent.load_conversation(candidates[0]["id"]):
            ui.print_error("No resumable conversation found for this directory.")
            sys.exit(1)
    elif args.resume:
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
        if args.prompt.lstrip().startswith("!"):
            command = args.prompt.lstrip()[1:].strip()
            result, success = agent._execute_tool_with_safety(
                "run_command", {"command": command, "cwd": agent.working_dir}
            )
            if args.output_format in ("json", "stream-json"):
                print(json.dumps({"type": "tool_call", "name": "run_command", "result": result, "success": success}))
            else:
                print(result)
            sys.exit(0 if success else 2)
        if args.print_mode or args.output_format != "text":
            content, events = agent.run_non_interactive(args.prompt)
            if args.output_format == "json":
                print(json.dumps({"result": content, "events": events, "session_id": agent.conversation_id}))
            elif args.output_format == "stream-json":
                for event in events:
                    print(json.dumps(event))
                print(json.dumps({"type": "result", "result": content, "session_id": agent.conversation_id}))
            else:
                print(content)
        else:
            agent.run(args.prompt)
        sys.exit(0)

    # Interactive mode
    run_interactive(agent)


if __name__ == "__main__":
    main()
