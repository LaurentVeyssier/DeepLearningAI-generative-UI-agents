# Lesson 3: Controlled Generative UI with the `useComponent` Hook

Welcome to **Lesson 3** of the *Generative UI Agents* course. This document provides a comprehensive guide explaining controlled generative UI, how React UI components are registered as agent tools, and how to run the standalone agent backend using [run_agent.py](run_agent.py).

---

## 🎨 What is Controlled Generative UI?

In **Controlled Generative UI**, the agent backend does not generate arbitrary HTML or CSS. Instead:
1. You author polished React components on the frontend (`FlightCard`, `PieChart`, `ShowMyName`).
2. You register them as available frontend tools using the `useComponent()` hook in React.
3. The agent receives these tool definitions via `CopilotKitMiddleware`.
4. When requested, the agent picks a tool and passes validated JSON arguments (matching a Zod schema).
5. The React frontend renders the component dynamically inside the chat interface!

```
┌───────────────────────────────────────────────────────────────┐
│                    React Chat Interface                       │
│  useComponent({ name: "pieChart", render: PieChart, ... })    │
└───────────────────────────────┬───────────────────────────────┘
                                │ Registers UI Tool Schemas
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                  CopilotRuntime (Node.js)                     │
│  - Routes chat & tool call streams between UI and Python      │
└───────────────────────────────┬───────────────────────────────┘
                                │ AG-UI Protocol
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                 Python Agent Backend (FastAPI)                │
│  - Executes query_data tool (db.csv)                          │
│  - Selects frontend tool (e.g. pieChart, flightCard)          │
└───────────────────────────────────────────────────────────────┘
```

---

## 🛠 Registered Frontend Components ([frontend/src/App.tsx](frontend/src/App.tsx))

The React application registers three UI components using `useComponent()`:

### 1. `showMyName`
```tsx
useComponent({
  name: "showMyName",
  description: "Show the user's name in a card",
  parameters: z.object({ name: z.string() }),
  render: ({ name }) => <div className="bg-blue-500 p-4">Hi, {name}!</div>,
});
```

### 2. `pieChart`
```tsx
useComponent({
  name: "pieChart",
  description: "Controlled Generative UI that displays data as a pie chart.",
  parameters: PieChartProps,
  render: PieChart,
});
```

### 3. `flightCard`
```tsx
useComponent({
  name: "flightCard",
  description: "Controlled Generative UI that displays a single flight summary card.",
  parameters: FlightCardProps,
  render: FlightCard,
});
```

---

## 🚀 Standalone Runner Script ([run_agent.py](run_agent.py))

The standalone runner [run_agent.py](run_agent.py) launches the L3 FastAPI agent backend on **Port 8003**, supporting both LangGraph (OpenAI) and Google ADK (Gemini).

### Key Features:
* **`query_data` Tool**: Includes the backend CSV reader tool for querying dataset rows from [db.csv](db.csv).
* **System Instruction**: Guides the agent to invoke `query_data` first for data requests and prefer matching UI tools (`pieChart`, `flightCard`, `showMyName`).
* **Dual Agent Support**: Switch between `AGENT_TYPE = "langgraph"` (OpenAI) and `AGENT_TYPE = "adk"` (Google Gemini).

> **Note:** the two agent types wire up frontend tools very differently — see [Troubleshooting](#-troubleshooting) below before assuming the two paths are interchangeable.

---

## 💻 How to Run Lesson 3

### Step 1: Start the Python Backend Server
In a terminal, run:

```bash
# Run LangGraph / OpenAI Agent (Default - Port 8003)
uv run python run_agent.py

# OR Run Google ADK / Gemini Agent (Port 8003)
AGENT_TYPE=adk uv run python run_agent.py
```

### Step 2: Start the Frontend Application
In a second terminal, run:

```bash
cd frontend
npm run dev
```

### Step 3: Try Prompting in the Chat Interface
Open `http://localhost:3003` in your browser and test these prompts:
* *"Show my name as Alex"* (Triggers `showMyName`)
* *"Show a pie chart of dataset categories"* (Calls `query_data` $\rightarrow$ triggers `pieChart`)
* *"Show me a flight card for flight AA123"* (Triggers `flightCard`)

---

## 🐞 Troubleshooting

### `Tool 'frontend:showMyName' not found. Available tools: ` when running `AGENT_TYPE=adk`

**Symptom:** the browser console shows a CopilotKit `agent_run_error_event` /
`BACKGROUND_EXECUTION_ERROR` with the message:

```
Tool 'frontend:showMyName' not found. Available tools:
Possible causes:
  1. LLM hallucinated the function name - review agent instruction clarity
  2. Tool not registered - verify agent.tools list
  3. Name mismatch - check for typos
```

`showMyName` renders partially (e.g. `Hi, l`) before the error appears, and
`pieChart`/`flightCard` never render at all.

**Root cause:** that error string is raised verbatim by Google ADK's own
dispatcher (`google/adk/flows/llm_flows/functions.py::_get_tool`) — it isn't a
CopilotKit error. `create_adk_app()` in [run_agent.py](run_agent.py) built the
`LlmAgent` with no `tools` list at all:

```python
gemini_agent = LlmAgent(
    name="assistant",
    model=model_name,
    instruction=(...),  # tells Gemini to call pieChart / flightCard / showMyName by name
)
```

The `ag_ui_adk` package only exposes the frontend's `useComponent()`-registered
tools to the model if the agent declares an `AGUIToolset()` placeholder in its
`tools` list — at run time, `ADKAgent` swaps that placeholder for a
`ClientProxyToolset` built from the tools the CopilotKit frontend actually
registered. Without it, Gemini has zero real tools to call, but the system
instruction still tells it to call `pieChart`, `flightCard`, and `showMyName`
by name — so it does, and ADK rejects the call as an unknown/hallucinated
function.

The partial `showMyName` render happens because CopilotKit's frontend
optimistically renders from the streamed `ToolCallArgsEvent` as soon as
`useComponent`'s locally-registered renderer matches the tool name — it
doesn't wait for the backend to confirm the tool exists. The run then fails
server-side once ADK tries to actually resolve the call.

**Fix:** declare `AGUIToolset()` on the ADK agent, per the `ag_ui_adk`
package's own documented pattern:

```python
from ag_ui_adk import ADKAgent, AGUIToolset, add_adk_fastapi_endpoint
from google.adk.agents import LlmAgent

gemini_agent = LlmAgent(
    name="assistant",
    model=model_name,
    instruction=(...),
    tools=[
        # Placeholder swapped per-run for the frontend's registered
        # showMyName/pieChart/flightCard tools.
        AGUIToolset(),
    ],
)
```

This is already applied in [run_agent.py](run_agent.py).

### Why doesn't the LangGraph path need this fix?

`AGENT_TYPE=langgraph` and `AGENT_TYPE=adk` wire up frontend tools through
completely different mechanisms:

| | LangGraph (`ag_ui_langgraph` + `CopilotKitMiddleware`) | ADK (`ag_ui_adk`) |
|---|---|---|
| **Where frontend tools come from** | Read fresh off every AG-UI request (`input.tools`) and merged into `state["copilotkit"]["actions"]` | Bound to the agent's `tools` list; needs a static placeholder to know where to inject them |
| **Declaration required in agent code** | None — `middleware=[CopilotKitMiddleware()]` is enough | `AGUIToolset()` must be listed in `LlmAgent.tools` |
| **Unknown-tool-call handling** | `CopilotKitMiddleware.after_model` strips frontend tool calls from the message *before* LangGraph's `ToolNode` ever sees them | ADK dispatches the call directly against `agent.tools`; if it's missing, `_get_tool` raises |

`create_langgraph_app()` already passes `middleware=[CopilotKitMiddleware()]`,
which merges the frontend's registered tools into the model call on every
turn automatically — no equivalent of `AGUIToolset()` is needed there. If you
see similar "tool not found" errors while running `AGENT_TYPE=langgraph`,
double-check you're not accidentally pointed at an ADK server on the same
port — the failure mode above is specific to the ADK integration.
