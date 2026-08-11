\# Project Overview

each lesson covers a specific stage of Generative UI

- controlled GenUI (pre-built components the agent select from)
- Declarative GenUI (lego blocks component catalog the agent can assemble)
- open-ended Generative UI (MCP Apps)
- Full stack genetative UI App (sync backend and frontend shared state, frontend tool calling)

\# Project Structure

Each lesson has:

- a run_agent.py script replicating the notebook
- a detailed readme with implementation details
- run frontend in a terminal: frontend/npm run dev
- run script : uv run run_agent.py

a uv venv is available in the root project folder
frontend node modules installed at root level using workspaces. check package.json at root to see the structure

\# How to RUN

Create your .env and add your API keys

in addition,

- select adk to use adk agent + gemini (free quota using gemini-3.5-flash-lite)
- select langgraph to run deep_agent + openai

Note:

a few lessons do not support gpt-5.6-luna reasoning output format -> use gpt-5.4-mini
L6 does not support adk so we use langgraph + gemini
