
from typing import TypedDict, List, Optional, Literal, Annotated, Sequence
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.message import add_messages
from langchain_core.tools import tool

# ? this is a file where i test the graph structure, that it builds correctly

# -----------------------------------------------------------
# GLOBAL VARIABLES
# -----------------------------------------------------------

guidepup_client = None


# -----------------------------------------------------------
# MISC
# -----------------------------------------------------------

# TODO sin usar el RPC server, asumiendo todos los inputs:
# crear el flow del agente, con mas o menos como se iria viendo cada cosa, que "entienda" donde esta, que tiene que hacer y como llegar ahi, simular todo el flow
# tal vez tengo que crear las imagenes yo mismo


# en el estado, tengo que tener una lista de todo lo que ha "dicho" el agente junto con los mensajes de prompt y tal vez human in the loop si los pongo

# annotated:
# email = Annotated[str, "this has to be a valid email format"]

# sequence
# adding new messages to a chat history



# -----------------------------------------------------------
# MODEL, STATE
# -----------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    daemonstate_snapshot: str # TODO volver esto un objeto que devuelve el rcp

model = ChatOpenAI(
    model="gpt-4.1-nano",
    temperature=0)


# -----------------------------------------------------------
# TOOLS
# -----------------------------------------------------------

@tool
def daemon_state_snapshot():
    # TODO descriptions
    """
    Gives a full snapshot of the current state of the system. 
    Including, the voiceover, browser, and last screenshot path.
    """
    return 'yes!'

# TODO all of the voiceover commands and things, with verbose descriptions
# i think these should have shortcuts too, like voiceover list of all hyperlinks and voiceover list of actions and all that 

@tool
def voiceover_perform():
    return


# -----------------------------------------------------------
# NODES
# -----------------------------------------------------------

def init(state: AgentState)-> AgentState:
    """This node parses the task and impairment profile"""
    # This is where we first add those human and system messages in the list for the agent to understand where it is located, what it needs to do, and give them the starting tips for like knowing all the links and what to do and where to go

    # Task: The user defines what the task is and the visual impairment the agent has, so that it has some context.

    # state['goal'] = "" # TODO
    # state['goal_reached'] = 'not_reached'
    return state

def bootstrap(state: AgentState)-> AgentState:
    '''This node sets up the browser, the screen reader, makes sure everything works correctly'''
    # # logic for starting them: RCP server calls
    # state['sr_status'] = True
    # state['browser_status'] = True
    # # if any of them fail, state should be false and raise error
    # state['utterances'] = []
    # state['snapshot'] = {}
    # state['iteration'] = 0
    
    global guidepup_client 
    guidepup_client = GuidepupClient()
    guidepup_client.call(
        "browser.start",
        {
            'url': 'https://projects.accesscomputing.uw.edu/au/after.html'
        }
    )
    guidepup_client.call("voiceover.start")

    return state

def snapshot(state: AgentState)-> AgentState:
    '''This node takes the snapshot of the current state.'''
    # Snapshot: Fetch current browser state with visual impairment filter, fetch screen reader utterances
    # logic for getting the snapshot
    res = guidepup_client.call("daemonstate.snapshot") # TODO convert this object into something the state can read

    return state

def perception(state: AgentState)-> AgentState:
    '''
    This node takes in the input of the snapshot and returns a summary of:
    - Where are we?
    - What can we do?
    - What element seems to be focused?
    - What does the page look like?
    '''
    # LLM calls to process image and sr output, to produce
    # left side of brain

    # state['snapshot']['site_description'] = 'We are currently in a website for []'
    # state['snapshot']['focus_element'] = 'We are focused on a button that has these capabilities'
    # state['snapshot']['possibilities'] = 'From here we can go to these headings:[] links:[] or move to these places[] '
    
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

    # LLM calls
    # right brain
    
    return state

def decide_goal_reached(state: AgentState):
    '''Conditional edges for decision, have we reached the goal? '''
    if state['goal_reached'] == 'not_reached':
        return 'decide_actions'
    else:
        return 'report'

def decision(state: AgentState)-> AgentState:
    '''This node decides the set of actions to take. 
    - Out of all the possible actions of screen reader, which are relevant in this scenario?. 
    - Do we need more context? 
    Output a structured next step or short action plan.
    '''
    # state['action_plan'] = 'Here are the set of actions to execute. We can use these []. Since we need more context, we can do these [].'

    # LLM calls
    # right brain 

    return state

def action(state: AgentState) -> AgentState:
    '''This node executes the set of actions planned earlier'''
    # tool calling and checking if everything was executed correctly
    # TODO should be ToolNode?
    return state

def stop(state: AgentState) -> AgentState:
    '''This node stops the browser and screen reader'''
    # RCP calls
    guidepup_client.call("voiceover.stop")
    guidepup_client.call("browser.stop")
    return state

def report(state: AgentState) -> AgentState:
    '''This node outputs the final reasoning'''
    # LLM call
    state['final_summary'] = 'These are the set of steps we took ...'
    return state



# -----------------------------------------------------------
# GRAPH COMPILATION
# -----------------------------------------------------------

graph = StateGraph(AgentState)

graph.add_node('node_init', init)
graph.add_node('node_bootstrap', bootstrap)
graph.add_node('node_snapshot', snapshot)
graph.add_node('node_perception', perception)
graph.add_node('node_evaluation', evaluation)
graph.add_node('node_decision', decision)
graph.add_node('node_report', report)
graph.add_node('node_stop', stop)
graph.add_node('node_action', action)

graph.add_edge(START, 'node_init')
graph.add_edge('node_init', 'node_bootstrap')
graph.add_edge('node_bootstrap', 'node_snapshot')
graph.add_edge('node_snapshot', 'node_perception')
graph.add_edge('node_perception', 'node_evaluation')
graph.add_conditional_edges(
    source='node_evaluation',
    path=decide_goal_reached,
    path_map={
        'decide_actions': 'node_decision',
        'report': 'node_report'
    }
)
graph.add_edge('node_decision', 'node_action')
graph.add_edge('node_action', 'node_snapshot')
graph.add_edge('node_report', 'node_stop')
graph.add_edge('node_stop', END)

app = graph.compile()

# See graph
# from io import BytesIO
# from PIL import Image

# png_bytes = app.get_graph().draw_mermaid_png()

# img = Image.open(BytesIO(png_bytes))
# img.save("output.png")

