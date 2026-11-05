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

import uuid

from langchain_openai import ChatOpenAI
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

model = ChatOpenAI(
    model="gpt-6-luna",
    reasoning_effort="none",
    streaming=True,
    stream_usage=True,
)

perception_model = model.with_structured_output(Perception, method="function_calling")
evaluation_model = model.with_structured_output(Evaluation, method="function_calling")
voiceover_tools_model = model.bind_tools(voiceover_tools)

FORMAT_ERRORS = (ValidationError, OutputParserException, ValueError, KeyError, TypeError)
MAX_FORMAT_ATTEMPTS = 3


def invoke_with_retry(runnable, messages: list, *, expect_tool_or_text: bool = False):
    """Call an LLM; if the reply has the wrong format, ask again with a changed request.

    Each retry (1) tells the model what was wrong with its previous reply, and (2) puts a unique
    marker at the very start of the system prompt. Provider prompt caching matches on the prefix of
    the request, so the changed first line forces a fresh, uncached request instead of replaying the
    same one.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_FORMAT_ATTEMPTS + 1):
        request = list(messages)
        if attempt > 1:
            request[0] = {
                **request[0],
                "content": f"[retry {attempt} · request {uuid.uuid4().hex[:12]}]\n{request[0]['content']}",
            }
            request.append({
                "role": "user",
                "content": (
                    "Your previous reply could not be used because its format was invalid: "
                    f"{str(last_error)[:600]}\nReply again with exactly the required format."
                ),
            })
        try:
            result = runnable.invoke(request)
            invalid = getattr(result, "invalid_tool_calls", None)
            if expect_tool_or_text and invalid and not getattr(result, "tool_calls", None):
                raise ValueError(f"malformed tool call: {invalid[0].get('error') or invalid[0]}")
            if result is None:
                raise ValueError("empty reply")
            return result
        except FORMAT_ERRORS as error:
            last_error = error
    raise last_error


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
    state["snapshot"] = current
    last = state.get("last_action")
    if last:
        batch = [a["name"] for a in state.get("action_history", []) if a.get("decision") == last.get("decision")]
        last = {**last, "name": " -> ".join(batch) or last["name"]}
    state["transition"] = build_transition(previous, current, last)
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
    response = invoke_with_retry(model, [
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
    

    result = invoke_with_retry(perception_model, [
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

    result = invoke_with_retry(evaluation_model, [
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

    response = invoke_with_retry(voiceover_tools_model, messages, expect_tool_or_text=True)
    
    return {"messages": [response]}

# Tool Nodes
MAX_ACTIONS_PER_DECISION = 4  # VoiceOver's item text log keeps the last 5 phrases, so 4 stay readable
# Actions that change what is focused or what the page is doing: nothing may follow them unseen.
STATE_CHANGING = {
    "voiceover_act",
    "voiceover_type",
    "voiceover_escape",
    "voiceover_go_to_web_content",
    "voiceover_start_interacting",
    "voiceover_stop_interacting",
}
TOOLS_BY_NAME = {t.name: t for t in voiceover_tools}


def voiceover_tool_node(state: AgentState, config: RunnableConfig) -> dict:
    """Run the decision's tool calls one after another, in the order given (never in parallel).

    Stops early after a state-changing action, after a failure, or at the per-decision limit; calls
    that were not run still get a ToolMessage saying so (the API requires one per tool call).
    """
    calls = state["messages"][-1].tool_calls
    history = list(state.get("action_history", []))
    decision_id = state["iteration"]
    messages: list[ToolMessage] = []
    last_action = state.get("last_action")
    skip_reason = None
    executed = 0

    for call in calls:
        if skip_reason is None and executed >= MAX_ACTIONS_PER_DECISION:
            skip_reason = f"at most {MAX_ACTIONS_PER_DECISION} actions run per decision"
        if skip_reason:
            messages.append(ToolMessage(f"Not executed: {skip_reason}.", tool_call_id=call["id"], name=call["name"]))
            continue

        action = {"name": call["name"], "arguments": call.get("args", {}), "result": None, "decision": decision_id}
        try:
            result = str(TOOLS_BY_NAME[call["name"]].invoke(call.get("args", {}), config))
        except Exception as error:
            if executed == 0:
                raise  # nothing ran yet: let the node's retry policy handle it
            result = f"Error: {error!r}"
            skip_reason = f"the previous action '{call['name']}' failed"
        action["result"] = result
        history.append(action)
        last_action = action
        executed += 1
        messages.append(ToolMessage(result, tool_call_id=call["id"], name=call["name"]))
        if skip_reason is None and call["name"] in STATE_CHANGING:
            skip_reason = f"'{call['name']}' changes the page state and must be observed before acting again"

    return {"messages": messages, "last_action": last_action, "action_history": history}




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

    result = invoke_with_retry(model, [
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
