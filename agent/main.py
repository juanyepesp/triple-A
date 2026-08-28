import argparse
from graph.build import build_graph
from copy import deepcopy
from pprint import pprint


def render_active_node(active_node: str) -> None:
    """Show the graph route with the node currently being inspected."""
    route = [
        "bootstrap",
        "snapshot",
        "perception",
        "evaluation",
        "normal_decision / rotor_decision",
        "normal_tools / rotor_tools",
        "report",
        "stop",
    ]
    labels = [
        f"[ {node} ]" if active_node in node.split(" / ") else f"  {node}  "
        for node in route
    ]
    print("  -> ".join(labels))


def print_node_event(node_name: str, output: dict, previous_state: dict) -> bool:
    changed_state = {
        key: value
        for key, value in output.items()
        if key not in previous_state or previous_state[key] != value
    }
    previous_state.update({key: deepcopy(value) for key, value in output.items()})

    if not changed_state:
        return False

    print(f"\n{'=' * 50}")
    print(f"NODE: {node_name}")
    print(f"{'=' * 50}")
    render_active_node(node_name)
    pprint(changed_state)
    for message in changed_state.get("messages", []):
        for tool_call in getattr(message, "tool_calls", []):
            print(f"ACTION: {tool_call['name']}({tool_call.get('args', {})})")
    return True


parser = argparse.ArgumentParser(description="Run the accessibility agent.")
parser.add_argument(
    "--step",
    action="store_true",
    help="pause after each changed LangGraph node until Enter is pressed",
)
args = parser.parse_args()

app = build_graph()
# app.get_graph().draw_mermaid_png(output_file_path='graph.png')
end_goal = "On this website, find the table for enrollment trends and describe the tend for English majors (detailed as ENG)."
url = "https://projects.accesscomputing.uw.edu/au/after.html"

initial_state = {
    "messages": [],
    "goal": end_goal,
    "initial_URL": url,
    "snapshot": {},
    "memory": [],
    "iteration": 0,
    "goal_reached": False,
    "action_plan": {},
    "final_summary": "",
}

previous_state = {}

for event in app.stream(initial_state):
    for node_name, output in event.items():
        changed = print_node_event(node_name, output, previous_state)
        if args.step and changed:
            input("\nPress Enter to continue to the next node... ")