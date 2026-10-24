import argparse
import os
import shutil
import subprocess
import tempfile
import webbrowser
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SRC = HERE / "data/voiceover_task_revisions.csv"
OUT = HERE / "data/reviewed_tasks.csv"
EXPORT = HERE / "data/reviewed_tasks_export.csv"


def open_editor(path):
    if os.environ.get("EDITOR"):
        subprocess.call([os.environ["EDITOR"], path])
    elif shutil.which("code"):
        subprocess.call(["code", "--wait", path])
    else:
        subprocess.call(["open", "-W", "-t", path])  # macOS TextEdit, waits until closed


def edit(base, other, base_name, other_name):
    """Edit `base` in a GUI editor; `other` is shown as '#' reference lines (ignored on save)."""
    ref = "\n".join(f"# {l}" for l in other.splitlines())
    body = (f"{base}\n\n# ---- Edit the text above, save and close the window. ----\n"
            f"# Lines starting with '#' are ignored. For reference, the {other_name} goal:\n{ref}\n")
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write(body)
        path = f.name
    open_editor(path)
    lines = [l for l in Path(path).read_text().splitlines() if not l.startswith("#")]
    os.unlink(path)
    return " ".join(" ".join(lines).split()) or base


def load():
    df = pd.read_csv(SRC, encoding="utf-8-sig")
    df["final_goal"] = df["proposed_goal"]
    df["decision"] = ""
    if OUT.exists():
        prev = pd.read_csv(OUT).set_index("task_id")
        for col in ("final_goal", "decision"):
            df[col] = df["task_id"].map(prev[col]).fillna(df[col] if col == "final_goal" else "")
    return df


def review(redo):
    df = load()
    for i, row in df.iterrows():
        if row.decision and not redo:
            continue
        print(f"\n=== {row.task_id} · {row.site} ({i + 1}/{len(df)}) · priority {row.review_priority}")
        print(f"URL: {row.url}\n\nORIGINAL:\n{row.original_goal}\n\nPROPOSED:\n{row.final_goal}\n")
        webbrowser.open(row.url)
        while True:
            k = input("[enter]=accept [e]dit proposed [o]edit original [r]eject [s]kip [q]uit > ").strip().lower()
            if k in ("", "e", "o", "r", "s", "q"):
                break
        if k == "q":
            break
        if k in ("e", "o"):
            if k == "e":
                new = edit(row.final_goal, row.original_goal, "proposed", "original")
            else:
                new = edit(row.original_goal, row.final_goal, "original", "proposed")
            df.at[i, "final_goal"] = new
            df.at[i, "decision"] = "edited"
        elif k == "r":
            df.at[i, "decision"] = "rejected"
        elif k == "":
            df.at[i, "decision"] = "accepted"
        df.to_csv(OUT, index=False)


def export():
    df = pd.read_csv(OUT)
    ok = df[df.decision.isin(["accepted", "edited"])].rename(
        columns={"final_goal": "goal", "impairment_original": "impairment"})
    ok[["task_id", "site", "url", "goal", "impairment"]].to_csv(EXPORT, index=False)
    print(f"exported {len(ok)}/{len(df)} tasks to {EXPORT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--export", action="store_true")
    a = ap.parse_args()
    export() if a.export else review(a.redo)
