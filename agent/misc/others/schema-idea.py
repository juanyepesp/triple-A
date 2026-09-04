from typing import TypedDict, Annotated, Sequence, Literal, NotRequired
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ============================================================
# LLM OUTPUTS
# ============================================================

class Vision(TypedDict):
    """
    Structured output from the vision model.

    The vision model describes only information that can be obtained from
    the supplied screenshot. It does not infer VoiceOver state or decide
    what action the agent should take.
    """

    description: Annotated[
        str,
        ...,
        (
            "Describe the visually relevant content visible in the screenshot. "
            "Mention page regions, visible controls, text, layout, dialogs, "
            "focus indicators, visual states, and other information that could "
            "help a blind user understand the interface when combined with "
            "screen-reader information. Do not invent content that is not "
            "visually supported by the screenshot. Do not decide what action "
            "to take."
        ),
    ]


class Perception(TypedDict):
    """
    Structured interpretation of the current browser environment.

    This is the agent's understanding of the current situation from the
    perspective of a blind VoiceOver user. It should combine the AOM,
    VoiceOver output/state, and vision information when available.
    """

    current_location: Annotated[
        str,
        ...,
        (
            "Describe where the user currently is within the webpage or "
            "application. Identify the current page and, when possible, the "
            "relevant structural or interactive region, such as a navigation "
            "landmark, main content area, form, dialog, table, or particular "
            "section. Infer location from the accessibility tree, page title, "
            "URL, VoiceOver cursor description, and recent observations. "
            "Do not confuse the URL with the user's current position within "
            "the page."
        ),
    ]

    current_focused_element: Annotated[
        str | None,
        None,
        (
            "Describe the element currently under the VoiceOver cursor. "
            "Use the accessibility tree and VoiceOver cursor description "
            "as the primary evidence. Include the element's accessible name, "
            "role, relevant state or value, and important contextual "
            "information when available. For example, distinguish between "
            "a heading, link, button, textbox, checkbox, table, row, or "
            "landmark. If the focused element cannot be determined reliably, "
            "return null rather than guessing."
        ),
    ]

    page_description: Annotated[
        str,
        ...,
        (
            "Describe the webpage in terms that are useful to a blind "
            "screen-reader user. Summarize its purpose, major semantic "
            "regions, important content, and overall structure. Use the "
            "accessibility tree as a primary source because it exposes "
            "semantic roles, names, states, and hierarchy. Use screenshot "
            "information only as supplementary evidence. Do not turn this "
            "into an action plan."
        ),
    ]

    available_elements: Annotated[
        list[str],
        ...,
        (
            "List the relevant elements currently available to the user that "
            "could help accomplish the goal. Describe them using information "
            "available to a screen-reader user, especially accessible name, "
            "role, and relevant state. Include useful links, headings, "
            "buttons, form controls, landmarks, tables, dialogs, or other "
            "interactive/content elements. Prioritize elements relevant to "
            "the current goal rather than listing every node in the "
            "accessibility tree."
        ),
    ]

    available_navigation: Annotated[
        list[str],
        ...,
        (
            "Describe useful navigation opportunities available from the "
            "current state. Consider normal VoiceOver navigation as well as "
            "semantic navigation through the VoiceOver Rotor. Identify "
            "whether headings, links, form controls, landmarks, tables, or "
            "other semantic groups provide a useful way to reach information. "
            "This field describes possible navigation strategies; it does "
            "not choose the next action."
        ),
    ]

    voiceover_state: Annotated[
        str,
        ...,
        (
            "Describe the current VoiceOver interaction state from the "
            "available daemon information and VoiceOver output. State whether "
            "VoiceOver is running, whether it is in normal navigation or "
            "Rotor mode, what the VoiceOver cursor is currently describing, "
            "and any other relevant VoiceOver context. Treat the daemon state "
            "as authoritative; do not infer a mode that contradicts it."
        ),
    ]

    relevant_observations: Annotated[
        list[str],
        ...,
        (
            "List important observations that may influence future reasoning. "
            "Include facts such as a relevant heading or link being present, "
            "a form control having a particular state, the current focus "
            "being inside a specific region, a dialog being open, a Rotor "
            "category being active, or a significant visual/accessibility "
            "relationship. These should be observations supported by the "
            "available evidence, not proposed actions."
        ),
    ]

    ambiguities: Annotated[
        list[str],
        ...,
        (
            "List anything about the current environment that is uncertain, "
            "missing, contradictory, or difficult to determine from the "
            "available evidence. Explicitly identify uncertainty about focus, "
            "page location, element identity, interaction state, Rotor "
            "category, or the meaning of an interface element. Do not resolve "
            "uncertainty by guessing."
        ),
    ]


class Evaluation(TypedDict):
    """
    Evaluation of whether the user's goal has actually been achieved.
    """

    goal_reached: Annotated[
        bool,
        ...,
        (
            "Set to true only when the current evidence demonstrates that the "
            "user's goal has actually been completed. Do not equate performing "
            "an action with accomplishing the goal. For example, activating "
            "a link does not prove that the resulting page contains the "
            "requested information. Require evidence from the current "
            "perception/state that the desired outcome exists."
        ),
    ]

    confidence: Annotated[
        float,
        ...,
        (
            "Your confidence in the evaluation, expressed as a value from "
            "0.0 to 1.0. Use high confidence only when the current evidence "
            "clearly supports the conclusion."
        ),
    ]

    progress_status: Annotated[
        str,
        ...,
        (
            "Describe the agent's current progress toward the goal. Explain "
            "whether it is making meaningful progress, has made no progress, "
            "is stalled, has moved away from the goal, or appears to have "
            "reached a terminal/blocked state."
        ),
    ]

    evidence: Annotated[
        list[str],
        ...,
        (
            "List the concrete observations from the current perception that "
            "support the evaluation. Prefer specific evidence such as an "
            "accessible name, heading, page region, form value, table content, "
            "or VoiceOver state over vague statements."
        ),
    ]

    blocked: Annotated[
        bool,
        ...,
        (
            "Set to true only when the available evidence indicates that the "
            "agent cannot reasonably continue toward the goal from the "
            "current state, such as an unrecoverable error, missing required "
            "information, or an interaction state that prevents progress."
        ),
    ]


# ============================================================
# DETERMINISTIC DAEMON STATE
# ============================================================

class VoiceOverInfo(TypedDict):
    """
    VoiceOver state reported by the daemon.
    """

    running: bool
    mode: Literal["normal", "rotor"]

    cursor_description: str | None


class RotorState(TypedDict):
    """
    Current VoiceOver Rotor state reported by the daemon.
    """

    open: bool
    category: str | None
    query: str | None


class DaemonSnapshot(TypedDict):
    """
    Parsed state returned by the Guidepup daemon.

    This represents the environment itself rather than the agent's
    interpretation of that environment.
    """

    version: int
    ready: bool

    page_url: str | None
    page_title: str | None

    accessibility_tree: str | None
    screenshot_path: str | None

    voiceover: VoiceOverInfo
    rotor: RotorState

    events: list[dict]


# ============================================================
# LANGGRAPH STATE
# ============================================================

class AgentState(TypedDict):
    """
    State maintained by the LangGraph agent.
    """

    messages: Annotated[
        Sequence[BaseMessage],
        add_messages,
    ]

    goal: Annotated[
        str,
        "The user's ultimate task that the agent must accomplish.",
    ]

    initial_URL: Annotated[
        str,
        "The URL where the browser session should begin.",
    ]

    snapshot: Annotated[
        DaemonSnapshot,
        (
            "The latest authoritative observation of the browser and "
            "VoiceOver environment returned by the daemon. This is raw "
            "environmental state, not an LLM interpretation."
        ),
    ]

    impairment: Annotated[
        str,
        (
            "The accessibility/impairment profile under which the agent "
            "should reason about the interaction."
        ),
    ]

    screenshot_runtime_dir: NotRequired[str]

    vision: NotRequired[Vision]

    perception: Perception

    evaluation: Evaluation

    memory: list[str]

    iteration: int

    goal_reached: bool

    final_summary: str