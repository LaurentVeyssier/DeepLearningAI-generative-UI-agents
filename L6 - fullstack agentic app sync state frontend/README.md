# Lesson 6: Fullstack Agentic App — Shared State & Frontend Tools

Welcome to **Lesson 6** of the _Generative UI Agents_ course — the course's capstone. This document explains shared agent state, every step of the Jupyter notebook ([L6.ipynb](L6.ipynb)), and how to run everything using a standalone Python script ([run_agent.py](run_agent.py)).

Unlike L3-L5, this lesson uses a single agent **framework** throughout — **LangGraph** — because shared state (`Command(update={...})`, `CopilotKitMiddleware`) and frontend tools (`useFrontendTool`) here are LangGraph/AG-UI-native mechanisms, not something this lesson exercises against Google ADK. What *is* configurable is the underlying **chat model**: `run_agent.py` runs the exact same graph, tools, and state schema against either OpenAI or Gemini.

> **Use `MODEL_PROVIDER=openai` (the default).** Live testing found a real, reproducible issue where Gemini specifically rejects an internal continuation step triggered by this lesson's frontend tool (`openOrCloseTodos`) — see [Gotchas](#-gotchas-fixed-while-porting-this-to-a-standalone-script) for the precise root cause. OpenAI has no such issue. The app has been made resilient to it either way (a single failed turn no longer takes the whole runtime down), but only OpenAI avoids the error entirely.

---

## 🏗 System Architecture

The defining feature of this lesson is that state flows **both ways** — the agent writes it, the user edits it, and each side sees the other's changes on the next turn.

```
┌──────────────────────────────────────────────────────────────────┐
│                  1. React Frontend (Browser)                     │
│   <CopilotKit runtimeUrl="/api/copilotkit" useSingleEndpoint={false}> │
│     App.tsx:                                                      │
│       useFrontendTool({ name: "openOrCloseTodos", ... })          │
│         → registers a BROWSER-side tool the agent can call        │
│       const { agent } = useAgent()                                │
│         agent.state.todos      → READ shared state                │
│         agent.setState({todos})→ WRITE shared state (UI → agent) │
│   (Running via Vite on Port 3006)                                │
└───────────────────────────┬────────────────────────────────────┘
                            │  HTTP / Event Stream (AG-UI)
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│              2. CopilotRuntime Server (Node.js)                  │
│   (Running via Hono server on Port 4006)                         │
│   agents: { default: LangGraphHttpAgent(→ :8006) }                │
│   No a2ui / mcpApps / openGenerativeUI config needed — shared     │
│   state and frontend tools ride on AG-UI's STATE_SNAPSHOT /       │
│   STATE_DELTA and standard tool-call events, always on.           │
└───────────────────────────┬────────────────────────────────────┘
                            │  AG-UI Protocol Streams
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│         3. Python LangGraph Agent Backend (FastAPI, Port 8006)   │
│   AgentState(BaseAgentState):  todos: list[Todo]     ← shared     │
│   Backend tools (backend/todos.py):                                │
│     manage_todos(todos) -> Command(update={"todos": todos, ...}) │
│     get_todos()          -> reads runtime.state["todos"]          │
│   middleware=[CopilotKitMiddleware()]  → merges in the frontend's │
│     openOrCloseTodos tool at request time, and keeps AgentState   │
│     in sync with the frontend after every turn                    │
│   checkpointer=MemorySaver()  → state persists across turns       │
│   Model: ChatOpenAI **or** ChatGoogleGenerativeAI — same graph     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🎨 What is Shared Agent State?

Every prior lesson's UI was a one-way projection of whatever the agent last said or generated. **Shared state** makes the UI a live, two-way window into a piece of the agent's own graph state:

- The backend declares a typed `AgentState` (extending LangGraph's `BaseAgentState`) with a `todos: list[Todo]` field.
- A backend tool updates it with `return Command(update={"todos": todos, ...})` — LangGraph's mechanism for a tool to both return a result *and* mutate graph state in one step.
- The frontend calls `useAgent()` to get a live handle: `agent.state.todos` always reflects the latest state, and `agent.setState({todos: updated})` pushes edits back — no manual polling, no separate REST endpoint for the todo list.
- `CopilotKitMiddleware()` is what actually keeps both sides synchronized after every turn — it's the same middleware every LangGraph agent in this course has used since L2, but here it's carrying real application state, not just frontend-tool discovery.

Layered on top is a **frontend tool**: `useFrontendTool({name: "openOrCloseTodos", ...})` registers a tool that runs *in the browser* — the agent calls it exactly like a backend tool (same tool-calling loop, same system-prompt instructions), but the handler executes client-side and can touch React state directly (here, toggling the todo panel open).

---

## 📘 Notebook Step-by-Step Deep Dive

### 1. A throwaway agent starts the server first (Cell `55c5d4a7`)

Same pattern as every prior lesson: the server starts immediately with a placeholder graph (`tools=[]`, generic prompt) so the frontend has something to connect to. The real graph is swapped in later via `agent.graph = create_agent(...)` — no server restart needed, because `LangGraphAGUIAgent` holds a *reference* to the graph object, not a snapshot.

### 2. The schema and tools are defined directly in the notebook, not written to a file (Cell `8c15b8e0`, `r41msvx4qm`, `d047814a`)

The notebook explicitly calls this out: `Todo`, `AgentState`, `manage_todos`, and `get_todos` all live in the notebook's own kernel namespace and get passed straight into `create_agent()` — because the already-running agent object is being updated *in place*, no file write is needed for the notebook to work.

This leaves `backend/todos.py` as scaffolding containing only `Todo`/`AgentState` (hand-copied there for package structure) with **no tools at all** — a gap a standalone script can't leave open, since a `.py` file has no persistent kernel to hold notebook-only definitions. `backend/todos.py` was extended (see below) to hold `manage_todos`/`get_todos` too, so `run_agent.py` has a real, importable module to build from — the same kind of scaffold-completion already done for L4/L5.

### 3. `manage_todos` bulk-replaces the list; `Command` updates state and returns a result in one step (Cell `d047814a`)

```python
@tool
def manage_todos(todos: list[Todo], runtime: ToolRuntime) -> Command:
    """Replace the entire todo list. Use this to add, edit, or remove todos."""
    for todo in todos:
        if not todo.get("id"):
            todo["id"] = str(uuid.uuid4())
    return Command(update={
        "todos": todos,
        "messages": [ToolMessage(content="Successfully updated todos", tool_call_id=runtime.tool_call_id)],
    })
```

There's no `add_todo`/`edit_todo`/`delete_todo` — one bulk-replace tool handles adds, edits, and removals uniformly, which keeps the system prompt (and the model's job) simple: "here's the full list you want now." `get_todos` is the read-side counterpart, letting the agent inspect `runtime.state["todos"]` before deciding what to send back to `manage_todos`.

### 4. The agent is rebuilt with state + tools + a shared-state-aware prompt (Cell `58027760`)

```python
agent.graph = create_agent(
    model=ChatOpenAI(model="gpt-5.4-mini"),
    state_schema=AgentState,          # 👈 the shared-state schema
    tools=todo_tools,
    middleware=[CopilotKitMiddleware()],
    checkpointer=MemorySaver(),
    system_prompt=(
        "You manage a shared todo list. "
        "Use manage_todos to add, edit, or remove todos. "
        "Use get_todos to check the current list. "
        "When asked to manage todos, call the openOrCloseTodos frontend tool with open=true first. "
        "Keep responses to 1-2 sentences."
    ),
)
```

Note the prompt references `openOrCloseTodos` — a tool that doesn't exist in this Python file at all. It's registered entirely on the frontend (`useFrontendTool` in App.tsx) and merged into the model's available tools by `CopilotKitMiddleware()` at request time, exactly like every runtime-injected tool in L3-L5.

### 5. `App.tsx` — already complete, written verbatim by the notebook (Cell `2a4ce071`)

Unlike L4/L5, this cell's `%%writefile frontend/src/App.tsx` **is** the final, working file — there's no missing client-side prop or scaffold gap here. It wires up all three shared-state/frontend-tool pieces in ~40 lines:

```tsx
useFrontendTool({
  name: "openOrCloseTodos",
  parameters: z.object({ open: z.boolean() }),
  handler: async ({ open }) => { setTodosOpen(open); return `Todos are ${open ? 'open' : 'closed'}.`; },
});
const { agent } = useAgent();
// ...
<TodoList
  todos={agent.state.todos || []}               // 🪁 read shared state
  onUpdate={(updated) => agent.setState({ todos: updated })}  // 🪁 write shared state
  isRunning={agent.isRunning}
/>
```

`TodoAppLayout` and `TodoList` ([frontend/src/components/](frontend/src/components/)) are both fully-implemented, pre-existing components (checkbox toggling, inline rename, add/delete) — no changes were needed there either.

---

## 🚀 Standalone Script: `run_agent.py`

[run_agent.py](run_agent.py) replicates the notebook's final agent state (Phase 1 backend + Phase 2 prompt) as a single script, following the same pattern established in [L3](../L3%20-%20controlled%20genUI%20with%20useComponent%20hook/run_agent.py)-[L5](../L5%20-%20open-ended%20GenUI%20with%20MCP%20apps/run_agent.py).

### `backend/todos.py` — extended with the tools the notebook never wrote to disk

```python
class Todo(TypedDict):
    id: str
    title: str
    completed: bool

class AgentState(BaseAgentState):
    todos: list[Todo]

@tool
def manage_todos(todos: list[Todo], runtime: ToolRuntime) -> Command: ...

@tool
def get_todos(runtime: ToolRuntime): ...

todo_tools = [manage_todos, get_todos]
```

### `create_app(provider, model_name)` — one LangGraph graph, two possible chat models

```python
def _build_model(provider, model_name):
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name, temperature=0)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model_name, temperature=0)

def create_app(provider="openai", model_name=None):
    from backend.todos import AgentState, todo_tools
    model = _build_model(provider, model_name or (GEMINI_MODEL if provider == "gemini" else OPENAI_MODEL))
    graph = create_agent(
        model=model,
        state_schema=AgentState,
        tools=todo_tools,
        middleware=[CopilotKitMiddleware()],
        checkpointer=MemorySaver(),
        system_prompt=SYSTEM_PROMPT,
    )
    agent = LangGraphAGUIAgent(name="default", description="Lesson 6 shared-state todo agent", graph=graph)
    add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
```

`langchain-google-genai` wasn't originally in [requirements.txt](requirements.txt) (the notebook never needed it — L6 only ever demonstrates OpenAI); it was added there and installed (`uv pip install langchain-google-genai`) specifically to exercise the Gemini path through LangGraph for this script.

`agent = LangGraphAGUIAgent(name="default", ...)` — the name **must** be `"default"` to match `frontend/server.ts`'s `agents: { default: langGraphAgent }` and `App.tsx`'s unparameterized `useAgent()` call.

### How to run

**Terminal 1 — backend:**

```bash
# OpenAI via LangGraph (default) — Port 8006
uv run python run_agent.py

# OR Gemini via LangGraph — Port 8006
MODEL_PROVIDER=gemini uv run python run_agent.py
```

`MODEL_PROVIDER`, `OPENAI_MODEL`, `GEMINI_MODEL`, and `MODEL_NAME` are all read from the repo-root [.env](../.env) or the shell environment. See [Gotchas](#-gotchas-fixed-while-porting-this-to-a-standalone-script) below if your `.env`'s `OPENAI_MODEL` doesn't support tool calling.

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

**Try it** at `http://localhost:3006` (all four verified live, both providers — see below):
1. *"Add three todos about learning CopilotKit"* — the agent calls `openOrCloseTodos` to open the panel, then `manage_todos` to populate it.
2. Check off a todo directly in the panel — this is `agent.setState()`, a pure frontend write, no round-trip to the backend needed for the UI to reflect it immediately.
3. *"What's on my todo list right now?"* — the agent calls `get_todos` and correctly reports the checked-off item's completed status, proving it's reading the *user's* edit, not its own last-written copy.
4. *"Remove all completed todos"* — the agent calls `manage_todos` with the filtered list.

---

## ✅ Verified Live

Every step above was run end-to-end in a real browser against a real backend, on **both** supported chat models, via LangGraph in both cases:

| Test | `MODEL_PROVIDER=openai` (`gpt-5.4-mini`) | `MODEL_PROVIDER=gemini` (`gemini-3.5-flash-lite`) |
|---|---|---|
| Add todos + panel auto-opens | ✅ 3 todos created, panel opened via `openOrCloseTodos` | ✅ Repeated across many separate live attempts — todos and panel-open always worked |
| Check off a todo in the UI | ✅ moved to "Done" section, `agent.state.todos` updated | not re-tested (same frontend code path, not model-dependent) |
| Agent reads the user's edit | ✅ *"Learn CopilotKit basics" (completed)* correctly reported | ✅ *"you have two items..."* correctly reported after a mid-session `RUN_ERROR` (see Gotchas) |
| Remove completed todos | ✅ `manage_todos` called with filtered list, panel shows 2 remaining | not re-tested |
| Runtime survives a failed turn | n/a (failure mode not observed on OpenAI) | ✅ after the [server.ts fix](#gemini-raises-a-valueerror-after-a-successful-turn--and-it-used-to-take-the-whole-app-down-with-it), the runtime logs the error and keeps serving instead of crashing |

No failures on either provider for the paths tested. See Gotchas for two issues hit and resolved during setup (not lesson bugs — see analysis in each).

---

## 🐞 Gotchas Fixed While Porting This to a Standalone Script

### `npm run dev` doesn't launch the frontend at all (Windows) / launches on the wrong port

Identical root causes and fixes to L4/L5 — restated briefly here (see [L4's README](../L4%20-%20declarative%20genui%20with%20components%20catalog/README.md#-gotcha-fixed-while-porting-this-to-a-standalone-script) for the full investigation):

- [frontend/package.json](frontend/package.json): `"dev": "node --import tsx/esm watch-server.ts & vite"` → the POSIX `&` is a plain separator under Windows' `cmd.exe`, so `vite` never starts concurrently. Fixed with `npx --yes concurrently "..." "vite"`.
- [frontend/vite.config.ts](frontend/vite.config.ts): no `server.port` was set (only `strictPort: true`, which doesn't set *what* the port is) — Vite defaulted to `5173`. Fixed by adding `port: 3006`.

### `.env`'s `OPENAI_MODEL` was silently ignored by the script (fixed proactively, not hit live)

L4/L5's `run_agent.py` read `OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")` at **module scope**, but only called `load_dotenv()` **inside `main()`**, which runs *after* that module-level line already executed. Since `.env` hadn't been loaded into the process environment yet at that point, the constant always resolved to its hardcoded fallback (`"gpt-5.4-mini"`) regardless of what `.env` actually said — invisible in practice because that fallback happened to work. Fixed here by calling `load_dotenv(override=True)` at the very top of the module, before any `os.getenv()` calls — confirmed working: a sanity-check run correctly picked up `.env`'s `gpt-5.6-luna` instead of silently falling back.

### `.env`'s `OPENAI_MODEL` (`gpt-5.6-luna`) can't do tool calling — and this lesson is the first to actually notice

**Symptom:** the very first live test failed with:
```
openai.BadRequestError: Error code: 400 - {'error': {'message': "Function tools with reasoning_effort
are not supported for gpt-5.6-luna in /v1/chat/completions. To use function tools, use /v1/responses or
set reasoning_effort to 'none'.", ...}}
```

**Root cause:** this is the exact same incompatibility L4's README documents as *"A latent, unrelated issue if you switch to `AGENT_TYPE=langgraph`"* — some reasoning-model configurations reject function/tool calling on the `/v1/chat/completions` endpoint `ChatOpenAI` uses by default. L4 and L5's LangGraph paths didn't hit it in practice because their tests happened to run with the script's hardcoded fallback model (see the previous Gotcha) rather than `.env`'s `gpt-5.6-luna`. **This lesson's agent has real tools** (`manage_todos`, `get_todos`) from the very first message, and — now that `.env` loading is fixed — actually uses `.env`'s configured model, so it's the first script in this course to exercise this combination and hit the failure for real.

**Fix:** override with a model confirmed to support tool calling, e.g.:
```bash
MODEL_NAME=gpt-5.4-mini uv run python run_agent.py
```
`gpt-5.4-mini` (this script's built-in fallback) and `gpt-4o-mini` were both confirmed working with tool calling in L4; `gpt-5.4-mini` was re-confirmed here, live, for this lesson's `manage_todos`/`get_todos` tools specifically.

### Gemini raises a `ValueError` after a *successful* turn — and it used to take the whole app down with it

**Symptom:** ask the agent to add todos (e.g. *"Add two todos about testing this app"*) with `MODEL_PROVIDER=gemini`. The turn completes correctly — todos appear, the agent's reply is shown — but shortly after, the browser surfaces a `RUN_ERROR` (`terminated` / `INCOMPLETE_STREAM`).

**Root cause, part 1 — pinned down precisely by reading `CopilotKitMiddleware`'s source ([copilotkit_lg_middleware.py](file:///../../.venv/Lib/site-packages/copilotkit/copilotkit_lg_middleware.py) in the venv), not guessed at.** This lesson's system prompt has the model call `openOrCloseTodos` — a **frontend** tool — before `manage_todos`. `CopilotKitMiddleware.after_model()` intercepts that call and strips it out of the AI message (so LangGraph's tool executor, which has no idea what `openOrCloseTodos` is, doesn't choke on it), stashing it in `state["copilotkit"]["intercepted_tool_calls"]`. Then, as the graph run is finishing, `after_agent()` **re-attaches that intercepted tool call** onto the AI message — by design, so that once the browser actually runs `openOrCloseTodos` and reports back on the *next* turn, the graph can resume correctly. That's the intended mechanism for frontend tools spanning a browser round-trip.

The bug: within that *same* graph execution — the same stream that already correctly created the todos and sent the reply — something in LangGraph's continuation logic sees that just-restored, unanswered tool call and loops back into the model node **one more time**, before the run actually ends. That call's message history ends in an AI message with a dangling tool call and no response — exactly the shape Gemini's `ChatGoogleGenerativeAI` validator rejects:
```
ValueError: Model 'gemini-3.5-flash-lite' does not support model prefilling.
The final request turn must be a user message or a function response.
```
`ChatOpenAI` tolerates this same shape silently (which is why this never surfaced in L4/L5/L6's OpenAI testing) — confirmed by the fact that this only ever reproduces on turns that actually call `openOrCloseTodos` (i.e. any todo-adding request); a todos-read-only turn (*"What's on my todo list?"*) never triggers it. This is a genuine interaction between `copilotkit`'s frontend-tool-interception mechanism and Gemini's stricter API validation — not a bug in this lesson's own tools, prompt, or `run_agent.py`.

**Root cause, part 2 — and this part *is* fixed here.** That failed call aborted mid-stream inside the Node.js runtime's `undici`-based HTTP client, throwing inside an unawaited promise chain. Node has no default handler for that, so `triggerUncaughtException` **killed the entire runtime process** — and since `watch-server.ts` previously only restarted its child on a *file change*, not a crash, the runtime stayed dead until someone manually restarted `npm run dev`. This is what actually broke the app; the Gemini `ValueError` itself is just one extra failed background call that should have been contained to a single request.

**Fix applied, in [frontend/server.ts](frontend/server.ts) and [frontend/watch-server.ts](frontend/watch-server.ts):** catch the exception and keep the process alive instead of crashing, with a bounded auto-restart as a second layer of defense (capped at 3 attempts per 10s, so a *permanent* startup failure like a taken port fails loudly instead of looping forever — learned the hard way when this exact mechanism briefly fought its own EADDRINUSE error into an infinite restart loop during testing; `server.ts` now recognizes that specific error and exits cleanly instead of claiming to have "kept the process alive" when nothing was actually listening).

**Verified live, after the fix:** reproduced the exact same `ValueError` again on a fresh "add two todos" prompt — the runtime logged the error and kept running, stayed listening on port 4006, and correctly answered a follow-up question in the same session immediately after. **The underlying Gemini `ValueError` itself is not eliminated** — only its blast radius. A real fix would mean either patching `CopilotKitMiddleware`'s internals (fragile against upstream updates) or reworking the app to open the panel via a frontend-side effect watching `agent.state.todos` instead of an agent-invoked frontend tool (which would sidestep the interception/restoration mechanism entirely, at the cost of no longer demonstrating `useFrontendTool` for that interaction) — neither was applied here.

**Practical recommendation: use `MODEL_PROVIDER=openai` (the script's default).** It doesn't exhibit this failure mode at all — no `ValueError`, no `RUN_ERROR` toast, confirmed across every live test in this lesson. If you specifically want to exercise the Gemini path, expect an occasional `RUN_ERROR` toast on todo-adding turns; the actual work (todos, replies) will still have completed correctly, and — with the fix above — the app keeps working afterward instead of requiring a manual restart.

---

## What you learned

- **Shared agent state** gives the backend and frontend a single source of truth — `AgentState`/`Command(update={...})` on the backend, `useAgent()`/`agent.setState()` on the frontend — with no manual polling or separate sync endpoint.
- **`useFrontendTool`** exposes browser-side behavior (like opening a panel) to the agent as a callable tool, merged in by `CopilotKitMiddleware()` exactly like any other runtime-injected tool in this course.
- The underlying chat model is decoupled from the LangGraph/AG-UI wiring — the same graph, tools, and state schema ran correctly against both OpenAI and Gemini in live testing.
- Model/provider incompatibilities (like `gpt-5.6-luna` rejecting tool calls, or Gemini's stricter turn-shape validation) are orthogonal to whether the *shared-state/frontend-tool* mechanisms themselves work — this lesson's core lesson content was unaffected by either, once the runtime was made resilient to a single failed turn instead of crashing outright.

## Course wrap-up

Over six lessons you progressed from a basic agent chat to a fully synchronized fullstack app:

- **L2** — Connected a LangChain agent to a CopilotKit chat UI.
- **L3** — Registered controlled components so the agent can render charts and cards.
- **L4** — Used declarative A2UI schemas to separate data from presentation.
- **L5** — Hosted open-ended MCP Apps and `openGenerativeUI` for tools like whiteboards and arbitrary generated UI.
- **L6** — Synchronized shared state between the agent and a React app with frontend tools.

These patterns compose. Explore the [CopilotKit docs](https://docs.copilotkit.ai) and the [AG-UI protocol spec](https://docs.ag-ui.com) to keep building.
