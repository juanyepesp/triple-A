from state.schema import AgentState, Perception, Evaluation
from prompts.load import load_prompt
from tools import actions as guidepup
from tools.voiceover import normal_tools
from tools.rotor import rotor_tools
from tools.image_processing import (apply_impairment, encode_jpeg, image_changed, image_hash, load_screenshot, save_vision_report)
from state.parsers import parse_daemon_snapshot

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode

model = ChatOpenAI(
    model="gpt-4.1-nano",
    temperature=0,
)

perception_model = model.with_structured_output(Perception)
evaluation_model = model.with_structured_output(Evaluation)
normal_tools_model = model.bind_tools(normal_tools) 
rotor_tools_model = model.bind_tools(rotor_tools) 

def bootstrap(state: AgentState)-> AgentState:
    '''This node sets up the browser, the screen reader, makes sure everything works correctly'''

    state['goal_reached'] = False
    state["iteration"] = 0

    try:
        guidepup.browser_start(
            url=state['initial_URL']
        )
        guidepup.voiceover_start()
        guidepup.voiceover_go_to_web_content()

    except Exception as e:
        raise RuntimeError(
            f"Failed to bootstrap browser environment: {e}"
        ) from e

    return state

def snapshot(state: AgentState)-> AgentState:
    '''
    This node takes the snapshot of the current state, 
    TODO determines if rotor is on
    '''
    state['snapshot'] = parse_daemon_snapshot(guidepup.snapshot())
    return state

def vision(state: AgentState)-> AgentState:
    '''
    This node takes in the screenshot, applies the visual filter, and
    sends the picture to an LLM for description.
    '''
    screenshot_path, image = load_screenshot(
        state["snapshot"]["screenshot_path"],
        state.get("screenshot_runtime_dir"),
    )
    current_hash = image_hash(image)
    previous_hash = state.get("vision", {}).get("screenshot_hash")
    impairment = state.get("impairment", "none")

    if not image_changed(image, previous_hash):
        return state

    transformed_image = apply_impairment(image, impairment)
    system_prompt = load_prompt("vision.md")
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
                    "text": f"Impairment simulation: {impairment} \nWebsite URL: {state['snapshot']['page_url']}",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_jpeg(transformed_image),
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
    
    save_vision_report(
        transformed_image,
        description,
        "vision_outputs",
        screenshot_path,
        impairment,
        current_hash,
    )
    
    return state

def perception(state: AgentState)-> AgentState:
    '''
    This node takes in the input of the snapshot and returns a summary of:
    - Where are we?
    - What can we do?
    - What element seems to be focused?
    - What does the page look like?
    '''
    # Input:
    # raw AOM
    # VoiceOver utterances
    # screenshot metadata
    # current goal

    # Output:

    # a human-like description of the current situation
    # what is focused
    # what interactive things exist
    # what navigation paths seem available
    # LLM calls to process image and sr output, to produce
    # left side of brain

    # state['snapshot']['site_description'] = 'We are currently in a website for []'
    # state['snapshot']['focus_element'] = 'We are focused on a button that has these capabilities'
    # state['snapshot']['possibilities'] = 'From here we can go to these headings:[] links:[] or move to these places[] '

    system_prompt = load_prompt("perception.md")

    # user_input = f""" # TODO change this
    #     Current goal:

    #     {state["goal"]}

    #     Current daemon snapshot:

    #     {state["snapshot"]}
        
    #     Current vision description, with visual impairment {state['impairment']}:
        
    #     {state['vision']}
    # """
    
    user_input = f"""
        The ultimate goal to tackle: {state['goal']}
        
        VoiceOver information: {state['snapshot']['voiceover']}
        
        Page title: {state['snapshot']['page_title']}
        Current URL: {state['snapshot']['page_url']}
        
        Page description with {state['impairment']} impairment: {state['vision']}
    """
    

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
    - How many times have I tried to accomplish an action? 
    - How frustrated am I?
    '''
    # llm reads from snapshot and updates memory
    # state['iteration'] += 1
    # state['memory'] = 'We have been trying to achieve this (), and it seems we are in this phase (). '

    # # llm decides if state is reached or not
    # import secrets
    # state['goal_reached'] = secrets.choice(['reached', 'not_reached', 'unreachable'])

    # This is the “am I making progress?” call.

    # Input:

    # state["perception"]
    # task goal
    # prior memory / iterations

    # Output:

    # goal_reached: bool
    # progress_status
    # confidence
    # why

    # This node should not plan actions yet. It should only judge the current situation.

    # LLM calls
    # right brain

    system_prompt = load_prompt("evaluation.md")

    user_input = f"""
    Goal:

    {state["goal"]}

    Current perception:

    {state["perception"]}

    Iteration:

    {state["iteration"]}
    """

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

    state['goal_reached'] = result['goal_reached']
    
    state["evaluation"] = result

    state["iteration"] += 1

    return state

def decision(state: AgentState) -> AgentState:
    system_prompt = load_prompt("decision.md")

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        *state["messages"],
        {
            "role": "user",
            "content": f"""
    Goal:
    {state["goal"]}

    Current perception:
    {state["perception"]}

    Current evaluation:
    {state["evaluation"]}

    Current VoiceOver mode:
    {state["snapshot"]['voiceover']['mode']}
    """,
        },
    ]

    messages.extend(state["messages"])

    response = (
        rotor_tools_model
        if state["snapshot"]['voiceover']['mode'] == "rotor"
        else normal_tools_model
    ).invoke(messages)
    
    print("\n=== DECISION RAW RESPONSE ===")
    print(response)
    print("TOOL CALLS:", response.tool_calls)
    print("CONTENT:", response.content)
    print("INVALID TOOL CALLS:", response.invalid_tool_calls)
    print("FINISH REASON:", response.response_metadata.get("finish_reason"))

    return {
        "messages": [response]
    }

# Tool Nodes
normal_tool_node = ToolNode(normal_tools)
rotor_tool_node = ToolNode(rotor_tools)


def stop(state: AgentState) -> AgentState:
    try:
        guidepup.voiceover_stop()
    finally:
        guidepup.browser_stop()

    return state

def report(state: AgentState) -> AgentState:
    '''This node outputs the final reasoning'''
    # LLM call
    system_prompt = load_prompt("report.md")

    user_input = f"""
    Goal:

    {state["goal"]}

    Final perception:

    {state["perception"]}

    Evaluation:

    {state["evaluation"]}

    Actions taken:

    {state["execution_results"]}
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
