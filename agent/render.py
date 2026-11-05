"""Shared terminal rendering for a step of the agent: used by the live step mode and by replay."""
from rich.console import Console
from rich.panel import Panel
from rich.pretty import pprint
from rich.text import Text

console = Console()

ROUTE = [
    "bootstrap",
    "snapshot",
    "vision",
    "perception",
    "evaluation",
    "decision",
    "voiceover_tools",
    "report",
    "stop",
]


def render_active_node(active_node: str) -> None:
    """Show the graph route with the node currently being inspected."""
    labels = [f"[ {n} ]" if n == active_node else f"  {n}  " for n in ROUTE]
    console.print("  -> ".join(labels), highlight=False, markup=False)


PREVIEW_CHARS = 1200


def show_llm_calls(calls: list[dict], full: bool = False) -> None:
    """Print the messages the LLM saw and what it returned; long text is clipped unless full."""
    for call in calls:
        console.print(f"[bold cyan]LLM call[/bold cyan] node={call['node']} model={call['model']}")
        for message in call["input"] + [call["output"]]:
            text = message["content"]
            if not full and len(text) > PREVIEW_CHARS:
                text = text[:PREVIEW_CHARS] + f"\n... [{len(message['content']) - PREVIEW_CHARS} more chars, use i to see all]"
            if message is call["output"]:
                title, style = "OUTPUT", "green"
            else:
                title, style = f"INPUT ({message['role']})", "yellow"
            if message.get("tool_calls"):
                text += f"\ntool_calls: {message['tool_calls']}"
            console.print(Panel(Text(text or "<empty>"), title=title, border_style=style, title_align="left"))


def show_state(value) -> None:
    pprint(value, expand_all=True, max_string=200, max_length=6, max_depth=4)
