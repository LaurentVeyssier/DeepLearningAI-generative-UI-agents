"""L3 Agent Backend Runner for Controlled Generative UI.

This script launches an AG-UI compatible FastAPI backend server for CopilotKit,
supporting both LangGraph (OpenAI) and Google ADK (Gemini).
It includes backend tools (such as querying db.csv) and system instructions
that guide the agent to use frontend components registered via useComponent().
"""

import csv
import logging
import os
from pathlib import Path
from typing import Any, Literal
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI
from langchain.tools import tool
from rich.console import Console
from rich.logging import RichHandler

# Setup structured logging with rich
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("l3_agent_runner")
console = Console()

# -----------------------------------------------------------------------------
# CONFIGURATION
# Set AGENT_TYPE to "langgraph" (OpenAI) or "adk" (Google Gemini)
# -----------------------------------------------------------------------------
AGENT_TYPE: Literal["langgraph", "adk"] = "langgraph"
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Path to database CSV file
SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATH = SCRIPT_DIR / "db.csv"


@tool
def query_data(query: str) -> list[dict[str, Any]]:
    """Query the lesson dataset. Always call before showing a chart or graph."""
    if not CSV_PATH.exists():
        logger.warning("CSV file not found at %s", CSV_PATH)
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def create_langgraph_app(model_name: str = "gpt-5.6-luna") -> FastAPI:
    """Create a FastAPI application hosting a LangGraph AG-UI agent for L3.

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

    logger.info("Initializing LangGraph Agent for L3 (model: %s)", model_name)
    graph = create_agent(
        model=ChatOpenAI(model=model_name),
        tools=[query_data],
        middleware=[CopilotKitMiddleware()],
        checkpointer=MemorySaver(),
        system_prompt=(
            "You are a helpful assistant for a demo app with a few available UI tools. "
            "When a user asks for charts based on the lesson dataset, always call query_data first to fetch all CSV rows. "
            "Prefer using a matching frontend tool when it would present the answer clearly. "
            "Use pieChart for category distributions, "
            "flightCard for a single flight summary when relevant, "
            "and showMyName to display the user's name. "
            "Tool arguments must match the provided schema exactly."
        ),
    )

    app = FastAPI(title="L3 LangGraph Controlled Generative UI Agent API")
    agent = LangGraphAGUIAgent(
        name="lesson3_charts_agent",
        description="Lesson 3 controlled generative UI agent",
        graph=graph,
    )
    add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
    return app


def create_adk_app(model_name: str = "gemini-3.5-flash-lite") -> FastAPI:
    """Create a FastAPI application hosting a Google ADK AG-UI agent for L3.

    Args:
        model_name: Name of the Gemini model to use.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    from ag_ui_adk import ADKAgent, AGUIToolset, add_adk_fastapi_endpoint
    from google.adk.agents import LlmAgent
    from google.adk.integrations.langchain import LangchainTool

    logger.info("Initializing Google ADK Agent for L3 (model: %s)", model_name)
    gemini_agent = LlmAgent(
        name="assistant",
        model=model_name,
        instruction=(
            "You are a helpful assistant for a demo app with a few available UI tools. "
            "When a user asks for charts based on the lesson dataset, always call query_data first to fetch all CSV rows. "
            "Prefer using a matching frontend tool when it would present the answer clearly. "
            "Use pieChart for category distributions, "
            "flightCard for a single flight summary when relevant, "
            "and showMyName to display the user's name."
        ),
        tools=[
            # Backend tool: wraps the shared LangChain @tool so ADK can call it
            # like any native FunctionTool.
            LangchainTool(query_data),
            # Placeholder swapped per-run for the frontend's registered
            # showMyName/pieChart/flightCard tools (see ag_ui_adk.AGUIToolset).
            AGUIToolset(),
        ],
    )

    adk_agent = ADKAgent(
        adk_agent=gemini_agent,
        app_name="demo_app",
        user_id="demo_user",
        session_timeout_seconds=3600,
        use_in_memory_services=True,
    )

    app = FastAPI(title="L3 Google ADK Controlled Generative UI Agent API")
    add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
    return app


def main() -> None:
    """Main entrypoint to load environment variables and launch the FastAPI server."""
    load_dotenv(override=True)

    selected_agent = os.getenv("AGENT_TYPE", AGENT_TYPE).lower()
    port = int(os.getenv("PORT", "8003"))

    if selected_agent == "adk":
        model = os.getenv("MODEL_NAME", GEMINI_MODEL)
        console.print(
            f"[bold green]🚀 Launching L3 Google ADK Agent Server on port {port} (Model: {model})...[/bold green]"
        )
        app = create_adk_app(model_name=model)
    else:
        model = os.getenv("MODEL_NAME", OPENAI_MODEL)
        console.print(
            f"[bold cyan]🚀 Launching L3 LangGraph Agent Server on port {port} (Model: {model})...[/bold cyan]"
        )
        app = create_langgraph_app(model_name=model)

    console.print(
        f"📖 Swagger Docs available at: [link=http://localhost:{port}/docs]http://localhost:{port}/docs[/link]"
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
