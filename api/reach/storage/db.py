"""Table definitions and engine factory. ``metadata`` is the single source of truth for the schema."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

entities = Table(
    "entities",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("domain_id", String(32), nullable=False),
    Column("name", String(160), nullable=False),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("adm1", String(80)),
    Column("adm2", String(80)),
    Column("adm3", String(80)),
    Column("attributes_json", Text, nullable=False, default="{}"),
    Column("source", String(16), nullable=False),
    Column("external_id", String(80)),
    Column("current_status", String(32), nullable=False, default="unknown"),
    Column("confidence", Float, nullable=False, default=0.0),
    Column("last_report_at", DateTime),
    Column("served_population", Integer),
    Index("ix_entities_domain_geo", "domain_id", "lat", "lon"),
)

aliases = Table(
    "aliases",
    metadata,
    Column("entity_id", String(64), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
    Column("alias", String(160), primary_key=True),
)

reports = Table(
    "reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entity_id", String(64), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
    Column("reporter_hash", String(64), nullable=False),
    Column("channel", String(8), nullable=False),
    Column("lang", String(2)),
    Column("raw_text", Text),
    Column("status_claimed", String(32), nullable=False),
    Column("note", Text),
    Column("weight", Float, nullable=False, default=1.0),
    Column("created_at", DateTime, nullable=False),
    Index("ix_reports_entity_created", "entity_id", "created_at"),
    Index("ix_reports_reporter_created", "reporter_hash", "created_at"),
)

interactions = Table(
    "interactions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(8), nullable=False),
    Column("sender_hash", String(64), nullable=False),
    Column("lang", String(2)),
    Column("body", Text, nullable=False),
    Column("reply", Text, nullable=False),
    Column("intent", String(16), nullable=False),
    Column("entity_id", String(64)),
    Column("latency_ms", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False),
    Index("ix_interactions_created", "created_at"),
)

conversations = Table(
    "conversations",
    metadata,
    Column("key", String(80), primary_key=True),  # "<channel>:<reporter_hash>"
    Column("channel", String(8), nullable=False),
    Column("domain_id", String(32), nullable=False),
    Column("lang", String(2), nullable=False),
    Column("kind", String(16), nullable=False),  # confirm | choose | need_entity
    Column("status_claimed", String(32)),
    Column("candidates_json", Text, nullable=False, default="[]"),
    Column("raw_text", Text),
    Column("attempts", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False),
    Column("expires_at", DateTime, nullable=False),
)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).expanduser().parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)


def drop_all(engine: Engine) -> None:
    metadata.drop_all(engine)
