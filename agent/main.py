"""Accessibility agent CLI.

  python main.py                      interactive task picker (tasks.csv)
  python main.py run t001 t005 --step run tasks sequentially, pausing after every node
  python main.py inspect [run_id]     browse a saved run step by step
"""
import argparse
import atexit
import signal

from rich.console import Console
from rich.panel import Panel
from rich.pretty import pprint
from rich.table import Table
from rich.text import Text

from inspect_run import inspect
from runs import Run, latest_status, load_tasks, to_jsonable
from tools import actions
from tracing import LLMTrace

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


class AgentAborted(Exception):
    pass


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


BRIEF_CHARS = 200


def show_brief(step_no: int, node: str, output: dict | None, calls: list[dict]) -> None:
    """Compact non-step output: one line per node plus a short clip of each LLM response."""
    console.print(f"[bold]step {step_no}[/bold] {node}")
    for call in calls:
        text = " ".join(call["output"]["content"].split())
        if text:
            clipped = text[:BRIEF_CHARS] + ("..." if len(text) > BRIEF_CHARS else "")
            console.print(Text.assemble(("  " + call["output"]["role"] + ": ", "dim"), clipped))
    summary = (output or {}).get("final_summary")
    if summary:
        console.print(Panel(Text(summary), title="Final summary", border_style="green", title_align="left"))


def show_state(value) -> None:
    pprint(value, expand_all=True, max_string=200, max_length=6, max_depth=4)


def step_prompt(state: dict, calls: list[dict]) -> None:
    """Pause after a node; see the prompt below for commands."""
    while True:
        cmd = input("\n[Enter] next  [i] full LLM input/output  [s] full state  [k <key>] one key  [q] abort > ").strip()
        if cmd == "":
            return
        if cmd == "i":
            show_llm_calls(calls, full=True)
        elif cmd == "s":
            pprint(state, expand_all=True, max_string=2000)
        elif cmd.startswith("k"):
            pprint(state.get(cmd[1:].strip(), "<no such key>"), expand_all=True, max_string=5000)
        elif cmd == "q":
            raise AgentAborted


def run_task(task: dict, step: bool) -> str:
    run = Run(task)
    console.rule(f"{run.run_id}")
    console.print(f"[bold]Goal:[/bold] {task['goal']}\n[bold]URL:[/bold] {task['url']}  [bold]Impairment:[/bold] {task['impairment']}")

    recording_owned = False
    cleaned_up = False

    def cleanup() -> None:
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        if recording_owned:
            for action in (actions.voiceover_stop, actions.browser_stop):
                try:
                    action()
                except Exception as error:
                    print(f"Cleanup warning: {error}", flush=True)
            try:
                result = actions.recording_stop()
                print(f"Recording saved to {result['recording']['path']}", flush=True)
            except Exception as error:
                print(f"Cleanup warning: {error}", flush=True)

    atexit.register(cleanup)
    status = "done"
    try:
        recording_status = actions.recording_status()
        recording = recording_status.get("recording", {})
        if recording.get("active"):
            print("Using the existing interaction recording; the agent will not stop it.", flush=True)
        else:
            recording = actions.recording_start(task["url"], task["impairment"])["recording"]
            recording_owned = True
            print(f"Recording agent interactions to {recording['path']}", flush=True)
        run.attach_recording(recording["path"], lambda event: actions.client.call("recording.event", event))

        from graph.build import build_graph  # lazy: needs OPENAI_API_KEY, inspect doesn't

        app = build_graph()
        app.get_graph().draw_mermaid_png(output_file_path=str(run.dir / "graph.png"))

        initial_state = {
            "messages": [],
            "goal": task["goal"],
            "initial_URL": task["url"],
            "snapshot": {},
            "memory": [],
            "last_action": None,
            "action_history": [],
            "transition": None,
            "iteration": 0,
            "goal_reached": False,
            "final_summary": "",
            "impairment": task["impairment"],
        }

        step_no, pending, calls = 0, None, []
        trace = LLMTrace(console)
        # "updates" gives per-node deltas, "values" the full state after each superstep.
        for mode, chunk in app.stream(
            initial_state,
            config={"callbacks": [trace]},
            stream_mode=["updates", "values"],
        ):
            if mode == "updates":
                step_no += 1
                pending = chunk
                calls = trace.drain()
                for call in calls:
                    run.log(step_no, "llm", call["node"], call)
                for node, output in chunk.items():
                    run.log(step_no, "update", node, output)
            else:
                run.log(step_no, "state", None, chunk)
                if pending is None:
                    continue
                for node, output in pending.items():
                    if step:
                        console.rule(f"step {step_no}: {node}")
                        render_active_node(node)
                        show_llm_calls(calls)
                        console.print("[bold magenta]State update (abridged)[/bold magenta]")
                        show_state(output)
                    else:
                        show_brief(step_no, node, output, calls)
                pending = None
                if step:
                    step_prompt(to_jsonable(chunk), calls)
    except (KeyboardInterrupt, AgentAborted):
        status = "aborted"
        print("Agent stopped.", flush=True)
    except Exception as error:
        status = "failed"
        console.print_exception()
        run.meta["error"] = repr(error)
    finally:
        run.set_status(status)
        run.close()
        cleanup()
    return status


def select_tasks(tasks: list[dict]) -> list[dict]:
    status = latest_status()
    table = Table(title="Tasks")
    widths = {"#": 3, "id": 4, "status": 7, "imp.": 3, "site": 22}
    for name, width in widths.items():
        table.add_column(name, no_wrap=True, width=width, overflow="ellipsis")
    # 3 chars of padding + 1 border per column, plus outer borders
    goal_width = max(20, console.width - sum(widths.values()) - 4 * (len(widths) + 1) - 2)
    table.add_column("goal", no_wrap=True, width=goal_width, overflow="ellipsis")
    for i, t in enumerate(tasks):
        table.add_row(
            str(i),
            t["task_id"],
            status.get((t["task_id"], t["impairment"]), "-"),
            {"low_vision": "lv", "tunnel_vision": "tv", "diabetic_retinopathy": "dr"}.get(t["impairment"], t["impairment"]),
            t["site"],
            t["goal"],
        )
    console.print(table)
    raw = input("Pick: ids/indices separated by spaces, ranges like 3-7, 'pending', or 'all' > ").strip()
    if raw == "all":
        return tasks
    if raw == "pending":
        return [t for t in tasks if (t["task_id"], t["impairment"]) not in status]
    picked = []
    for token in raw.split():
        if "-" in token and all(p.isdigit() for p in token.split("-", 1)):
            a, b = map(int, token.split("-", 1))
            picked += tasks[a : b + 1]
        elif token.isdigit() and int(token) < len(tasks):
            picked.append(tasks[int(token)])
        else:
            picked += [t for t in tasks if t["task_id"] == token]
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the accessibility agent.")
    parser.add_argument("command", nargs="?", choices=["run", "inspect"], help="omit for the interactive menu")
    parser.add_argument("ids", nargs="*", help="task ids for 'run' (or run id for 'inspect')")
    parser.add_argument("--step", action="store_true", help="pause after each node")
    args = parser.parse_args()

    if args.command == "inspect":
        inspect(args.ids[0] if args.ids else None)
        return

    tasks = load_tasks()
    if args.command == "run":
        selected = [t for t in tasks if t["task_id"] in args.ids]
        step = args.step
    else:
        selected = select_tasks(tasks)
        step = args.step or input("Step through nodes? [y/N] ").strip().lower() == "y"

    if not selected:
        console.print("No tasks selected.")
        return

    # One VoiceOver + browser daemon exists, so tasks must run one at a time.
    for task in selected:
        result = run_task(task, step)
        if result == "aborted" and input("Run aborted. Continue with remaining tasks? [y/N] ").strip().lower() != "y":
            break


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    main()
