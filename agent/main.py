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
        "decision",
        "voiceover_tools",
        "report",
        "stop",
    ]
    labels = [
        f"[ {node} ]" if active_node in node.split(" / ") else f"  {node}  "
        for node in route
    ]
    print("  -> ".join(labels))


def comparable(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


def print_node_event(node_name: str, output: dict, previous_state: dict) -> bool:
    changed_state = {
        key: value
        for key, value in output.items()
        if key not in previous_state or previous_state[key] != comparable(value)
    }
    previous_state.update({key: deepcopy(comparable(value)) for key, value in output.items()})

    if not changed_state:
        return False

    print(f"\n{'=' * 50}")
    print(f"NODE: {node_name}")
    print(f"{'=' * 50}")

    def describe(obj, indent=0):
        prefix = "  " * indent

        if isinstance(obj, dict):
            print(f"{prefix}dict ({len(obj)} keys)")
            for key, value in obj.items():
                print(f"{prefix}├── {key!r}: ", end="")
                if isinstance(value, dict):
                    print()
                    describe(value, indent + 1)
                elif isinstance(value, (list, tuple, set)):
                    print(f"{type(value).__name__} ({len(value)} items)")
                elif isinstance(value, str):
                    print(f"str (len={len(value)})")
                else:
                    print(type(value).__name__)

        elif isinstance(obj, (list, tuple, set)):
            print(f"{type(obj).__name__} ({len(obj)} items)")

        else:
            print(type(obj).__name__)


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
app.get_graph().draw_mermaid_png(output_file_path='graph.png')

# TODO change and or standardize for multiple goals and tests
# end_goal = "On this website, without using visual page search, find the percentage of respondents who said they primarily navigate lengthy web pages using headings. Report the percentage and the other navigation methods listed in that section."
# url = "https://webaim.org/projects/screenreadersurvey10/#finding"

end_goal = "Starting from the TSA homepage, inside the What Can I Bring? section, find the elements a user can bring into a plane inside the carry-on and the checked luggage, reviewing the applicable restrictions for each item, including prohibited items, size and quantity limits."
url = "https://www.tsa.gov/"


initial_state = {
    "messages": [],
    "goal": end_goal,
    "initial_URL": url,
    "snapshot": {},
    "memory": [],
    "last_action": None,
    "action_history": [],
    "transition": None,
    "iteration": 0,
    "goal_reached": False,
    "final_summary": "",
    "impairment": "low_vision",
}

previous_state = {}

for event in app.stream(initial_state, stream_mode="updates"):
    for node_name, output in event.items():
        changed = print_node_event(node_name, output, previous_state)
        if args.step and changed:
            input("\nPress Enter to continue to the next node... ")