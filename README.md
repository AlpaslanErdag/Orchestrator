# <img src="assets/logo.png" width="50" align="center"> Loom (Local AI Orchestration)

> A self-hosted, privacy-first AI agent orchestration platform...
# LoomAI

> A self-hosted, privacy-first AI agent orchestration platform powered by [Ollama](https://ollama.com).  
> Build, run, and chain autonomous AI agents — entirely on your own machine.

---

## What is LoomAI?

LoomAI is an **n8n-style visual workflow builder** for local LLMs.  
You create specialised agents (Researcher, Translator, Vision Analyst, …), give them tools (Web Scraper, PDF Generator, Email Sender), and connect them into pipelines with a drag-and-drop canvas — no cloud, no API keys, no data leaving your machine.

---

## Features

| Category | Capability |
|---|---|
| **Agents** | Create custom agents with individual models, roles, system prompts, and tool access |
| **Chat Interface** | Send tasks to any agent; see responses in a clean chat UI |
| **Process Monitor** | Real-time SSE-streamed thought process with stage pipeline (INIT → THINKING → ACTING → OBS → DONE) |
| **Tools** | PDF Report Generator · Web Scraper · Email Sender (SMTP) · Vision Analysis |
| **Visual Workflow Builder** | Drawflow-powered node canvas; connect triggers → actions → agents → outputs |
| **Display Output** | Automatic table, JSON, markdown, and PDF-download rendering of workflow results |
| **Agent Builder** | Full CRUD for agents — create, edit, delete via UI |
| **Local LLMs** | Ollama integration (mistral, llama3, llama3.2-vision, and any other Ollama-compatible model) |
| **Self-hosted** | SQLite database, no external services required |

---

## Tech Stack

- **Backend:** FastAPI · SQLAlchemy · SQLite · asyncio  
- **LLM Engine:** Ollama (OpenAI-compatible API at `localhost:11434`)  
- **Frontend:** Vanilla JS · Tailwind CSS · Drawflow  
- **Tools:** fpdf2 · httpx · BeautifulSoup4 · smtplib  

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- At least one model pulled: `ollama pull mistral:7b`

### 1. Clone & install

```bash
git clone <repo-url> agentflow-local
cd agentflow-local
pip install -r requirements.txt
```

### 2. (Optional) Configure environment

Create a `.env` file or export variables:

```bash
# Ollama endpoint (default: http://localhost:11434/v1)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_API_KEY=ollama

# PDF UTF-8 font (optional — needed for Turkish/non-Latin characters)
AGENTFLOW_PDF_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

# SMTP (for Email Sender tool)
AGENTFLOW_SMTP_HOST=smtp.gmail.com
AGENTFLOW_SMTP_PORT=587
AGENTFLOW_SMTP_USER=you@gmail.com
AGENTFLOW_SMTP_PASS=your-app-password
AGENTFLOW_SMTP_FROM=you@gmail.com
```

### 3. Run

```bash
uvicorn app.main:app --reload --port 5000
```

Open **http://localhost:5000** in your browser.

---

## Docker

```bash
# Build
docker build -t agentflow-local .

# Run (Ollama must be accessible at host.docker.internal:11434)
docker run -p 5000:5000 \
  -v $(pwd)/agentflow.db:/app/agentflow.db \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/uploads:/app/uploads \
  agentflow-local
```

> On Linux, add `--add-host=host.docker.internal:host-gateway` to reach host Ollama.

---

## Using the Workflow Builder

1. Click **Workflows** in the sidebar.
2. **Drag** nodes from the left palette onto the canvas.
3. **Connect** nodes: drag from the right ● output port of one node to the left ● input port of the next.
4. Enter a URL in the toolbar if using a URL Input trigger.
5. Click **Run Workflow** — results appear in the Process Monitor and the **Display Output** panel.

### Example: Tech News Briefing

```
URL Input (techcrunch.com)
    ↓
Web Scraper  — fetches page text
    ↓
Agent (Researcher)  — summarises headlines
    ↓
Display Result  — renders formatted output
```

Click **Load Example** in the Workflow toolbar to load this scenario automatically.

---

## Project Structure

```
agentflow-local/
├── app/
│   ├── main.py              # FastAPI routes & app factory
│   ├── database.py          # SQLAlchemy engine & session
│   ├── engine/
│   │   ├── orchestrator.py  # ReAct loop + SSE streaming
│   │   └── workflow_executor.py  # DAG workflow runner
│   └── models/
│       ├── agent_models.py  # Agent & TaskLog ORM models
│       └── workflow_models.py    # Workflow graph ORM models
├── tools/
│   ├── pdf_tool.py          # PDF report generator
│   ├── vision_tool.py       # Multimodal image analysis
│   ├── scraper_tool.py      # Web scraper (httpx + BS4)
│   └── mail_tool.py         # SMTP email sender
├── ui/
│   └── index.html           # Single-page frontend
├── reports/                 # Generated PDF reports
├── uploads/                 # Uploaded images
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## License

MIT — free for personal, academic, and research use.
