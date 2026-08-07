from graph.build import build_graph
# TODO this is an example of what the main file would look like
# backend = TODO
app = build_graph()

result = app.invoke({
    "messages": [],
    "goal": "Find the privacy policy",
    "snapshot": {},
    "memory": [],
    "iteration": 0,
    "goal_reached": False,
    "action_plan": {},
    "final_summary": "",
})