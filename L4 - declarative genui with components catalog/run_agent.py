"""L4 Agent Backend Runner for Declarative Generative UI (A2UI).

This script launches an AG-UI compatible FastAPI backend server for CopilotKit,
supporting both LangGraph (OpenAI) and Google ADK (Gemini).

It powers a chat interface that can render two kinds of declarative UI, built
from the component catalog in frontend/src/catalog/:
- A **dynamic schema** sales dashboard, generated on the fly by the agent via
  the auto-injected `generate_a2ui` tool (see frontend/server.ts's
  `a2ui: { injectA2UITool: true }`).
- A **fixed schema** flight-search carousel, rendered by the `display_flights`
  tool from a predefined A2UI component tree (built with the A2UI Composer)
  that only the runtime `flights` data changes.

Backend tools (`get_sales_data`, `search_flights`, `display_flights`) and the
shared system instruction are identical in behavior for both agent types —
only how each framework is told about the tools differs:
- LangGraph: passed directly via `tools=[...]` and merged with frontend/A2UI
  tools at request time by `CopilotKitMiddleware()`.
- ADK: `get_sales_data`/`search_flights` are wrapped with
  `google.adk.integrations.langchain.LangchainTool` so the same LangChain
  `@tool`-decorated functions run natively as ADK `FunctionTool`s (see L3's
  README for why this wrapping is required in general). `display_flights`
  is the one exception — its nested array-of-objects schema doesn't survive
  `LangchainTool`'s legacy schema conversion against the live Gemini API, so
  it's registered as a native `FunctionTool` instead, calling the same
  rendering helper. See this file's README for the full story.
"""

import json
import logging
import os
from typing import Any, Literal

from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI
from langchain.tools import tool
from rich.console import Console
from rich.logging import RichHandler
from typing_extensions import TypedDict

# Setup structured logging with rich
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("l4_agent_runner")
console = Console()

# -----------------------------------------------------------------------------
# CONFIGURATION
# Set AGENT_TYPE to "langgraph" (OpenAI) or "adk" (Google Gemini)
# -----------------------------------------------------------------------------
AGENT_TYPE: Literal["langgraph", "adk"] = "langgraph"
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# -----------------------------------------------------------------------------
# A2UI catalog / surface identifiers — must match frontend/src/catalog
# (createCatalog's catalogId in renderers.tsx) and the runtime's `a2ui`
# config in frontend/server.ts.
# -----------------------------------------------------------------------------
CATALOG_ID = "copilotkit://app-dashboard-catalog"
SURFACE_ID = "flight-search-results"

# Fixed A2UI schema for the flight-card carousel, produced by the A2UI
# Composer (https://a2ui-editor.ag-ui.com/) — see L4.ipynb cell 35. The
# layout never changes; only the `/flights` data bound at runtime does.
FLIGHT_SCHEMA: list[dict[str, Any]] = [
    {"id": "root", "component": "List", "children": {"componentId": "flight-card", "path": "/flights"}, "direction": "horizontal", "gap": 16},
    {"id": "flight-card", "component": "Card", "child": "main-col"},
    {"id": "main-col", "component": "Column", "children": ["airline-img", "header-row", "meta-row", "divider-1", "times-row", "route-row", "divider-2", "status-row", "divider-3", "book-btn"], "align": "stretch", "gap": 8},
    {"id": "airline-img", "component": "Image", "src": {"path": "airlineLogo"}, "alt": {"path": "airline"}, "height": 32},
    {"id": "header-row", "component": "Row", "children": ["airline-name", "price-text"], "justify": "spaceBetween", "align": "center"},
    {"id": "airline-name", "component": "Text", "text": {"path": "airline"}, "variant": "h3"},
    {"id": "price-text", "component": "Text", "text": {"path": "price"}, "variant": "h2"},
    {"id": "meta-row", "component": "Row", "children": ["flight-number", "date-text"], "justify": "spaceBetween", "align": "center"},
    {"id": "flight-number", "component": "Text", "text": {"path": "flightNumber"}, "variant": "caption"},
    {"id": "date-text", "component": "Text", "text": {"path": "date"}, "variant": "caption"},
    {"id": "divider-1", "component": "Divider"},
    {"id": "times-row", "component": "Row", "children": ["depart-time", "duration-text", "arrive-time"], "justify": "spaceBetween", "align": "center"},
    {"id": "depart-time", "component": "Text", "text": {"path": "departureTime"}, "variant": "h2"},
    {"id": "duration-text", "component": "Text", "text": {"path": "duration"}, "variant": "caption"},
    {"id": "arrive-time", "component": "Text", "text": {"path": "arrivalTime"}, "variant": "h2"},
    {"id": "route-row", "component": "Row", "children": ["origin-code", "arrow-text", "dest-code"], "justify": "spaceBetween", "align": "center"},
    {"id": "origin-code", "component": "Text", "text": {"path": "origin"}, "variant": "h3"},
    {"id": "arrow-text", "component": "Text", "text": "→", "variant": "h3"},
    {"id": "dest-code", "component": "Text", "text": {"path": "destination"}, "variant": "h3"},
    {"id": "divider-2", "component": "Divider"},
    {"id": "status-row", "component": "Row", "children": ["status-text"], "align": "center"},
    {"id": "status-text", "component": "Text", "text": {"path": "status"}, "variant": "caption"},
    {"id": "divider-3", "component": "Divider"},
    {"id": "book-btn", "component": "Button", "label": "Book Flight", "variant": "primary", "action": {"event": {"name": "bookFlight"}}},
]


class Flight(TypedDict):
    id: str
    airline: str
    airlineLogo: str
    flightNumber: str
    origin: str
    destination: str
    date: str
    departureTime: str
    arrivalTime: str
    duration: str
    status: str
    price: str


# -----------------------------------------------------------------------------
# Backend tools — shared verbatim by both the LangGraph and ADK agent builders.
# -----------------------------------------------------------------------------
@tool
def get_sales_data() -> str:
    """Fetch current sales metrics and revenue data.

    Returns sales data including revenue, customers, conversion rates,
    and breakdowns by category and month.
    """
    # Placeholder: in production, this would query your actual database or API.
    return json.dumps({
        "totalRevenue": "$1.2M",
        "newCustomers": 3842,
        "conversionRate": "3.6%",
        "revenueByCategory": [
            {"label": "Electronics", "value": 420000},
            {"label": "Clothing", "value": 310000},
            {"label": "Home & Garden", "value": 185000},
            {"label": "Sports", "value": 160000},
            {"label": "Books", "value": 125000},
        ],
        "monthlySales": [
            {"label": "Jan", "value": 85000},
            {"label": "Feb", "value": 92000},
            {"label": "Mar", "value": 108000},
            {"label": "Apr", "value": 95000},
            {"label": "May", "value": 115000},
            {"label": "Jun", "value": 125000},
        ],
    })


@tool
def search_flights(origin: str, destination: str) -> list[Flight]:
    """Search for available flights between two airports.

    Args:
        origin: Origin airport IATA code (e.g. "SFO").
        destination: Destination airport IATA code (e.g. "JFK").
    """
    # Placeholder: in production, this would call a real flight search API.
    return [
        {"id": "1", "airline": "Delta Air Lines", "airlineLogo": "https://www.gstatic.com/flights/airline_logos/70px/DL.png", "flightNumber": "DL 520", "origin": origin, "destination": destination, "date": "2026-04-11", "departureTime": "08:00", "arrivalTime": "16:35", "duration": "5h 35m", "status": "On Time", "price": "$389"},
        {"id": "2", "airline": "United Airlines", "airlineLogo": "https://www.gstatic.com/flights/airline_logos/70px/UA.png", "flightNumber": "UA 1583", "origin": origin, "destination": destination, "date": "2026-04-11", "departureTime": "10:15", "arrivalTime": "18:42", "duration": "5h 27m", "status": "On Time", "price": "$412"},
        {"id": "3", "airline": "JetBlue", "airlineLogo": "https://www.gstatic.com/flights/airline_logos/70px/B6.png", "flightNumber": "B6 416", "origin": origin, "destination": destination, "date": "2026-04-11", "departureTime": "14:30", "arrivalTime": "23:05", "duration": "5h 35m", "status": "On Time", "price": "$345"},
        {"id": "4", "airline": "American Airlines", "airlineLogo": "https://www.gstatic.com/flights/airline_logos/70px/AA.png", "flightNumber": "AA 178", "origin": origin, "destination": destination, "date": "2026-04-11", "departureTime": "17:00", "arrivalTime": "01:20+1", "duration": "5h 20m", "status": "On Time", "price": "$398"},
    ]


def _flights_a2ui_operations(flights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the fixed-schema A2UI operations list for a list of flights.

    Shared by both agent builders' `display_flights` tool so the actual A2UI
    operations are defined in exactly one place. Returns the raw operations
    list rather than a serialized payload — each caller wraps it however its
    framework needs (see `display_flights` below vs. `display_flights_adk` in
    `create_adk_app()`).
    """
    from copilotkit import a2ui

    return [
        a2ui.create_surface(SURFACE_ID, catalog_id=CATALOG_ID),
        a2ui.update_components(SURFACE_ID, FLIGHT_SCHEMA),
        a2ui.update_data_model(SURFACE_ID, {"flights": flights}),
    ]


@tool
def display_flights(flights: list[Flight]) -> str:
    """Display flights as rich cards in a horizontal row.

    Each flight must have: id, airline, airlineLogo (URL), flightNumber,
    origin, destination, date, departureTime, arrivalTime, duration,
    status, and price.
    """
    from copilotkit import a2ui

    return a2ui.render(operations=_flights_a2ui_operations(flights))


# `generate_a2ui` is NOT declared here: the CopilotKit runtime auto-injects it
# as a frontend tool whenever `a2ui: { injectA2UITool: true }` is set (see
# frontend/server.ts) — both CopilotKitMiddleware (LangGraph) and ag_ui_adk
# pick it up from the AG-UI request automatically. See the README for details.
SYSTEM_PROMPT = (
    "You are a helpful assistant that creates rich visual UI.\n\n"
    "Tool guidance:\n"
    "- ALL flight-related queries: first call search_flights to fetch flight "
    "data, then call display_flights with the results. NEVER use generate_a2ui "
    "for flights.\n"
    "- For sales/business data requests: first call get_sales_data to fetch "
    "the latest metrics, then call generate_a2ui to visualize the results.\n"
    "- For other rich UI: call generate_a2ui directly.\n\n"
    "Airline logos: use https://www.gstatic.com/flights/airline_logos/70px/<IATA>.png\n"
    "Common codes: DL=Delta, UA=United, AA=American, WN=Southwest, B6=JetBlue, "
    "NK=Spirit, AS=Alaska, F9=Frontier, BA=British Airways, LH=Lufthansa, "
    "AF=Air France, EK=Emirates, QF=Qantas, SQ=Singapore Airlines, NH=ANA.\n\n"
    "IMPORTANT: After calling a tool, do NOT repeat or summarize the data "
    "in your text response. The tool renders UI automatically. "
    "Just confirm what was rendered."
)


def create_langgraph_app(model_name: str = "gpt-5.4-mini") -> FastAPI:
    """Create a FastAPI application hosting a LangGraph AG-UI agent for L4.

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

    logger.info("Initializing LangGraph Agent for L4 (model: %s)", model_name)
    graph = create_agent(
        model=ChatOpenAI(model=model_name),
        tools=[get_sales_data, search_flights, display_flights],
        middleware=[CopilotKitMiddleware()],
        checkpointer=MemorySaver(),
        system_prompt=SYSTEM_PROMPT,
    )

    app = FastAPI(title="L4 LangGraph Declarative Generative UI Agent API")
    agent = LangGraphAGUIAgent(
        name="lesson4_a2ui_agent",
        description="Lesson 4 declarative generative UI (A2UI) agent",
        graph=graph,
    )
    add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
    return app


def create_adk_app(model_name: str = "gemini-3.5-flash-lite") -> FastAPI:
    """Create a FastAPI application hosting a Google ADK AG-UI agent for L4.

    Args:
        model_name: Name of the Gemini model to use.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    from ag_ui_adk import ADKAgent, AGUIToolset, add_adk_fastapi_endpoint
    from google.adk.agents import LlmAgent
    from google.adk.integrations.langchain import LangchainTool
    from google.adk.tools import FunctionTool

    def display_flights_adk(flights: list[dict[str, Any]]) -> dict[str, Any]:
        """Display flights as rich cards in a horizontal row.

        Args:
            flights: The flights to display. Each flight needs id, airline,
              airlineLogo (a URL), flightNumber, origin, destination, date,
              departureTime, arrivalTime, duration, status, and price.
        """
        # Returns a dict (not the JSON *string* copilotkit.a2ui.render()
        # normally returns) on purpose: ADK requires FunctionTool results to
        # be a dict and auto-wraps any non-dict return as {"result": <value>}
        # (google/adk/flows/llm_flows/functions.py::__build_response_event).
        # A wrapped string hides "a2ui_operations" from the runtime's A2UI
        # detection, so nothing renders even though the call succeeds with no
        # error. Returning the dict directly avoids the wrap. See the
        # README's Troubleshooting section.
        return {"a2ui_operations": _flights_a2ui_operations(flights)}

    display_flights_adk.__name__ = "display_flights"

    logger.info("Initializing Google ADK Agent for L4 (model: %s)", model_name)
    gemini_agent = LlmAgent(
        name="assistant",
        model=model_name,
        instruction=SYSTEM_PROMPT,
        tools=[
            # get_sales_data / search_flights: simple schemas (no args, or
            # plain strings) — LangchainTool wraps the shared LangChain @tool
            # functions fine here so ADK can call them like native
            # FunctionTools (see L3's README for why LangchainTool wrapping
            # is required in general).
            LangchainTool(get_sales_data),
            LangchainTool(search_flights),
            # display_flights: NOT wrapped with LangchainTool. Its `flights`
            # parameter is an array of objects, and LangchainTool converts
            # schemas through ADK's legacy `Schema` proto type, which the
            # live Gemini API rejects for this exact shape — first over
            # `$ref` (nested TypedDict), then over `additionalProperties`
            # (a bare dict), and finally with a cryptic
            # "field predicate failed: $type == Type.ARRAY" even for a fully
            # explicit flat schema. A native `FunctionTool` instead uses
            # ADK's newer `parameters_json_schema` field (real JSON Schema,
            # sent as-is to Gemini) and works — verified live against the
            # actual API. See the README's Troubleshooting section.
            FunctionTool(display_flights_adk),
            # Placeholder swapped per-run for whatever frontend tools the
            # AG-UI request carries. On this lesson's frontend that's the
            # CopilotKit runtime's own `render_a2ui` tool (injected by its
            # A2UIMiddleware) — WITHOUT this, ag_ui_adk logs
            # "Tools from frontend: ['render_a2ui']" but never actually
            # exposes it to the model. With `a2ui.inject_a2ui_tool` enabled
            # below, `render_a2ui` gets dropped in favor of the native
            # `generate_a2ui` tool anyway (see below) — this placeholder is
            # kept for forward-compatibility if this lesson ever registers a
            # real `useComponent()` frontend tool. See L3's README for the
            # general AGUIToolset explanation.
            AGUIToolset(),
        ],
    )

    adk_agent = ADKAgent(
        adk_agent=gemini_agent,
        app_name="demo_app",
        user_id="demo_user",
        session_timeout_seconds=3600,
        use_in_memory_services=True,
        # Force the backend-native `generate_a2ui` auto-injection on
        # regardless of `forwardedProps.injectA2UITool` — on this frontend
        # version (@copilotkit/runtime@1.55.2-next.0) that flag is never
        # actually sent, so without this override the model can only see the
        # CopilotKit runtime's own JS-injected `render_a2ui` tool, whose
        # schema doesn't require every component to have a `component` field
        # and lets Gemini omit it or confuse catalogId with surfaceId. The
        # native path fixes the catalog binding explicitly (`default_catalog_id`)
        # and — critically — retries automatically on an invalid tree via
        # `recovery`, instead of surfacing the raw client-side render error.
        #
        # IMPORTANT — this alone is not sufficient. ag_ui_adk's own internal
        # nested subagent tool call (built by this config) is ALSO literally
        # named "render_a2ui", which collides with the JS runtime's own
        # progressive-streaming interception of that same name (defaulting
        # to the public basic catalog when it doesn't find catalogId in that
        # inner call's args, which never has one). frontend/server.ts must
        # set `a2ui: { a2uiToolNames: [] }` to disable that progressive path
        # — it still detects/renders `a2ui_operations` from any tool's final
        # result, which is the only thing that actually matters. See the
        # README's Troubleshooting section for the full story.
        a2ui={
            "inject_a2ui_tool": True,
            "default_catalog_id": CATALOG_ID,
            "recovery": {"maxAttempts": 3},
        },
    )

    app = FastAPI(title="L4 Google ADK Declarative Generative UI Agent API")
    add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
    return app


def main() -> None:
    """Main entrypoint to load environment variables and launch the FastAPI server."""
    load_dotenv(override=True)

    selected_agent = os.getenv("AGENT_TYPE", AGENT_TYPE).lower()
    port = int(os.getenv("PORT", "8004"))

    if selected_agent == "adk":
        model = os.getenv("MODEL_NAME", GEMINI_MODEL)
        console.print(
            f"[bold green]🚀 Launching L4 Google ADK Agent Server on port {port} (Model: {model})...[/bold green]"
        )
        app = create_adk_app(model_name=model)
    else:
        model = os.getenv("MODEL_NAME", OPENAI_MODEL)
        console.print(
            f"[bold cyan]🚀 Launching L4 LangGraph Agent Server on port {port} (Model: {model})...[/bold cyan]"
        )
        app = create_langgraph_app(model_name=model)

    console.print(
        f"📖 Swagger Docs available at: [link=http://localhost:{port}/docs]http://localhost:{port}/docs[/link]"
    )
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
