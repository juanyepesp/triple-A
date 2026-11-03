"""Replay a saved agent run step by step:
  python main.py replay [run_id | task_id | recording.jsonl | folder-with-runs_log.csv]
Add --live to also send the logged commands to the running guidecore daemon as you advance, so the
browser and VoiceOver reproduce the run (and each result is compared with what VoiceOver said originally).
With no argument it lists the runs of guidecore/runs/all-recordings (via its runs_log.csv).

Reads only the guidecore recording (agent.llm / agent.update / agent.state events plus the VoiceOver and
browser `interaction` commands), so it works on any copy of the file; screenshots are optional extras.
Each step shows what the live step mode shows (route, LLM input/output boxes, state update), plus the
commands executed on the daemon during that step and, with `v`, what the agent perceived.
"""
import csv
import json
import subprocess
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from rich.panel import Panel
from rich.pretty import Pretty, pprint
from rich.table import Table
from rich.text import Text

from render import console, render_active_node, show_llm_calls, show_state
from runs import RUNS_DIR, ROOT, list_runs

RECORDINGS_DIR = ROOT.parent / "guidecore" / "recordings"
BAR = "Enter next · p prev · g N goto · j/b node · t timeline · v perceived · i llm (i N / i node) · s state · k key · o image · ? help · q quit"
BAR_LIVE = "Enter run next command · c N run N · a [secs] run all · d detail · x resend · t timeline · v perceived · i all LLM output (i N / i node) · s state · k key · o image · ? help · q quit"
HELP = (
    "[Enter] next  [p]rev  [g N] go to step  [j node]/[b node] next/previous step of a node  [t]imeline\n"
    "--live: [Enter] run the next command(s) · [c N] run N · [a [secs]] run all, Ctrl-C stops · [d] full step detail · [x] resend\n"
    "[v] what the agent perceived  [i] full LLM input/output of the last command's steps (live) or this step; [i N], [i N-M] or [i node] to pick  [s] full state  [k a.b.c] one key  [o]pen image  [q]uit"
)


@dataclass
class Step:
    number: int
    ts: str = ""
    nodes: list[str] = field(default_factory=list)
    updates: dict[str, int] = field(default_factory=dict)  # node -> byte offset in the recording
    llm: list[int] = field(default_factory=list)
    state: int | None = None
    commands: list[dict] = field(default_factory=list)


class Recording:
    """Index of a recording file; heavy payloads (states, LLM calls) are read from disk on demand."""

    def __init__(self, path: Path, run_id: str | None):
        self.path = path
        self.file = open(path, "rb")
        self.cache: OrderedDict[int, dict] = OrderedDict()
        self.started = ""
        entries = []
        offset = 0
        for raw in self.file:
            try:
                data = json.loads(raw)
            except ValueError:
                offset += len(raw)
                continue
            entries.append((offset, data))
            offset += len(raw)
        run_ids = list(dict.fromkeys(e["run_id"] for _, e in entries if e.get("run_id")))
        if run_id is None:
            run_id = pick(run_ids, "Run") if len(run_ids) > 1 else (run_ids[0] if run_ids else None)
        self.run_id = run_id
        self.steps: dict[int, Step] = {}
        pending: list[dict] = []
        for offset, e in entries:
            kind = str(e.get("type", ""))
            if kind == "recording.started":
                self.started = e["timestamp"]
            elif kind == "interaction":
                pending.append({k: e.get(k) for k in ("timestamp", "method", "parameters", "source")})
            elif kind.startswith("agent.") and e.get("run_id") == run_id:
                step = self.steps.setdefault(e["step"], Step(e["step"], e["timestamp"]))
                if kind == "agent.update":
                    step.nodes.append(e["node"])
                    step.updates[e["node"]] = offset
                    step.commands, pending = step.commands + pending, []  # commands run just before their node's update
                elif kind == "agent.llm":
                    step.llm.append(offset)
                elif kind == "agent.state":
                    step.state = offset
        self.order = sorted(n for n, s in self.steps.items() if s.nodes)

    def read(self, offset: int) -> dict:
        if offset not in self.cache:
            self.file.seek(offset)
            self.cache[offset] = json.loads(self.file.readline())["data"]
            if len(self.cache) > 12:
                self.cache.popitem(last=False)
        return self.cache[offset]

    def state_at(self, number: int) -> dict:
        """Full state after a step; falls back to the nearest earlier step that has one."""
        for n in range(number, -1, -1):
            step = self.steps.get(n)
            if step and step.state is not None:
                return self.read(step.state)
        return {}


def pick(options: list[str], label: str) -> str | None:
    for i, option in enumerate(options):
        console.print(f"[{i}] {option}")
    choice = input(f"{label} #: ").strip()
    return options[int(choice)] if choice.isdigit() and int(choice) < len(options) else None


ARCHIVE_DIR = ROOT.parent / "guidecore" / "runs" / "all-recordings"


def archive_runs(folder: Path) -> list[dict]:
    """Runs of a folder of recordings, described by its runs_log.csv (rows whose recording file is there)."""
    log = folder / "runs_log.csv"
    if not log.exists():
        return []
    runs = []
    with open(log, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = Path(row.get("recording") or "").name
            if name and (folder / name).is_file():
                runs.append({**row, "path": folder / name})
    return runs


def choose_archive_run(runs: list[dict], wanted: str | None = None) -> dict | None:
    if wanted:
        hits = [r for r in runs if r["run_id"] == wanted or r["task_id"] == wanted]
        runs = hits[-1:] if hits and hits[-1]["run_id"] == wanted else hits  # a task id may have several attempts
        if len(runs) == 1:
            return runs[0]
    if not runs:
        return None
    table = Table(show_header=True, header_style="bold")
    for column in ("#", "run", "outcome", "iter", "s", "MB", "site"):
        table.add_column(column)
    for i, r in enumerate(runs):
        table.add_row(
            str(i), r["run_id"], r["outcome"], r["iterations"], r["duration_s"],
            str(round(r["path"].stat().st_size / 1e6)), clip(r["url"], 40),
        )
    console.print(table)
    choice = input("Run #: ").strip()
    return runs[int(choice)] if choice.isdigit() and int(choice) < len(runs) else None


def resolve(target: str | None) -> tuple[Path, str | None] | None:
    """What to replay: a recording file, a folder of recordings (with runs_log.csv), or a run / task id."""
    if target and Path(target).is_file():
        return Path(target), None
    folders = [Path(target)] if target and Path(target).is_dir() else [ARCHIVE_DIR, RECORDINGS_DIR]
    wanted = None if target and Path(target).is_dir() else target
    for folder in folders:
        run = choose_archive_run(archive_runs(folder), wanted)
        if run:
            return run["path"], run["run_id"]
    runs = [r for r in list_runs() if r.get("recording")]
    if wanted is None:
        if not runs:
            console.print("No runs found. Pass a recording file or a folder with runs_log.csv.")
            return None
        wanted = pick([f"{r['run_id']}  {r.get('outcome') or r.get('status')}" for r in runs], "Run")
        wanted = wanted.split()[0] if wanted else None
        if not wanted:
            return None
    meta_path = RUNS_DIR / wanted / "meta.json"
    if not meta_path.exists():
        console.print(f"[red]No run, task or file matching {wanted}.[/red]")
        return None
    recording = Path(json.loads(meta_path.read_text()).get("recording") or "")
    searched = [recording, RECORDINGS_DIR / recording.name, ARCHIVE_DIR / recording.name]
    for candidate in searched:
        if candidate.is_file():
            return candidate, wanted
    # Recordings get moved around (e.g. archived under guidecore/runs/); look for the file name anywhere under guidecore/.
    for candidate in (ROOT.parent / "guidecore").rglob(recording.name):
        return candidate, wanted
    console.print(f"[red]{recording.name} (run {wanted}) is not on this machine.[/red] Looked in:")
    for place in dict.fromkeys(str(p.parent) for p in searched):
        console.print(f"  {place}")
    console.print("Copy the file here, or pass its path / a folder with runs_log.csv: python main.py replay <path>")
    return None


def clip(value, limit: int = 60) -> str:
    text = " ".join(str(value if value is not None else "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def locate(path: str | None) -> Path | None:
    """Screenshot / vision report paths come from the machine that recorded them; look in the usual places."""
    if not path:
        return None
    name = Path(path).name
    for candidate in (Path(path), ROOT.parent / "guidecore" / path, ROOT / "vision_outputs" / name, ROOT.parent / "screenshots" / name):
        if candidate.is_file():
            return candidate
    return None


def show_commands(commands: list[dict], start: str) -> None:
    table = Table(show_header=True, header_style="bold", expand=False)
    for column in ("+s", "source", "command", "parameters"):
        table.add_column(column)
    for c in commands:
        table.add_row(
            str(elapsed(start, c["timestamp"])), c.get("source") or "", c["method"],
            clip(json.dumps(c["parameters"]) if c.get("parameters") else "", 80),
        )
    console.print(Panel(table, title="Commands executed on the daemon", border_style="blue", title_align="left"))


def show_perceived(state: dict) -> None:
    """The world as the agent received it, then what each stage made of it."""
    context = (state.get("snapshot") or {}).get("context") or {}
    page, voiceover = context.get("page") or {}, context.get("voiceoverFocus") or {}
    focus = context.get("browserFocus") or {}
    vision = state.get("vision") or {}
    rows = [
        ("Page", f"{page.get('title')} — {page.get('url')}"),
        ("VoiceOver said", voiceover.get("lastSpokenPhrase") or "(nothing)"),
        ("Item text log", " | ".join(voiceover.get("itemTextLog") or []) or "(empty)"),
        ("Outside web content", voiceover.get("isOutsideWebContent")),
        ("Browser focus", f"{focus.get('role')} {focus.get('name') or ''}".strip() if focus else "(none)"),
        ("Cursor path", " > ".join(map(str, context.get("cursorPath") or [])) or "(empty)"),
        ("Screenshot", page.get("screenshotPath")),
        ("Vision report", vision.get("report_path")),
    ]
    text = Text()
    for label, value in rows:
        text.append(f"{label}: ", style="bold")
        text.append(f"{value}\n")
    console.print(Panel(text, title="Snapshot: what the daemon reported", border_style="cyan", title_align="left"))
    try:
        from state.parsers import render_nearby_content

        nearby = render_nearby_content((context.get("a11y") or {}).get("tree"))
        console.print(Panel(Text(nearby), title="Nearby content (readable without moving)", border_style="cyan", title_align="left"))
    except Exception as error:  # parsers need the agent's dependencies (pydantic)
        console.print(f"[dim]Nearby content unavailable here: {error!r}[/dim]")
    for title, key, style in (
        ("Vision (what the picture looked like)", "vision", "magenta"),
        ("Perception (what the agent understood)", "perception", "green"),
        ("Evaluation (is the goal reached?)", "evaluation", "yellow"),
        ("Memory", "memory", "white"),
        ("Transition (what the last action changed)", "transition", "white"),
    ):
        value = state.get(key)
        if key == "vision" and value:
            value = value.get("description")
        value = value if value not in (None, [], {}) else "(empty)"
        body = Text(value) if isinstance(value, str) else Pretty(value, expand_all=True, max_string=4000)
        console.print(Panel(body, title=title, border_style=style, title_align="left"))
    history = state.get("action_history") or []
    if history:
        lines = [f"decision {a.get('decision', '?')}: {a['name']} {json.dumps(a.get('arguments') or {})} -> {clip(a.get('result'), 60)}" for a in history[-8:]]
        console.print(Panel(Text("\n".join(lines)), title=f"Action history (last {len(lines)} of {len(history)})", title_align="left"))


def timeline(rec: Recording) -> None:
    """One row per decision: what the agent concluded about progress, and what it did next."""
    table = Table(title=f"{rec.run_id}", show_lines=False)
    for column in ("step", "+s", "iter", "progress", "after the action, VoiceOver said", "actions chosen"):
        table.add_column(column)
    t0 = rec.started
    for n in rec.order:
        step = rec.steps[n]
        if "decision" not in step.nodes:
            continue
        update = rec.read(step.updates["decision"])
        calls = [c for m in update.get("messages", []) for c in m.get("tool_calls", [])]
        state = rec.state_at(n)
        evaluation = state.get("evaluation") or {}
        spoken = ((state.get("snapshot") or {}).get("context") or {}).get("voiceoverFocus", {}).get("lastSpokenPhrase")
        table.add_row(
            str(n), str(elapsed(t0, step.ts)), str(state.get("iteration", "")),
            evaluation.get("progress_status", "") + (" ✔ goal" if evaluation.get("goal_reached") else "") + (" ⚠ blocked" if evaluation.get("blocked") else ""),
            clip(spoken, 50), ", ".join(c["name"].removeprefix("voiceover_") for c in calls) or "(none)",
        )
    console.print(table)
    final = rec.state_at(rec.order[-1]) if rec.order else {}
    if final.get("final_summary"):
        console.print(Panel(Text(final["final_summary"]), title="Final summary", border_style="green", title_align="left"))


def elapsed(start: str, now: str) -> int:
    from datetime import datetime

    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return int((parse(now) - parse(start)).total_seconds()) if start and now else 0


def show_step(rec: Recording, position: int) -> None:
    n = rec.order[position]
    step = rec.steps[n]
    state = rec.state_at(n)
    t0 = rec.started
    console.rule(f"step {n} ({position + 1}/{len(rec.order)}) · +{elapsed(t0, step.ts)}s · iteration {state.get('iteration', 0)} · {rec.run_id}")
    render_active_node(step.nodes[0])
    if step.commands:
        show_commands(step.commands, rec.started)
    if "snapshot" in step.nodes:
        show_perceived_snapshot_only(state)
    show_llm_calls([rec.read(o) for o in step.llm])
    for node, offset in step.updates.items():
        console.print(f"[bold magenta]State update by {node} (abridged)[/bold magenta]")
        show_state(rec.read(offset))


def show_perceived_snapshot_only(state: dict) -> None:
    """On a snapshot step show just the daemon-reported part; the later stages appear on their own steps."""
    context = (state.get("snapshot") or {}).get("context") or {}
    page, voiceover = context.get("page") or {}, context.get("voiceoverFocus") or {}
    focus = context.get("browserFocus") or {}
    text = Text()
    for label, value in (
        ("Page", f"{page.get('title')} — {page.get('url')}"),
        ("VoiceOver said", voiceover.get("lastSpokenPhrase") or "(nothing)"),
        ("Item text log", " | ".join(voiceover.get("itemTextLog") or []) or "(empty)"),
        ("Browser focus", f"{focus.get('role')} {focus.get('name') or ''}".strip() if focus else "(none)"),
    ):
        text.append(f"{label}: ", style="bold")
        text.append(f"{value}\n")
    console.print(Panel(text, title="What the daemon reported", border_style="cyan", title_align="left"))


def dig(value, path: str):
    for part in path.split("."):
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return f"<nothing at {part!r}>"
    return value


def open_image(state: dict) -> None:
    vision = state.get("vision") or {}
    page = ((state.get("snapshot") or {}).get("context") or {}).get("page") or {}
    target = locate(vision.get("report_path")) or locate(vision.get("path")) or locate(page.get("screenshotPath"))
    if target:
        subprocess.run(["open", str(target)], check=False)
        console.print(f"Opened {target}")
    else:
        console.print("[yellow]Image not found on this machine (screenshots and vision reports stay on the machine that recorded them).[/yellow]")


LIVE_SKIP = ("recording.",)  # the daemon's own recording is not part of the run being reproduced


class LiveDaemon:
    """Sends a recording's logged commands to the guidecore daemon, in order, tagged source=replay."""

    def __init__(self):
        from tools.client import GuidecoreClient

        self.client = GuidecoreClient(source="replay")
        self.client.call("recording.status")  # fail early if the daemon is not running
        self.done: set[int] = set()

    def spoken(self) -> str | None:
        try:
            snap = self.client.call("daemonstate.snapshot")["daemon_state"]
            return ((snap.get("context") or {}).get("voiceoverFocus") or {}).get("lastSpokenPhrase")
        except Exception:
            return None

    def send(self, rec: "Recording", number: int, compact: bool = False) -> None:
        step = rec.steps[number]
        commands = [c for c in step.commands if not c["method"].startswith(LIVE_SKIP)]
        if not commands:
            return
        ok = True
        for c in commands:
            label = f"{c['method']} {json.dumps(c['parameters']) if c.get('parameters') else ''}".strip()
            try:
                self.client.call(c["method"], c.get("parameters") or {})
                console.print(f"[green]sent[/green] {label}")
            except Exception as error:
                ok = False
                console.print(f"[red]failed[/red] {label}: {error}")
                break
        if ok:
            self.done.add(number)
        after = next((n for n in rec.order if n > number and "snapshot" in rec.steps[n].nodes), None)
        if ok and after is not None and commands[-1]["method"].startswith("voiceover."):
            recorded = (((rec.state_at(after).get("snapshot") or {}).get("context") or {}).get("voiceoverFocus") or {}).get("lastSpokenPhrase")
            now = self.spoken()
            same = " ".join((recorded or "").split()) == " ".join((now or "").split())
            if compact and same:
                console.print(f"  [green]✓ same as recorded:[/green] {clip(now, 100)}")
            elif compact:
                console.print(f"  [red]✗ differs[/red]  recorded: {clip(recorded, 100)}\n             live: {clip(now, 100)}")
            else:
                console.print(Panel(
                    Text(f"recorded: {clip(recorded, 200)}\nlive:     {clip(now, 200)}"),
                    title="VoiceOver now vs recording: " + ("same" if same else "DIFFERENT"),
                    border_style="green" if same else "red", title_align="left",
                ))


def live_commands(rec: Recording, number: int) -> list[dict]:
    return [c for c in rec.steps[number].commands if not c["method"].startswith(LIVE_SKIP)]


def brief_step(rec: Recording, number: int) -> None:
    """One or two lines for a step: the node and what its LLM said (the agent's reasoning), clipped."""
    step = rec.steps[number]
    t0 = rec.started
    head = f"[bold]step {number}[/bold] [dim]+{elapsed(t0, step.ts)}s[/dim] {', '.join(step.nodes)}"
    console.print(head)
    for offset in step.llm:
        call = rec.read(offset)
        output = call["output"]
        text = clip(output.get("content"), 220)
        calls = ", ".join(f"{c['name']}({json.dumps(c.get('args') or {}) if c.get('args') else ''})" for c in output.get("tool_calls") or [])
        console.print(Text.assemble(("    " + call["node"] + ": ", "cyan"), text, (("  → " + calls) if calls else "", "bold green")))


def show_llm(rec: Recording, steps: list[int], node: str | None = None) -> None:
    """Full LLM input/output of the given steps (optionally one node), each call labelled with its step."""
    shown = 0
    for number in steps:
        for offset in rec.steps[number].llm:
            call = rec.read(offset)
            if node and call["node"] != node:
                continue
            console.rule(f"step {number} · {call['node']}")
            show_llm_calls([call], full=True)
            shown += 1
    if not shown:
        console.print("No LLM calls in " + (f"node {node!r} of " if node else "") + f"steps {steps[0]}-{steps[-1]}." if steps else "No steps.")


def advance_live(rec: Recording, daemon: LiveDaemon, position: int, verbose: bool) -> int | None:
    """Move to the next step that has commands, summarising the steps in between, then send them.

    Returns the new position, or None if the recording has no more commands.
    """
    target = next((i for i in range(position + 1, len(rec.order)) if live_commands(rec, rec.order[i])), None)
    # Steps before the command step get a short summary; the command step itself is shown below.
    stop = target if target is not None else len(rec.order)
    for i in range(position + 1, stop):
        brief_step(rec, rec.order[i])
    if target is None:
        return None
    number = rec.order[target]
    if verbose:
        show_step(rec, target)
    else:
        console.print(f"[bold]step {number}[/bold] [dim]+{elapsed(rec.started, rec.steps[number].ts)}s · iteration {rec.state_at(number).get('iteration', 0)}[/dim]")
    daemon.send(rec, number, compact=not verbose)
    return target


def replay(target: str | None = None, live: bool = False) -> None:
    resolved = resolve(target)
    if not resolved:
        return
    console.print(f"Indexing {resolved[0]} ...")
    rec = Recording(*resolved)
    if not rec.order:
        console.print("No agent steps in this recording.")
        return
    console.print(f"{len(rec.order)} steps of {rec.run_id}.")
    console.print(HELP, markup=False, style="dim")
    daemon = None
    if live:
        try:
            daemon = LiveDaemon()
        except Exception as error:
            console.print(f"[red]Cannot reach the guidecore daemon ({error!r}). Start it first (live replay sends the commands to it).[/red]")
            return
    position, verbose = 0, False
    window = [rec.order[0]]  # steps passed over by the last command: what `i` shows
    if daemon:
        console.print("[bold]Live: Enter runs the next command(s) and summarises the agent steps in between; a runs everything; d toggles full step detail.[/bold]")
        daemon.send(rec, rec.order[0])
    show_step(rec, position)
    while True:
        n = rec.order[position]
        try:
            console.print(BAR_LIVE if daemon else BAR, markup=False, style="dim")
            cmd = input("> ").strip()
        except EOFError:
            return
        word, _, arg = cmd.partition(" ")
        arg = arg.strip()
        if daemon and (cmd == "p" or word in ("g", "j", "b")):
            console.print("Live replay only moves forward: the commands change the real browser.")
            continue
        if daemon and cmd == "x":
            daemon.send(rec, n)
            continue
        if daemon and cmd == "d":
            verbose = not verbose
            console.print(f"Full step detail {'on' if verbose else 'off'}.")
            continue
        if daemon and word in ("", "n", "c", "a") and not (word == "c" and not arg.isdigit()):
            count = int(arg) if word == "c" else None
            pause = float(arg) if word == "a" and arg.replace(".", "", 1).isdigit() else 0.0
            ran = 0
            window_start = position
            try:
                limit = None if word == "a" else (count or 1)
                while limit is None or ran < limit:
                    moved = advance_live(rec, daemon, position, verbose)
                    if moved is None:
                        console.print("End of the recording: no more commands.")
                        break
                    position, ran = moved, ran + 1
                    if rec.order[position] not in daemon.done:
                        console.print("[red]A command failed; stopped.[/red]")
                        break
                    if word == "a" and pause:
                        time.sleep(pause)
            except KeyboardInterrupt:
                console.print("\nStopped.")
            window = rec.order[window_start + 1 : position + 1] or window
            continue
        if cmd in ("", "n"):
            if position == len(rec.order) - 1:
                console.print("End of the recording.")
                continue
            position += 1
            if daemon:
                daemon.send(rec, rec.order[position])
        elif cmd == "p":
            position = max(position - 1, 0)
        elif word == "g" and arg.isdigit():
            later = [i for i, s in enumerate(rec.order) if s >= int(arg)]
            position = later[0] if later else len(rec.order) - 1
        elif word in ("j", "b") and arg:
            hits = [i for i, s in enumerate(rec.order) if arg in rec.steps[s].nodes]
            hits = [i for i in hits if i > position] if word == "j" else [i for i in hits if i < position][::-1]
            if not hits:
                console.print(f"No {'later' if word == 'j' else 'earlier'} step of node {arg!r}.")
                continue
            position = hits[0]
        elif cmd == "t":
            timeline(rec)
            continue
        elif cmd == "v":
            show_perceived(rec.state_at(n))
            continue
        elif word == "i":
            steps = window if daemon else [n]
            if arg.isdigit() and int(arg) in rec.steps:
                steps, arg = [int(arg)], ""
            elif "-" in arg and all(p.isdigit() for p in arg.split("-", 1)):
                lo, hi = map(int, arg.split("-", 1))
                steps, arg = [x for x in rec.order if lo <= x <= hi], ""
            show_llm(rec, steps, arg or None)
            continue
        elif cmd == "s":
            pprint(rec.state_at(n), expand_all=True, max_string=2000)
            continue
        elif word == "k":
            pprint(dig(rec.state_at(n), arg), expand_all=True, max_string=5000)
            continue
        elif cmd == "o":
            open_image(rec.state_at(n))
            continue
        elif cmd == "q":
            return
        else:
            console.print(HELP, markup=False, style="dim")
            continue
        show_step(rec, position)
