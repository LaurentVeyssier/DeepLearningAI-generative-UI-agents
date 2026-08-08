# Lesson 4: Declarative Generative UI with the A2UI Component Catalog

Welcome to **Lesson 4** of the _Generative UI Agents_ course. This document provides a comprehensive guide explaining declarative generative UI (A2UI), every step of the Jupyter notebook ([L4.ipynb](L4.ipynb)), and how to run everything using a standalone Python script ([run_agent.py](run_agent.py)) — for both the LangGraph/OpenAI and Google ADK/Gemini agent paths.

> **Setting up ADK/Gemini?** Jump straight to [⚙️ Required Configuration for Google ADK / Gemini](#-required-configuration-for-google-adk--gemini) for the complete, actionable checklist. LangGraph/OpenAI needs none of it.

---

## 🏗 System Architecture

Same three decoupled layers as Lesson 2 and 3, with one addition: the frontend now owns an **A2UI component catalog** that the CopilotKit runtime uses to validate and stream the agent's generated UI trees.

```
┌──────────────────────────────────────────────────────────────────┐
│                  1. React Frontend (Browser)                     │
│   <CopilotKit runtimeUrl="/api/copilotkit"                       │
│               a2ui={{ catalog: demonstrationCatalog }}>          │
│       └── <CopilotChat />                                        │
│   Component catalog: frontend/src/catalog/                       │
│     - definitions.ts  → Zod schemas the agent can target         │
│     - renderers.tsx   → React components + createCatalog()       │
│   (Running via Vite on Port 3004)                                │
└───────────────────────────┬────────────────────────────────────┘
                            │  HTTP / Event Stream
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│              2. CopilotRuntime Server (Node.js)                  │
│   (Running via Hono server on Port 4004)                         │
│   - a2ui: { injectA2UITool: true, a2uiToolNames: [] }             │
│     → its A2UIMiddleware injects a `render_a2ui` tool directly   │
│       into every request's `tools` list (like a real frontend    │
│       tool). `a2uiToolNames: []` disables its progressive         │
│       (args-streaming) interception of that name — required on   │
│       ADK, see Gotchas — while it still detects/renders any       │
│       tool's final `a2ui_operations` result                       │
│   - Detects `a2ui_operations` in ANY tool result and routes it   │
│     to the frontend for rendering                                 │
└───────────────────────────┬────────────────────────────────────┘
                            │  AG-UI Protocol Streams
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│               3. Python Agent Backend (FastAPI)                  │
│   - LangGraph / OpenAI Agent (Port 8004)                         │
│   OR                                                              │
│   - Google ADK / Gemini Agent (Port 8004)                        │
│   Backend tools: get_sales_data, search_flights, display_flights │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🎨 What is Declarative Generative UI (A2UI)?

Controlled Generative UI (Lesson 3) maps one agent tool to one hand-authored React component — great for your highest-traffic surfaces, but it doesn't scale to every possible request. **Declarative Generative UI** solves the long tail: instead of one tool per layout, you give the agent a **catalog of reusable UI primitives** (`Card`, `Row`, `Metric`, `PieChart`, …) and let it *compose* them into a tree at runtime.

[A2UI](https://a2ui.org/) (Agent-to-UI) is the specification behind this, created by Google in collaboration with CopilotKit. Three pieces make it work:

* **Component catalog** — the UI primitives your app supports, split into:
  * **Definitions** ([frontend/src/catalog/definitions.ts](frontend/src/catalog/definitions.ts)): platform-agnostic Zod schemas describing each component's name, props, and purpose.
  * **Renderers** ([frontend/src/catalog/renderers.tsx](frontend/src/catalog/renderers.tsx)): the React implementations, type-checked against the definitions and assembled with `createCatalog()`.
* **Schema** — the structured tree describing which components to use, how they nest, and how they relate (a list of `{id, component, props...}` nodes).
* **Data bindings** — the runtime values (`{"path": "flights"}`-style references) that populate the schema with real content.

This lesson builds **both** approaches A2UI supports:

| | **Dynamic schema** (sales dashboard) | **Fixed schema** (flight carousel) |
|---|---|---|
| **Layout** | Agent-generated, varies per request | Predefined, identical every time |
| **Agent's role** | Chooses components *and* layout | Fills in data only |
| **Tool** | `generate_a2ui` (LangGraph) / `render_a2ui` (auto-injected by the runtime, both paths) | `display_flights` (a normal backend tool) |
| **Best for** | Long-tail, exploratory, internal surfaces | Polished, brand-sensitive, high-traffic surfaces |
| **ADK/Gemini status** | ✅ Fully working, verified live (3/3 clean runs) — required both a Python-side fix (`ADKAgent(a2ui={...})`) and a frontend one (`a2uiToolNames: []`); see Gotchas | ✅ Fully working, verified live |

---

## ⚙️ Required Configuration for Google ADK / Gemini

**Read this section before wiring up ADK/Gemini for A2UI, controlled genUI, or anything else that routes frontend/CopilotKit tools through `ag_ui_adk`.** LangGraph/OpenAI works with the "obvious" code — none of this is needed there. ADK requires six additional, non-obvious pieces, split across **two files**. Skip any one and you get a specific, reproducible failure (listed below so you can diagnose backwards from a symptom too). Every fix here was confirmed against the live Gemini API and the real browser — not inferred from documentation alone.

### The six required pieces

| # | What | Where | Why (one line — full root cause in [Gotchas](#-gotcha-fixed-while-porting-this-to-a-standalone-script)) |
|---|---|---|---|
| 1 | Wrap simple LangChain `@tool` functions in `LangchainTool(...)` before adding them to `LlmAgent.tools` | `run_agent.py` | ADK never runs plain LangChain tools natively |
| 2 | For any tool whose parameter is an **array of objects** (e.g. `flights: list[dict]`), wrap it in a native `google.adk.tools.FunctionTool(...)` **instead of** `LangchainTool(...)` | `run_agent.py` | `LangchainTool`'s schema conversion cannot express "array of objects" against the live Gemini API in *any* form — always a `400 INVALID_ARGUMENT` |
| 3 | Any such tool must **`return` a `dict`** (e.g. `{"a2ui_operations": [...]}`) — never a JSON-encoded *string* | `run_agent.py` | ADK auto-wraps non-dict results as `{"result": "<string>"}`, hiding sentinel keys like `a2ui_operations` one level too deep — the call succeeds with **no error**, and nothing renders |
| 4 | Add `AGUIToolset()` to `LlmAgent.tools` | `run_agent.py` | Any tool the CopilotKit *runtime* injects (`useComponent()` tools in L3, `render_a2ui` here) gets logged (`Tools from frontend: [...]`) but never exposed to the model — the agent silently does nothing |
| 5 | Pass `a2ui={"inject_a2ui_tool": True, "default_catalog_id": <your catalog id>, "recovery": {"maxAttempts": N}}` to `ADKAgent(...)` | `run_agent.py` | Without this, dynamic A2UI generation either never triggers, or triggers through a path that's unreliable on ADK (see #6) |
| 6 | Set `a2ui: { a2uiToolNames: [] }` on the JS `CopilotRuntime` config, alongside `injectA2UITool: true` | `frontend/server.ts` | `ag_ui_adk`'s internal nested tool call for A2UI generation is **also named `render_a2ui`** — colliding with the JS runtime's own progressive-rendering interception of that name, which defaults to the wrong catalog before the correct result ever arrives |

### Copy-pasteable reference

**`run_agent.py`** (pieces 1–5):

```python
from ag_ui_adk import ADKAgent, AGUIToolset, add_adk_fastapi_endpoint
from google.adk.agents import LlmAgent
from google.adk.integrations.langchain import LangchainTool
from google.adk.tools import FunctionTool

def my_array_of_objects_tool_adk(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Same docstring/behavior as your shared LangChain tool."""
    return {"a2ui_operations": build_operations(items)}   # (3) dict, never a JSON string

my_array_of_objects_tool_adk.__name__ = "my_array_of_objects_tool"  # match the name your prompt uses

gemini_agent = LlmAgent(
    name="assistant",
    model=model_name,
    instruction=SYSTEM_PROMPT,
    tools=[
        LangchainTool(simple_tool_a),               # (1) scalar/no-arg params — LangchainTool is fine
        LangchainTool(simple_tool_b),
        FunctionTool(my_array_of_objects_tool_adk),  # (2) array-of-objects param — native FunctionTool only
        AGUIToolset(),                               # (4) required for any runtime-injected tool to reach the model
    ],
)
adk_agent = ADKAgent(
    adk_agent=gemini_agent,
    app_name="demo_app",
    user_id="demo_user",
    a2ui={                                            # (5) required for reliable dynamic A2UI generation
        "inject_a2ui_tool": True,
        "default_catalog_id": "your-catalog-id-here",
        "recovery": {"maxAttempts": 3},
    },
)
add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
```

**`frontend/server.ts`** (piece 6 — needed only if you also use dynamic A2UI generation):

```ts
const runtime = new CopilotRuntime({
  agents: { default: langGraphAgent },  // same URL/agent object regardless of Python framework
  a2ui: {
    injectA2UITool: true,
    a2uiToolNames: [],  // (6) required on ADK — see table above
  },
});
```

### If you're only using controlled generative UI (no A2UI) on ADK

You still need pieces 1, 2 (if any tool has an array-of-objects parameter), 3 (if any tool returns a client-detected sentinel payload), and 4. Pieces 5 and 6 are A2UI-specific — skip them.

### Applies beyond this lesson

None of this is specific to sales dashboards or flight cards. The underlying causes are properties of `ag_ui_adk`/Gemini and the CopilotKit JS runtime, so:
- Any ADK tool with a `list[dict]`/array-of-objects parameter hits #2, regardless of what it does.
- Any ADK tool returning a sentinel dict key (`a2ui_operations` or otherwise) that a client is supposed to detect hits #3.
- Any CopilotKit-runtime-injected tool (not just `render_a2ui`) hits #4 without `AGUIToolset()`.
- #6 only matters if you enable A2UI's dynamic-schema generation on ADK specifically.

---

## 📘 Notebook Step-by-Step Deep Dive

### 1. Starting the server vs. defining the agent (Cells 12 vs 15/38)

- **Cell 12 ("Start the server")** — same pattern as L2/L3: mounts the AG-UI FastAPI endpoint and starts the web server on **port 8004** with a throwaway placeholder graph. You only run this once per session.
- **Cell 15 ("Define agent")** — builds the real graph: `get_sales_data` as a backend tool, `CopilotKitMiddleware()` for frontend/A2UI tool discovery, and a system prompt that tells the model when to call `generate_a2ui`. Updates `agent.graph = graph` in place — no server restart needed.
- **Cell 38 ("Re-create graph with both tools")** — rebuilds the graph a second time, adding `search_flights` and `display_flights` alongside `get_sales_data`, with an expanded system prompt that also covers the fixed-schema flight flow.

### 2. Neither `generate_a2ui` nor `render_a2ui` is ever declared as a Python tool — two independent runtime layers inject them (Cell 15, 18)

Look closely at cell 15: `tools=[get_sales_data]`, yet the system prompt tells the agent to call `generate_a2ui`. That tool doesn't exist in the Python code:

```ts
// frontend/server.ts (cell 18)
const runtime = new CopilotRuntime({
  agents: { default: langGraphAgent },
  a2ui: { injectA2UITool: true },
});
```

`a2ui: { injectA2UITool: true }` actually turns on **two separate, independently-implemented** injection mechanisms — this distinction matters a lot for the ADK path (see the Gotchas section):

1. **JS-side, framework-agnostic (`@ag-ui/a2ui-middleware`, wrapping the agent inside the Node.js runtime process).** Its `A2UIMiddleware` adds a real `render_a2ui` tool definition directly to the AG-UI request's `tools` list — exactly as if the *frontend* had registered it with `useComponent()`/`useFrontendTool()` in Lesson 3 — plus context entries documenting how to call it. It then watches the outgoing event stream: as soon as `render_a2ui`'s streamed arguments contain a complete `components` array, it emits a UI update to the frontend, without waiting for the tool call to fully resolve.
2. **Backend-native, framework-specific (`ag_ui_langgraph` / `ag_ui_adk`).** Each framework's own adapter can *also* auto-inject a native `generate_a2ui` tool directly onto the agent's model, gated on `forwardedProps.injectA2UITool` in the AG-UI request (`ag_ui_adk/a2ui_tool.py::plan_a2ui_injection` is the ADK implementation; `ag_ui_langgraph` has the LangGraph equivalent). Internally this makes a *separate* structured-generation LLM call and streams a synthetic nested `render_a2ui`-shaped event to the frontend.

On this frontend/runtime version (`@copilotkit/runtime@1.55.2-next.0`), mechanism (1) is what actually fires — `render_a2ui` genuinely reaches the Python backend's `tools` list, but `forwardedProps.injectA2UITool` is **not** set on the outgoing request, so mechanism (2)'s native `generate_a2ui` auto-injection never triggers on the LangGraph or ADK side. `CopilotKitMiddleware()` on the LangGraph side merges `render_a2ui` into the model's bound tools the same way it merges any frontend tool, and the model just calls that instead — which is why the notebook's mention of "calling `generate_a2ui`" works in practice even though, on the wire, it's `render_a2ui` doing the work. See the Gotchas section for why this same mechanism needs one extra piece of wiring on ADK.

### 3. Component catalog — definitions and renderers (Cells 19–22)

- [frontend/src/catalog/definitions.ts](frontend/src/catalog/definitions.ts) declares ~15 primitives (`Title`, `Text`, `Card`, `Row`, `Column`, `DashboardCard`, `Metric`, `PieChart`, `BarChart`, `Badge`, `DataTable`, `Button`, …), each with a Zod props schema. This is what the agent sees when deciding how to compose a UI — the LLM is constrained to *only* these component names and props shapes.
- [frontend/src/catalog/renderers.tsx](frontend/src/catalog/renderers.tsx) maps each definition to a real React component, then assembles everything with:
  ```tsx
  export const demonstrationCatalog = createCatalog(
    demonstrationCatalogDefinitions,
    demonstrationCatalogRenderers,
    { catalogId: "copilotkit://app-dashboard-catalog", includeBasicCatalog: false },
  );
  ```
  `catalogId` matters — it's the same string the backend's fixed-schema tool uses (`CATALOG_ID` in [run_agent.py](run_agent.py)) to tell the runtime which catalog a fixed surface belongs to.

### 4. Wiring the catalog into the app (Cells 23–26)

- [frontend/src/main.tsx](frontend/src/main.tsx) registers the catalog on the provider: `<CopilotKit a2ui={{ catalog: demonstrationCatalog }}>`. This is what connects the agent's A2UI output to your React rendering layer.
- [frontend/src/App.tsx](frontend/src/App.tsx) renders `<CopilotChat />` and wires up example suggestion buttons via `useExampleDynamicSuggestions()` / `useExampleFixedSuggestions()` ([frontend/src/hooks/use-example-suggestions.tsx](frontend/src/hooks/use-example-suggestions.tsx)).

### 5. Fixed schema: the A2UI Composer and `display_flights` (Cells 32–38)

Rather than letting the agent improvise a layout every time, a **fixed schema** is designed once — with the [A2UI Composer](https://a2ui-editor.ag-ui.com/) — and reused for every flight search:

- The Composer prompt used: *"Create a carousel of flight cards with origin, destination, duration, time of departure, and time of arrival"*. Its `Copy JSON` output becomes `FLIGHT_SCHEMA` in [run_agent.py](run_agent.py).
- `display_flights` is a **plain backend tool** — any tool can return A2UI operations by wrapping its result in an `a2ui_operations` array:
  ```python
  from copilotkit import a2ui

  return a2ui.render(operations=[
      a2ui.create_surface(SURFACE_ID, catalog_id=CATALOG_ID),
      a2ui.update_components(SURFACE_ID, FLIGHT_SCHEMA),   # the fixed layout
      a2ui.update_data_model(SURFACE_ID, {"flights": flights}),  # runtime data
  ])
  ```
  The runtime's A2UI middleware detects `a2ui_operations` in *any* tool's return value and routes it to the frontend — this is completely independent of whether the tool ran on LangGraph or ADK.
- The system prompt tells the agent: *"ALL flight-related queries: first call `search_flights`, then call `display_flights` with the results. NEVER use `generate_a2ui` for flights."* — dynamic and fixed schemas coexist, and the agent picks the right one per request.

---

## 🚀 Standalone Script: `run_agent.py`

[run_agent.py](run_agent.py) replicates the notebook's final backend state (cell 38) as a single script supporting **both** agent frameworks, following the same pattern established in [L3's run_agent.py](../L3%20-%20controlled%20genUI%20with%20useComponent%20hook/run_agent.py).

### Shared backend tools & instruction

`get_sales_data`, `search_flights`, and `display_flights` are defined **once**, at module scope, as LangChain `@tool`-decorated functions — and reused verbatim by both agent builders, along with one shared `SYSTEM_PROMPT` string. `generate_a2ui`/`render_a2ui` is deliberately **not** declared anywhere in Python — see step 2 above; it's injected by the CopilotKit runtime's `A2UIMiddleware` whenever `injectA2UITool: true`. The ADK builder does need one extra piece of wiring for this to actually reach the model — `AGUIToolset()` — see `create_adk_app()` below and the Gotchas section.

### `create_langgraph_app()` — OpenAI via LangGraph

```python
graph = create_agent(
    model=ChatOpenAI(model=model_name),
    tools=[get_sales_data, search_flights, display_flights],
    middleware=[CopilotKitMiddleware()],
    checkpointer=MemorySaver(),
    system_prompt=SYSTEM_PROMPT,
)
agent = LangGraphAGUIAgent(name="lesson4_a2ui_agent", ..., graph=graph)
add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
```

Identical to the notebook's cell 38 — `CopilotKitMiddleware()` merges the runtime-injected `generate_a2ui` tool (and any other frontend tools) into the model's bound tools at request time. No extra wiring needed.

### `create_adk_app()` — Gemini via Google ADK

```python
from google.adk.integrations.langchain import LangchainTool
from google.adk.tools import FunctionTool

def display_flights_adk(flights: list[dict[str, Any]]) -> dict[str, Any]:
    """... same docstring as display_flights ..."""
    return {"a2ui_operations": _flights_a2ui_operations(flights)}  # dict, not a2ui.render()'s string

display_flights_adk.__name__ = "display_flights"

gemini_agent = LlmAgent(
    name="assistant",
    model=model_name,
    instruction=SYSTEM_PROMPT,
    tools=[
        LangchainTool(get_sales_data),      # simple schema — LangchainTool is fine
        LangchainTool(search_flights),      # simple schema — LangchainTool is fine
        FunctionTool(display_flights_adk),  # nested schema — needs native FunctionTool
        AGUIToolset(),                      # forward-compat placeholder, see point 3
    ],
)
adk_agent = ADKAgent(
    adk_agent=gemini_agent, app_name="demo_app", user_id="demo_user", ...,
    a2ui={
        "inject_a2ui_tool": True,             # force generate_a2ui on regardless of the runtime flag
        "default_catalog_id": CATALOG_ID,     # bind generated surfaces to our custom catalog
        "recovery": {"maxAttempts": 3},       # validate → retry loop for malformed trees
    },
)
add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
```

Four things to know about the ADK path — all covered in depth in the Gotchas section below:

1. **`LangchainTool` wrapping.** ADK doesn't run LangChain tools natively — `google.adk.integrations.langchain.LangchainTool` converts each `@tool`-decorated function into a real ADK `FunctionTool`, preserving its name, description, and schema. (Same fix as `query_data` in L3 — see [L3's README](../L3%20-%20controlled%20genUI%20with%20useComponent%20hook/README.md#-troubleshooting).)
2. **`display_flights` is the one exception** — wrapped as a native `FunctionTool` because `LangchainTool`'s schema conversion cannot express its array-of-objects parameter against the live Gemini API in *any* form, **and** it returns a `dict` rather than `a2ui.render()`'s JSON string, because ADK auto-wraps non-dict tool results in a way that hides `a2ui_operations` from the runtime.
3. **`AGUIToolset()` alone isn't enough for the dynamic dashboard** — it correctly exposes the JS-injected `render_a2ui` frontend tool to the model, but that tool's inner naming collides with the JS runtime's own progressive-streaming logic (see point 4). It's kept in the tools list as a forward-compat placeholder (matching L3's pattern) in case this lesson ever registers a real `useComponent()` tool, but the dashboard itself is driven by mechanism 4 instead.
4. **`ADKAgent(a2ui={...})` + a matching `frontend/server.ts` change is what actually makes the dashboard reliable.** Forcing the backend-native `generate_a2ui` tool on (`inject_a2ui_tool: True`) with an explicit `default_catalog_id` and a `recovery` retry loop fixes the model-facing side. But `ag_ui_adk`'s internal nested tool call is *also* named `render_a2ui`, colliding with the JS runtime's default progressive interception of that name — which requires the companion frontend fix, `a2ui: { a2uiToolNames: [] }` in `frontend/server.ts`, to fully resolve. See the Gotchas section for the full investigation.

### How to run

**Terminal 1 — backend:**

```bash
# LangGraph / OpenAI (default) — Port 8004
uv run python run_agent.py

# OR Google ADK / Gemini — Port 8004
AGENT_TYPE=adk uv run python run_agent.py
```

`AGENT_TYPE` (and `OPENAI_MODEL` / `GEMINI_MODEL`) are read from the repo-root [.env](../.env) — set `AGENT_TYPE=adk` there to default to Gemini without passing it on the command line every time. Both agent types serve on the same port (8004), so [frontend/server.ts](frontend/server.ts) — which always points `LangGraphHttpAgent` at `http://localhost:8004` — works unchanged for either backend; AG-UI is a framework-agnostic wire protocol, so the JS side doesn't need to know which Python framework is actually running.

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

**Try it** at `http://localhost:3004`:
* *"Find flights from San Francisco (SFO) to New York (JFK) for next Friday. Show me options from different airlines."* → fixed schema, via `search_flights` + `display_flights`. Fully reliable on both `AGENT_TYPE=langgraph` and `AGENT_TYPE=adk` — verified live.
* *"Show me a sales dashboard with total revenue, new customers, and conversion rate metrics. Include a pie chart of revenue by category and a bar chart of monthly sales."* → dynamic schema, via `get_sales_data` + `generate_a2ui`/`render_a2ui`. Fully reliable on both `AGENT_TYPE=langgraph` and `AGENT_TYPE=adk` — verified live across repeated runs after the fixes in the Gotchas section below.

---

## 🐞 Gotcha fixed while porting this to a standalone script

For the short, actionable version of everything below, see [⚙️ Required Configuration for Google ADK / Gemini](#-required-configuration-for-google-adk--gemini) above. This section is the full investigation — including two dead-end hypotheses that turned out to be wrong — for anyone who wants to understand *why*, not just *what*.

### `display_flights` fails under ADK/Gemini — `LangchainTool`'s legacy schema conversion can't express "array of objects"

**Symptom:** asking for flights (or, transitively, the Sales Dashboard — both go through the same `LangchainTool`-wrapped tool list) fails with a `400 INVALID_ARGUMENT` from the live Gemini API, in one of three shapes depending on how `display_flights(flights: ...)` is typed:

```
# list[Flight] (a nested TypedDict) —pydantic renders it as $ref/$defs:
pydantic_core._pydantic_core.ValidationError: 1 validation error for Schema
properties.flights.items.$ref
  Extra inputs are not permitted [type=extra_forbidden, input_value='#/$defs/Flight', ...]

# list[dict[str, Any]] — produces additionalProperties, which the live API rejects:
"Invalid JSON payload received. Unknown name \"additional_properties\" at
'tools[0].function_declarations[2].parameters.properties[0].value.items':
Cannot find field."

# An explicit, fully-flattened JSON-schema dict (no $ref, no additionalProperties) — still fails:
"* GenerateContentRequest.tools[0].function_declarations[2].parameters.properties[flights].items:
field predicate failed: $type == Type.ARRAY"
```

**Root cause:** none of these are really three separate bugs — they're three symptoms of the same thing. `google.adk.integrations.langchain.LangchainTool` (used to run our shared LangChain `@tool` functions natively on ADK — see the fix in [L3's README](../L3%20-%20controlled%20genUI%20with%20useComponent%20hook/README.md#-troubleshooting)) builds its function declaration through ADK's **legacy** `Schema` proto type (`_automatic_function_calling_util.build_function_declaration_for_langchain`) whenever the wrapped LangChain tool has any `args_schema` set — which it always does, whether inferred from type hints or passed explicitly. That legacy path can't correctly express "array of objects with named fields" at all against the live Gemini Developer API, no matter how the schema is spelled — `$ref` is rejected, `additionalProperties` is rejected, and even a fully explicit, flat, correctly-typed schema still fails validation once actually sent over the wire.

ADK has a **second**, newer schema path — `parameters_json_schema` — used automatically by native `google.adk.tools.FunctionTool`s (not LangChain-wrapped ones). It accepts genuine JSON Schema as-is, `$ref`/`additionalProperties`/nested objects included, because Gemini's newer function-calling surface is designed to take arbitrary JSON Schema rather than Google's restricted `Schema` proto subset.

**Fix:** in [run_agent.py](run_agent.py), only `display_flights` (the tool with a nested array-of-objects parameter) is treated specially for ADK:

```python
from google.adk.tools import FunctionTool

def display_flights_adk(flights: list[dict[str, Any]]) -> dict[str, Any]:
    """Display flights as rich cards in a horizontal row.

    Args:
        flights: The flights to display. Each flight needs id, airline,
          airlineLogo (a URL), flightNumber, origin, destination, date,
          departureTime, arrivalTime, duration, status, and price.
    """
    return {"a2ui_operations": _flights_a2ui_operations(flights)}  # see next Gotcha for why a dict, not a string

display_flights_adk.__name__ = "display_flights"  # match the name the system prompt uses

tools=[
    LangchainTool(get_sales_data),   # simple schemas — LangchainTool is fine here
    LangchainTool(search_flights),
    FunctionTool(display_flights_adk),  # nested schema — native FunctionTool instead
]
```

The actual A2UI-rendering logic lives in one shared `_flights_a2ui_operations()` helper (returns the raw operations *list*), called by both the LangGraph tool (`display_flights`, back to its original notebook form — `flights: list[Flight]`, no special-casing needed since OpenAI has never had a problem with `$ref` — which wraps the list in `a2ui.render()`'s JSON string) and the ADK-only wrapper above (which wraps it in a plain `dict` instead — see the next Gotcha for why). Verified against the **real** Gemini API end-to-end (not just local schema construction, which had looked correct multiple times before and still failed live): "Search flights" now renders a full flight-card carousel with no errors on `AGENT_TYPE=adk` — confirmed visually in the browser, not just via clean log output.

If you add your own tools with array-of-object parameters and want them to run under ADK, use a native `google.adk.tools.FunctionTool` for those specifically rather than `LangchainTool` — reserve `LangchainTool` for tools with simple (scalar or argument-less) schemas.

### `display_flights` succeeds with no error under ADK, but nothing renders — a second, independent bug

**Symptom:** after the fix above, the tool call completes cleanly (`TOOL_CALL_RESULT`, no error), the agent even says *"I have displayed the available flights"* — but the frontend shows nothing.

**Root cause:** comparing the actual `TOOL_CALL_RESULT.content` between backends revealed the difference. LangGraph: `{"a2ui_operations": [...]}`. ADK: `{"result": "{\"a2ui_operations\": [...]}"}"` — **double-wrapped**, and the inner value is a JSON *string*, not an object. ADK's own function-calling spec requires a tool's result to be a `dict`; `google/adk/flows/llm_flows/functions.py::__build_response_event` auto-wraps any non-dict return value as `{"result": <value>}`. Since `display_flights_adk` returned `a2ui.render(...)`'s JSON *string* output, ADK wrapped it, burying `a2ui_operations` one level deeper than the runtime's A2UI-detection logic looks — so it never matches, and nothing renders, with no error anywhere because every individual step technically succeeded.

**Fix:** return a plain `dict` — `{"a2ui_operations": _flights_a2ui_operations(flights)}` — instead of the JSON string `a2ui.render()` produces. A `dict` return satisfies ADK's spec check directly, so it's never wrapped, and the shape reaching the runtime matches LangGraph's exactly.

This is a general lesson for any ADK tool meant to return `a2ui_operations` (or any other client-detected sentinel key): **return a `dict`, never a JSON-encoded string**, even though `copilotkit.a2ui.render()` itself returns a string (it's designed for frameworks — like LangGraph — whose `ToolMessage.content` is expected to be a string).

### `render_a2ui` never gets called under ADK at all — even though it's injected — because of a missing `AGUIToolset()`

**Symptom:** asking for "Sales Dashboard" produces no error and no tool call — the agent just calls `get_sales_data` and writes a text summary, never touching any A2UI tool, even when the prompt explicitly says *"Call the generate_a2ui tool right now."*

**Root cause:** found by replaying the browser's actual captured request against a controlled backend instance with full logging (the request itself can't be inspected by browser dev tools alone — `render_a2ui` injection happens **inside** the Node.js runtime process, on the hop *after* the browser→runtime request, so intercepting `fetch()` in the browser only shows `tools: []`). The real Python-bound request does contain a genuine `render_a2ui` tool definition — `ag_ui_adk` logs `Tools from frontend: ['render_a2ui']` — but without an `AGUIToolset()` placeholder anywhere in `LlmAgent.tools`, `ag_ui_adk` has no mechanism to actually expose that frontend tool to the model: `[TOOL_SETUP] Agent assistant has 3 tools before replacement` / `... now has 3 tools after replacement` — the count never changes, `render_a2ui` is logged and then silently dropped.

This mirrors the exact mechanism from L3, just for a different tool: `AGUIToolset()` is a construction-time placeholder that `ADKAgent` swaps for a per-run `ClientProxyToolset` built from whatever frontend tools the AG-UI request carries — `useComponent()`-registered ones in L3, `render_a2ui` (injected by the JS runtime, not by any `useComponent()` call) here. The a2ui-specific backend-native `generate_a2ui` auto-injection (`plan_a2ui_injection`, gated on `forwardedProps.injectA2UITool`) is a completely separate mechanism that never triggers on this frontend version regardless — see step 2 of the notebook deep-dive above.

**Fix:** add `AGUIToolset()` to the ADK agent's `tools` list (see the code overview above). After this, `[TOOL_SETUP]` logs `Found AGUIToolset ... replacing with per-run ClientProxyToolset` and `Available AG-UI tools: ['render_a2ui']`, and Gemini correctly calls it — this alone is enough to prove the plumbing works, though the final dashboard mechanism ends up going a different route (see the next Gotcha for why `AGUIToolset()`/`render_a2ui` isn't actually what drives the working dashboard).

### The dashboard reaches the model and generates a valid tree — but the browser still shows "Catalog not found: sales_dashboard" / "Cannot create component root without a type"

**Symptom:** with the `AGUIToolset()` fix in place, `render_a2ui` gets called, but the browser shows `A2UI render error: Catalog not found: sales_dashboard` (the model put the *surfaceId*'s value in the `catalogId` field) or `A2UI render error: Cannot create component root without a type` (the root component is missing its `component` field) — reproduced with both `gemini-3.5-flash-lite` and `gemini-3.5-flash`.

**First hypothesis (wrong): a Gemini formatting problem.** The JS-injected `render_a2ui` tool's schema types `components` as a bare `array` of `object` and has no `catalogId` enum — it relies on *textual* context guidance rather than schema enforcement, and it seemed plausible that weaker/faster Gemini tiers just don't follow that reliably. A targeted instruction reminder ("catalogId MUST be exactly `copilotkit://app-dashboard-catalog`") reduced but did not eliminate the failures, which was the first sign this wasn't really about Gemini's output at all.

**Actual root cause: a cross-package tool-name collision, confirmed by instrumenting the exact function that decides the catalog ID.** `ag_ui_adk` supports a **second**, independent mechanism for A2UI: `ADKAgent(a2ui={"inject_a2ui_tool": True, ...})` forces its own backend-native `generate_a2ui` tool onto the model (bypassing the JS-injected `render_a2ui` entirely, and unlocking `default_catalog_id` and a `recovery` validate→retry loop — exactly what's needed here). Monkey-patching `ag_ui_a2ui_toolkit.build_a2ui_envelope` to print its actual runtime arguments proved the **final result was always correct**: `default_catalog_id param: 'copilotkit://app-dashboard-catalog'`, `is_update: False`, `prior: None`. The bug was never in what Gemini generated.

The real cause: `ag_ui_adk`'s internal nested subagent tool call — the one that streams the actual component tree — is **also literally named `render_a2ui`** (an ADK implementation detail, hardcoded as `_RENDER_A2UI_NAME`). The CopilotKit JS runtime's `A2UIMiddleware` watches the SSE stream for *any* tool call named `render_a2ui` (`a2uiToolNames`, defaults to `["render_a2ui"]`) to progressively build a UI snapshot **as its arguments stream in**, before the call resolves. That inner tool's schema deliberately has no `catalogId` parameter — "catalog ownership stays with the host; the subagent never picks a catalog" — but the JS middleware doesn't know that; seeing no `catalogId` in the streaming args, it defaults to the public basic catalog (`https://a2ui.org/specification/v0_9/basic_catalog.json`) and renders a broken surface immediately. This happens *before* the correct, fully-resolved result (with the right catalog ID, built by `build_a2ui_envelope`) ever reaches the frontend — and once the premature error renders, the correct follow-up update doesn't recover it.

This explains every earlier symptom: standalone ASGI tests bypassing the Node.js runtime entirely (going straight to the Python backend) never hit this, since there's no JS middleware in that path to misfire — they were 3/3 clean. Every real browser test, going through the full stack, failed the same way regardless of thread freshness or backend process restarts, because the JS middleware intercepts *any* stream carrying a `render_a2ui`-named call, unconditionally.

**Fix (two parts, both required):**

1. **Python** — `create_adk_app()` configures `ADKAgent(a2ui={"inject_a2ui_tool": True, "default_catalog_id": CATALOG_ID, "recovery": {"maxAttempts": 3}})` (shown in the code overview above) — the backend-native path, with an explicit catalog binding and automatic retry on a malformed tree.
2. **Frontend** — [frontend/server.ts](frontend/server.ts) sets `a2ui: { injectA2UITool: true, a2uiToolNames: [] }`. The empty array disables *only* the progressive/args-streaming interception that collides with `ag_ui_adk`'s inner tool name; the middleware still detects and renders `a2ui_operations` from any tool's **final** result, per its own documented fallback ("will still detect and render any valid A2UI JSON in the event stream"). This is what actually matters — the final result was correct all along.

**Verified live, repeatedly, after both fixes:** 3/3 clean dashboard renders in the browser (metrics, bar chart, donut chart, even a data table on one run) and — confirmed separately — "Search flights" is unaffected by the `server.ts` change (it never used `render_a2ui` in the first place).

If you hit a similar "client renders something wrong even though my tool's result looks right" symptom with any AG-UI integration, check whether your framework's internal tool-call naming happens to collide with whatever name the CopilotKit runtime's `A2UIMiddleware` (or any other name-based interception) is watching for.

### A latent, unrelated issue if you switch to `AGENT_TYPE=langgraph`

While verifying the fix above, testing the LangGraph path against whatever model `OPENAI_MODEL` in `.env` resolves to failed with:

```
openai.BadRequestError: Error code: 400 - {'error': {'message': "Function tools with reasoning_effort
are not supported for <model> in /v1/chat/completions. To use function tools, use /v1/responses or
set reasoning_effort to 'none'.", ...}}
```

This is unrelated to A2UI or schemas — some reasoning-model configurations reject function/tool calling entirely on the `/v1/chat/completions` endpoint that `ChatOpenAI` uses by default. It isn't hit while `AGENT_TYPE=adk` (the default here), but would surface if you switch to LangGraph with such a model configured. `gpt-5.4-mini` (this script's built-in fallback default) and `gpt-4o-mini` were both confirmed to work fine with tool calling here; if you hit the error above, point `OPENAI_MODEL` at one of those instead.

### `npm run dev` doesn't launch the frontend at all (Windows)

**Symptom:** `uv run python run_agent.py` starts the backend fine, but `npm run dev` never opens port 3004 — it just hangs.

**Root cause:** [frontend/package.json](frontend/package.json)'s `dev` script was `node --import tsx/esm watch-server.ts & vite`. The `&` is a POSIX background operator; on Windows, `npm run` shells out to `cmd.exe`, where `&` is a plain command separator instead. So `vite` never started concurrently — it waited for `watch-server.ts` to exit, which runs forever. This is the same Windows incompatibility already fixed in L2 and L3 (see their READMEs' *Fixes Applied for Windows Compatibility* sections) but not carried over to this lesson's scaffold. Fixed by switching to the same cross-platform runner:

```json
"dev": "npx --yes concurrently \"node --import tsx/esm watch-server.ts\" \"vite\"",
```

### `npm run dev` launches, but the chat UI is on port 5173, not 3004

**Symptom:** with the fix above applied, the servers start, but the browser needs `http://localhost:5173` instead of the documented `http://localhost:3004`.

**Root cause:** [frontend/vite.config.ts](frontend/vite.config.ts) never set a `server.port` — only `strictPort: true` (which just makes Vite fail instead of auto-incrementing if its port *is* taken; it doesn't set what that port is). Vite's own default is 5173. Inside the notebook this is invisible because `helper.py`'s `start_frontend(port)` always launches with an explicit CLI flag (`npm run dev -- --port 3004`); a bare `npm run dev` from the terminal has no such flag. Fixed by pinning the port directly in the config, so the plain command documented above just works:

```ts
server: {
  host: "0.0.0.0",
  port: 3004,          // 👈 added
  allowedHosts: true,
  strictPort: true,
  proxy: { "/api/copilotkit": "http://localhost:4004" },
},
```

Verified end-to-end after both fixes: `npm run dev` brings up Vite on `:3004` and the CopilotKit runtime on `:4004`; `http://localhost:3004/api/copilotkit/info` correctly reports the `default` agent with `a2uiEnabled: true`; and the chat UI renders with both the "Sales Dashboard" and "Search flights" suggestion buttons.
