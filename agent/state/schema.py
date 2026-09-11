from typing import Optional, TypedDict, Annotated, Sequence, Literal, NotRequired
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

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
    Structured output from the vision model
    """
    description: str
    path: str
    screenshot_hash: str
    impairment: str

class Perception(TypedDict):
    """
    Structured output from the perception model
    """

    element_role : Annotated[
        str,
        ...,
        (
            "Usually detailed at the beggining of the cursor description,"
            "It is the role of the current element. Most commonly,"
            "link, heading, table, paragraph, landmark, form control, text,"
            "list, button, checkbox, image, frame, navigation, text box"
        )
    ]
    
    ambiguities: Annotated[
        list[str],
        ...,
        (
            "A list of anything that is uncertain,"
            "missing, contradictory, or difficult to determine from the"
            "available evidence. It explicitly identifies uncertainty about focus,"
            "page location, element identity, interaction state, Rotor"
            "category, or the meaning of an interface element."
        ),
    ]
    
    page_description: Annotated[
        str,
        ...,
        (
            "A summary of the current website purpose, major semantic"
            "regions, important content, and overall structure."
        )
        
    ]
    
    element_interactions : Annotated[
        list[str],
        ...,
        (
            "A list of the available action from the element,"
            "provided by the from the cursor description."
        ) # TODO maybe few shot examples?
        
    ]
    
    relevant_observations: Annotated[
        list[str],
        ...,
        (
            "List important observations that may influence future reasoning. "
        )
    ]
    
    
    # current_focused_element: Optional[str]
    # available_elements: list[str]
    # available_navigation: list[str]
    # relevant_observations: list[str]
    # ambiguities: list[str]
    


class Evaluation(TypedDict):
    """
    Structured output from the evaluation model
    """
    goal_reached: bool

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
        ...,
        (
            "List the concrete observations from the current perception that "
            "support the evaluation. Prefer specific evidence such as an "
            "accessible name, heading, page region, form value, table content, "
            "or VoiceOver state over vague statements."
        ), # TODO no se como poner esto
    ]
    
    # TODO how to choose between rotor and actions
    
    
# Deterministic State
    
class VoiceOverInfo(TypedDict):
    """
    VoiceOver information from the Daemon State.
    """
    running: bool
    mode: Literal["normal", "rotor"]
    cursor_description: Optional[str]

class DaemonSnapshot(TypedDict):
    """
    Parsed state from the Guidepup Daemon
    """
    version: int
    ready: bool

    page_url: Optional[str]
    page_title: Optional[str]

    accessibility_tree: str
    screenshot_path: str

    voiceover: VoiceOverInfo
    # events: list[dict] TODO

class AgentState(TypedDict):
    """
    Final State passed through each node
    """
    # TODO needs to be reset every once in a while
    messages: Annotated[Sequence[BaseMessage], add_messages]
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
    iteration: int
    goal_reached: bool
    final_summary: str
