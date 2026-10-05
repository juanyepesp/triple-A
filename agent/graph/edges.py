from state.schema import AgentState

def route_after_evaluation(state: AgentState):
    if state["goal_reached"]:
        return "report"
    return "decision"

def route_to_tools(state: AgentState):
    last_message = state["messages"][-1]

    if not last_message.tool_calls:
        return "done"

    return "voiceover_tools"
