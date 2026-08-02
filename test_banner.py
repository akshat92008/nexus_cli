import time
from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.panel import Panel
from rich.align import Align

console = Console()

def play_banner():
    # Space invader style mascot
    frames = [
        # Frame 1 (eyes open)
        r"""
  [#d946ef]▀▄   ▄▀[/]  
 [#00f0ff]▄█▀███▀█▄[/] 
[#00f0ff]█▀███████▀█[/]
[#00f0ff]█ [#fbbf24]█▀▀▀▀▀█[/#fbbf24] █[/]
  [#d946ef]▀▀   ▀▀[/]  
""",
        # Frame 2 (eyes closed / squinting)
        r"""
  [#d946ef]▀▄   ▄▀[/]  
 [#00f0ff]▄█▀███▀█▄[/] 
[#00f0ff]█▀███████▀█[/]
[#00f0ff]█ [#fbbf24]█▀   ▀█[/#fbbf24] █[/]
  [#d946ef]▀▀   ▀▀[/]  
"""
    ]
    
    welcome_text = "Welcome to Nexus!"
    
    with Live(refresh_per_second=15, transient=False) as live:
        for i in range(12):
            frame_idx = i % 2
            
            # Typewriter effect for welcome text
            text_len = min(len(welcome_text), int((i / 8) * len(welcome_text)))
            current_text = welcome_text[:text_len]
            
            output = frames[frame_idx] + f"\n[bold white]{current_text}[/]"
            
            panel = Panel(
                Align.center(output),
                border_style="dim",
                box=None,
            )
            live.update(panel)
            time.sleep(0.08)
            
        # Final state
        output = frames[0] + f"\n[bold white]{welcome_text}[/]\n\n[dim]Run /help for commands. /status for setup info.[/]"
        panel = Panel(
            Align.center(output),
            border_style="dim",
            box=None,
        )
        live.update(panel)

play_banner()
