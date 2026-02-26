from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from openai import OpenAI
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.agent_models import Agent, TaskLog
from tools.mail_tool import MailTool
from tools.pdf_tool import PDFReportTool
from tools.scraper_tool import WebScraperTool
from tools.vision_tool import VisionAnalysisTool


OLLAMA_BASE_URL_ENV = "OLLAMA_BASE_URL"
OLLAMA_API_KEY_ENV  = "OLLAMA_API_KEY"

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_API_KEY  = "ollama"
DEFAULT_MODEL_NAME      = "mistral:7b"
MAX_REACT_STEPS         = 10

REPORTS_DIR = Path("reports")

# ──────────────────────────────────────────────────────────────────────────────
# SSE event helpers
# ──────────────────────────────────────────────────────────────────────────────

def _sse(event: str, data: str) -> str:
    """Serialise a single SSE frame."""
    payload = data.replace("\n", "\\n")  # keep each frame on one logical line
    return f"event: {event}\ndata: {payload}\n\n"


# ──────────────────────────────────────────────────────────────────────────────
# Ollama client
# ──────────────────────────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    return OpenAI(
        base_url=os.getenv(OLLAMA_BASE_URL_ENV, DEFAULT_OLLAMA_BASE_URL),
        api_key=os.getenv(OLLAMA_API_KEY_ENV, DEFAULT_OLLAMA_API_KEY),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Agent / tool helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_system_prompt(agent: Agent) -> str:
    parts: List[str] = [
        f"You are an AI agent named '{agent.name}' with the role '{agent.role}'.",
    ]
    if agent.backstory:
        parts.append(f"Background and instructions: {agent.backstory}")

    # Parse tool names from JSON list stored in DB
    tool_names: List[str] = []
    if agent.tools:
        try:
            parsed = json.loads(agent.tools)
            if isinstance(parsed, list):
                tool_names = [str(t) for t in parsed]
        except json.JSONDecodeError:
            tool_names = [agent.tools]

    if tool_names:
        readable = ", ".join(tool_names)
        parts.append(f"You have access to these tools: {readable}.")
        parts.append(
            "CRITICAL RULES FOR TOOL USE — follow these without exception:\n"
            "1. NEVER ask the user for a URL or any other input if your instructions already specify "
            "   a website, URL, or data source. Extract the URL from your instructions and call "
            "   web_scraper_tool immediately.\n"
            "2. If the task involves producing a document or report, call pdf_report_tool with the "
            "   collected content — do not just describe the output.\n"
            "3. ALWAYS call tools by emitting a valid function call (or a JSON block with "
            "   {\"tool\": \"<name>\", \"arguments\": {...}}). Never describe what you would do; execute it.\n"
            "4. After receiving a tool observation, synthesise a clear final answer for the user."
        )

    parts.append(
        "Follow the ReAct loop strictly: THINK → ACT (call a tool) → OBSERVE → repeat until done "
        "→ give a concise final answer."
    )
    return "\n".join(parts)


def _get_tool_schemas(agent: Agent) -> List[Dict[str, Any]]:
    schemas: List[Dict[str, Any]] = []
    tool_names: List[str] = []
    if agent.tools:
        try:
            parsed = json.loads(agent.tools)
            if isinstance(parsed, list):
                tool_names = [str(t) for t in parsed]
        except json.JSONDecodeError:
            tool_names = [agent.tools]

    mapping = {
        "pdf_report_tool": PDFReportTool.get_schema,
        "vision_analysis_tool": VisionAnalysisTool.get_schema,
        "web_scraper_tool": WebScraperTool.get_schema,
        "send_email": MailTool.get_schema,
    }
    for name in tool_names:
        if name in mapping:
            schemas.append({"type": "function", "function": mapping[name]()})
    return schemas


# ──────────────────────────────────────────────────────────────────────────────
# Tool execution
# ──────────────────────────────────────────────────────────────────────────────

_TOOL_ALIASES: Dict[str, str] = {
    "pdf_report_tool": "generate_pdf_report",
    "pdf_tool":        "generate_pdf_report",
    "scraper_tool":    "web_scraper_tool",
    "web_scraper":     "web_scraper_tool",
}


def _execute_tool(
    tool_name: str,
    arguments_json: str,
    model_name: str,
) -> Tuple[str, Optional[str]]:
    """
    Execute a tool call and return (observation_text, optional_artifact_path).
    Never raises – errors are returned as observation strings so the model can
    react gracefully.
    """
    try:
        args: Dict[str, Any] = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        return "ERROR: tool arguments could not be parsed as JSON.", None

    name = _TOOL_ALIASES.get(tool_name, tool_name)

    try:
        if name == "generate_pdf_report":
            pdf_tool = PDFReportTool()
            title    = args.get("title", "AI Research Report")
            content  = args.get("content", "")
            raw_file = args.get("filename", "report.pdf")
            if os.path.isabs(raw_file):
                raw_file = os.path.basename(raw_file)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            path = pdf_tool.generate_report(
                title=title, content=content,
                filename=str(REPORTS_DIR / raw_file),
            )
            return f"SUCCESS: PDF saved to '{path}'.", path

        if name == "analyze_image":
            img = args.get("image_path")
            if not img:
                return "ERROR: image_path is required.", None
            desc = VisionAnalysisTool.analyze_image(
                image_path=img,
                prompt=args.get("prompt"),
                model_name=model_name,
            )
            return f"Image analysis result:\n{desc}", None

        if name == "web_scraper_tool":
            url = args.get("url") or args.get("target_url") or args.get("source")
            if not url:
                return "ERROR: 'url' is required for web scraping.", None
            text = asyncio.run(WebScraperTool.scrape_url(url=url))
            preview = text[:3000]
            return f"Scraped content from {url}:\n{preview}", None

        if name == "send_email":
            to      = args.get("to") or []
            subject = args.get("subject") or "AgentFlow Local Report"
            body    = args.get("body") or ""
            if isinstance(to, str):
                to = [to]
            if not to:
                return "ERROR: 'to' (recipient list) is required.", None
            MailTool.send_email(to=to, subject=subject, body=body)
            return f"SUCCESS: email dispatched to {', '.join(to)}.", None

    except Exception as exc:  # noqa: BLE001
        return f"ERROR while executing '{name}': {exc}", None

    return f"ERROR: unknown tool '{tool_name}'.", None


# ──────────────────────────────────────────────────────────────────────────────
# Fallback: detect JSON tool call embedded in plain assistant text
# ──────────────────────────────────────────────────────────────────────────────

def _parse_inline_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    name = obj.get("tool") or obj.get("tool_name") or obj.get("name")
    if not name:
        return None
    raw_args = obj.get("arguments") or obj.get("args") or obj.get("params") or {}
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except json.JSONDecodeError:
            raw_args = {}
    if not isinstance(raw_args, dict):
        raw_args = {}
    return name, raw_args


# ──────────────────────────────────────────────────────────────────────────────
# SSE streaming generator  (main public API for the stream endpoint)
# ──────────────────────────────────────────────────────────────────────────────

async def stream_agent_task(
    agent_id: int,
    user_prompt: str,
    image_path: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Async generator that runs the full ReAct loop and yields SSE frames.

    SSE event types emitted:
      thought    – model reasoning text
      action     – tool invocation detail
      observation– tool result
      final      – final answer (chat-ready)
      error      – any fatal error
      done       – signals stream end (data: [DONE])
    """
    client  = _get_client()
    session = SessionLocal()

    try:
        agent: Optional[Agent] = session.get(Agent, agent_id)
        if agent is None:
            yield _sse("error", f"Agent #{agent_id} not found.")
            yield _sse("done",  "[DONE]")
            return

        model_name     = agent.model_name or DEFAULT_MODEL_NAME
        system_prompt  = _build_system_prompt(agent)
        tool_schemas   = _get_tool_schemas(agent)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        user_content = user_prompt
        if image_path:
            user_content += (
                "\n\n[Note: an image is available at the server path below. "
                "Call the vision tool if you need to inspect it.]\n"
                f"image_path: {image_path}"
            )
        messages.append({"role": "user", "content": user_content})

        thought_log: List[str] = [f"USER: {user_prompt}"]
        if image_path:
            thought_log.append(f"USER IMAGE: {image_path}")

        final_answer:      Optional[str] = None
        last_artifact_path: Optional[str] = None

        # ── ReAct while-loop ────────────────────────────────────────────────
        for step in range(MAX_REACT_STEPS):
            yield _sse("thought", f"[Step {step + 1}] Querying model {model_name}…")

            # Call the model (synchronous Ollama/OpenAI client; run in thread pool)
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=tool_schemas or None,
                    tool_choice="auto" if tool_schemas else None,
                ),
            )

            choice  = response.choices[0]
            message = choice.message

            # ── 1. Model returned plain reasoning text ───────────────────────
            if message.content:
                thought_log.append(f"THOUGHT (step {step}): {message.content}")
                yield _sse("thought", message.content)

            # ── 2a. Native tool_calls (OpenAI / Ollama tools API) ────────────
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                for tc in tool_calls:
                    t_name = tc.function.name
                    t_args = tc.function.arguments or "{}"

                    yield _sse("action", f"[ACTION] Executing tool: {t_name}\nArgs: {t_args}")
                    thought_log.append(f"ACTION (step {step}): {t_name} | {t_args}")

                    observation, artifact = _execute_tool(t_name, t_args, model_name)
                    if artifact:
                        last_artifact_path = artifact
                    thought_log.append(f"OBSERVATION (step {step}): {observation}")
                    yield _sse("observation", f"[OBSERVATION] {observation}")

                    # Feed observation back into context
                    messages.append({
                        "role": "assistant",
                        "tool_calls": [{
                            "id":       tc.id,
                            "type":     "function",
                            "function": {"name": t_name, "arguments": t_args},
                        }],
                    })
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "name":         t_name,
                        "content":      observation,
                    })
                continue  # next ReAct step

            # ── 2b. Inline JSON tool call (fallback for models w/o tool API) ─
            if message.content:
                parsed = _parse_inline_tool_call(message.content)
                if parsed:
                    t_name, t_args_dict = parsed
                    t_args = json.dumps(t_args_dict)

                    yield _sse("action", f"[ACTION] Intercepted inline tool call: {t_name}\nArgs: {t_args}")
                    thought_log.append(f"ACTION (step {step}): {t_name} | {t_args}")

                    observation, artifact = _execute_tool(t_name, t_args, model_name)
                    if artifact:
                        last_artifact_path = artifact
                    thought_log.append(f"OBSERVATION (step {step}): {observation}")
                    yield _sse("observation", f"[OBSERVATION] {observation}")

                    messages.append({
                        "role":    "assistant",
                        "content": f"[Tool '{t_name}' executed.]\n{observation}",
                    })
                    continue  # next ReAct step

            # ── 3. No tool calls – this is the final answer ──────────────────
            if message.content:
                final_answer = message.content
                break

            # ── 4. Empty response – abort ────────────────────────────────────
            break

        if final_answer is None:
            final_answer = "The agent completed its reasoning but produced no final text response."

        thought_process = "\n".join(thought_log)

        # Persist to DB
        log = TaskLog(
            agent_id=agent.id,
            input_query=user_prompt,
            thought_process=thought_process,
            final_output=final_answer,
        )
        session.add(log)
        session.commit()
        session.refresh(log)

        # Emit final answer
        result_payload = json.dumps({
            "task_log_id":   log.id,
            "agent_id":      agent.id,
            "final_output":  final_answer,
            "artifact_path": last_artifact_path,
        })
        yield _sse("final", result_payload)

    except Exception as exc:  # noqa: BLE001
        yield _sse("error", f"Fatal error: {exc}")

    finally:
        session.close()
        yield _sse("done", "[DONE]")


# ──────────────────────────────────────────────────────────────────────────────
# Legacy synchronous wrapper (kept for workflow executor compatibility)
# ──────────────────────────────────────────────────────────────────────────────

def run_agent_task(
    agent_id: int,
    user_prompt: str,
    image_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Blocking wrapper around stream_agent_task.
    Collects all SSE frames and returns the last 'final' payload as a dict.
    """

    async def _collect() -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "task_log_id":   -1,
            "agent_id":      agent_id,
            "final_output":  "",
            "artifact_path": None,
            "thought_process": "",
        }
        thought_lines: List[str] = []
        async for frame in stream_agent_task(agent_id, user_prompt, image_path):
            # frame is a raw SSE string; parse event / data
            event, data = "", ""
            for line in frame.split("\n"):
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip().replace("\\n", "\n")

            if event in ("thought", "action", "observation"):
                thought_lines.append(data)
            elif event == "final":
                try:
                    payload = json.loads(data)
                    result.update(payload)
                except json.JSONDecodeError:
                    result["final_output"] = data

        result["thought_process"] = "\n".join(thought_lines)
        return result

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_collect())
    finally:
        loop.close()
