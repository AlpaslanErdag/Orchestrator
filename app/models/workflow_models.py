from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Workflow(Base):
    """
    A saved workflow definition, composed of nodes and edges.
    """

    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    nodes = relationship(
        "WorkflowNode",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    edges = relationship(
        "WorkflowEdge",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )


class WorkflowNode(Base):
    """
    A node on the workflow canvas (source, agent, tool, or output).

    - type: high-level category, e.g. 'source', 'agent', 'tool', 'output'
    - key: concrete implementation, e.g. 'url_input', 'file_upload', 'agent', 'pdf_tool'
    - config: JSON-encoded dict with node-specific settings (agent_id, prompt template, etc.)
    """

    __tablename__ = "workflow_nodes"

    id = Column(Integer, primary_key=True, index=True)

    workflow_id = Column(
        Integer,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type = Column(String(50), nullable=False)
    key = Column(String(100), nullable=True)
    label = Column(String(255), nullable=True)

    position_x = Column(Float, nullable=False, default=0.0)
    position_y = Column(Float, nullable=False, default=0.0)

    config = Column(
        Text,
        nullable=True,
        comment="JSON-encoded configuration for this node (agent_id, URL template, etc.)",
    )

    workflow = relationship("Workflow", back_populates="nodes")

    outgoing_edges = relationship(
        "WorkflowEdge",
        foreign_keys="WorkflowEdge.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming_edges = relationship(
        "WorkflowEdge",
        foreign_keys="WorkflowEdge.target_node_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )


class WorkflowEdge(Base):
    """
    A directed connection between two workflow nodes.

    - source_handle / target_handle can map specific ports/slots on the node
      (useful for complex tools with multiple inputs/outputs).
    - config: JSON-encoded dict for edge-specific settings (e.g., field mappings).
    """

    __tablename__ = "workflow_edges"

    id = Column(Integer, primary_key=True, index=True)

    workflow_id = Column(
        Integer,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_node_id = Column(
        Integer,
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id = Column(
        Integer,
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_handle = Column(String(100), nullable=True)
    target_handle = Column(String(100), nullable=True)

    config = Column(
        Text,
        nullable=True,
        comment="JSON-encoded configuration for this edge (e.g., data mapping rules).",
    )

    workflow = relationship("Workflow", back_populates="edges")
    source_node = relationship(
        "WorkflowNode",
        foreign_keys=[source_node_id],
        back_populates="outgoing_edges",
    )
    target_node = relationship(
        "WorkflowNode",
        foreign_keys=[target_node_id],
        back_populates="incoming_edges",
    )


