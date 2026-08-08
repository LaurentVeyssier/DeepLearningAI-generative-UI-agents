"""L5 Agent Backend Runner for Open-Ended Generative UI (MCP Apps + openGenerativeUI).

This script launches an AG-UI compatible FastAPI backend server for CopilotKit,
supporting both LangGraph (OpenAI) and Google ADK (Gemini).

Unlike L2-L4, this agent declares NO backend Python tools at all — every visual
capability comes from the CopilotKit *runtime* (frontend/server.ts), which:
- Discovers Excalidraw's MCP App server (`mcpApps.servers`) and surfaces its
  tool to the model, letting the agent open a real whiteboard app in the chat.
- Auto-injects a `generateSandboxedUi` tool (`openGenerativeUI: true`) that
  lets the model write raw HTML/CSS/JS, rendered live in a sandboxed iframe.

Mermaid diagrams are deliberately NOT wired up as an MCP App: Mermaid's
official hosted server (mcp.mermaid.ai) doesn't implement the MCP Apps
extension (no `ui://` resources) — it's a plain, data-returning MCP server,
so `mcpApps` has nothing to render for it (see the README's Troubleshooting
section for the full story). Instead, the shared SYSTEM_PROMPT below tells
the agent to render Mermaid diagrams itself via `generateSandboxedUi`,
loading mermaid.js from one of the sandbox's allowed CDNs
(jsdelivr/unpkg/esm.sh/cdnjs) — fully open-ended, no MCP server involved.

Both agent types need identical tool-level wiring EXCEPT for ADK, which needs
one extra piece to actually expose these runtime-injected tools to Gemini —
`AGUIToolset()` — for the exact same reason L4's README documents for
`render_a2ui`: without it, `ag_ui_adk` logs the tools as available
("Tools from frontend: [...]") but never hands them to the model.
"""

import logging
import os
import textwrap
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
logging.getLogger("langgraph.checkpoint").setLevel(logging.ERROR)
logger = logging.getLogger("l5_agent_runner")
console = Console()

# -----------------------------------------------------------------------------
# CONFIGURATION
# Set AGENT_TYPE to "langgraph" (OpenAI) or "adk" (Google Gemini)
# -----------------------------------------------------------------------------
AGENT_TYPE: Literal["langgraph", "adk"] = "langgraph"
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# -----------------------------------------------------------------------------
# Shared system instruction — identical for both agent types. No backend tools
# are declared anywhere in this file; every tool named below (`generateSandboxedUi`,
# the Excalidraw MCP App tool) is injected by the CopilotKit runtime
# (frontend/server.ts), not by this script.
# -----------------------------------------------------------------------------
SYSTEM_PROMPT: str = textwrap.dedent("""
    You are a helpful assistant operating in an interactive UI. Your name is Bob.

    Default behavior:
    - For any visual/interactive output, use the sandbox UI tool with a 400px tall card wrapping all content you make.
    - For an architecture or whiteboarding, use Excalidraw.
    - For flowcharts, sequence diagrams, or other Mermaid-style diagrams, use the
      sandbox UI tool — NOT Excalidraw.
    - Otherwise, respond conversationally.

    WHEN MAKING SANDBOX UI:
    - Always wrap your UI in a 400px tall card. NEVER MAKE A UI WITHOUT A CARD.
    - When making it rain tacos, use emojis - do NOT generate an SVG for it.

    WHEN RENDERING A MERMAID DIAGRAM IN THE SANDBOX UI:
    - Put the diagram source in a `<pre class="mermaid">...</pre>` block.
    - Load mermaid.js as an ES module from
      https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs
      (a CDN the sandbox already allows) and call `mermaid.initialize({ startOnLoad: true })`.
    - Keep the diagram syntax valid Mermaid — flowchart/sequenceDiagram/etc.

    WHEN USING EXCALIDRAW:
    - Remember you're on a cartesian plane - you need to account for the size of cards and labels.
    - Network/architecture diagrams (any request to draw/show a diagram
      with routers, servers, laptops, etc.): use the excalidraw tool
      instead of the sandbox UI. Keep it clean and simple, with clear
      labels and a title.
""").strip()


def create_langgraph_app(model_name: str = "gpt-5.4-mini") -> FastAPI:
    """Create a FastAPI application hosting a LangGraph AG-UI agent for L5.

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

    logger.info("Initializing LangGraph Agent for L5 (model: %s)", model_name)
    graph = create_agent(
        model=ChatOpenAI(model=model_name, temperature=0),
        tools=[],
        middleware=[CopilotKitMiddleware()],
        checkpointer=MemorySaver(),
        system_prompt=SYSTEM_PROMPT,
    )

    app = FastAPI(title="L5 LangGraph Open-Ended Generative UI Agent API")
    agent = LangGraphAGUIAgent(
        name="app_agent",
        description="Lesson 5 open-ended generative UI agent",
        graph=graph,
    )
    add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
    return app


def create_adk_app(model_name: str = "gemini-3.5-flash-lite") -> FastAPI:
    """Create a FastAPI application hosting a Google ADK AG-UI agent for L5.

    Args:
        model_name: Name of the Gemini model to use.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    from ag_ui_adk import ADKAgent, AGUIToolset, add_adk_fastapi_endpoint
    from google.adk.agents import LlmAgent

    logger.info("Initializing Google ADK Agent for L5 (model: %s)", model_name)
    gemini_agent = LlmAgent(
        name="assistant",
        model=model_name,
        instruction=SYSTEM_PROMPT,
        tools=[
            # This lesson has no backend Python tools at all — both
            # `generateSandboxedUi` (openGenerativeUI) and Excalidraw's MCP
            # App tool are injected by the CopilotKit runtime as frontend
            # tools on every AG-UI request. Without AGUIToolset() here,
            # ag_ui_adk logs them ("Tools from frontend: [...]") but never
            # actually exposes them to Gemini — see L4's README for the full
            # story on why this placeholder is required on ADK.
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

    app = FastAPI(title="L5 Google ADK Open-Ended Generative UI Agent API")
    add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
    return app


def main() -> None:
    """Main entrypoint to load environment variables and launch the FastAPI server."""
    load_dotenv(override=True)

    selected_agent = os.getenv("AGENT_TYPE", AGENT_TYPE).lower()
    port = int(os.getenv("PORT", "8005"))

    if selected_agent == "adk":
        model = os.getenv("MODEL_NAME", GEMINI_MODEL)
        console.print(
            f"[bold green]🚀 Launching L5 Google ADK Agent Server on port {port} (Model: {model})...[/bold green]"
        )
        app = create_adk_app(model_name=model)
    else:
        model = os.getenv("MODEL_NAME", OPENAI_MODEL)
        console.print(
            f"[bold cyan]🚀 Launching L5 LangGraph Agent Server on port {port} (Model: {model})...[/bold cyan]"
        )
        app = create_langgraph_app(model_name=model)

    console.print(
        f"📖 Swagger Docs available at: [link=http://localhost:{port}/docs]http://localhost:{port}/docs[/link]"
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
