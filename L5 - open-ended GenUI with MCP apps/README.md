# Lesson 5: Open-Ended Generative UI with MCP Apps & `openGenerativeUI`

Welcome to **Lesson 5** of the _Generative UI Agents_ course. This document explains open-ended generative UI, every step of the Jupyter notebook ([L5.ipynb](L5.ipynb)), and how to run everything using a standalone Python script ([run_agent.py](run_agent.py)) — for both the LangGraph/OpenAI and Google ADK/Gemini agent paths.

> **Setting up ADK/Gemini?** Jump straight to [⚙️ Required Configuration for Google ADK / Gemini](#-required-configuration-for-google-adk--gemini) for the checklist — and then read [🐞 Known Limitation: `openGenerativeUI` is broken on ADK](#-known-limitation-opengenerativeui-is-broken-on-adk) before you rely on it for anything beyond Excalidraw. LangGraph/OpenAI needs none of the ADK-specific wiring and has **no known limitations** — every feature in this lesson works cleanly there.

---

## 🏗 System Architecture

Unlike every previous lesson, **no UI is registered anywhere in this app's own code** — no `useComponent()` hooks (L3), no component catalog (L4). Both visual capabilities are owned entirely by the CopilotKit *runtime* layer:

```
┌──────────────────────────────────────────────────────────────────┐
│                  1. React Frontend (Browser)                     │
│   <CopilotKit runtimeUrl="/api/copilotkit"                       │
│               openGenerativeUI={{}}>   👈 client-side opt-in     │
│       └── <CopilotChat />              (App.tsx has NO catalog,  │
│                                          NO useComponent() hooks) │
│   (Running via Vite on Port 3005)                                │
└───────────────────────────┬────────────────────────────────────┘
                            │  HTTP / Event Stream
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│              2. CopilotRuntime Server (Node.js)                  │
│   (Running via Hono server on Port 4005)                         │
│   - openGenerativeUI: true                                        │
│     → auto-injects a `generateSandboxedUi` tool. Model streams   │
│       raw HTML/CSS/JS; runtime renders it in a sandboxed,        │
│       double-iframe surface (no same-origin access). CSP allows  │
│       exactly 4 CDNs: cdnjs.cloudflare.com, esm.sh,               │
│       cdn.jsdelivr.net, unpkg.com.                                │
│   - mcpApps.servers: [{ url: "https://mcp.excalidraw.com" }]      │
│     → discovers Excalidraw's MCP App (a real MCP Apps extension  │
│       server — see below) and injects its `create_view` tool.    │
│       Rendering fetches a `ui://` HTML resource into a sandboxed │
│       iframe — a fundamentally different mechanism from above.   │
└───────────────────────────┬────────────────────────────────────┘
                            │  AG-UI Protocol Streams
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│               3. Python Agent Backend (FastAPI)                  │
│   - LangGraph / OpenAI Agent (Port 8005)                         │
│   OR                                                              │
│   - Google ADK / Gemini Agent (Port 8005)                        │
│   Backend tools: NONE. Every tool the model calls in this        │
│   lesson (`generateSandboxedUi`, `create_view`) is injected by   │
│   the runtime above, not declared in Python.                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🎨 What is Open-Ended Generative UI?

Controlled generative UI (L3) is one tool → one hand-authored component. Declarative generative UI (L4) is a fixed catalog the agent composes from. **Open-ended generative UI removes both constraints**: the agent can launch a full external application, or write arbitrary HTML/CSS/JS from scratch, on demand.

Two independent mechanisms deliver this, and this lesson uses **both**:

| | **MCP Apps** (Excalidraw) | **`openGenerativeUI`** (sandboxed HTML/CSS/JS) |
|---|---|---|
| **What it is** | An [MCP extension](https://modelcontextprotocol.io/extensions/apps/overview) (SEP-1865) that lets an MCP server ship a real interactive app (`ui://` HTML resource) alongside its tools | A CopilotKit-runtime-only mechanism — completely independent of MCP — that auto-injects a `generateSandboxedUi` tool letting the model author raw HTML/CSS/JS |
| **Server needed?** | Yes — a real MCP server that implements the Apps extension | No — no MCP server involved at all |
| **Config** | `mcpApps.servers: [{ type: "http", url, serverId }]` on `CopilotRuntime` | `openGenerativeUI: true` on `CopilotRuntime` **and** `openGenerativeUI={{}}` on the client `<CopilotKit>` provider (two-sided — see Gotchas) |
| **Used for in this lesson** | Whiteboard/architecture diagrams | Everything else (taco animations, Mermaid diagrams via CDN-loaded `mermaid.js`) |
| **ADK/Gemini status** | ✅ Fully working, verified live | ❌ **Broken on ADK** — verified live, root cause below. ✅ Fully working on LangGraph. |

### Why isn't Mermaid wired up as an MCP App?

The natural instinct is to connect Mermaid's own hosted MCP server (`mcp.mermaid.ai`) the same way Excalidraw is connected. This **does not work**: Mermaid's official server is a plain, data-returning MCP server — it has tools, but none of them are backed by a `ui://` HTML resource, because it doesn't implement the MCP Apps extension at all. `mcpApps` has nothing to render for it; the runtime would just get back text/JSON like any ordinary MCP tool call, not an embeddable app.

Rather than trying to bolt the MCP Apps extension onto a third-party server you don't control, this script takes the simpler, fully-supported path: the shared `SYSTEM_PROMPT` tells the agent to render Mermaid diagrams itself via `generateSandboxedUi` — putting the diagram source in a `<pre class="mermaid">` block and loading `mermaid.js` as an ES module from `cdn.jsdelivr.net` (one of the sandbox's 4 allowed CDNs), then calling `mermaid.initialize({ startOnLoad: true })`. No MCP server is involved in the Mermaid path at all — it's pure `openGenerativeUI`.

---

## ⚙️ Required Configuration for Google ADK / Gemini

Same underlying cause as every prior lesson's ADK section, restated for this lesson's specific tools:

| # | What | Where | Why |
|---|---|---|---|
| 1 | Add `AGUIToolset()` to `LlmAgent.tools` | `run_agent.py` | Both `generateSandboxedUi` and Excalidraw's `create_view` are injected by the CopilotKit **runtime**, not declared as Python tools. Without `AGUIToolset()`, `ag_ui_adk` logs them (`Tools from frontend: ['generateSandboxedUi', 'create_view']`) but never exposes them to Gemini — the agent just responds with text and never calls either tool. |

That's the *only* piece needed to get either tool **called** at all on ADK. Whether the result actually **renders** once called is a separate story — see the next section, because for one of the two tools, it currently does not.

```python
from ag_ui_adk import ADKAgent, AGUIToolset, add_adk_fastapi_endpoint
from google.adk.agents import LlmAgent

gemini_agent = LlmAgent(
    name="assistant",
    model=model_name,
    instruction=SYSTEM_PROMPT,
    tools=[AGUIToolset()],   # exposes generateSandboxedUi + create_view to Gemini
)
adk_agent = ADKAgent(adk_agent=gemini_agent, app_name="demo_app", user_id="demo_user", ...)
add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
```

Nothing else from L4's six-item ADK checklist applies here — there are no backend Python tools at all in this lesson, so `LangchainTool`/`FunctionTool` wrapping and dict-vs-string return values are moot.

---

## 🐞 Known Limitation: `openGenerativeUI` is broken on ADK

**Summary, verified live on both backends:** Excalidraw (MCP App) works correctly on **both** LangGraph and ADK. `openGenerativeUI` (`generateSandboxedUi` — tacos, Mermaid, or anything else routed through it) works correctly on **LangGraph** but renders an empty/incomplete shell on **ADK**. This is a limitation of `ag_ui_adk`'s current architecture, not a bug in this script — no configuration was found that fixes it.

### The two tools go through the identical ADK code path

Both `generateSandboxedUi` and `create_view` are proxied through `AGUIToolset()` → `ClientProxyToolset`. `ag_ui_adk` hardcodes **every** client-proxied tool as an ADK "long-running" (human-in-the-loop-style) tool — there is no per-tool override:

```
INFO  Initialized ClientProxyToolset with 2 tools (all long-running)
INFO  [GET_TOOLS] Created proxy tool for 'generateSandboxedUi' (long-running)
INFO  [GET_TOOLS] Created proxy tool for 'create_view' (long-running)
```

Confirmed via source inspection of `ag_ui_adk/client_proxy_tool.py`: `ClientProxyTool.__init__` unconditionally sets `is_long_running=True`, with a comment to the effect of "all client-side tools are long-running for architectural simplicity." Being long-running means: the model's function call is treated like an async human-approval step. ADK drains the call, adds it to a "pending" list, **ends the run**, and the client then automatically resumes with a synthesized tool result via a second, independent exec cycle:

```
INFO  LRO detected with partial=True, will drain until persistence completes
INFO  Added tool call JLmvRH0F to thread ... pending list
...
INFO  [EXEC] HITL_RESUME - thread=..., tool_results=['JLmvRH0F']
```

### Excalidraw survives this; `generateSandboxedUi` does not

**Excalidraw, live test** — prompt: *"Show me a simple network diagram of three routers, two laptops and a server using excalidraw"* (`AGENT_TYPE=adk`). Result: a fully rendered, labeled Excalidraw whiteboard (routers, laptops, server, arrows, title) — despite `create_view` going through the exact same `LRO detected` → pending-list → `HITL_RESUME` cycle logged above.

**`generateSandboxedUi`, live test #1** — prompt: *"Make it rain tacos!"* (`AGENT_TYPE=adk`). Result: a correctly-styled, correctly-sized 400px card `<div>` appears in the DOM — but with **zero children** and **zero `<iframe>` elements** anywhere on the page. No visual content at all, despite the agent's text response ("It's officially a Taco Storm!...") coming through fine.

**`generateSandboxedUi`, live test #2** — prompt: *"Draw a flowchart of a login process using mermaid"* (`AGENT_TYPE=adk`). Result: the card renders this time, with a title ("🔒 Login Process Flowchart") and — instead of a rendered diagram — the **raw Mermaid source text** printed as plain content (`flowchart TD / A([Start...`). The `<script>` that loads `mermaid.js` from the CDN and calls `mermaid.initialize()` never executes.

Both `generateSandboxedUi` failures are consistent with the same underlying cause: the tool's streamed argument sequence (`initialHeight → placeholderMessages → css → html → jsFunctions → jsExpressions`) is progressive by design — the frontend's sandboxed-UI renderer expects to keep receiving argument deltas as the model writes them. ADK's long-running "drain until persistence completes, then resume via a synthetic separate exec cycle" flow collapses that progressive stream: some prefix of the sequence lands (enough for a styled shell, sometimes enough for the static HTML/title text), but the pipeline is cut short before the `<script>`/JS execution stage ever arrives, and the model's *actual* final content is never delivered in a form the renderer can use. The **real difference is not "long-running vs. not"** — Excalidraw is long-running too and still works — it's that MCP Apps rendering only needs the tool's call **arguments** (a small, complete JSON blob identifying the view, sent early) to open a `ui://` resource in an iframe, while `openGenerativeUI` needs the tool's entire progressive delivery pipeline to complete, which ADK's proxy architecture does not preserve.

**Confirmed working on LangGraph, live, same prompts:** all three — tacos, Mermaid flowchart, and Excalidraw network diagram — render correctly and completely with `AGENT_TYPE=langgraph`. LangGraph's AG-UI adapter streams tool-call arguments directly, without an intermediate long-running/HITL-resume translation layer, so the full progressive sequence reaches the frontend intact.

### Practical takeaway

- **If you need `openGenerativeUI` (arbitrary HTML/CSS/JS, including the Mermaid pattern used here), use `AGENT_TYPE=langgraph`.** It is not currently reliable on ADK, and no configuration in `ag_ui_adk` (as of this writing) provides a bypass equivalent to L4's `ADKAgent(a2ui={...})` backend-native escape hatch — `generateSandboxedUi` has no such native ADK equivalent; it is inherently and only a JS-runtime-injected tool.
- **MCP Apps (Excalidraw) work fine on either backend.** If your use case is "launch a real external app," ADK is not a blocker.
- If a future `ag_ui_adk` release adds a per-tool override for the long-running designation (or preserves the full argument-streaming sequence through the HITL-resume cycle), this limitation would likely be resolved — worth re-testing on version upgrades.

---

## 📘 Notebook Step-by-Step Deep Dive

### 1. No backend tools anywhere (Cells 10–11)

Cell 10 starts the backend (`backend/server.py`'s `start_backend(port=8005)`) and cell 11 starts the frontend — both using a throwaway/placeholder agent construction, same pattern as prior lessons. Unlike L3/L4, no Python tool is ever declared in this notebook. Every capability comes from the frontend runtime config in the two `server.ts` cells below.

### 2. Connecting Excalidraw as an MCP App (Cell 17)

```ts
const runtime = new CopilotRuntime({
  agents: { default: appAgent },
  mcpApps: {
    servers: [
      { type: "http", url: "https://mcp.excalidraw.com", serverId: "example_mcp_server" },
    ],
  },
});
```

`mcpApps.servers` connects the runtime to one or more MCP servers exposing app tools. CopilotKit auto-discovers Excalidraw's tools and surfaces them to the model — no other wiring required on the frontend or backend.

### 3. Enabling `openGenerativeUI` (Cell 24)

```ts
const runtime = new CopilotRuntime({
  agents: { default: appAgent },
  openGenerativeUI: true,   // 👈 one line
  mcpApps: { servers: [ /* same as above */ ] },
});
```

One line on the server. **What the notebook doesn't show** (it's a static scaffold file, never `%%writefile`-generated with this line) is that the **client** side also needs an opt-in — [frontend/src/main.tsx](frontend/src/main.tsx) must pass `openGenerativeUI={{}}` to the `<CopilotKit>` provider:

```tsx
<CopilotKit runtimeUrl="/api/copilotkit" useSingleEndpoint={false} openGenerativeUI={{}}>
  <App />
</CopilotKit>
```

Without the client-side prop, the server still streams `generateSandboxedUi` calls, but the client has nothing registered to render them — the feature is silently half-wired. This mirrors the same "scaffold gap" pattern L4 had with `AGUIToolset()`: the notebook's `%%writefile` cells only ever touch `frontend/server.ts`, never `main.tsx`, so this one-line client addition has to be made by hand.

### 4. `App.tsx` — no catalog, no hooks

[frontend/src/App.tsx](frontend/src/App.tsx) is the simplest of any lesson so far:

```tsx
export const agentId = "default";
export default function App() {
  return <CopilotChat agentId={agentId} />;
}
```

No `useComponent()`, no catalog import — because there's nothing to register. Both Excalidraw and `generateSandboxedUi` are handled entirely by the runtime/provider layer above.

---

## 🚀 Standalone Script: `run_agent.py`

[run_agent.py](run_agent.py) replicates the notebook's final backend state as a single script supporting **both** agent frameworks, following the same pattern established in [L3](../L3%20-%20controlled%20genUI%20with%20useComponent%20hook/run_agent.py) and [L4](../L4%20-%20declarative%20genui%20with%20components%20catalog/run_agent.py).

### Shared system prompt, zero backend tools

Unlike every prior lesson, `run_agent.py` declares **no Python tools at all**. The shared `SYSTEM_PROMPT` tells the agent, in plain language:
- Use the sandbox UI tool (always wrapped in a 400px card) for any visual/interactive output — including Mermaid diagrams, which must load `mermaid.js` from `cdn.jsdelivr.net` as an ES module and call `mermaid.initialize({ startOnLoad: true })`.
- Use Excalidraw specifically for network/architecture/whiteboard-style diagrams.
- Otherwise, respond conversationally.

### `create_langgraph_app()` — OpenAI via LangGraph

```python
graph = create_agent(
    model=ChatOpenAI(model=model_name, temperature=0),
    tools=[],                              # nothing — every tool is runtime-injected
    middleware=[CopilotKitMiddleware()],
    checkpointer=MemorySaver(),
    system_prompt=SYSTEM_PROMPT,
)
agent = LangGraphAGUIAgent(name="app_agent", description="Lesson 5 open-ended generative UI agent", graph=graph)
add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
```

`CopilotKitMiddleware()` merges the runtime-injected `generateSandboxedUi` and `create_view` tools into the model's bound tools at request time — no extra wiring needed, and (per the Gotchas section) this is the path where both tools work reliably end to end.

### `create_adk_app()` — Gemini via Google ADK

```python
from ag_ui_adk import ADKAgent, AGUIToolset, add_adk_fastapi_endpoint
from google.adk.agents import LlmAgent

gemini_agent = LlmAgent(
    name="assistant",
    model=model_name,
    instruction=SYSTEM_PROMPT,
    tools=[AGUIToolset()],   # required — see Required Configuration above
)
adk_agent = ADKAgent(adk_agent=gemini_agent, app_name="demo_app", user_id="demo_user",
                     session_timeout_seconds=3600, use_in_memory_services=True)
add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
```

`AGUIToolset()` is required for Gemini to see either runtime-injected tool at all (see Required Configuration). Excalidraw works correctly through this path; `generateSandboxedUi` does not (see Known Limitation above).

### How to run

**Terminal 1 — backend:**

```bash
# LangGraph / OpenAI (default, and the ONLY backend with no known limitations) — Port 8005
uv run python run_agent.py

# OR Google ADK / Gemini — Port 8005 (Excalidraw works; openGenerativeUI does not — see Known Limitation)
AGENT_TYPE=adk uv run python run_agent.py
```

`AGENT_TYPE` (and `OPENAI_MODEL` / `GEMINI_MODEL`) are read from the repo-root [.env](../.env). Both agent types serve on the same port (8005), so [frontend/server.ts](frontend/server.ts) — always pointing `LangGraphHttpAgent` at `http://localhost:8005` — works unchanged for either backend.

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

**Try it** at `http://localhost:3005`:
* *"Make it rain tacos!"* → `openGenerativeUI`. ✅ LangGraph. ❌ ADK (empty card, see Known Limitation).
* *"Draw a flowchart of a login process using mermaid"* → `openGenerativeUI` + CDN-loaded `mermaid.js`. ✅ LangGraph. ❌ ADK (raw source text, no rendered diagram).
* *"Show me a simple network diagram of three routers, two laptops and a server using excalidraw"* → MCP App. ✅ LangGraph. ✅ ADK.

---

## 🐞 Other Gotchas Fixed While Porting This to a Standalone Script

### `npm run dev` doesn't launch the frontend at all (Windows)

**Symptom:** the backend starts fine, but `npm run dev` never opens port 3005 — it just hangs.

**Root cause:** [frontend/package.json](frontend/package.json)'s `dev` script was `node --import tsx/esm watch-server.ts & vite`. The `&` is a POSIX background operator; on Windows, `npm run` shells out to `cmd.exe`, where `&` is a plain command separator instead, so `vite` never starts concurrently — it waits for `watch-server.ts` to exit, which runs forever. Same Windows incompatibility already documented in L2/L3/L4's READMEs, not carried over to this lesson's scaffold. Fixed with the same cross-platform runner:

```json
"dev": "npx --yes concurrently \"node --import tsx/esm watch-server.ts\" \"vite\"",
```

### `npm run dev` launches, but the chat UI is on port 5173, not 3005

**Root cause:** [frontend/vite.config.ts](frontend/vite.config.ts) never set a `server.port` — only `strictPort: true` (which just makes Vite fail instead of auto-incrementing if its port *is* taken; it doesn't set what that port is). Vite's own default is 5173. Inside the notebook this is invisible because `helper.py`'s `start_frontend(port)` always launches with an explicit CLI flag; a bare `npm run dev` from the terminal has no such flag. Fixed by pinning the port directly in the config:

```ts
server: {
  host: "0.0.0.0",
  port: 3005,          // 👈 added
  allowedHosts: true,
  strictPort: true,
  proxy: { "/api/copilotkit": "http://localhost:4005" },
},
```

Verified end-to-end after both fixes: `npm run dev` brings up Vite on `:3005` and the CopilotKit runtime on `:4005`; `http://localhost:3005/api/copilotkit/info` correctly reports `openGenerativeUIEnabled: true`.

### The missing client-side `openGenerativeUI={{}}` prop

Covered in the notebook deep-dive above (step 3) — restated here because it's the single most common way to end up with "the server logs show `generateSandboxedUi` being called, but nothing ever appears in the chat." `openGenerativeUI` requires **both** sides to opt in:

- Server: `new CopilotRuntime({ openGenerativeUI: true, ... })` in [frontend/server.ts](frontend/server.ts)
- Client: `<CopilotKit openGenerativeUI={{}}>` in [frontend/src/main.tsx](frontend/src/main.tsx)

Omitting the client-side prop leaves the feature half-wired: the runtime streams the tool call, but the client has no renderer registered for it.

### Harmless browser console 404: `cdn-cgi/rum`

**Symptom:** with Excalidraw working correctly, the browser dev tools still show `Failed to load resource: the server responded with a status of 404 (Not Found)` for `http://localhost:3005/cdn-cgi/rum?...`.

**Root cause:** `cdn-cgi/rum` is Cloudflare's automatic "Browser Insights" (Real User Monitoring) beacon — Cloudflare's edge auto-injects a `<script>` snippet with a **relative** URL into HTML it serves. Excalidraw's hosted MCP app (`mcp.excalidraw.com`) is itself served via Cloudflare, so the `ui://` HTML resource it returns carries that injected snippet. When the MCP Apps host renders that HTML inside a sandboxed `srcdoc` iframe, the iframe has no real origin of its own, so the relative URL resolves against the **parent page's** origin (your local dev server) instead of Cloudflare's — the beacon's `fetch("/cdn-cgi/rum?...")` lands on `localhost:3005`, which obviously has no such route, hence the 404.

**Impact:** none. It's Cloudflare analytics trying (and failing) to phone home; it has no connection to Excalidraw's actual rendering logic. Confirmed live: Excalidraw renders correctly regardless of this console error. Safe to ignore.

---

## What you learned

- Open-ended generative UI removes the constraint of pre-registered components or schemas — the agent can launch full external apps (MCP Apps) or generate arbitrary UI from scratch (`openGenerativeUI`).
- MCP Apps and `openGenerativeUI` are **independent** mechanisms with different requirements, different rendering pipelines, and — as this lesson's live testing showed — different reliability characteristics on ADK.
- Mermaid's official MCP server doesn't implement the MCP Apps extension, so Mermaid diagrams here are rendered via `openGenerativeUI` (a CDN-loaded `mermaid.js`), not via an MCP server at all.
- `openGenerativeUI` needs two-sided enablement (server config + client prop) — a gap the notebook's own scaffold doesn't fill in automatically.
- ADK's `ag_ui_adk` proxies **every** frontend/runtime-injected tool as "long-running," which is compatible with MCP Apps' argument-based rendering but currently breaks `openGenerativeUI`'s progressive-streaming content pipeline — confirmed via live testing on both backends, not assumption.
