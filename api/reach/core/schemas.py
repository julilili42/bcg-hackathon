"""Shared contracts between channels, core, storage, and the web API (ADR 0007: contracts first)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Channel = Literal["voice", "sms", "web", "import"]
Lang = Literal["sw", "en"]
Intent = Literal["report", "query", "help", "other"]
PendingKind = Literal["confirm", "choose", "need_entity"]


class InboundMessage(BaseModel):
    channel: Channel
    reporter_hash: str
    text: str = Field(max_length=500)
    lang_hint: Lang | None = None
    domain_hint: str | None = None


class Understanding(BaseModel):
    intent: Intent
    entity_name: str | None = None
    entity_id: str | None = None
    entity_confidence: float = 0.0
    status: str | None = None
    lang: Lang = "en"
    place_hint: str | None = None
    source: Literal["claude", "keywords"] = "keywords"


class AlternativeOut(BaseModel):
    entity_id: str
    name: str
    distance_km: float
    walk_minutes: int
    status: str
    confidence: float
    verified: bool


class OutboundReply(BaseModel):
    text: str
    lang: Lang
    intent: Intent
    domain_id: str
    entity_id: str | None = None
    entity_name: str | None = None
    status_recorded: str | None = None
    current_status: str | None = None
    confidence: float | None = None
    needs_confirmation: bool = False
    pending_kind: PendingKind | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    candidate_names: list[str] = Field(default_factory=list)
    alternatives: list[AlternativeOut] = Field(default_factory=list)
    understanding_source: Literal["claude", "keywords", "none"] = "none"


class PendingQuestion(BaseModel):
    """One open follow-up per sender and channel. Expires after a few minutes."""

    key: str
    channel: Channel
    domain_id: str
    lang: Lang
    kind: PendingKind
    status_claimed: str | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    raw_text: str | None = None
    attempts: int = 0
    created_at: datetime
    expires_at: datetime


class Entity(BaseModel):
    id: str
    domain_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    lat: float
    lon: float
    adm1: str | None = None
    adm2: str | None = None
    adm3: str | None = None
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    source: Literal["wpdx", "hfr", "osm", "report", "demo", "web"]
    external_id: str | None = None
    current_status: str = "unknown"
    confidence: float = 0.0
    last_report_at: datetime | None = None
    served_population: int | None = None


class Report(BaseModel):
    id: int | None = None
    entity_id: str
    reporter_hash: str
    channel: Channel
    lang: Lang | None = None
    raw_text: str | None = None
    status_claimed: str
    note: str | None = None
    weight: float = 1.0
    created_at: datetime


class ReportOut(Report):
    entity_name: str | None = None
    domain_id: str | None = None


class ReportIn(BaseModel):
    entity_id: str
    status: str
    note: str | None = Field(default=None, max_length=500)
    lang: Lang = "en"


class Interaction(BaseModel):
    id: int | None = None
    channel: Channel
    sender_hash: str
    lang: Lang | None
    body: str
    reply: str
    intent: Intent
    entity_id: str | None
    latency_ms: int
    created_at: datetime


class Stats(BaseModel):
    domain_id: str
    total: int
    by_status: dict[str, int]
    people_affected: int
    verified: int
    unverified: int
    disputed: int
    reports_24h: int


class DomainOut(BaseModel):
    id: str
    entity_type: str
    names: dict[str, str]
    good_statuses: list[str]
    bad_statuses: list[str]
    status_labels: dict[str, dict[str, str]]
