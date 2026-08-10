from state.schema import AgentState

def decide_goal_reached(state: AgentState):
    '''Conditional edges for decision, have we reached the goal? '''
    if state['goal_reached'] == 'not_reached':
        return 'decide_actions'
    else:
        return 'report'