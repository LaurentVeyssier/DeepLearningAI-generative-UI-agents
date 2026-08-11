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
- a `frontend/` folder

The Python environment is managed by `uv` from the root project folder (single shared venv for all lessons).
The frontend node modules are managed by npm workspaces from the root `package.json` — each lesson's `frontend/` folder is one workspace, so a single `npm install` at the root installs all of them.

# Setup

Run these once, from the project root:

1. `uv init` — initialize/confirm the uv-managed Python project (uses `pyproject.toml`, requires Python >= 3.13)
2. `uv sync` — create the venv and install all Python dependencies
3. `npm install` — install node modules for every lesson's frontend (via workspaces)
4. Create your `.env` (see `.env.example`) and add your API keys

# How to Run

For each lesson, from its folder:

- Backend: `uv run run_agent.py`
- Frontend (separate terminal): `cd frontend && npm run dev`

In your `.env`, set `AGENT_TYPE`:

- `adk` — uses the ADK agent + Gemini (free quota using `gemini-3.5-flash-lite`)
- `langgraph` — uses `deep_agent` + OpenAI

Note:

- a few lessons do not support `gpt-5.6-luna`'s reasoning output format — use `gpt-5.4-mini` instead
- L6 does not support `adk`, so it uses `langgraph` + Gemini
