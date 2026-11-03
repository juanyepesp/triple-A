"""Task list (tasks.csv) and on-disk run store (runs/<run_id>/).

Each run directory contains:
  meta.json    task info + status (running / done / failed / aborted) + path of the recording
  transcript.md  readable log of every step: LLM inputs/outputs (the agent's "thoughts"), tool calls, evaluations
  trace.jsonl    the same step data, machine readable (llm calls + node updates; no full states)
Step events (llm / update / state) are written to the guidecore recording JSONL as
{"type": "agent.<kind>", "run_id", "step", "node", "data"}, next to the browser/voiceover
interactions. events.jsonl is only a fallback when no recording is reachable.
"""
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
TASKS_CSV = ROOT / "tasks.csv"
RUNS_DIR = ROOT / "runs"


def load_tasks(path: Path = TASKS_CSV) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_jsonable(value):
    """Convert pydantic models / LangChain messages / anything else to JSON."""
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def list_runs() -> list[dict]:
    runs = []
    for meta_path in sorted(RUNS_DIR.glob("*/meta.json")):
        runs.append(json.loads(meta_path.read_text()))
    return runs


def latest_status() -> dict[tuple[str, str], str]:
    """(task_id, impairment) -> status of its most recent run."""
    return {(r["task_id"], r["impairment"]): r["status"] for r in list_runs()}


class Run:
    def __init__(self, task: dict):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_id = f"{task['task_id']}_{task['impairment']}_{stamp}"
        self.dir = RUNS_DIR / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta = {
            "run_id": self.run_id,
            "task_id": task["task_id"],
            "url": task["url"],
            "goal": task["goal"],
            "impairment": task["impairment"],
            "status": "running",
            "started": datetime.now().isoformat(timespec="seconds"),
        }
        self._events = None
        self._sink = None
        self._seen_system: set[str] = set()
        self.set_status("running")
        self.meta["transcript"] = str(self.dir / "transcript.md")
        self.meta["trace"] = str(self.dir / "trace.jsonl")
        (self.dir / "transcript.md").write_text(
            f"# {self.run_id}\n\n- Goal: {task['goal']}\n- URL: {task['url']}\n- Impairment: {task['impairment']}\n"
            f"- Started: {self.meta['started']}\n"
        )

    def attach_recording(self, path: str, sink) -> None:
        """Send step events to the guidecore recording (same file as human/agent actions)."""
        self.meta["recording"] = path
        self._sink = sink
        self.set_status(self.meta["status"])

    def set_status(self, status: str) -> None:
        self.meta["status"] = status
        if status != "running":
            self.meta["ended"] = datetime.now().isoformat(timespec="seconds")
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "meta.json").write_text(json.dumps(self.meta, indent=2))

    def trace(self, step: int, kind: str, node: str | None, data) -> None:
        """Always-on local log of llm calls and node updates, independent of the recording."""
        data = to_jsonable(data)
        ts = datetime.now().isoformat(timespec="seconds")
        with open(self.dir / "trace.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"step": step, "kind": kind, "node": node, "ts": ts, "data": data}, ensure_ascii=False) + "\n")

        lines = []
        if kind == "llm":
            m = data.get("metrics") or {}
            lines.append(f"\n## step {step} · {node} · LLM call ({data.get('model')}) · {ts}")
            if m:
                lines.append(f"_{m.get('total_s')}s, {m.get('input_tokens')} in / {m.get('output_tokens')} out tokens_")
            for msg in data["input"]:
                if msg["role"] == "system":
                    if node in self._seen_system:
                        continue  # same system prompt every time; print it once per node
                    self._seen_system.add(node)
                lines.append(f"\n**INPUT ({msg['role']})**\n\n```text\n{msg['content']}\n```")
            out = data["output"]
            lines.append(f"\n**OUTPUT**\n\n```text\n{out.get('content') or '<empty>'}\n```")
            if out.get("tool_calls"):
                lines.append(f"\n**TOOL CALLS**\n\n```json\n{json.dumps(out['tool_calls'], indent=2, ensure_ascii=False)}\n```")
        elif kind == "update":
            lines.append(f"\n### step {step} · {node} · state update")
            lines.append(f"\n```json\n{json.dumps(self._clip(data), indent=2, ensure_ascii=False)}\n```")
        if lines:
            with open(self.dir / "transcript.md", "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

    def trace_error(self, text: str) -> None:
        with open(self.dir / "transcript.md", "a", encoding="utf-8") as f:
            f.write(f"\n### Error traceback\n\n```text\n{text}\n```\n")

    @classmethod
    def _clip(cls, value, limit: int = 3000):
        if isinstance(value, str):
            return value if len(value) <= limit else value[:limit] + f"... [{len(value) - limit} more chars, see trace.jsonl]"
        if isinstance(value, dict):
            return {k: cls._clip(v, limit) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._clip(v, limit) for v in value]
        return value

    def log(self, step: int, kind: str, node: str | None, data) -> None:
        if kind in ("llm", "update"):
            self.trace(step, kind, node, data)
        record = {
            "step": step,
            "kind": kind,
            "node": node,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "data": to_jsonable(data),
        }
        if self._sink is not None:
            try:
                result = self._sink({
                    "type": f"agent.{kind}",
                    "source": "agent",
                    "run_id": self.run_id,
                    "step": step,
                    "node": node,
                    "data": record["data"],
                })
                if not isinstance(result, dict) or result.get("ok") is not False:
                    return
            except Exception:
                pass
        # Recording unavailable: keep the event locally instead of losing it.
        if self._events is None:
            self._events = open(self.dir / "events.jsonl", "a", encoding="utf-8")
        self._events.write(json.dumps(record) + "\n")
        self._events.flush()

    def close(self) -> None:
        if self._events is not None:
            self._events.close()


def load_events(run_id: str) -> list[dict]:
    """Events of a run, read from its guidecore recording (or the legacy/fallback events.jsonl)."""
    events = []
    meta_path = RUNS_DIR / run_id / "meta.json"
    recording = json.loads(meta_path.read_text()).get("recording") if meta_path.exists() else None
    if recording and Path(recording).exists():
        for line in Path(recording).read_text().splitlines():
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("run_id") == run_id and str(entry.get("type", "")).startswith("agent."):
                events.append({
                    "step": entry["step"],
                    "kind": entry["type"].removeprefix("agent."),
                    "node": entry.get("node"),
                    "ts": entry["timestamp"],
                    "data": entry["data"],
                })
    path = RUNS_DIR / run_id / "events.jsonl"
    if path.exists():
        events += [json.loads(line) for line in path.read_text().splitlines() if line]
    return events
