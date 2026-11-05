"""Capture what each node's LLM actually receives and returns."""
import json
import time

from langchain_core.callbacks import BaseCallbackHandler
from rich.text import Text


def _clip(value, limit: int) -> str:
    text = " ".join(str(value).split())
    return text[:limit] + ("..." if len(text) > limit else "")


def flatten_content(content) -> str:
    """Message content -> readable text; images become a placeholder."""
    if isinstance(content, str):
        return content
    parts = []
    for part in content or []:
        if isinstance(part, str):
            parts.append(part)
        elif part.get("type") == "text":
            parts.append(part.get("text", ""))
        elif part.get("type") in ("image_url", "image"):
            url = part.get("image_url", {})
            url = url.get("url", "") if isinstance(url, dict) else str(url)
            parts.append(f"[image: {url[:40]}... {len(url)} chars]")
        else:
            parts.append(repr(part)[:200])
    return "\n".join(parts)


def message_view(message) -> dict:
    view = {"role": getattr(message, "type", "?"), "content": flatten_content(message.content)}
    if getattr(message, "tool_calls", None):
        view["tool_calls"] = message.tool_calls
    return view


class LLMTrace(BaseCallbackHandler):
    """Collects one record per LLM call; main.py drains `calls` after every node."""

    def __init__(self, console=None):
        self.calls: list[dict] = []
        self._open: dict = {}
        self._console = console
        self._progress: dict = {}
        self._tools: dict = {}

    def _start_progress(self, run_id, call):
        if self._console is None:
            return
        status = self._console.status(
            f"[cyan]{call['node']}[/cyan] calling {call['model']}...", spinner="dots"
        )
        status.start()
        self._progress[run_id] = (status, time.monotonic())

    def on_llm_new_token(self, token, *, run_id, **kwargs):
        call = self._open.get(run_id)
        if call is not None and "first_token" not in call:
            call["first_token"] = time.monotonic()

    def _metrics(self, call, message, now):
        started = call["started"]
        total = now - started
        ttft = call["first_token"] - started if "first_token" in call else None
        usage = getattr(message, "usage_metadata", None) or {}
        metrics = {
            "total_s": round(total, 3),
            "ttft_s": round(ttft, 3) if ttft is not None else None,
            "generation_s": round(total - ttft, 3) if ttft is not None else None,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }
        out, gen = metrics["output_tokens"], metrics["generation_s"]
        metrics["tokens_per_s"] = round(out / gen, 1) if out and gen else None
        return metrics

    def _print_metrics(self, metrics):
        parts = []
        if metrics["ttft_s"] is not None:
            parts.append(f"ttft {metrics['ttft_s']:.2f}s")
        if metrics["generation_s"] is not None:
            parts.append(f"gen {metrics['generation_s']:.2f}s")
        parts.append(f"total {metrics['total_s']:.2f}s")
        if metrics["input_tokens"] is not None:
            parts.append(f"in {metrics['input_tokens']} tok")
        if metrics["output_tokens"] is not None:
            parts.append(f"out {metrics['output_tokens']} tok")
        if metrics["tokens_per_s"] is not None:
            parts.append(f"{metrics['tokens_per_s']} tok/s")
        self._console.print(Text("    " + " · ".join(parts), style="dim"))

    def _finish_progress(self, run_id, call, error=None):
        entry = self._progress.pop(run_id, None)
        if entry is None:
            return
        status, started = entry
        status.stop()
        elapsed = time.monotonic() - started
        if error is None:
            self._console.print(f"[green]✓[/green] {call['node']} ({call['model']}) done in {elapsed:.1f}s")
        else:
            self._console.print(f"[red]✗[/red] {call['node']} ({call['model']}) failed after {elapsed:.1f}s: {error!r}")

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        call = {
            "node": (metadata or {}).get("langgraph_node"),
            "model": (metadata or {}).get("ls_model_name"),
            "input": [message_view(m) for m in messages[0]],
            "started": time.monotonic(),
            # with_structured_output(method="function_calling") forces a single tool_choice
            "structured": isinstance((kwargs.get("invocation_params") or {}).get("tool_choice"), dict),
        }
        self._open[run_id] = call
        self._start_progress(run_id, call)

    def on_llm_end(self, response, *, run_id, **kwargs):
        call = self._open.pop(run_id, None)
        if call is None:
            return
        message = response.generations[0][0].message
        call["output"] = message_view(message)
        if call.get("structured") and message.tool_calls:
            # Not a real tool call: it is the schema-shaped answer, so show it as content.
            first = message.tool_calls[0]
            call["output"]["content"] = f"{first['name']} " + json.dumps(first["args"], indent=2, ensure_ascii=False)
            call["output"].pop("tool_calls")
        call["metrics"] = self._metrics(call, message, time.monotonic())
        self.calls.append(call)
        self._finish_progress(run_id, call)
        if self._console is not None:
            self._print_metrics(call["metrics"])

    def on_llm_error(self, error, *, run_id, **kwargs):
        call = self._open.pop(run_id, None)
        if call is not None:
            call["output"] = {"role": "error", "content": repr(error)}
            self.calls.append(call)
            self._finish_progress(run_id, call, error)

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        args = inputs if inputs is not None else input_str
        self._tools[run_id] = (name, args, time.monotonic())
        if self._console is not None:
            self._console.print(Text.assemble(("→ tool ", "bold magenta"), f"{name}({_clip(args, 150)})"))

    def on_tool_end(self, output, *, run_id, **kwargs):
        entry = self._tools.pop(run_id, None)
        if entry is None or self._console is None:
            return
        name, _, started = entry
        content = getattr(output, "content", output)
        self._console.print(Text.assemble(
            ("✓ ", "green"), f"{name} {time.monotonic() - started:.1f}s → ", _clip(content, 300)
        ))

    def on_tool_error(self, error, *, run_id, **kwargs):
        entry = self._tools.pop(run_id, None)
        if entry is None or self._console is None:
            return
        self._console.print(Text.assemble(("✗ ", "red"), f"{entry[0]} failed: ", _clip(error, 300)))

    def drain(self) -> list[dict]:
        calls, self.calls = self.calls, []
        return calls
