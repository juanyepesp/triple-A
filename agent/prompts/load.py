from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()