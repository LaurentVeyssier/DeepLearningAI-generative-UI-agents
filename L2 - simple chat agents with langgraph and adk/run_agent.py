"""Agent Backend Runner for Generative UI (LangGraph/OpenAI or Google ADK/Gemini).

This script launches an AG-UI compatible FastAPI backend server for CopilotKit,
allowing seamless switching between LangGraph (OpenAI) and Google ADK (Gemini).
"""

import logging
import os
from typing import Literal
from dotenv import load_dotenv
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
logger = logging.getLogger("agent_runner")
console = Console()

# -----------------------------------------------------------------------------
# CONFIGURATION
# Set AGENT_TYPE to "langgraph" (OpenAI) or "adk" (Google Gemini)
# -----------------------------------------------------------------------------
AGENT_TYPE: Literal["langgraph", "adk"] = "langgraph"
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def create_langgraph_app(model_name: str = "gpt-5.6-luna") -> FastAPI:
    """Create a FastAPI application hosting a LangGraph AG-UI agent.

    Args:
        model_name: Name of the OpenAI model to use.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    from ag_ui_langgraph import add_langgraph_fastapi_endpoint
    from copilotkit import CopilotKitMiddleware, LangGraphAGUIAgent
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import MemorySaver

    logger.info("Initializing LangChain / LangGraph Agent (model: %s)", model_name)
    graph = create_agent(
        model=ChatOpenAI(model=model_name),
        tools=[],
        middleware=[CopilotKitMiddleware()],
        checkpointer=MemorySaver(),
        system_prompt="You are a helpful assistant",
    )

    app = FastAPI(title="LangGraph AG-UI Agent API")
    agent = LangGraphAGUIAgent(
        name="langgraph_agent", description="LangGraph Agent", graph=graph
    )
    add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
    return app


def create_adk_app(model_name: str = "gemini-3.5-flash-lite") -> FastAPI:
    """Create a FastAPI application hosting a Google ADK AG-UI agent.

    Args:
        model_name: Name of the Gemini model to use.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
    from google.adk.agents import LlmAgent

    logger.info("Initializing Google ADK Agent (model: %s)", model_name)
    gemini_agent = LlmAgent(
        name="assistant",
        model=model_name,
        instruction="Be helpful and fun!",
    )

    adk_agent = ADKAgent(
        adk_agent=gemini_agent,
        app_name="demo_app",
        user_id="demo_user",
        session_timeout_seconds=3600,
        use_in_memory_services=True,
    )

    app = FastAPI(title="Google ADK AG-UI Agent API")
    add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
    return app


def main() -> None:
    """Main entrypoint to load environment variables and launch the FastAPI server."""
    load_dotenv()

    # Allow overriding via environment variable AGENT_TYPE or fallback to constant
    selected_agent = os.getenv("AGENT_TYPE", AGENT_TYPE).lower()

    port = int(os.getenv("PORT", "8002"))

    if selected_agent == "adk":
        model = os.getenv("MODEL_NAME", GEMINI_MODEL)
        console.print(
            f"[bold green]🚀 Launching Google ADK Agent Server on port {port} (Model: {model})...[/bold green]"
        )
        app = create_adk_app(model_name=model)
    else:
        model = os.getenv("MODEL_NAME", OPENAI_MODEL)
        console.print(
            f"[bold cyan]🚀 Launching LangGraph Agent Server on port {port} (Model: {model})...[/bold cyan]"
        )
        app = create_langgraph_app(model_name=model)

    console.print(f"📖 Swagger Docs available at: [link=http://localhost:{port}/docs]http://localhost:{port}/docs[/link]")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
