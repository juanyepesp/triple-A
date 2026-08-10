from typing import TypedDict, Annotated, Sequence, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from dataclasses import dataclass

@dataclass
class VoiceOverInfo:
    running: bool
    mode: Literal["normal", "rotor", None]
    cursor_description: str | None

@dataclass
class DaemonSnapshot:
    version: int
    ready: bool

    page_url: str | None
    page_title: str | None

    accessibility_tree: str
    screenshot_path: str

    voiceover: VoiceOverInfo

    events: list[dict]

class Perception(TypedDict):
    current_location: str
    focused_element: str | None
    page_description: str
    available_elements: list[str]
    available_navigation: list[str]
    voiceover_state: str
    relevant_observations: list[str]
    ambiguities: list[str]


class Evaluation(TypedDict):
    goal_reached: bool
    confidence: float
    progress_status: str
    evidence: list[str]
    blocked: bool

class PlannedAction(TypedDict):
    name: Literal[
        "voiceover.next",
        "voiceover.previous",
        "voiceover.startInteracting",
        "voiceover.stopInteracting",
        "voiceover.escape",
        "voiceover.rotor.open",
        "voiceover.rotor.nextCategory",
        "voiceover.rotor.previousCategory",
        "voiceover.rotor.nextItem",
        "voiceover.rotor.previousItem",
        "voiceover.rotor.activate",
    ]

    params: dict = {}


class ActionPlan(TypedDict):
    reasoning: str
    actions: list[PlannedAction]

class ActionPlan(TypedDict):
    reasoning: str
    actions: list[PlannedAction]

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    goal: str # The ultimate goal to reach. "Go to this marketplace site and find the about us page, summarize the page."
    initial_URL: str
    snapshot: DaemonSnapshot # Comes from Guidepup
    perception: Perception # Output of the perception node
    evaluation: Evaluation # Output of the evaluation node
    action_plan: ActionPlan # Output of the decision node
    memory: list[str] 
    iteration: int
    goal_reached: bool
    final_summary: str
    execution_results: list[str]

