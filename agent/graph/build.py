from langgraph.graph import StateGraph, START, END

from state.schema import AgentState

from graph.nodes import (
    bootstrap,
    snapshot,
    vision,
    perception,
    evaluation,
    normal_decision,
    rotor_decision,
    normal_tool_node,
    rotor_tool_node,
    report,
    stop,
)

from graph.edges import (
    route_after_evaluation,
    route_mode,
    route_after_decision,
)


def build_graph():
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("bootstrap", bootstrap)
    graph.add_node("snapshot", snapshot)
    graph.add_node("vision", vision)
    graph.add_node("perception", perception)
    graph.add_node("evaluation", evaluation)

    graph.add_node("normal_decision", normal_decision)
    graph.add_node("rotor_decision", rotor_decision)

    graph.add_node("normal_tools", normal_tool_node)
    graph.add_node("rotor_tools", rotor_tool_node)

    graph.add_node("report", report)
    graph.add_node("stop", stop)

    # Startup
    graph.add_edge(START, "bootstrap")
    graph.add_edge("bootstrap", "snapshot")
    graph.add_edge("snapshot", "vision")
    graph.add_edge("vision", "perception")
    graph.add_edge("perception", "evaluation")

    # Decide what to do next
    graph.add_conditional_edges(
        "evaluation",
        route_after_evaluation,
        {
            "report": "report",
            "normal": "normal_decision",
            "rotor": "rotor_decision",
        },
    )

    # Normal mode
    graph.add_conditional_edges(
        "normal_decision",
        route_after_decision,
        {
            "tools": "normal_tools",
            "done": "snapshot",
        },
    )

    graph.add_edge("normal_tools", "snapshot")

    # Rotor mode
    graph.add_conditional_edges(
        "rotor_decision",
        route_after_decision,
        {
            "tools": "rotor_tools",
            "done": "snapshot",
        },
    )

    graph.add_edge("rotor_tools", "snapshot")

    # Finish
    graph.add_edge("report", "stop")
    graph.add_edge("stop", END)

    return graph.compile()