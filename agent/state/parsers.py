from typing import Any

from pydantic import ValidationError

from state.schema import DaemonSnapshot, SnapshotModel


def parse_daemon_snapshot(raw: dict[str, Any]) -> DaemonSnapshot:
    """Validate and unwrap a Guidecore RPC snapshot.

    This is the boundary between untrusted RPC data and agent state.
    """
    if not isinstance(raw, dict):
        raise TypeError("Guidecore snapshot response must be an object.")

    daemon_state = raw.get("daemon_state")
    if not isinstance(daemon_state, dict):
        raise ValueError("Guidecore snapshot response is missing daemon_state.")

    try:
        validated = SnapshotModel.model_validate(daemon_state)
    except ValidationError as exc:
        raise ValueError(f"Invalid Guidecore daemon snapshot: {exc}") from exc

    return validated.model_dump(by_alias=True)


# ---------------------------
# Snapshot -> compact LLM prompt text
# ---------------------------

MAX_TREE_DEPTH = 3
MAX_LIST_ITEMS = 10
WRAPPER_ROLES = {"generic", "group", "none", "presentation", "paragraph"}


def as_node(node: Any) -> dict:
    """The a11y tree mixes dict nodes with bare strings (text nodes); normalise to a dict."""
    if isinstance(node, dict):
        return node
    return {"role": "text", "text": str(node)}


def node_label(node: Any) -> str:
    """`role "name" [ref=e5] -> href`, without boxes or coordinates.

    Nodes without a name are labeled explicitly so the LLM doesn't read the
    omission as missing data.
    """
    node = as_node(node)
    parts = [str(node.get("role") or "unknown")]
    name = node.get("name") or node.get("text")
    name = str(name).strip() if name else ""
    parts.append(f'"{name[:120]}"' if name else "(name unavailable)")
    if node.get("ref"):
        parts.append(f"[ref={node['ref']}]")
    label = " ".join(parts)
    if node.get("url"):
        label += f" -> {node['url']}"
    return label


def is_meaningful(node: Any) -> bool:
    node = as_node(node)
    return node.get("role") not in WRAPPER_ROLES or bool(node.get("name"))


def render_tree(nodes: list[dict], depth: int = 0, budget: list[int] | None = None) -> list[str]:
    """Indented outline of meaningful nodes; unnamed wrappers are skipped but their children kept."""
    budget = budget if budget is not None else [MAX_LIST_ITEMS]
    lines: list[str] = []
    for node in nodes:
        node = as_node(node)
        if budget[0] <= 0:
            lines.append("  " * depth + "... (more omitted)")
            break
        children = node.get("children") or []
        if is_meaningful(node):
            budget[0] -= 1
            lines.append("  " * depth + "- " + node_label(node))
            if depth + 1 < MAX_TREE_DEPTH:
                lines += render_tree(children, depth + 1, budget)
        else:
            lines += render_tree(children, depth, budget)
    return lines


def render_flat(nodes: list[dict]) -> str:
    if not nodes:
        return "(none)"
    shown = [f"- {node_label(n)}" for n in nodes[:MAX_LIST_ITEMS]]
    if len(nodes) > MAX_LIST_ITEMS:
        shown.append(f"... and {len(nodes) - MAX_LIST_ITEMS} more")
    return "\n".join(shown)


def render_browser_focus(focus: dict | None) -> str:
    if not focus:
        return "No element has browser focus."
    return (
        "The element that receives a click or VO+Space activation, regardless of where "
        f"the VoiceOver cursor is: {node_label(focus)}"
    )


def render_cursor_path(path: list[dict]) -> str:
    if not path:
        return "(empty)"
    path = [as_node(n) for n in path]
    kept = [n for n in path if is_meaningful(n) or n is path[-1]]
    text = " > ".join(node_label(n) for n in kept)
    skipped = len(path) - len(kept)
    if skipped:
        text += f"\n({skipped} unnamed wrapper node(s) omitted)"
    if len(path) == 1 and not (path[0].get("name") or path[0].get("text")):
        text += "\n(the cursor is on an unnamed container, not on a specific named element)"
    return text


def render_focus_comparison(comparison: dict | None, voiceover_phrase: Any) -> str:
    comparison = comparison or {}
    same = comparison.get("VOCursorBrowserFocusAreSimilarEnough")
    score = comparison.get("similarityScore")
    if same is None:
        return "Unknown: focus comparison unavailable."
    if same:
        verdict = (
            "SAME ELEMENT: the VoiceOver cursor is on the element that has browser focus, "
            "so activating (VO+Space) acts on what VoiceOver just announced."
        )
    else:
        verdict = (
            "DIFFERENT ELEMENTS: the VoiceOver cursor is NOT on the browser-focused element. "
            "VO+Space or a click acts on the browser-focused element, not on what VoiceOver "
            "just announced. Move focus first if the announced element is the target."
        )
    return f"{verdict} (similarity {score}; role match: {comparison.get('roleMatches')})"


NEARBY_SIBLINGS = 6
NEARBY_NODE_CHARS = 400
ACTIVE_TEXT_CHARS = 1500


def node_text(node: dict) -> str:
    """Own name/text of a node."""
    node = as_node(node)
    return " ".join(str(node.get("name") or node.get("text") or "").split())


def subtree_text(node: dict, limit: int) -> str:
    """All readable text under a node, in reading order, clipped to `limit`."""
    parts: list[str] = []

    def visit(n: Any) -> None:
        n = as_node(n)
        own = node_text(n)
        if own and (not parts or parts[-1] != own):
            parts.append(own)
        for child in n.get("children") or []:
            visit(child)

    visit(node)
    text = " ".join(parts)
    return text if len(text) <= limit else text[:limit] + "..."


def find_active_path(nodes: list[dict], path: list[dict] | None = None) -> list[dict] | None:
    path = path or []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        here = [*path, node]
        if node.get("active"):
            return here
        found = find_active_path(node.get("children") or [], here)
        if found:
            return found
    return None


def nearby_line(node: Any, marker: str = "  ") -> str:
    node = as_node(node)
    role = node.get("role") or "unknown"
    name = " ".join(str(node.get("name") or "").split())
    label = f'{role} "{name[:120]}"' if name else role
    if node.get("url"):
        label += f" -> {node['url']}"
    text = subtree_text(node, NEARBY_NODE_CHARS)
    if text and text != name:
        label += f": {text}"
    return f"{marker}{label}"


def render_nearby_content(tree: Any) -> str:
    """Text around the browser-focused element, in reading order, from the full a11y tree.

    The outline of the active element drops unnamed nodes (paragraphs, list items, text), which hides
    exactly the content a user would read next. This shows the focused element's full text and its
    neighbours so the agent can read without moving.
    """
    roots = tree if isinstance(tree, list) else [tree] if tree else []
    path = find_active_path(roots)
    if not path:
        return "(no element has browser focus, so there is no nearby content to show)"
    active = path[-1]

    # The nearest ancestor with other children to show (skips single-child wrappers).
    parent_index = len(path) - 2
    while parent_index >= 0 and len(path[parent_index].get("children") or []) <= 1:
        parent_index -= 1
    lines = [f"FOCUSED ELEMENT FULL TEXT: {subtree_text(active, ACTIVE_TEXT_CHARS) or '(no text)'}"]
    if parent_index < 0:
        return "\n".join(lines)

    parent = path[parent_index]
    focused_branch = path[parent_index + 1]
    siblings = parent.get("children") or []
    at = next((i for i, n in enumerate(siblings) if n is focused_branch), 0)
    start, end = max(0, at - NEARBY_SIBLINGS), min(len(siblings), at + NEARBY_SIBLINGS + 1)

    parent_name = " ".join(str(parent.get("name") or "").split())[:80]
    parent_label = f'{parent.get("role") or "container"}' + (f' "{parent_name}"' if parent_name else "")
    lines.append(f"\nSURROUNDING CONTENT inside {parent_label} (reading order, >>> marks the focused branch):")
    if start:
        lines.append(f"  ... {start} earlier item(s) omitted")
    for i in range(start, end):
        lines.append(nearby_line(siblings[i], ">>> " if i == at else "    "))
    if end < len(siblings):
        lines.append(f"  ... {len(siblings) - end} later item(s) omitted")
    return "\n".join(lines)


def render_relevant_nodes(relevant: dict) -> str:
    active = render_tree(relevant.get("active", []))
    sections = {
        "Active element and nearby structure (outline)": "\n".join(active) or "(none)",
        "Pressed/toggled": render_flat(relevant.get("pressed", [])),
        "Landmarks": render_flat(relevant.get("landmarks", [])),
        "Headings": render_flat(relevant.get("headings", [])),
        "Links": render_flat(relevant.get("links", [])),
    }
    return "\n\n".join(f"{title}:\n{body}" for title, body in sections.items())


def format_perception_evidence(state: dict) -> str:
    context = state["snapshot"]["context"]
    page = context["page"]
    vo_focus = context["voiceoverFocus"]
    return f"""
GOAL
{state["goal"]}

PAGE
Title: {page.get("title")}
URL: {page.get("url")}

VOICEOVER
Running: {context["voiceover"].get("running")}
Last spoken phrase: {vo_focus.get("lastSpokenPhrase")}
Item text log: {vo_focus.get("itemTextLog", [])}
Outside web content: {vo_focus.get("isOutsideWebContent")}

BROWSER FOCUS (what a click / VO+Space would activate)
{render_browser_focus(context.get("browserFocus"))}

IS VOICEOVER FOCUS THE SAME AS BROWSER FOCUS?
{render_focus_comparison(context.get("focusComparison"), vo_focus.get("lastSpokenPhrase"))}

CURSOR PATH (ancestors of the VoiceOver cursor, outermost first)
{render_cursor_path(context.get("cursorPath", []))}

PAGE STRUCTURE
{render_relevant_nodes(context["relevantNodes"])}

NEARBY CONTENT (full text next to the browser-focused element; use it to read without moving)
{render_nearby_content((context.get("a11y") or {}).get("tree"))}

VISUAL DESCRIPTION
{state.get("vision", {}).get("description")}
""".strip()


# ---------------------------
# Evaluation / decision context
# ---------------------------

RECENT_ACTIONS = 6


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(none)"


def format_perception(perception: Any) -> str:
    """Readable view of the structured Perception output."""
    return f"""
Page: {perception.page_description}
Current element role: {perception.element_role}
Confidence: {perception.confidence}
Relevant observations:
{bullets(perception.relevant_observations)}
Ambiguities / conflicting evidence:
{bullets(perception.ambiguities)}
""".strip()


def format_transition(transition: dict | None) -> str:
    """What changed between the previous snapshot and this one, as a short comparison."""
    if not transition or not transition.get("action"):
        return "No action has been taken yet; this is the first snapshot."
    verdict = (
        "The VoiceOver position CHANGED."
        if transition.get("state_changed")
        else "Nothing observable changed (same phrase, role and cursor path): the action had no visible effect."
    )
    return f"""
Action taken: {transition["action"]}
{verdict}
Before: {transition.get("previous_role")} - "{transition.get("previous_phrase")}"
After:  {transition.get("current_role")} - "{transition.get("current_phrase")}"
""".strip()


def consecutive_repeats(history: list[dict]) -> int:
    """How many decisions in a row ended with the same action (same tool and arguments).

    A decision may issue several actions (e.g. next, next, next); those count once, so a deliberate
    short read-ahead is not mistaken for a loop.
    """
    if not history:
        return 0
    key = lambda a: (a["name"], str(a.get("arguments")))
    latest = key(history[-1])
    decisions = []
    for action in reversed(history):
        if key(action) != latest:
            break
        decision = action.get("decision")
        if decision is None:
            decision = object()  # legacy record without a decision id: count it on its own
        if not decisions or decisions[-1] != decision:
            decisions.append(decision)
    return len(decisions)


def format_action_history(history: list[dict], limit: int = RECENT_ACTIONS) -> str:
    """Most recent actions plus a warning when the same action is repeated back to back."""
    if not history:
        return "(no actions yet)"
    recent = history[-limit:]
    offset = len(history) - len(recent)
    lines = [
        f"{offset + i + 1}. {a['name']}({a.get('arguments') or ''})"
        for i, a in enumerate(recent)
    ]
    repeats = consecutive_repeats(history)
    text = f"{len(history)} action(s) so far; most recent last:\n" + "\n".join(lines)
    if repeats >= 3:
        text += (
            f"\nWARNING: '{history[-1]['name']}' has been chosen in {repeats} consecutive decisions. Moving the cursor "
            "is not progress by itself: if the last several elements did not contain what the goal asks for, "
            "STOP stepping the same way and change strategy (a different navigation method, the site's search, "
            "a different section, or a link that leads straight to the target)."
        )
    return text
