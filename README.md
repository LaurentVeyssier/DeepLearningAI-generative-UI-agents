# Project Overview

Each lesson covers a specific stage of Generative UI:

- Controlled GenUI (pre-built components the agent selects from)
- Declarative GenUI (lego blocks component catalog the agent can assemble)
- Open-ended Generative UI (MCP Apps)
- Full stack generative UI App (sync backend and frontend shared state, frontend tool calling)

# Project Structure

Each lesson has:

- a `run_agent.py` script replicating the notebook
- a detailed README with implementation details
- run frontend in a terminal: `frontend/npm run dev`
- run script: `uv run run_agent.py`

A uv venv is available in the root project folder.
Frontend node modules are installed at root level using workspaces — check `package.json` at root to see the structure.

# How to Run

Create your `.env` (see `.env.example`) and add your API keys.

In addition:

- select `adk` to use the ADK agent + Gemini (free quota using `gemini-3.5-flash-lite`)
- select `langgraph` to run `deep_agent` + OpenAI

Note:

- a few lessons do not support `gpt-5.6-luna`'s reasoning output format — use `gpt-5.4-mini` instead
- L6 does not support `adk`, so it uses `langgraph` + Gemini
