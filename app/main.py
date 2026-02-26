from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.engine.orchestrator import run_agent_task, stream_agent_task
from app.engine.workflow_executor import WorkflowExecutor
from app.models.agent_models import Agent, TaskLog


BASE_DIR = Path(__file__).resolve().parent.parent
UI_DIR = BASE_DIR / "ui"
REPORTS_DIR = BASE_DIR / "reports"


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


templates = Jinja2Templates(directory=str(UI_DIR))


class AgentCreate(BaseModel):
    name: str
    role: str
    backstory: Optional[str] = ""
    model_name: Optional[str] = None
    tools: Optional[str] = None


class AgentRead(BaseModel):
    id: int
    name: str
    role: str
    backstory: Optional[str] = None
    model_name: Optional[str] = None
    tools: Optional[str] = None


class TaskRequest(BaseModel):
    prompt: str
    image_path: Optional[str] = None


class TaskResponse(BaseModel):
    task_log_id: int
    agent_id: int
    final_output: str
    artifact_path: Optional[str] = None
    thought_process: str


class AgentBuilderCreate(BaseModel):
    """Schema for the Agent Builder endpoint (POST /agents)."""
    name: str
    model_name: str
    role_description: str
    instructions: str
    selected_tools: List[str]


class AgentBuilderUpdate(BaseModel):
    """Schema for updating an existing agent (PUT /api/agents/{id})."""
    name: Optional[str] = None
    model_name: Optional[str] = None
    role_description: Optional[str] = None
    instructions: Optional[str] = None
    selected_tools: Optional[List[str]] = None


class WorkflowExecuteRequest(BaseModel):
    graph: Dict[str, Any]


class WorkflowExecuteResponse(BaseModel):
    results: Dict[str, Any]


def seed_default_agents(db: Session) -> None:
    """
    Ensure we have a minimal set of default agents for the UI.
    """
    if db.query(Agent).count() > 0:
        return

    defaults = [
        {
            "name": "Researcher",
            "role": "Researcher",
            "model_name": "mistral:7b",
            "backstory": "A methodical analyst focused on gathering and synthesizing information from diverse sources.",
            "tools": ["pdf_report_tool"],
        },
        {
            "name": "Writer",
            "role": "Writer",
            "model_name": "mistral:7b",
            "backstory": "A clear and diplomatic communicator skilled at structuring ideas into polished prose.",
            "tools": ["pdf_report_tool"],
        },
        {
            "name": "Analyst",
            "role": "Analyst",
            "model_name": "mistral:7b",
            "backstory": "An analytical thinker specializing in comparisons, trade-offs, and crisp recommendations.",
            "tools": ["pdf_report_tool"],
        },
        {
            "name": "Summarizer",
            "role": "Özetleyici",
            "model_name": "mistral:7b",
            "backstory": "Uzun metinleri yöneticiler için net ve öz özetlere dönüştürmeye odaklanan diplomatik bir özetleyici.",
            "tools": ["pdf_report_tool"],
        },
        {
            "name": "Vision Analyst",
            "role": "Görsel Yorumlayıcı",
            "model_name": "llama3.2-vision:11b",
            "backstory": "Grafikler, tablolar ve görseller üzerinden yorum ve içgörü üreten çok modlu bir analist.",
            "tools": ["vision_analysis_tool"],
        },
        {
            "name": "Polyglot",
            "role": "Çevirmen",
            "model_name": "mistral:7b",
            "backstory": "Türkçe ve İngilizce arasında teknik ve diplomatik metinleri yüksek sadakatle çeviren bir uzman.",
            "tools": ["pdf_report_tool"],
        },
    ]
    for spec in defaults:
        agent = Agent(
            name=spec["name"],
            role=spec["role"],
            model_name=spec["model_name"],
            backstory=spec["backstory"],
            tools=json.dumps(spec["tools"]),
        )
        db.add(agent)
    db.commit()


def create_app() -> FastAPI:
    """
    Application factory for AgentFlow Local.
    Keeps initialization logic in one place for future extension
    (DB, middleware, routers, etc.).
    """
    app = FastAPI(
        title="AgentFlow Local",
        description="Local AI Agent Orchestration platform (self-hosted, Ollama-powered).",
        version="0.1.0",
    )

    # Ensure database tables are created on startup
    init_db()

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """
        Serve the main web interface.
        """
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "app": "AgentFlow Local"}

    @app.get("/api/agents", response_model=List[AgentRead])
    async def list_agents(db: Session = Depends(get_db)) -> List[AgentRead]:
        seed_default_agents(db)
        agents = db.query(Agent).order_by(Agent.id.asc()).all()
        return [
            AgentRead(
                id=a.id,
                name=a.name,
                role=a.role,
                backstory=a.backstory,
                model_name=a.model_name,
                tools=a.tools,
            )
            for a in agents
        ]

    @app.post("/api/agents", response_model=AgentRead)
    async def create_agent(payload: AgentCreate, db: Session = Depends(get_db)) -> AgentRead:
        tools_value = payload.tools
        # If user passes a JSON list as a string, keep it; otherwise default tools.
        if tools_value is None:
            # Vision agents should include the vision tool; others at least PDF.
            default_tools = ["pdf_report_tool"]
            if (payload.role or "").lower().startswith("görsel"):
                default_tools = ["vision_analysis_tool"]
            tools_value = json.dumps(default_tools)

        agent = Agent(
            name=payload.name,
            role=payload.role,
            backstory=payload.backstory or "",
            model_name=payload.model_name,
            tools=tools_value,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return AgentRead(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            backstory=agent.backstory,
            model_name=agent.model_name,
            tools=agent.tools,
        )

    @app.post("/agents", response_model=AgentRead)
    async def create_agent_builder(payload: AgentBuilderCreate, db: Session = Depends(get_db)) -> AgentRead:
        """
        Agent Builder endpoint with explicit instructions and tool selection.
        """
        tools_value = json.dumps(payload.selected_tools or [])

        agent = Agent(
            name=payload.name,
            role=payload.role_description,
            model_name=payload.model_name,
            backstory=payload.instructions,
            tools=tools_value,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        return AgentRead(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            backstory=agent.backstory,
            model_name=agent.model_name,
            tools=agent.tools,
        )

    @app.put("/api/agents/{agent_id}", response_model=AgentRead)
    async def update_agent(
        agent_id: int, payload: AgentBuilderUpdate, db: Session = Depends(get_db)
    ) -> AgentRead:
        """Update an existing agent's properties."""
        agent: Optional[Agent] = db.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found.")

        if payload.name is not None:
            agent.name = payload.name
        if payload.model_name is not None:
            agent.model_name = payload.model_name
        if payload.role_description is not None:
            agent.role = payload.role_description
        if payload.instructions is not None:
            agent.backstory = payload.instructions
        if payload.selected_tools is not None:
            agent.tools = json.dumps(payload.selected_tools)

        db.commit()
        db.refresh(agent)
        return AgentRead(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            backstory=agent.backstory,
            model_name=agent.model_name,
            tools=agent.tools,
        )

    @app.delete("/api/agents/{agent_id}")
    async def delete_agent(agent_id: int, db: Session = Depends(get_db)):
        """Delete an agent and its task logs."""
        from fastapi.responses import Response
        agent: Optional[Agent] = db.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found.")
        db.delete(agent)
        db.commit()
        return Response(status_code=204)

    @app.post("/api/agents/{agent_id}/tasks", response_model=TaskResponse)
    async def run_task(agent_id: int, payload: TaskRequest) -> TaskResponse:
        if not payload.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

        result = run_agent_task(
            agent_id=agent_id,
            user_prompt=payload.prompt,
            image_path=payload.image_path,
        )
        return TaskResponse(**result)  # type: ignore[arg-type]

    @app.post("/api/agents/{agent_id}/stream")
    async def stream_task(agent_id: int, payload: TaskRequest) -> StreamingResponse:
        """
        Server-Sent Events stream of the ReAct reasoning loop.
        The client reads events: thought | action | observation | final | error | done.
        """
        if not payload.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

        async def _generator():
            async for frame in stream_agent_task(
                agent_id=agent_id,
                user_prompt=payload.prompt,
                image_path=payload.image_path,
            ):
                yield frame

        return StreamingResponse(
            _generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control":    "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/tasks/{task_log_id}", response_model=TaskResponse)
    async def get_task(task_log_id: int, db: Session = Depends(get_db)) -> TaskResponse:
        task: Optional[TaskLog] = db.get(TaskLog, task_log_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found.")

        return TaskResponse(
            task_log_id=task.id,
            agent_id=task.agent_id,
            final_output=task.final_output or "",
            artifact_path=None,
            thought_process=task.thought_process or "",
        )

    @app.get("/api/reports/download")
    async def download_report(path: str) -> FileResponse:
        """
        Download a generated PDF report.
        Only files inside the dedicated reports/ directory are allowed.
        """
        requested_path = Path(path).resolve()
        reports_root = REPORTS_DIR.resolve()

        if not str(requested_path).startswith(str(reports_root)):
            raise HTTPException(status_code=400, detail="Invalid report path.")
        if not requested_path.is_file():
            raise HTTPException(status_code=404, detail="Report not found.")

        return FileResponse(
            str(requested_path),
            media_type="application/pdf",
            filename=requested_path.name,
        )

    @app.post("/api/upload-image")
    async def upload_image(file: UploadFile = File(...)) -> JSONResponse:
        """
        Upload an image file and return its server-side path.
        """
        uploads_dir = BASE_DIR / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        target_path = uploads_dir / file.filename
        # Avoid clobbering by appending a counter if needed.
        counter = 1
        stem = target_path.stem
        suffix = target_path.suffix
        while target_path.exists():
            target_path = uploads_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        with open(target_path, "wb") as out:
            out.write(await file.read())

        return JSONResponse({"path": str(target_path)})

    @app.get("/api/models")
    async def list_models() -> JSONResponse:
        """
        Proxy to Ollama's /api/tags endpoint to list available models.
        Returns a simplified structure: {"models": ["mistral:7b", ...]}.
        """
        base_url = os.getenv("OLLAMA_HTTP_BASE", "http://localhost:11434")
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
                resp = await client.get("/api/tags")
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch models from Ollama: {exc}",
            ) from exc

        data = resp.json()
        models_raw = data.get("models", [])
        names: List[str] = []
        for m in models_raw:
            name = m.get("model") or m.get("name")
            if name:
                names.append(name)

        return JSONResponse({"models": names})

    @app.post("/api/workflows/execute", response_model=WorkflowExecuteResponse)
    async def execute_workflow(payload: WorkflowExecuteRequest) -> WorkflowExecuteResponse:
        """
        Execute a workflow graph produced by the visual builder.
        """
        executor = WorkflowExecutor()
        result = await executor.execute_graph(payload.graph)
        return WorkflowExecuteResponse(**result)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
    )


