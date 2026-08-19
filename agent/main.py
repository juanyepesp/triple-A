from graph.build import build_graph
from pprint import pprint

app = build_graph()
end_goal = "On this website, find the table for enrollment trends and describe it."
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
    "execution_results": []
}

for event in app.stream(initial_state):
    for node_name, output in event.items():
        print(f"\n{'=' * 50}")
        print(f"NODE: {node_name}")
        print(f"{'=' * 50}")
        pprint(output)