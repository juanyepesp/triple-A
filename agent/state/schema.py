from typing import Any, Optional, TypedDict, Annotated, Sequence, Literal, NotRequired
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

# ! LLM nodes are non-deterministic even when trying to force structured outputs, there is this potential to get erroneous responses

# Tools I can use
# TypedDict -> Less complex classes
# Literal -> Defines possible outputs
# Union -> Can be more than one data type (say, float and integer)
# Optional -> Either the type, or nothing else
# Any (i'll try not to use it)
# Annotated is for specifying metadata
# Annotated[type, default, description]
    # justification: Annotated[
    #     str | None, None, "A justification for the answer."
    # ]

# -----------------------------------------------------------
# MODELS
# Structured outputs from the models (non-deterministic)
# -----------------------------------------------------------

class Vision(TypedDict):
    """
    Structured output from the vision node, the model just gets the description
    """
    description: str
    path: str
    screenshot_hash: str
    report_path: NotRequired[str]

class Perception(BaseModel):
    """
    Structured output from the perception model
    """

    model_config = ConfigDict(extra="forbid")

    element_role: Literal[
            "web content",
            "heading",
            "link",
            "table",
            "list",
            "button",
            "form control",
            "text field",
            "search field",
            "image",
            "landmark",
            "frame",
            "text",
            "unknown",
        ] = Field(
        description=(
            "Usually detailed at the beggining of the VO cursor_description,"
            "It is the role of the current element. Most commonly,"
            "link, heading, table, paragraph, landmark, form control, text,"
            "list, button, checkbox, image, frame, navigation, text box"
        ),
    )
    
    ambiguities: list[str] = Field(
        description=(
            "A list of anything that is uncertain,"
            "missing, contradictory, or difficult to determine from the"
            "available evidence. It explicitly identifies uncertainty about focus,"
            "page location, element identity, interaction state, Rotor"
            "category, or the meaning of an interface element."
        ),
    )
    
    page_description: str = Field(
        description=(
            "A summary of the current website purpose, major semantic"
            "regions, important content, and overall structure."
        )
    )
    
    element_interactions: list[str] = Field(
        description=(
            "A list of the available action from the element,"
            "provided by the from the cursor description. Usually announced"
            "at the end, with the literal commands, such as: "
            "To exit this group, press Control-Option-Shift-Up Arrow"
        ),
    )
    
    relevant_observations: list[str] = Field(
        description=(
            "List important observations that may influence future reasoning. "
        ),
    )
    current_element: Optional[dict[str, Any]] = None
    current_role: Optional[str] = None
    browser_focus: Optional[dict[str, Any]] = None
    is_outside_web_content: Optional[bool] = None
    confidence: Literal["high", "medium", "low"] = "low"


class Evaluation(BaseModel):
    """
    Structured output from the evaluation model
    """
    model_config = ConfigDict(extra="forbid")

    goal_reached: bool
    confidence: Literal["high", "medium", "low"]

    progress_status: Annotated[
        Literal['meaningful-progress', 'some-progress', 'stalled', 'moved-away-from-goal', 'blocked'],
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
        (
            "List the concrete observations from the current perception that "
            "support the evaluation. Prefer specific evidence such as an "
            "accessible name, heading, page region, form value, table content, "
            "or VoiceOver state over vague statements."
        ),
    ]
    
    blocked: bool
    
# Deterministic State
    
class VoiceOverInfo(TypedDict):
    """
    VoiceOver information from the Daemon State.
    """
    running: bool
    lastSpokenPhrase: Optional[str]

class RelevantNodes(TypedDict):
    '''
    Nodes that are in some way relevant for the agent.
    '''
    active: Annotated[
        list[dict[str, Any]],
        ...,
        (
            "The element that is currently in focus.",
            "Hitting interact (VO-Space) when this element is",
            "active, will activate this element, even if",
            "last spoken phrase by VoiceOver says we are somewhere else."
        ),
    ]
    pressed: Annotated[
        list[dict[str, Any]],
        ...,
        (
            "Any element in the website that was pressed."
            "Think of buttons, checkmarks, etc." #TODO check for preciseness
        ),
    ]
    landmarks: list[dict[str, Any]]
    headings: list[dict[str, Any]]
    links: list[dict[str, Any]]
    

class PageInformation(TypedDict):
    """
    The website we are currently on
    """
    url: Optional[str]
    title: Optional[str]
    screenshotPath: Optional[str]
    viewportLocation: Optional[dict[str, Any]]
    

class VoiceOverFocus(TypedDict):
    bounds: Optional[dict[str, Any]]
    lastSpokenPhrase: Optional[str]
    isOutsideWebContent: Optional[bool]
    itemTextLog: list[str]


class FocusComparison(TypedDict):
    VOCursorBrowserFocusAreSimilarEnough: Optional[bool]
    similarityScore: Optional[float]
    textSimilarity: Any
    roleMatches: Optional[bool]
    dimensionsSimilarity: Optional[float]


class SnapshotContext(TypedDict):
    page: PageInformation
    browserFocus: Optional[dict[str, Any]]
    voiceoverFocus: VoiceOverFocus
    focusComparison: FocusComparison
    cursorPath: list[dict[str, Any]]
    relevantNodes: RelevantNodes
    a11y: dict[str, Any]
    voiceover: VoiceOverInfo
    ready: bool
    events: list[dict[str, Any]]


class DaemonSnapshot(TypedDict):
    """
    Parsed state from the Guidepup Daemon
    """
    version: int
    context: SnapshotContext


class SnapshotPageModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    url: Optional[str] = None
    title: Optional[str] = None
    screenshot_path: Optional[str] = Field(default=None, alias="screenshotPath")
    viewport_location: Optional[dict[str, Any]] = Field(
        default=None, alias="viewportLocation"
    )


class SnapshotVoiceOverFocusModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    bounds: Optional[dict[str, Any]] = None
    last_spoken_phrase: Optional[str] = Field(default=None, alias="lastSpokenPhrase")
    is_outside_web_content: Optional[bool] = Field(
        default=None, alias="isOutsideWebContent"
    )
    item_text_log: list[str] = Field(default_factory=list, alias="itemTextLog")


class SnapshotFocusComparisonModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    similar: Optional[bool] = Field(
        default=None, alias="VOCursorBrowserFocusAreSimilarEnough"
    )
    similarity_score: Optional[float] = Field(default=None, alias="similarityScore")
    text_similarity: Any = Field(default=None, alias="textSimilarity")
    role_matches: Optional[bool] = Field(default=None, alias="roleMatches")
    dimensions_similarity: Optional[float] = Field(
        default=None, alias="dimensionsSimilarity"
    )


class SnapshotRelevantNodesModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    active: list[dict[str, Any]] = Field(default_factory=list)
    pressed: list[dict[str, Any]] = Field(default_factory=list)
    landmarks: list[dict[str, Any]] = Field(default_factory=list)
    headings: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)


class SnapshotVoiceOverModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    running: bool
    last_spoken_phrase: Optional[str] = Field(default=None, alias="lastSpokenPhrase")


class SnapshotContextModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    page: SnapshotPageModel
    browser_focus: Optional[dict[str, Any]] = Field(
        default=None, alias="browserFocus"
    )
    voiceover_focus: SnapshotVoiceOverFocusModel = Field(alias="voiceoverFocus")
    focus_comparison: SnapshotFocusComparisonModel = Field(alias="focusComparison")
    cursor_path: list[dict[str, Any]] = Field(alias="cursorPath")
    relevant_nodes: SnapshotRelevantNodesModel = Field(alias="relevantNodes")
    a11y: dict[str, Any]
    voiceover: SnapshotVoiceOverModel
    ready: bool
    events: list[dict[str, Any]]


class SnapshotModel(BaseModel):
    """Runtime-validated representation of the Guidecore snapshot."""

    model_config = ConfigDict(extra="forbid")

    version: int
    context: SnapshotContextModel


class ActionRecord(TypedDict):
    name: str
    arguments: dict[str, Any]
    result: Optional[str]


class TransitionSummary(TypedDict):
    action: Optional[str]
    previous_phrase: Optional[str]
    current_phrase: Optional[str]
    previous_role: Optional[str]
    current_role: Optional[str]
    previous_cursor_path: list[dict[str, Any]]
    current_cursor_path: list[dict[str, Any]]
    state_changed: bool

class AgentState(TypedDict):
    """
    Final State passed through each node
    """
    messages: Annotated[Sequence[BaseMessage], add_messages] # TODO needs to be reset every once in a while
    goal: str # The ultimate goal to reach. "Go to this marketplace site and find the about us page, summarize the page."
    initial_URL: str
    snapshot: DaemonSnapshot # All that comes from Guidepup
    impairment: str
    # TODO
    screenshot_runtime_dir: NotRequired[str]
    
    vision: Vision
    perception: Perception # Output of the perception node
    evaluation: Evaluation # Output of the evaluation node
    memory: list[str]
    last_action: Optional[ActionRecord]
    action_history: list[ActionRecord]
    transition: Optional[TransitionSummary]
    iteration: int
    goal_reached: bool
    final_summary: str
