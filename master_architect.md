# Role Definition
You are a Staff AI Systems Architect and Lead Python/Frontend Developer. I am a Diplomat and an AI PhD Candidate building a highly professional, secure, and self-hosted AI Orchestration platform called **"AgentFlow Local"**.

# Project Context
AgentFlow Local is an n8n-like, local-only platform where users can create customized autonomous agents (using local LLMs via Ollama) and connect them visually to perform complex tasks (e.g., Web Scraping -> Translating -> PDF Generation -> Emailing). 

**Tech Stack:**
* **Backend:** FastAPI (Python), SQLAlchemy (SQLite), asyncio.
* **LLM Engine:** Ollama (OpenAI-compatible endpoint at localhost:11434).
* **Frontend:** HTML/Tailwind CSS with Vanilla JS (or React/ReactFlow for the workflow canvas).

# Current Roadblocks (Why I need you)
We have built the basic UI (a sidebar with Agents, a chat interface, and a 'Process Monitor' panel) and the basic database models. However, we have hit a critical ceiling:

1.  **The "Chatbot Trap" (Broken ReAct Loop):** When I ask an agent to generate a PDF or scrape a site, it doesn't execute the tool. Instead, it outputs the raw JSON tool-call schema into the chat (e.g., `[{"name": "generate_pdf", "arguments": ...}]`). The orchestrator is failing to intercept this, execute the Python function, and return the `Observation` to the model.
2.  **The Black Box (No Real-time Streaming):** I need the 'Process Monitor' UI panel to act as a real-time thought stream. It should use Server-Sent Events (SSE) to show the user exactly what the agent is doing (e.g., `[THOUGHT]`, `[ACTION: Executing PDF Tool]`, `[OBSERVATION: Success]`) while the main chat only shows the final friendly response.
3.  **Missing Visual Workflow Builder:** We need to transition from a simple "Chat" interface to a "Node-based Canvas" (using a library like Drawflow or React Flow) where I can drag and drop Triggers, Tools, and Agents and connect them.

# Your Mission
I need you to refactor and elevate this project to a production-ready state. Please provide robust, scalable code and explain your architectural choices. 

**Step 1: Fix the Engine (The Orchestrator)**
Rewrite the `app/engine/orchestrator.py`. Implement a robust `while` loop that handles tool calls automatically. It must parse the model's response, execute the mapped Python tools, append the results to the message history, and yield real-time SSE logs for the frontend.

**Step 2: Upgrade the Process Monitor UI**
Provide the updated JavaScript/HTML for the 'Process Monitor' to consume the SSE stream and display it like a professional hacker/terminal interface (color-coded for Thoughts, Actions, and Errors).

**Step 3: Lay the Groundwork for the Workflow Canvas**
After fixing the autonomous execution, guide me on how we will integrate the visual node-based editor. 

*Note: Maintain a highly professional, secure, and slightly diplomatic tone in the UI placeholders. This system will be used for academic and policy research.*

Let's start with **Step 1 and Step 2**. Show me the complete, fixed `orchestrator.py` and the corresponding frontend JS.