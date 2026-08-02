import time
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.align import Align
from rich.text import Text

console = Console()

frames = [
    r"""
    [#d946ef]  .   .  [/]
    [#d946ef]   \ /   [/]
    [#00f0ff]/█████\[/]
    [#00f0ff]██[#fbbf24]o[/#fbbf24] ██ [#fbbf24]o[/#fbbf24]██[/]
    [#00f0ff]███████[/]
    [#d946ef]/ /   \ \[/]
    """,
    r"""
    [#d946ef]    .    [/]
    [#d946ef]   / \   [/]
    [#00f0ff]/█████\[/]
    [#00f0ff]██[#fbbf24]-[/#fbbf24] ██ [#fbbf24]-[/#fbbf24]██[/]
    [#00f0ff]███████[/]
    [#d946ef] /     \ [/]
    """
]

def render_frame(idx, text):
    f = frames[idx % len(frames)]
    return Align.center(Text.from_markup(f + "\n" + text))

with Live(render_frame(0, ""), refresh_per_second=10) as live:
    for i in range(15):
        msg = f"[bold cyan]NexusAI CLI v3.2.1[/]\n[dim]Initializing core systems...[/]"
        if i > 10:
            msg = f"[bold cyan]NexusAI CLI v3.2.1[/]\n[bold green]Ready.[/]"
        live.update(render_frame(i, msg))
        time.sleep(0.15)
