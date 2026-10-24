from state.schema import AgentState, Perception, Evaluation, ActionRecord, TransitionSummary
from prompts.load import load_component_prompt
from tools import actions as guidecore
from tools.voiceover import voiceover_tools
from tools.image_processing import (
    VISION_REPORTS_DIR,
    encode_jpeg,
    image_changed,
    image_hash,
    load_screenshot,
    save_vision_report,
)
from state.parsers import (
    bullets,
    format_action_history,
    format_perception,
    format_perception_evidence,
    format_transition,
    parse_daemon_snapshot,
)

from langchain_openai import ChatOpenAI
from langchain_core.exceptions import OutputParserException
from langgraph.prebuilt import ToolNode
from pydantic import ValidationError

model = ChatOpenAI(
    model="gpt-6-luna",
    reasoning_effort="none",
    streaming=True,
    stream_usage=True,
)

perception_model = model.with_structured_output(
    Perception,
    method="function_calling",
).with_retry(
    retry_if_exception_type=(ValidationError, OutputParserException),
    stop_after_attempt=3,
    wait_exponential_jitter=False,
)
evaluation_model = model.with_structured_output(
    Evaluation,
    method="function_calling",
).with_retry(
    retry_if_exception_type=(ValidationError, OutputParserException),
    stop_after_attempt=3,
    wait_exponential_jitter=False,
)
voiceover_tools_model = model.bind_tools(voiceover_tools)

def bootstrap(state: AgentState)-> AgentState:
    '''This node sets up the browser, the screen reader, makes sure everything works correctly'''
    state['goal_reached'] = False
    state["iteration"] = 0

    try:
        guidecore.browser_start(
            url=state['initial_URL'],
            impairment=state.get("impairment", "none"),
        )
        guidecore.voiceover_start()
        guidecore.voiceover_go_to_web_content()

    except Exception as e:
        raise RuntimeError(
            f"Failed to bootstrap browser environment: {e}"
        ) from e

    return state

def snapshot(state: AgentState)-> AgentState:
    '''
    This node takes the snapshot of the current state.
    '''
    previous = state.get("snapshot")
    current = parse_daemon_snapshot(guidecore.snapshot())
    if state.get("last_action") and state.get("messages"):
        latest_message = state["messages"][-1]
        if latest_message.type == "tool":
            action = {
                **state["last_action"],
                "result": str(latest_message.content),
            }
            state["last_action"] = action
            history = state.get("action_history", [])
            state["action_history"] = [*history[:-1], action] if history else [action]
    state["snapshot"] = current
    state["transition"] = build_transition(previous, current, state.get("last_action"))
    return state


def build_transition(
    previous: dict | None,
    current: dict,
    last_action: ActionRecord | None,
) -> TransitionSummary:
    previous_context = (previous or {}).get("context", {})
    current_context = current["context"]
    previous_focus = previous_context.get("voiceoverFocus", {})
    current_focus = current_context.get("voiceoverFocus", {})
    previous_path = previous_context.get("cursorPath", [])
    current_path = current_context.get("cursorPath", [])
    previous_active = (previous_context.get("relevantNodes", {}).get("active") or [])
    current_active = (current_context.get("relevantNodes", {}).get("active") or [])
    previous_role = previous_active[0].get("role") if previous_active else None
    current_role = current_active[0].get("role") if current_active else None
    previous_phrase = previous_focus.get("lastSpokenPhrase")
    current_phrase = current_focus.get("lastSpokenPhrase")

    return {
        "action": last_action["name"] if last_action else None,
        "previous_phrase": previous_phrase,
        "current_phrase": current_phrase,
        "previous_role": previous_role,
        "current_role": current_role,
        "previous_cursor_path": previous_path,
        "current_cursor_path": current_path,
        "state_changed": (
            previous is not None
            and (
                previous_phrase != current_phrase
                or previous_role != current_role
                or previous_path != current_path
            )
        ),
    }

def vision(state: AgentState)-> AgentState:
    '''
    This node sends the Guidecore-provided screenshot to an LLM for description.
    '''
    screenshot_path, image = load_screenshot(
        state["snapshot"]["context"]["page"]["screenshotPath"],
        state.get("screenshot_runtime_dir"),
    )
    current_hash = image_hash(image)
    previous_hash = state.get("vision", {}).get("screenshot_hash")
    impairment = state.get("impairment", "none")

    if not image_changed(image, previous_hash):
        return state

    system_prompt = load_component_prompt("vision")
    response = model.invoke([
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Impairment simulation: {impairment} \n"
                        f"Website URL: {state['snapshot']['context']['page']['url']}"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_jpeg(image),
                        "detail": "low"},
                },
            ],
        },
    ])
    
    description = response.content
    
    state["vision"] =  {
        "path": str(screenshot_path),
        "screenshot_hash": current_hash,
        "description": description,
    }
    
    report_path = save_vision_report(
        image,
        description,
        VISION_REPORTS_DIR,
        screenshot_path,
        impairment,
        current_hash,
    )
    state["vision"]["report_path"] = str(report_path)
    
    return state

def perception(state: AgentState)-> AgentState:
    '''
    This node takes in the input of the snapshot and returns a summary of:
    - Where are we?
    - What can we do?
    - What element seems to be focused?
    - What does the page look like?
    '''
    system_prompt = load_component_prompt("perception")
    
    user_input = format_perception_evidence(state)
    

    result = perception_model.invoke([
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_input,
        },
    ])

    state["perception"] = result

    return state


def evaluation(state: AgentState)-> AgentState:
    '''
    This node evaluates
    - Is the goal reached?
    - Is the agent making progress, or looping?
    '''
    system_prompt = load_component_prompt("evaluation")

    user_input = f"""
# GOAL
{state["goal"]}

# STEP
Iteration {state["iteration"]}

# WHAT JUST HAPPENED
{format_transition(state.get("transition"))}

# RECENT ACTIONS
{format_action_history(state.get("action_history", []))}

# PERCEPTION (interpretation of the current snapshot)
{format_perception(state["perception"])}

# CURRENT EVIDENCE (raw, authoritative)
{format_perception_evidence(state)}
""".strip()

    result = evaluation_model.invoke([
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_input,
        },
    ])

    state['goal_reached'] = result.goal_reached

    state["evaluation"] = result

    state["iteration"] += 1

    return state

def decision(state: AgentState) -> AgentState:
    system_prompt = load_component_prompt("decision")

    evaluation_result = state["evaluation"]
    user_input = f"""
# GOAL
{state["goal"]}

# WHAT JUST HAPPENED
{format_transition(state.get("transition"))}

# RECENT ACTIONS
{format_action_history(state.get("action_history", []))}

# EVALUATION (progress so far)
Progress: {evaluation_result.progress_status} (confidence: {evaluation_result.confidence})
Blocked: {evaluation_result.blocked}
Evidence:
{bullets(evaluation_result.evidence)}

# PERCEPTION (interpretation of the current snapshot)
{format_perception(state["perception"])}

# CURRENT EVIDENCE (raw, authoritative)
{format_perception_evidence(state)}
""".strip()

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        *state["messages"],
        {
            "role": "user",
            "content": user_input,
        },
    ]

    response = voiceover_tools_model.invoke(messages)
    
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        action = {
            "name": tool_call["name"],
            "arguments": tool_call.get("args", {}),
            "result": None,
        }
        return {
            "messages": [response],
            "last_action": action,
            "action_history": [*state.get("action_history", []), action],
        }

    return {
        "messages": [response]
    }

# Tool Nodes
voiceover_tool_node = ToolNode(voiceover_tools)


def stop(state: AgentState) -> AgentState:
    try:
        guidecore.voiceover_stop()
    finally:
        guidecore.browser_stop()

    return state

def report(state: AgentState) -> AgentState:
    '''This node outputs the final reasoning'''
    # LLM call
    system_prompt = load_component_prompt("report")

    user_input = f"""
Goal:

{state["goal"]}

Final perception:

{state["perception"]}

Evaluation:

{state["evaluation"].model_dump_json(indent=2)}

Actions taken:

{state.get("action_history", [])}
    """

    result = model.invoke([
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_input,
        },
    ])

    state["final_summary"] = result.content

    return state
