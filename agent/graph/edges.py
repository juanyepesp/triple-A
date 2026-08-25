from state.schema import AgentState

def decide_goal_reached(state: AgentState):
    '''Conditional edges for decision, have we reached the goal? '''
    if state['goal_reached'] == 'not_reached':
        return 'decide_actions'
    else:
        return 'report'

def route_after_decision(state: AgentState):

    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"

    return "done"


def route_mode(state: AgentState):

    mode = state['snapshot'].voiceover.mode

    if mode == "rotor":
        return "rotor"

    return "normal"

def route_after_normal_decision(state: AgentState):

    last = state["messages"][-1]

    if getattr(last, "tool_calls", None):
        return "normal_tools"

    return "done"

def route_after_rotor_decision(state: AgentState):

    last = state["messages"][-1]

    if getattr(last, "tool_calls", None):
        return "rotor_tools"

    return "done"

def route_after_evaluation(state: AgentState):

    if state["evaluation"]["goal_reached"]:
        return "report"

    mode = state['snapshot'].voiceover.mode

    if mode == "rotor":
        return "rotor"

    return "normal"