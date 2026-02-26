from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    role = Column(String(255), nullable=False)
    # Optional default LLM model to use for this agent (e.g. mistral:7b, llama3.2-vision:11b)
    model_name = Column(String(255), nullable=True)
    backstory = Column(Text, nullable=True)
    # Store tools as a JSON-encoded string (e.g., '["web_search", "bash_tool"]')
    tools = Column(Text, nullable=True, comment="JSON-encoded list of tools for this agent")

    task_logs = relationship("TaskLog", back_populates="agent", cascade="all, delete-orphan")


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), index=True, nullable=False)

    input_query = Column(Text, nullable=False)
    thought_process = Column(Text, nullable=True)
    final_output = Column(Text, nullable=True)

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    agent = relationship("Agent", back_populates="task_logs")


