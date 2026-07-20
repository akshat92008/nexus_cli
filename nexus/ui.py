"""
Rich terminal UI — beautiful output for the coding agent.
"""

import os
import shutil
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from rich.syntax import Syntax
from rich.columns import Columns
from rich.rule import Rule
from rich.live import Live
from rich.spinner import Spinner
from rich import box
from nexus.models import list_models

console = Console()

# ── Color palette ────────────────────────────────────────────────────────────

CYAN    = "#00e5ff"
MAGENTA = "#e040fb"
GREEN   = "#76ff03"
ORANGE  = "#ff9100"
RED     = "#ff1744"
DIM     = "#6c757d"
WHITE   = "#e0e0e0"
GOLD    = "#ffd740"
PURPLE  = "#b388ff"


def print_banner():
    """Print the gorgeous startup banner."""
    banner = r"""
[bold #00e5ff]  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗[/]  [bold #e040fb] █████╗ ██╗[/]
[bold #00e5ff]  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝[/]  [bold #e040fb]██╔══██╗██║[/]
[bold #00e5ff]  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗[/]  [bold #e040fb]███████║██║[/]
[bold #00e5ff]  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║[/]  [bold #e040fb]██╔══██║██║[/]
[bold #00e5ff]  ██║ ╚████║███████╗██╔╝ ╚██╗╚██████╔╝███████║[/]  [bold #e040fb]██║  ██║██║[/]
[bold #00e5ff]  ╚═╝  ╚═══╝╚══════╝╚═╝   ╚═╝ ╚═════╝ ╚══════╝[/]  [bold #e040fb]╚═╝  ╚═╝╚═╝[/]
"""
    console.print(banner)
    console.print(
        f"  [bold {CYAN}]NVIDIA-Powered Coding Agent[/]  │  "
        f"[{DIM}]Free API • 20 Tools • Git • Web • Undo • Memory[/]",
        justify="center",
    )
    console.print()


def print_model_info(model_key: str, model_cfg: dict):
    """Print current model info."""
    console.print(
        Panel(
            f"[bold {GREEN}]{model_cfg['name']}[/]  "
            f"[{DIM}]({model_cfg['id']})[/]\n"
            f"[{WHITE}]{model_cfg['description']}[/]  │  "
            f"Context: [bold]{model_cfg['context']:,}[/] tokens  │  "
            f"Tools: {'[bold green]✓[/]' if model_cfg.get('supports_tools') else '[bold red]✗[/]'}",
            title=f"[bold {CYAN}]⚡ Active Model[/]",
            border_style=CYAN,
            padding=(0, 2),
        )
    )


def print_help():
    """Print command help."""
    table = Table(
        show_header=True,
        header_style=f"bold {CYAN}",
        border_style=DIM,
        box=box.ROUNDED,
        title=f"[bold {GOLD}]⌘ Commands[/]",
        padding=(0, 2),
    )
    table.add_column("Command", style=f"bold {GREEN}", min_width=22)
    table.add_column("Description", style=WHITE)

    commands = [
        ("/help", "Show this help message"),
        ("/models", "List all available models"),
        ("/model <name>", "Switch to a different model"),
        ("/tools", "List all 20 agent tools"),
        ("/clear", "Clear conversation history"),
        ("/reset", "Reset conversation and clear screen"),
        ("/project", "Show project structure"),
        ("/git", "Show git status"),
        ("/undo", "Undo the last file change"),
        ("/diff", "Show the last file change as a diff"),
        ("/changes", "List all file changes in this session"),
        ("/history", "List saved conversations"),
        ("/resume <id>", "Resume a previous conversation"),
        ("/compact", "Compress conversation to save context"),
        ("/cost", "Show token usage stats"),
        ("/system <prompt>", "Set a custom system prompt"),
        ("/save <file>", "Save conversation to a file"),
        ("/multi", "Enter multi-line input mode (end with Ctrl+D)"),
        ("/exit, /quit", "Exit NexusAI"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)
    console.print(table)


def print_tools_table():
    """Print all available agent tools."""
    table = Table(
        show_header=True,
        header_style=f"bold {CYAN}",
        border_style=DIM,
        box=box.ROUNDED,
        title=f"[bold {GOLD}]🔧 Agent Tools (20)[/]",
        padding=(0, 1),
    )
    table.add_column("Tool", style=f"bold {GREEN}", min_width=20)
    table.add_column("Category", style=PURPLE)
    table.add_column("Description", style=WHITE)

    tools = [
        ("read_file", "File", "Read file contents with line numbers"),
        ("write_file", "File", "Create/overwrite files (tracked for undo)"),
        ("edit_file", "File", "Surgical find-and-replace edits (tracked)"),
        ("patch_file", "File", "Line-range based editing (tracked)"),
        ("multi_edit", "File", "Batch edits across multiple files (tracked)"),
        ("file_info", "File", "File metadata (size, perms, lines, MD5)"),
        ("diff_files", "File", "Unified diff between two files"),
        ("search_code", "Search", "Regex search across codebase"),
        ("list_directory", "Search", "List directory contents"),
        ("find_files", "Search", "Find files by glob pattern"),
        ("get_project_structure", "Search", "Project tree view"),
        ("run_command", "Shell", "Execute shell commands (blocking)"),
        ("process_run", "Shell", "Start background processes"),
        ("git_status", "Git", "Full repository status"),
        ("git_diff", "Git", "View diffs (working/staged/commits)"),
        ("git_commit", "Git", "Stage and commit changes"),
        ("git_log", "Git", "View commit history"),
        ("git_branch", "Git", "List/create/switch/delete branches"),
        ("web_fetch", "Web", "Fetch and read any URL"),
        ("web_search", "Web", "Search the web (DuckDuckGo)"),
    ]

    category_colors = {
        "File": GREEN,
        "Search": CYAN,
        "Shell": ORANGE,
        "Git": MAGENTA,
        "Web": PURPLE,
    }

    for name, cat, desc in tools:
        color = category_colors.get(cat, WHITE)
        table.add_row(name, f"[{color}]{cat}[/]", desc)
    console.print(table)


def print_models_table():
    """Print all available models in a beautiful table."""
    table = Table(
        show_header=True,
        header_style=f"bold {CYAN}",
        border_style=DIM,
        box=box.ROUNDED,
        title=f"[bold {GOLD}]🚀 Available Models — NVIDIA API Catalog[/]",
        padding=(0, 1),
    )
    table.add_column("Key", style=f"bold {GREEN}", min_width=16)
    table.add_column("Model Name", style=f"bold {WHITE}")
    table.add_column("Category", style=PURPLE)
    table.add_column("Context", style=ORANGE, justify="right")
    table.add_column("Tools", justify="center")
    table.add_column("Description", style=DIM)

    category_colors = {
        "reasoning": MAGENTA,
        "coding": GREEN,
        "general": CYAN,
    }

    for m in list_models():
        cat_color = category_colors.get(m["category"], WHITE)
        tools = f"[bold {GREEN}]✓[/]" if m.get("supports_tools") else f"[{RED}]✗[/]"
        table.add_row(
            m["key"],
            m["name"],
            f"[{cat_color}]{m['category']}[/]",
            f"{m['context']:,}",
            tools,
            m["description"],
        )
    console.print(table)


def print_conversation_list(conversations: list[dict]):
    """Print a list of saved conversations."""
    table = Table(
        show_header=True,
        header_style=f"bold {CYAN}",
        border_style=DIM,
        box=box.ROUNDED,
        title=f"[bold {GOLD}]💬 Saved Conversations[/]",
        padding=(0, 1),
    )
    table.add_column("ID", style=f"bold {GREEN}", min_width=22)
    table.add_column("Model", style=PURPLE)
    table.add_column("Messages", style=ORANGE, justify="right")
    table.add_column("Preview", style=WHITE, max_width=50)

    for conv in conversations:
        table.add_row(
            conv["id"],
            conv.get("model_name", "unknown"),
            str(conv.get("message_count", 0)),
            conv.get("preview", "")[:50],
        )
    console.print(table)
    console.print(f"  [{DIM}]Use /resume <id> to load a conversation[/]")


def print_tool_call(name: str, args: dict):
    """Print a tool call with syntax highlighting."""
    args_str = ""
    for k, v in args.items():
        if k == "content" and len(str(v)) > 200:
            v_display = str(v)[:200] + f"... ({len(str(v))} chars)"
        elif k == "edits" and isinstance(v, list):
            v_display = f"[{len(v)} edits]"
        else:
            v_display = str(v)
        v_display = escape(v_display)
        args_str += f"  [bold]{escape(str(k))}[/]: {v_display}\n"

    console.print(
        Panel(
            args_str.rstrip(),
            title=f"[bold {ORANGE}]🔧 {name}[/]",
            border_style=ORANGE,
            padding=(0, 2),
        )
    )


def print_tool_result(result: str, success: bool = True):
    """Print a tool execution result."""
    color = GREEN if success else RED
    # Truncate very long results for display
    display = str(result)
    if len(display) > 3000:
        display = escape(display[:1500]) + f"\n\n[{DIM}]... ({len(display) - 3000} chars omitted) ...[/]\n\n" + escape(display[-1500:])
    else:
        display = escape(display)
    console.print(
        Panel(
            display,
            border_style=color,
            padding=(0, 1),
        )
    )


def print_streaming_start():
    """Print a divider before streaming starts."""
    console.print(Rule(style=DIM))


def print_response_complete():
    """Print a divider after response is complete."""
    console.print()


def print_error(message: str):
    """Print an error message."""
    console.print(f"[bold {RED}]✗ Error:[/] [{WHITE}]{escape(str(message))}[/]")


def print_info(message: str):
    """Print an info message."""
    console.print(f"[{CYAN}]ℹ {escape(str(message))}[/]")


def print_success(message: str):
    """Print a success message."""
    console.print(f"[{GREEN}]✓ {escape(str(message))}[/]")


def print_warning(message: str):
    """Print a warning."""
    console.print(f"[{ORANGE}]⚠ {escape(str(message))}[/]")


def print_token_usage(prompt_tokens: int, completion_tokens: int, total_tokens: int):
    """Print token usage stats."""
    table = Table(
        show_header=False,
        border_style=DIM,
        box=box.SIMPLE,
        padding=(0, 2),
    )
    table.add_column("Metric", style=f"bold {CYAN}")
    table.add_column("Value", style=WHITE, justify="right")
    table.add_row("Prompt tokens", f"{prompt_tokens:,}")
    table.add_row("Completion tokens", f"{completion_tokens:,}")
    table.add_row("Total tokens", f"[bold {GREEN}]{total_tokens:,}[/]")
    console.print(
        Panel(table, title=f"[bold {GOLD}]📊 Token Usage[/]", border_style=DIM, padding=(0, 1))
    )


def get_prompt(model_name: str) -> str:
    """Get user input with a styled prompt."""
    try:
        console.print()
        return console.input(f"[bold {CYAN}]❯ [/]")
    except (EOFError, KeyboardInterrupt):
        return "/exit"


def get_multiline_input() -> str:
    """Get multi-line input from user (end with Ctrl+D)."""
    console.print(f"[{DIM}]Enter multi-line input (Ctrl+D to submit, Ctrl+C to cancel):[/]")
    lines = []
    try:
        while True:
            line = console.input(f"[{DIM}]… [/]")
            lines.append(line)
    except EOFError:
        return "\n".join(lines)
    except KeyboardInterrupt:
        return ""
