from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.engine.orchestrator import stream_agent_task
from tools.mail_tool import MailTool
from tools.pdf_tool import PDFReportTool
from tools.scraper_tool import WebScraperTool


REPORTS_DIR = Path("reports").resolve()


class WorkflowExecutor:
    """
    Execute a simple directed acyclic workflow defined as a JSON graph.

    This is an initial skeleton that supports:
    - Source nodes: URL input
    - Tool nodes: web scraper, mail sender
    - Agent nodes: any existing Agent (by id)
    - Data propagation: output of one node becomes input to connected children.
    """

    def __init__(self) -> None:
        self.db: Session = SessionLocal()

    def close(self) -> None:
        self.db.close()

    async def execute_graph(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a workflow graph sent from the frontend.

        Expected structure (simplified):
        {
          "nodes": [
            {
              "id": "n1",
              "type": "source",
              "key": "url_input",
              "config": {"url": "https://nodejs.org/en"}
            },
            {
              "id": "n2",
              "type": "tool",
              "key": "web_scraper",
              "config": {}
            },
            {
              "id": "n3",
              "type": "agent",
              "key": "agent",
              "config": {"agent_id": 1}
            },
            ...
          ],
          "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            ...
          ]
        }
        """
        nodes: Dict[str, Dict[str, Any]] = {n["id"]: n for n in graph.get("nodes", [])}
        edges: List[Dict[str, Any]] = graph.get("edges", [])

        incoming: Dict[str, List[str]] = {nid: [] for nid in nodes}
        outgoing: Dict[str, List[str]] = {nid: [] for nid in nodes}
        for e in edges:
            s = e["source"]
            t = e["target"]
            outgoing.setdefault(s, []).append(t)
            incoming.setdefault(t, []).append(s)

        # Simple topological-ish execution: repeatedly run nodes whose parents have run.
        context: Dict[str, Any] = {}
        results: Dict[str, Any] = {}
        completed: set[str] = set()

        # Start with nodes that have no incoming edges (triggers).
        ready = [nid for nid, inc in incoming.items() if not inc]

        while ready:
            nid = ready.pop(0)
            node = nodes[nid]
            ntype = node.get("type")
            key = node.get("key")
            config = node.get("config") or {}
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    config = {}

            input_payloads = [results[p] for p in incoming.get(nid, []) if p in results]
            merged_input = self._merge_inputs(input_payloads)

            result = await self._execute_node(
                node_id=nid,
                node_type=ntype,
                key=key,
                config=config,
                data=merged_input,
            )
            results[nid] = result
            completed.add(nid)

            for child in outgoing.get(nid, []):
                if all(parent in completed for parent in incoming.get(child, [])):
                    ready.append(child)

        self.close()
        return {
            "results": results,
        }

    @staticmethod
    def _merge_inputs(inputs: List[Any]) -> Any:
        """
        Very simple data merge strategy:
        - If a single input, just pass it through.
        - If multiple text-like inputs, concatenate.
        - Otherwise, return list.
        """
        if not inputs:
            return None
        if len(inputs) == 1:
            return inputs[0]

        # If all are strings, concatenate.
        if all(isinstance(i, str) for i in inputs):
            return "\n\n".join(inputs)

        return inputs

    async def _execute_node(
        self,
        node_id: str,
        node_type: str,
        key: Optional[str],
        config: Dict[str, Any],
        data: Any,
    ) -> Any:
        """
        Execute a single node based on its type and key.
        """
        if node_type == "source":
            # For now only URL input is supported
            if key == "url_input":
                return config.get("url") or data
            if key == "schedule":
                # Schedules would normally trigger externally; here we just echo config.
                return {"schedule": config}

        if node_type == "tool":
            if key == "web_scraper":
                url = config.get("url") or data
                if not isinstance(url, str):
                    raise ValueError("Web scraper node requires a URL string input.")
                return await WebScraperTool.scrape_url(url=url)
            if key == "email_sender":
                # Expect data to contain final text, and config to contain recipient info.
                to = config.get("to") or []
                subject = config.get("subject") or "AgentFlow Local Report"
                body = str(data) if data is not None else ""
                if isinstance(to, str):
                    to = [to]
                if to:
                    MailTool.send_email(to=to, subject=subject, body=body)
                return {"status": "sent", "to": to}
            if key == "pdf_report":
                title = config.get("title", "AI Research Report")
                content = str(data) if data is not None else ""
                filename = config.get("filename", "workflow_report.pdf")
                # Güvenlik: sadece dosya adını kullan
                safe_name = Path(filename).name
                REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                output_path = REPORTS_DIR / safe_name
                pdf_tool = PDFReportTool()
                pdf_tool.generate_report(title=title, content=content, filename=str(output_path))
                return {"pdf_path": str(output_path)}

        if node_type == "agent":
            # config must contain agent_id; data becomes the prompt
            agent_id = config.get("agent_id")
            if agent_id is None:
                raise ValueError("Agent node requires an 'agent_id' in config.")
            prompt_prefix = config.get("prompt_prefix") or ""
            base_prompt   = str(data) if data is not None else ""
            full_prompt   = f"{prompt_prefix}\n\n{base_prompt}" if prompt_prefix else base_prompt

            # Collect the async SSE stream without spawning a new event loop
            # (we are already inside an async context via FastAPI/uvloop).
            final_output = ""
            async for frame in stream_agent_task(
                agent_id=int(agent_id), user_prompt=full_prompt
            ):
                evt, payload = "", ""
                for line in frame.split("\n"):
                    if line.startswith("event:"):
                        evt = line[6:].strip()
                    elif line.startswith("data:"):
                        payload = line[5:].strip().replace("\\n", "\n")
                if evt == "final" and payload:
                    try:
                        final_output = json.loads(payload).get("final_output", "")
                    except json.JSONDecodeError:
                        final_output = payload
            return final_output

        if node_type == "output":
            # For now, output nodes just echo the data; real implementations
            # could store artifacts or mark workflow completion.
            return data

        # Default fallback: pass-through
        return data


