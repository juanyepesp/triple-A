"""Batch run log (results/runs_log.csv) and the per-impairment summary used by `main.py batch`.

One row per run. Outcomes: success, max_iterations, stuck (same action repeated), timeout, site_error (page unreachable or
navigation failed), error (agent crash mid-run), setup_error (failed before the first step; retried automatically), aborted.
"""
import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
LOG = RESULTS / "runs_log.csv"
FIELDS = [
    "logged_at", "run_id", "task_id", "impairment", "url", "outcome", "success", "duration_s",
    "iterations", "actions", "blocked_evaluations", "last_progress_status", "error",
    "attempt", "goal", "final_summary", "recording", "transcript",
]


def read_log() -> list[dict]:
    if not LOG.exists():
        return []
    with open(LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_log(row: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerow(row)


def summary() -> None:
    rows = read_log()
    if not rows:
        print("No runs logged yet.")
        return
    # Only the latest attempt per (task, impairment) counts.
    latest = {(r["task_id"], r["impairment"]): r for r in rows}
    by_imp: dict[str, list[dict]] = defaultdict(list)
    for r in latest.values():
        by_imp[r["impairment"]].append(r)

    outcomes = sorted({r["outcome"] for r in latest.values()})
    header = ["impairment", "runs", "ok", "rate", "avg_s", "avg_iter"] + [f"n_{o}" for o in outcomes]
    print("\t".join(header))
    for imp, rs in sorted(by_imp.items()):
        ok = [r for r in rs if r["outcome"] == "success"]
        reachable = [r for r in rs if r["outcome"] != "site_error"]
        avg = lambda xs, k: round(sum(float(x[k]) for x in xs if x[k] != "") / max(1, len(xs)), 1)
        rate = f"{len(ok) / len(rs):.0%}"
        if len(reachable) != len(rs):
            rate += f" ({len(ok) / max(1, len(reachable)):.0%} excl. site errors)"
        counts = [str(sum(r["outcome"] == o for r in rs)) for o in outcomes]
        print("\t".join([imp, str(len(rs)), str(len(ok)), rate, str(avg(rs, "duration_s")), str(avg(rs, "iterations")), *counts]))

    # Tasks where impairments disagree are the interesting ones for the comparison.
    by_task: dict[str, dict[str, str]] = defaultdict(dict)
    for (task_id, imp), r in latest.items():
        by_task[task_id][imp] = r["outcome"]
    mixed = {t: o for t, o in by_task.items() if len(set(o.values())) > 1}
    if mixed:
        print(f"\nTasks with different outcomes per impairment ({len(mixed)}):")
        for t, o in sorted(mixed.items()):
            print(f"  {t}: " + ", ".join(f"{i}={v}" for i, v in sorted(o.items())))
