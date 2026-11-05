from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from state.schema import AgentState

from graph.nodes import (
    bootstrap,
    snapshot,
    vision,
    perception,
    evaluation,
    decision,
    voiceover_tool_node,
    report,
    stop,
)

from graph.edges import (
    route_after_evaluation,
    route_to_tools,
)


def build_graph():
    graph = StateGraph(AgentState)
    retry_policy = RetryPolicy(
        initial_interval=0.5,
        backoff_factor=2.0,
        max_interval=4.0,
        max_attempts=3,
        retry_on=Exception,
    )

    # ---------------------------
    # Nodes
    # ---------------------------

    graph.add_node("bootstrap", bootstrap, retry_policy=retry_policy)
    graph.add_node("snapshot", snapshot, retry_policy=retry_policy)
    graph.add_node("vision", vision, retry_policy=retry_policy)
    graph.add_node("perception", perception, retry_policy=retry_policy)
    graph.add_node("evaluation", evaluation, retry_policy=retry_policy)
    graph.add_node("decision", decision, retry_policy=retry_policy)

    graph.add_node(
        "voiceover_tools",
        voiceover_tool_node,
        retry_policy=retry_policy,
    )

    graph.add_node("report", report, retry_policy=retry_policy)
    graph.add_node("stop", stop, retry_policy=retry_policy)

    # ---------------------------
    # Initial flow
    # ---------------------------

    graph.add_edge(START, "bootstrap")
    graph.add_edge("bootstrap", "snapshot")
    graph.add_edge("snapshot", "vision")
    graph.add_edge("vision", "perception")
    graph.add_edge("perception", "evaluation")

    # ---------------------------
    # Evaluation
    # ---------------------------

    graph.add_conditional_edges(
        "evaluation",
        route_after_evaluation,
        {
            "report": "report",
            "decision": "decision",
        },
    )

    # ---------------------------
    # ToolNodes
    # ---------------------------

    graph.add_conditional_edges(
        "decision",
        route_to_tools,
        {
            "voiceover_tools": "voiceover_tools",
            "done": "snapshot",
        },
    )

    graph.add_edge("voiceover_tools", "snapshot")

    # ---------------------------
    # Finish
    # ---------------------------

    graph.add_edge("report", "stop")
    graph.add_edge("stop", END)

    return graph.compile()