from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# Allow override via environment variable for flexibility in different environments
DATABASE_URL = os.getenv("AGENTFLOW_DATABASE_URL", "sqlite:///./agentflow.db")


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    """
    Import models and create database tables.
    This should be called once on application startup.
    """
    # Import model modules so that they are registered with SQLAlchemy's metadata
    from app.models import agent_models  # noqa: F401
    from app.models import workflow_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


