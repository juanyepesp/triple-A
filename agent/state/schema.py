from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    goal: str
    snapshot: dict
    memory: list[str]
    iteration: int
    goal_reached: bool
    action_plan: dict
    final_summary: str