"""Accessibility agent CLI.

  python main.py                      interactive task picker (tasks.csv)
  python main.py run t001 t005 --step run tasks sequentially, pausing after every node
  python main.py replay [run_id|task_id|recording.jsonl] [--live]
  python main.py replay --review [folder|task_id ...] [--as-impairment none] [--redo]
                                      replay every archived run live (no impairment), then record your verdict
                                      step through a saved run: agent outputs, state and VoiceOver commands
  python main.py batch [ids] [--impairment tunnel_vision] [--retry timeout error] [--from t011] [--limit N]
                                      run many tasks unattended (same live output), logging each
                                      run to results/runs_log.csv; resumable
  python main.py summary              success rate / time / iterations per impairment
"""
import argparse
import atexit
import re
import signal
import time
import traceback

from rich.console import Console
from rich.panel import Panel
from rich.pretty import pprint
from rich.table import Table
from rich.text import Text

from render import render_active_node, show_llm_calls, show_state
from replay import replay, review_all
import runlog
from state.parsers import consecutive_repeats
from runs import Run, latest_status, load_tasks, to_jsonable
from tools import actions
from tracing import LLMTrace

console = Console()

class AgentAborted(Exception):
    pass


class RunTimeout(BaseException):
    """BaseException so the graph's RetryPolicy (retry_on=Exception) cannot swallow it."""


class RunStopped(Exception):
    def __init__(self, outcome: str, reason: str):
        super().__init__(reason)
        self.outcome, self.reason = outcome, reason


DEFAULT_MAX_ITERATIONS = 50
MAX_SAME_ACTION = 8  # same tool, same arguments, back to back
DEFAULT_TIMEOUT_S = 1200
# Each loop is snapshot, vision, perception, evaluation, decision and (usually) a tool node.
STEPS_PER_ITERATION = 7
SITE_ERROR = re.compile(
    r"net::ERR_|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_CERT|ERR_TIMED_OUT|NS_ERROR|"
    r"ERR_HTTP2|ERR_SSL|Timeout \d+ms exceeded",
    re.I,
)


BRIEF_CHARS = 200


def show_brief(step_no: int, node: str, output: dict | None, calls: list[dict], progress: str = "") -> None:
    """Compact non-step output: one line per node plus a short clip of each LLM response."""
    console.print(f"[bold]step {step_no}[/bold] {node}" + (f"  [dim]{progress}[/dim]" if progress else ""))
    for call in calls:
        text = " ".join(call["output"]["content"].split())
        if text:
            clipped = text[:BRIEF_CHARS] + ("..." if len(text) > BRIEF_CHARS else "")
            console.print(Text.assemble(("  " + call["output"]["role"] + ": ", "dim"), clipped))
    summary = (output or {}).get("final_summary")
    if summary:
        console.print(Panel(Text(summary), title="Final summary", border_style="green", title_align="left"))


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


def run_task(
    task: dict,
    step: bool,
    queue_label: str = "",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> dict:
    """Run one task; returns its meta (status, outcome, duration_s, iterations, ...)."""
    run = Run(task)
    run.meta.update(max_iterations=max_iterations, timeout_s=timeout_s)
    started = time.monotonic()
    iterations, blocked_evals, outcome, last_state = 0, 0, None, {}
    trace = LLMTrace(console)
    step_no = 0

    def on_alarm(*_):
        raise RunTimeout

    previous_alarm = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    console.rule(f"{queue_label}{run.run_id}")
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

        pending, calls = None, []
        # "updates" gives per-node deltas, "values" the full state after each superstep.
        for mode, chunk in app.stream(
            initial_state,
            config={"callbacks": [trace], "recursion_limit": max_iterations * STEPS_PER_ITERATION + 20},
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
                    if node == "evaluation" and output["evaluation"].blocked:
                        blocked_evals += 1
            else:
                run.log(step_no, "state", None, chunk)
                last_state = chunk
                iterations = chunk.get("iteration", iterations)
                repeats = consecutive_repeats(chunk.get("action_history") or [])
                if not chunk.get("goal_reached") and repeats >= MAX_SAME_ACTION:
                    name = chunk["action_history"][-1]["name"]
                    raise RunStopped("stuck", f"'{name}' repeated {repeats} times in a row without reaching the goal")
                if not chunk.get("goal_reached") and iterations >= max_iterations:
                    raise RunStopped("max_iterations", f"reached {iterations} iterations without the goal")
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
                        if queue_label:
                            render_active_node(node)
                        elapsed = int(time.monotonic() - started)
                        show_brief(
                            step_no, node, output, calls,
                            f"{queue_label}iter {iterations}/{max_iterations} · {elapsed}s/{timeout_s}s · blocked evals {blocked_evals}",
                        )
                pending = None
                if step:
                    step_prompt(to_jsonable(chunk), calls)
    except RunTimeout:
        status, outcome = "failed", "timeout"
        run.meta["error"] = f"exceeded {timeout_s}s"
        print("Run timed out.", flush=True)
    except RunStopped as stop:
        status, outcome = "failed", stop.outcome
        run.meta["error"] = stop.reason
        print(f"Run stopped: {stop.reason}", flush=True)
    except (KeyboardInterrupt, AgentAborted):
        status, outcome = "aborted", "aborted"
        print("Agent stopped.", flush=True)
    except Exception as error:
        status = "failed"
        console.print_exception()
        run.trace_error(traceback.format_exc())
        text = repr(error) + repr(error.__cause__ or "")
        if SITE_ERROR.search(text):
            outcome = "site_error"
        elif step_no <= 2:
            outcome = "setup_error"  # failed in bootstrap/first snapshot: daemon/API/environment, not the agent
        else:
            outcome = "error"
        run.meta["error"] = text[:500]
    finally:
        # LLM calls are normally logged when their node finishes; keep the ones of a node that failed or timed out.
        for call in trace.drain():
            run.log(step_no + 1, "llm", call["node"], call)
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_alarm)
        if outcome is None:
            outcome = "success" if last_state.get("goal_reached") else "error"
        evaluation = last_state.get("evaluation")
        run.meta.update(
            outcome=outcome,
            success=outcome == "success",
            duration_s=round(time.monotonic() - started, 1),
            iterations=iterations,
            actions=len(last_state.get("action_history", [])),
            blocked_evaluations=blocked_evals,
            last_progress_status=getattr(evaluation, "progress_status", None),
            final_summary=(last_state.get("final_summary") or "")[:2000],
        )
        run.set_status(status)
        with open(run.dir / "transcript.md", "a", encoding="utf-8") as f:
            f.write(
                f"\n---\n## Result: {outcome} ({status}) · {run.meta['duration_s']}s · "
                f"{iterations} iterations · {run.meta['actions']} actions\n"
                + (f"\nError: {run.meta['error']}\n" if run.meta.get("error") else "")
                + (f"\n{run.meta['final_summary']}\n" if run.meta.get("final_summary") else "")
            )
        run.close()
        cleanup()
    return run.meta


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
            {"low_vision": "lv", "tunnel_vision": "tv"}.get(t["impairment"], t["impairment"]),
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


def batch(tasks: list[dict], args) -> None:
    if args.ids:
        tasks = [t for t in tasks if t["task_id"] in args.ids]

    attempts: dict[tuple, int] = {}
    last_outcome: dict[tuple, str] = {}
    for r in runlog.read_log():
        key = (r["task_id"], r["impairment"])
        attempts[key] = attempts.get(key, 0) + 1
        last_outcome[key] = r["outcome"]
    retry = {"setup_error", *(args.retry or [])}
    if args.start_from:
        # Start over from this task: it and every later task run again, whatever the log says.
        ids = [t["task_id"] for t in tasks]
        if args.start_from not in ids:
            console.print(f"[red]Unknown task id {args.start_from}[/red]")
            return
        queue = tasks[ids.index(args.start_from):]
    else:
        queue = [
            t for t in tasks
            if (t["task_id"], t["impairment"]) not in last_outcome
            or last_outcome[(t["task_id"], t["impairment"])] in retry
        ]
    if args.limit:
        queue = queue[: args.limit]
    console.print(f"[bold]{len(queue)} runs queued[/bold] (log: {runlog.LOG})")
    if queue:
        try:
            actions.recording_status()
        except Exception as error:
            console.print(f"[red]Cannot reach the guidecore daemon ({error!r}). Start it first; nothing was run or logged.[/red]")
            return
    setup_failures = 0

    for n, task in enumerate(queue, 1):
        key = (task["task_id"], task["impairment"])
        meta = run_task(task, False, f"[{n}/{len(queue)}] ", args.max_iterations, args.timeout)
        attempts[key] = attempts.get(key, 0) + 1
        runlog.append_log({
            "logged_at": meta.get("ended", ""),
            "attempt": attempts[key],
            "outcome": meta.get("outcome", "error"),
            **{k: meta.get(k, "") for k in (
                "run_id", "task_id", "impairment", "url", "goal", "success", "duration_s",
                "iterations", "actions", "blocked_evaluations", "last_progress_status",
                "error", "final_summary", "recording", "transcript",
            )},
        })
        console.print(
            f"[bold]{task['task_id']} {task['impairment']}: {meta.get('outcome')}[/bold] "
            f"in {meta.get('duration_s')}s, {meta.get('iterations')} iterations"
        )
        setup_failures = setup_failures + 1 if meta.get("outcome") == "setup_error" else 0
        if setup_failures >= 3:
            console.print("[red]3 setup errors in a row; stopping the batch. Fix the environment (see the error column) and rerun; setup errors are retried automatically.[/red]")
            break
        if meta.get("outcome") == "aborted" and input("Run aborted. Continue with the batch? [y/N] ").strip().lower() != "y":
            break
    runlog.summary()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the accessibility agent.")
    parser.add_argument("command", nargs="?", choices=["run", "replay", "inspect", "batch", "summary"], help="omit for the interactive menu")
    parser.add_argument("ids", nargs="*", help="task ids for 'run' (or a run id / recording path for 'replay')")
    parser.add_argument("--step", action="store_true", help="pause after each node")
    parser.add_argument("--impairment", default="low_vision", help="only tasks with this impairment (default low_vision; 'all' for every row)")
    parser.add_argument("--retry", nargs="*", metavar="OUTCOME", help="batch: re-run logged runs with these outcomes")
    parser.add_argument("--from", dest="start_from", metavar="TASK_ID", help="batch: re-run this task and all later ones, ignoring the log")
    parser.add_argument("--live", action="store_true", help="replay: also send the recorded commands to the running daemon")
    parser.add_argument("--review", action="store_true", help="replay: run every archived run live without impairment and record your verdict")
    parser.add_argument("--as-impairment", default="none", help="review: impairment to replay with (default none)")
    parser.add_argument("--redo", action="store_true", help="review: also review runs that already have a verdict")
    parser.add_argument("--delay", type=float, default=1.0, help="review: seconds to wait after each command (default 1)")
    parser.add_argument("--compare-speech", action="store_true", help="review: capture VoiceOver speech and compare it with the recording (slower)")
    parser.add_argument("--limit", type=int, help="batch: run at most N runs")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="seconds per run")
    args = parser.parse_intermixed_args()

    if args.command == "summary":
        runlog.summary()
        return

    if args.command == "replay" and args.review:
        review_all(args.ids, replayed_as=args.as_impairment, redo=args.redo, delay=args.delay, fast=not args.compare_speech)
        return

    if args.command in ("replay", "inspect"):
        replay(args.ids[0] if args.ids else None, live=args.live)
        return

    tasks = load_tasks()
    if args.impairment != "all":
        tasks = [t for t in tasks if t["impairment"] == args.impairment]
    if args.command == "batch":
        batch(tasks, args)
        return
    if args.command == "run":
        selected = [
            t for t in tasks if t["task_id"] in args.ids
        ]
        step = args.step
    else:
        selected = select_tasks(tasks)
        step = args.step or input("Step through nodes? [y/N] ").strip().lower() == "y"

    if not selected:
        console.print("No tasks selected.")
        return

    # One VoiceOver + browser daemon exists, so tasks must run one at a time.
    for task in selected:
        result = run_task(task, step, "", args.max_iterations, args.timeout)["status"]
        if result == "aborted" and input("Run aborted. Continue with remaining tasks? [y/N] ").strip().lower() != "y":
            break


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    main()
