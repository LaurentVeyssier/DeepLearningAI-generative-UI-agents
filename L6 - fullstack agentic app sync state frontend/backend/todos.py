from __future__ import annotations

import uuid

from langchain.agents.middleware import AgentState as BaseAgentState
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from typing_extensions import TypedDict


class Todo(TypedDict):
    id: str
    title: str
    completed: bool


class AgentState(BaseAgentState):
    todos: list[Todo]


# -----------------------------------------------------------------------------
# Shared-state backend tools (notebook Phase 1, cell d047814a). The notebook
# defines these directly in its own kernel namespace rather than writing them
# here — this module fills that gap so a standalone script (run_agent.py) has
# a real, importable home for them, following the same pattern used for the
# schema above.
# -----------------------------------------------------------------------------


@tool
def manage_todos(todos: list[Todo], runtime: ToolRuntime) -> Command:
    """Replace the entire todo list. Use this to add, edit, or remove todos."""
    for todo in todos:
        if not todo.get("id"):
            todo["id"] = str(uuid.uuid4())

    # Command allows agents to update state via toolcalls
    return Command(update={
        "todos": todos,
        "messages": [
            ToolMessage(
                content="Successfully updated todos",
                tool_call_id=runtime.tool_call_id,
            )
        ],
    })


@tool
def get_todos(runtime: ToolRuntime):
    """Get the current todo list."""
    return runtime.state.get("todos", [])


todo_tools = [manage_todos, get_todos]
