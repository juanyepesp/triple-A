from state.schema import AgentState
from tools import actions as guidepup
from prompts.load import load_prompt
from tools import actions

from langchain_openai import ChatOpenAI
from state.schema import Perception, Evaluation, ActionPlan

model = ChatOpenAI(
    model="gpt-4.1-nano",
    temperature=0,
)

perception_model = model.with_structured_output(Perception)
evaluation_model = model.with_structured_output(Evaluation)
decision_model = model.with_structured_output(ActionPlan)


def bootstrap(state: AgentState)-> AgentState:
    '''This node sets up the browser, the screen reader, makes sure everything works correctly'''

    state['goal_reached'] = 'not_reached'
    state["iteration"] = 0
    state["messages"] = []

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
    '''This node takes the snapshot of the current state.'''
    state['snapshot'] = guidepup.snapshot() 
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

    user_input = f"""
    Current goal:

    {state["goal"]}

    Current daemon snapshot:

    {state["snapshot"]}
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

    Previous execution results:

    {state["execution_results"]}

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

    state["evaluation"] = result

    state["iteration"] += 1

    return state
    

def decision(state: AgentState)-> AgentState:
    '''This node decides the set of actions to take. 
    - Out of all the possible actions of screen reader, which are relevant in this scenario?. 
    - Do we need more context? 
    Output a structured next step or short action plan.
    '''
    # state['action_plan'] = 'Here are the set of actions to execute. We can use these []. Since we need more context, we can do these [].'

    # LLM calls
    # right brain

    system_prompt = load_prompt("decision.md")

    user_input = f"""
    Goal:

    {state["goal"]}

    Current perception:

    {state["perception"]}

    Current evaluation:

    {state["evaluation"]}

    Previous execution results:

    {state["execution_results"]}
    """

    result = decision_model.invoke([
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_input,
        },
    ])

    state["action_plan"] = result

    return state


def action(state: AgentState) -> AgentState:
    '''This node executes the set of actions planned earlier'''
    results = []

    for planned_action in state["action_plan"]["actions"]:

        result = actions.execute(planned_action)

        results.append({
            "action": planned_action,
            "result": result,
        })

    state["execution_results"] = results

    return state

def stop(state: AgentState) -> AgentState:

    try:
        actions.voiceover_stop()
    finally:
        actions.browser_stop()

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

