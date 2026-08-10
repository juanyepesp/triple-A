from langgraph.graph import StateGraph, START, END
from state.schema import AgentState
from graph.nodes import bootstrap, snapshot, perception, evaluation, decision, action, report, stop

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("node_bootstrap", lambda state: bootstrap(state))
    graph.add_node("node_snapshot", lambda state: snapshot(state))
    graph.add_node("node_perception", lambda state: perception(state))
    graph.add_node("node_evaluation", lambda state: evaluation(state))
    graph.add_node("node_decision", lambda state: decision(state))
    graph.add_node("node_action", lambda state: action(state))
    graph.add_node("node_report", lambda state: report(state))
    graph.add_node("node_stop", lambda state: stop(state))

    graph.add_edge(START, "node_bootstrap")
    graph.add_edge("node_bootstrap", "node_snapshot")
    graph.add_edge("node_snapshot", "node_perception")
    graph.add_edge("node_perception", "node_evaluation")

    graph.add_conditional_edges(
        "node_evaluation",
        lambda state: "decide_actions" if not state["evaluation"]["goal_reached"] else "report",
        {
            "decide_actions": "node_decision",
            "report": "node_report",
        },
    )

    graph.add_edge("node_decision", "node_action")
    graph.add_edge("node_action", "node_snapshot")
    graph.add_edge("node_report", "node_stop")
    graph.add_edge("node_stop", END)

    return graph.compile()