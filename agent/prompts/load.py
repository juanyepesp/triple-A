from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


def load_component_prompt(component: str) -> str:
    """Shared pipeline context followed by the component's own prompt (e.g. 'perception')."""
    context = load_prompt("system.md").replace("{component}", component)
    return f"{context}\n\n---\n\n{load_prompt(f'{component}.md')}"
