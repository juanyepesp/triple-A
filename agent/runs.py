"""Task list (tasks.csv) and on-disk run store (runs/<run_id>/).

Each run directory contains:
  meta.json    task info + status (running / done / failed / aborted) + path of the recording
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
        self.set_status("running")

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

    def log(self, step: int, kind: str, node: str | None, data) -> None:
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
