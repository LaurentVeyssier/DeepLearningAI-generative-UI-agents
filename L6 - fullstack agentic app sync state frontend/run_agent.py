"""L6 Agent Backend Runner for the Fullstack Shared-State Todo App.

This script launches an AG-UI compatible FastAPI backend for CopilotKit,
replicating the notebook's final agent (Phase 1 + Phase 2 backend state: a
typed `AgentState` carrying `todos`, plus `manage_todos`/`get_todos` tools
that read and write that state via `Command(update={...})`).

Unlike L3-L5, this lesson uses a single agent **framework** — LangGraph —
throughout. What's configurable here is the underlying **chat model**:
MODEL_PROVIDER selects "openai" (ChatOpenAI) or "gemini" (ChatGoogleGenerativeAI),
both running through the exact same LangGraph graph, tools, and state schema.
There is no Google ADK path in this lesson's script — CopilotKitMiddleware's
shared-state sync and `Command(update={...})` are LangGraph-native mechanisms;
porting them to ADK would need the same kind of `AGUIToolset()`/state-bridging
work documented in the L4/L5 READMEs, which is out of scope here.

The frontend's two runtime-injected tools (`openOrCloseTodos`, a
`useFrontendTool` registered in App.tsx) and shared state (`useAgent()` /
`agent.setState()`) are wired up entirely in frontend/src/App.tsx — already
written by the notebook's own `%%writefile` cell, so no frontend code changes
were needed there. See the README for the two frontend fixes that *were*
needed (Windows `npm run dev`, and pinning the Vite port) — the same pattern
already applied in L4 and L5.
"""

import logging
import os
import textwrap
from typing import Literal

from dotenv import load_dotenv

# Load .env as early as possible — before any module-level os.getenv() calls
# below — so OPENAI_MODEL/GEMINI_MODEL/MODEL_PROVIDER from the repo-root .env
# actually take effect (L4/L5's run_agent.py called load_dotenv() only inside
# main(), after these constants were already resolved from the process env,
# so a .env-only value was silently ignored unless the shell already had it
# exported — fixed here by loading up front instead).
load_dotenv(override=True)

import uvicorn
from fastapi import FastAPI
from rich.console import Console
from rich.logging import RichHandler

# Setup structured logging with rich
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logging.getLogger("langgraph.checkpoint").setLevel(logging.ERROR)
logger = logging.getLogger("l6_agent_runner")
console = Console()

# -----------------------------------------------------------------------------
# CONFIGURATION
# Framework is always LangGraph. MODEL_PROVIDER picks the underlying chat
# model: "openai" (ChatOpenAI) or "gemini" (ChatGoogleGenerativeAI).
# -----------------------------------------------------------------------------
MODEL_PROVIDER: Literal["openai", "gemini"] = "openai"

# Deliberately NOT `os.getenv("OPENAI_MODEL", "gpt-5.4-mini")` — the repo-root
# .env's OPENAI_MODEL (gpt-5.6-luna) is tuned for other lessons and doesn't
# support tool calling on /v1/chat/completions (see README Gotchas). L6's
# whole point is tool calling (manage_todos/get_todos), so this lesson
# always needs a model that supports it, regardless of what .env says.
# Override with MODEL_NAME if you want to try a different OpenAI model.
OPENAI_MODEL: str = "gpt-5.4-mini"
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# -----------------------------------------------------------------------------
# Shared system instruction — identical to the notebook's Phase 2 prompt
# (cell 58027760). Mentions `openOrCloseTodos` even though that tool is
# registered entirely on the frontend (App.tsx's useFrontendTool) — the model
# just needs to know it exists and when to call it.
# -----------------------------------------------------------------------------
SYSTEM_PROMPT: str = textwrap.dedent("""
    You manage a shared todo list.
    Use manage_todos to add, edit, or remove todos.
    Use get_todos to check the current list.
    When asked to manage todos, call the openOrCloseTodos frontend tool with open=true first.
    Keep responses to 1-2 sentences.
""").strip()


def _build_model(provider: str, model_name: str):
    """Construct the LangChain chat model for the given provider."""
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        logger.info("Using Gemini chat model via LangGraph (model: %s)", model_name)
        return ChatGoogleGenerativeAI(model=model_name, temperature=0)

    from langchain_openai import ChatOpenAI

    logger.info("Using OpenAI chat model via LangGraph (model: %s)", model_name)
    return ChatOpenAI(model=model_name, temperature=0)


def create_app(provider: str = "openai", model_name: str | None = None) -> FastAPI:
    """Create a FastAPI application hosting the L6 LangGraph shared-state agent.

    Args:
        provider: "openai" or "gemini" — selects the underlying chat model.
        model_name: Overrides the provider's default model name.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    from ag_ui_langgraph import add_langgraph_fastapi_endpoint
    from copilotkit import CopilotKitMiddleware, LangGraphAGUIAgent
    from langchain.agents import create_agent
    from langgraph.checkpoint.memory import MemorySaver

    from backend.todos import AgentState, todo_tools

    resolved_model_name = model_name or (GEMINI_MODEL if provider == "gemini" else OPENAI_MODEL)
    model = _build_model(provider, resolved_model_name)

    logger.info("Initializing LangGraph shared-state todo agent for L6")
    graph = create_agent(
        model=model,
        state_schema=AgentState,
        tools=todo_tools,
        middleware=[CopilotKitMiddleware()],
        checkpointer=MemorySaver(),
        system_prompt=SYSTEM_PROMPT,
    )

    app = FastAPI(title="L6 LangGraph Shared-State Todo Agent API")
    agent = LangGraphAGUIAgent(
        name="default",  # must match frontend/server.ts's `agents: { default: ... }`
        description="Lesson 6 shared-state todo agent",
        graph=graph,
    )
    add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
    return app


def main() -> None:
    """Main entrypoint to load environment variables and launch the FastAPI server."""
    provider = os.getenv("MODEL_PROVIDER", MODEL_PROVIDER).lower()
    port = int(os.getenv("PORT", "8006"))
    model_name = os.getenv("MODEL_NAME") or (GEMINI_MODEL if provider == "gemini" else OPENAI_MODEL)

    color = "bold green" if provider == "gemini" else "bold cyan"
    console.print(
        f"[{color}]🚀 Launching L6 LangGraph Shared-State Todo Agent Server on port {port} "
        f"(provider: {provider}, model: {model_name})...[/{color}]"
    )

    app = create_app(provider=provider, model_name=model_name)

    console.print(
        f"📖 Swagger Docs available at: [link=http://localhost:{port}/docs]http://localhost:{port}/docs[/link]"
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
