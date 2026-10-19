import argparse
import atexit
import signal
from graph.build import build_graph
from copy import deepcopy
from pprint import pprint
from tools import actions


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

# TODO change and or standardize for multiple goals and tests
# end_goal = "On this website, without using visual page search, find the percentage of respondents who said they primarily navigate lengthy web pages using headings. Report the percentage and the other navigation methods listed in that section."
# url = "https://webaim.org/projects/screenreadersurvey10/#finding"

end_goal = "Starting from the TSA homepage, inside the What Can I Bring? section, find the elements a user can bring into a plane inside the carry-on and the checked luggage, reviewing the applicable restrictions for each item, including prohibited items, size and quantity limits."
url = "https://www.tsa.gov/"
impairment = "low_vision"

recording_owned = False
cleaned_up = False


def cleanup() -> None:
    global cleaned_up
    if cleaned_up:
        return
    cleaned_up = True

    if recording_owned:
        for action in (actions.voiceover_stop, actions.browser_stop):
            try:
                action()
            except Exception as error:
                print(f"Cleanup warning: {error}", flush=True)
        try:
            result = actions.recording_stop()
            print(
                f"Recording saved to {result['recording']['path']}",
                flush=True,
            )
        except Exception as error:
            print(f"Cleanup warning: {error}", flush=True)


def handle_termination(signum, _frame) -> None:
    signal_name = signal.Signals(signum).name
    print(f"\nReceived {signal_name}; finalizing recording...", flush=True)
    raise KeyboardInterrupt


def start_recording() -> None:
    global recording_owned
    status = actions.recording_status()
    if status.get("recording", {}).get("active"):
        print(
            "Using the existing interaction recording; the agent will not stop it.",
            flush=True,
        )
        return
    recording = actions.recording_start(url, impairment)
    recording_owned = True
    print(
        f"Recording agent interactions to {recording['recording']['path']}",
        flush=True,
    )


signal.signal(signal.SIGINT, handle_termination)
signal.signal(signal.SIGTERM, handle_termination)
atexit.register(cleanup)

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
    "impairment": impairment,
}

previous_state = {}

try:
    start_recording()
    app = build_graph()
    app.get_graph().draw_mermaid_png(output_file_path="graph.png")

    for event in app.stream(initial_state, stream_mode="updates"):
        for node_name, output in event.items():
            changed = print_node_event(node_name, output, previous_state)
            if args.step and changed:
                input("\nPress Enter to continue to the next node... ")
except KeyboardInterrupt:
    print("Agent stopped.", flush=True)
finally:
    cleanup()