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

        launch_url = f"http://localhost:{port}/?token={app.state.web_token}"
        ui.console.print(
            f"  [bold {ui.GREEN}]🌐 Web Interface[/] starting on "
            f"[bold {ui.CYAN}]{launch_url}[/]\n"
            f"  [{ui.DIM}]The launch token is required and is not embedded in the page. "
            f"Press Ctrl+C to stop.[/]\n"
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

    app = create_app(api_key=api_key, model=model, working_dir=working_dir)
    launch_url = f"http://localhost:{port}/?token={app.state.web_token}"

    def _run():
        try:
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
            webbrowser.open(launch_url)
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

def exit_code_for_outcome(outcome: str) -> int:
    """Map canonical task outcome to deterministic process exit code."""
    mapping = {
        "VERIFIED": 0,
        "FAILED": 1,
        "INTERNAL_ERROR": 1,
        "PARTIALLY_VERIFIED": 2,
        "BLOCKED": 3,
        "BUDGET_EXHAUSTED": 4,
        "SECURITY_POLICY_DENIED": 5,
        "CONFIGURATION_ERROR": 6,
        "VERIFICATION_UNAVAILABLE": 7,
    }
    return mapping.get(str(outcome).upper(), 1)

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
    if _handle_collaboration_commands():
        return
    if _handle_sprint9_commands():
        return
    if _handle_change_commands():
        return
    if _handle_recovery_commands():
        return
    if _handle_plan_commands():
        return
    if _handle_extensions():
        return
    if _handle_mcp():
        return
    if _handle_enterprise():
        return
    if _handle_autonomy_project():
        return
    if _handle_performance_and_release():
        return
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
        "auto": "default",
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
        args.permission_mode = mode_permissions.get(args.mode, "default")

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

    # Sprint 9 Subcommands: nexus models, nexus model ..., nexus budget ..., nexus cost ...
    if len(sys.argv) >= 2 and sys.argv[1].lower() in ("models", "model", "budget", "cost"):
        sub = sys.argv[1].lower()
        from nexus.models import model_registry
        from nexus.model_doctor import model_doctor
        from nexus.cost_accounting import cost_ledger

        if sub == "models":
            descriptors = model_registry.list_all()
            print("\nRegistered Model Intelligence Matrix:")
            print(f"{'Key/ID':<25} {'Name':<28} {'Tier':<12} {'Privacy':<15} {'Context':<10} {'Cost (USD/1M)':<16} {'Cost (INR/1M)':<16}")
            print("-" * 125)
            for d in descriptors:
                in_usd = d.input_cost if d.input_cost is not None else 0.0
                out_usd = d.output_cost if d.output_cost is not None else 0.0
                in_inr = in_usd * 85.0
                out_inr = out_usd * 85.0
                cost_str = f"${in_usd:.2f} / ${out_usd:.2f}"
                inr_str = f"₹{in_inr:.1f} / ₹{out_inr:.1f}"
                key_name = model_registry.resolve_key(d.model_id) or d.model_id
                print(f"{key_name:<25} {d.display_name:<28} {d.tier.value:<12} {d.privacy_class.value:<15} {d.context_window or 0:<10} {cost_str:<16} {inr_str:<16}")
            sys.exit(0)

        elif sub == "model" and len(sys.argv) >= 3:
            action = sys.argv[2].lower()
            if action in ("show", "info") and len(sys.argv) >= 4:
                target = sys.argv[3]
                desc = model_registry.get_descriptor(target)
                if not desc:
                    print(f"Model '{target}' not found in registry.")
                    sys.exit(1)
                profile = model_doctor.get_profile(target)
                print(json.dumps({"descriptor": desc.to_dict(), "capability_profile": profile.to_dict() if profile else None}, indent=2))
                sys.exit(0)
            elif action == "doctor" and len(sys.argv) >= 4:
                target = sys.argv[3]
                print(f"Running Model Doctor capability probes for '{target}'...")
                profile = model_doctor.probe_model(target, trials_per_probe=2)
                print(json.dumps(profile.to_dict(), indent=2))
                sys.exit(0)
            elif action == "compare" and len(sys.argv) >= 5:
                model_a = sys.argv[3]
                model_b = sys.argv[4]
                res = model_doctor.compare_models(model_a, model_b)
                print(json.dumps(res, indent=2))
                sys.exit(0)

        elif sub == "budget":
            run_id = sys.argv[3] if len(sys.argv) >= 4 and sys.argv[2].lower() == "show" else (sys.argv[2] if len(sys.argv) >= 3 and sys.argv[2].lower() != "show" else None)
            snap = cost_ledger.snapshot(run_id)
            print(json.dumps({"budget_summary": snap}, indent=2))
            sys.exit(0)

        elif sub == "cost":
            run_id = sys.argv[3] if len(sys.argv) >= 4 and sys.argv[2].lower() == "show" else (sys.argv[2] if len(sys.argv) >= 3 and sys.argv[2].lower() != "show" else None)
            snap = cost_ledger.snapshot(run_id)
            print(json.dumps({"cost_ledger": snap, "entries": [e.to_dict() for e in cost_ledger.entries if run_id is None or e.run_id == run_id]}, indent=2))
            sys.exit(0)

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
            budget_inr=args.budget_inr,
            routing_mode=args.routing_mode,
            ask_before_frontier=args.ask_before_frontier,
            input_price_per_million=args.input_price_per_million,
            output_price_per_million=args.output_price_per_million,
            model_id_override=args.model_id,
            local_intern_mode=args.local_intern,
            enable_nova_fallback=args.enable_nova_fallback,
            plugins_enabled=args.enable_plugins,
            tools_enabled=not args.no_tools,
        )
        agent.keep_workspace = bool(args.keep_workspace)
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

