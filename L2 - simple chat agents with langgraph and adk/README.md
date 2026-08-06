# Lesson 2: Building a Basic Agent UI with CopilotKit & AG-UI

Welcome to **Lesson 2** of the _Generative UI Agents_ course. This document provides a comprehensive guide explaining the architecture, every step of the Jupyter notebook ([L2.ipynb](L2.ipynb)), the AG-UI protocol, and how to run everything using a simplified standalone Python script ([run_agent.py](run_agent.py)).

---

## 🏗 System Architecture

The application is structured into three decoupled layers:

```
┌────────────────────────────────────────────────────────┐
│               1. React Frontend (Browser)              │
│   <CopilotKit runtimeUrl="/api/copilotkit">            │
│       └── <CopilotChat agentId="default" />            │
│   (Running via Vite on Port 3002)                      │
└───────────────────────────┬────────────────────────────┘
                            │  HTTP / Event Stream
                            ▼
┌────────────────────────────────────────────────────────┐
│            2. CopilotRuntime Server (Node.js)          │
│   (Running via Hono server on Port 4002)               │
│   - Receives browser requests                          │
│   - Routes calls to designated agent backend           │
└───────────────────────────┬────────────────────────────┘
                            │  AG-UI Protocol Streams
                            ▼
┌────────────────────────────────────────────────────────┐
│             3. Python Agent Backend (FastAPI)          │
│   - LangGraph / OpenAI Agent (Port 8002)               │
│   OR                                                   │
│   - Google ADK / Gemini Agent (Port 8009)              │
└───────────────────────────┬────────────────────────────┘
```

---

## 📘 Notebook Step-by-Step Deep Dive

### 1. Starting the Server vs. Defining the Agent (Cells 12 vs 15)

- **Cell 12 ("Start the server")**:
  - **Role**: Initializes the FastAPI container (`app = FastAPI()`), mounts the AG-UI HTTP endpoint routes, and starts the web server background thread on **port 8002**.
  - **Frequency**: You only need to run Cell 12 **once** per session to keep port 8002 open.

- **Cell 15 ("Define agent")**:
  - **Role**: Constructs the full agent graph with `CopilotKitMiddleware()` (for frontend tool discovery) and `MemorySaver()` (for message persistence).
  - **Hot Reloading**: It updates `agent.graph = graph` in-place. This allows you to tweak system prompts, model options, or tools in Cell 15 and re-run it instantly **without restarting the FastAPI web server**.

---

### 2. Frontend Initialization & The Placeholder Shell (Cells 19 & 21)

- **Cell 19 (`start_frontend`)**: Starts Vite on port 3002 and the CopilotKit Node runtime on port 4002.
- **Cell 21 (`display_app`)**: Renders an inline preview of port 3002.
- **Why can't you chat yet?** The React application is initially an empty shell. The React components (`CopilotKit` provider and `CopilotChat`) have not been written to disk yet.

---

### 3. Setting Up `CopilotRuntime` (Cell 24 - `frontend/server.ts`)

- Writes [frontend/server.ts](frontend/server.ts), creating a Node.js API server running on **port 4002**.
- Points `LangGraphHttpAgent` to `http://localhost:8002` (Python FastAPI backend).
- Registers the agent under the name `"default"`.
- Exposes the endpoint at `/api/copilotkit`.

---

### 4. Wrapping the Application in `<CopilotKit>` (Cell 27 - `frontend/src/main.tsx`)

- Writes [frontend/src/main.tsx](frontend/src/main.tsx).
- Configures the client-side state engine by wrapping the root component (`<App />`) with `<CopilotKit runtimeUrl="/api/copilotkit">`.
- Manages message streaming, state synchronization, and tool execution across the React tree.

---

### 5. Defining the Root Component `<App />` (Cell 29 - `frontend/src/App.tsx`)

- Writes [frontend/src/App.tsx](frontend/src/App.tsx).
- Renders `<CopilotChat agentId="default" />`.
- Once this cell runs, Vite hot-reloads the frontend, making the chat interface **fully operational** in Cell 33.

---

### 6. Google ADK & Gemini Bonus Section (Cell 36 - 40)

- **Cell 36 ("Setup an ADK Agent")**:
  - Creates an `ADKAgent` using `LlmAgent(model="gemini-3.6-flash")`.
  - Starts a **FastAPI server on port 8009**.
  - **FastAPI Docs**: Interactive Swagger documentation is active and accessible at `http://localhost:8009/docs`.
- **Cell 38 (`server.ts`)**: Registers both agents simultaneously:
  - `"default"` -> LangGraph / OpenAI (port 8002)
  - `"gemini"` -> Google ADK / Gemini (port 8009)
- **Cell 40 (`App.tsx`)**: Swapping models requires only updating `agentId = "gemini"`. **Zero UI code changes are needed.**

---

## ⚡ What is AG-UI (Agent-User Interaction)?

AG-UI is an open, standardized, event-driven protocol that connects AI agent backends to UI frontends over HTTP.

- Standardizes chat state, streaming events, and tool calls.
- Decouples the frontend framework from the backend framework.
- Allows swapping LangChain/OpenAI for Google ADK/Gemini without altering UI code.

---

## 🔥 What is Hono Server?

**Hono** (_"Flame"_ 🔥 in Japanese) is a fast, lightweight, Web Standard-based web framework for JavaScript and TypeScript used by CopilotKit in [frontend/server.ts](frontend/server.ts).

### Why CopilotKit uses Hono for `CopilotRuntime`:

- **Universal Deployment**: Runs on **Node.js, Deno, Bun, Cloudflare Workers, Vercel Edge, Next.js API routes, and AWS Lambda** with zero code changes.
- **Native Web Streams & SSE**: Handles real-time Server-Sent Events (SSE) and token/tool streaming with minimal latency.
- **Web Standard APIs**: Uses standard `fetch`, `Request`, and `Response` objects rather than legacy Node-specific objects (`req`, `res`).

### Express vs Hono Comparison:

| Feature                | Express.js                      | Hono                                               |
| :--------------------- | :------------------------------ | :------------------------------------------------- |
| **API Standard**       | Node.js specific (`req`, `res`) | Standard Web APIs (`fetch`, `Request`, `Response`) |
| **Edge / Serverless**  | ❌ Requires heavy polyfills     | ✅ Native support out of the box                   |
| **Streaming Support**  | Custom stream callbacks         | Built-in Web Streams & SSE                         |
| **TypeScript Support** | Added via `@types/express`      | First-class native TypeScript                      |

---

## 🚀 Standalone Script: `run_agent.py`

Instead of running interactive notebook cells, you can launch the complete agent backend using the unified standalone script [run_agent.py](run_agent.py).

### How Routing & Ports Work:

- By default, `run_agent.py` listens on **Port 8002**.
- In [frontend/server.ts](frontend/server.ts), the default agent route (`http://localhost:8002`) handles all incoming requests from `<CopilotChat agentId="default" />` in [frontend/src/App.tsx](frontend/src/App.tsx).
- Because [run_agent.py](run_agent.py) runs on port `8002` for both `AGENT_TYPE = "langgraph"` and `AGENT_TYPE = "adk"`, the React chat interface works **out of the box for both agents** without needing to change `agentId` in `App.tsx`.

### How to Run:

1. **Terminal 1: Run LangGraph / OpenAI Agent (Port 8002)**:

   ```bash
   uv run python run_agent.py
   ```

2. **Run Google ADK / Gemini Agent (Port 8002)**:
   Change `AGENT_TYPE = "adk"` inside [run_agent.py](run_agent.py) or set the environment variable:

   ```bash
   AGENT_TYPE=adk uv run python run_agent.py
   ```

3. **Terminal 2: Launch Frontend**

   ```bash
   npm run dev
   ```

### Code Overview ([run_agent.py](run_agent.py)):

```python
import os
import logging
from typing import Literal
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI

# Toggle between "langgraph" and "adk"
AGENT_TYPE: Literal["langgraph", "adk"] = "langgraph"

def create_langgraph_app(model_name: str = "gpt-4o-mini") -> FastAPI:
    from ag_ui_langgraph import add_langgraph_fastapi_endpoint
    from copilotkit import CopilotKitMiddleware, LangGraphAGUIAgent
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import MemorySaver

    graph = create_agent(
        model=ChatOpenAI(model=model_name),
        tools=[],
        middleware=[CopilotKitMiddleware()],
        checkpointer=MemorySaver(),
        system_prompt="You are a helpful assistant",
    )
    app = FastAPI(title="LangGraph AG-UI Agent API")
    agent = LangGraphAGUIAgent(name="langgraph_agent", description="LangGraph Agent", graph=graph)
    add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/")
    return app

def create_adk_app(model_name: str = "gemini-3.5-flash-lite") -> FastAPI:
    from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
    from google.adk.agents import LlmAgent

    gemini_agent = LlmAgent(name="assistant", model=model_name, instruction="Be helpful!")
    adk_agent = ADKAgent(adk_agent=gemini_agent, app_name="demo", user_id="user")
    app = FastAPI(title="Google ADK AG-UI Agent API")
    add_adk_fastapi_endpoint(app=app, agent=adk_agent, path="/")
    return app

def main() -> None:
    load_dotenv()
    selected_agent = os.getenv("AGENT_TYPE", AGENT_TYPE).lower()
    if selected_agent == "adk":
        port = 8009
        app = create_adk_app()
    else:
        port = 8002
        app = create_langgraph_app()

    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
```

---

## 🛠 Fixes Applied for Windows Compatibility

If you run this repository on Windows, the following platform fixes have been implemented in [helper.py](helper.py) and [frontend/package.json](frontend/package.json):

1. **`npm.CMD` Path Resolution**:
   Resolved `shutil.which("npm")` to prevent `[WinError 2] Le fichier spécifié est introuvable` when invoking `subprocess.Popen`.
2. **Cross-Platform PATH Separator**:
   Replaced Unix `:` with `os.pathsep` (`;` on Windows) in `_node_env()`.
3. **Windows Port Cleanup**:
   Added `netstat -ano` and `taskkill /F /PID` support in `_kill_port` for Windows.
4. **Cross-Platform Script Execution**:
   Replaced shell background operator `&` in `frontend/package.json` with `npx --yes concurrently` to launch `watch-server.ts` and `vite` simultaneously.
