"""Interactive viewer for a saved run: python main.py inspect [run_id]

Commands: n/Enter next, p prev, <number> jump, k <key> drill into a state key,
          s toggle update/full-state view, l LLM input/output for the step, q quit.
"""
from rich.console import Console
from rich.pretty import Pretty
from rich.panel import Panel

from runs import list_runs, load_events

console = Console()


def pick_run() -> str | None:
    runs = list_runs()
    if not runs:
        console.print("No runs yet.")
        return None
    for i, r in enumerate(runs):
        console.print(f"[{i}] {r['run_id']}  {r['status']}")
    choice = input("Run #: ").strip()
    return runs[int(choice)]["run_id"] if choice.isdigit() and int(choice) < len(runs) else None


def inspect(run_id: str | None = None) -> None:
    run_id = run_id or pick_run()
    if not run_id:
        return
    events = load_events(run_id)
    updates = [e for e in events if e["kind"] == "update"]
    states = {e["step"]: e["data"] for e in events if e["kind"] == "state"}
    if not updates:
        console.print("Run has no events.")
        return

    llm = {}
    for e in events:
        if e["kind"] == "llm":
            llm.setdefault(e["step"], []).append(e["data"])

    i, full, key, show_llm = 0, False, None, False
    while True:
        e = updates[i]
        data = states.get(e["step"]) if full else e["data"]
        if show_llm:
            data = llm.get(e["step"], "<no LLM call in this step>")
        if data is None:
            data = {}
        if key and isinstance(data, dict):
            data = data.get(key, f"<no key {key!r}>")
        title = (
            f"step {e['step']} ({i + 1}/{len(updates)}) node={e['node']} "
            f"{'LLM CALLS' if show_llm else 'FULL STATE' if full else 'UPDATE'}{f' key={key}' if key else ''}"
        )
        console.print(Panel(Pretty(data, max_length=20, max_string=100000 if show_llm else 300, expand_all=True), title=title))
        cmd = input("[n]ext [p]rev [#] [k key] [s]tate/update [l]lm [q]uit > ").strip()
        if cmd in ("", "n"):
            i = min(i + 1, len(updates) - 1)
        elif cmd == "p":
            i = max(i - 1, 0)
        elif cmd.isdigit():
            i = min(int(cmd), len(updates) - 1)
        elif cmd.startswith("k"):
            key = cmd[1:].strip() or None
        elif cmd == "s":
            full, show_llm = not full, False
        elif cmd == "l":
            show_llm = not show_llm
        elif cmd == "q":
            return
