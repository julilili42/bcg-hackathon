"""Repository over the Core tables. Returns the pydantic contracts from ``reach.core.schemas``."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.engine import Engine, Row

from reach.core.geo import BBox
from reach.core.schemas import Channel, Entity, Interaction, PendingQuestion, Report, ReportOut, Stats
from reach.storage.db import aliases, conversations, entities, interactions, reports


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # ---------------------------------------------------------------- entities
    def upsert_entity(self, entity: Entity) -> None:
        values: dict[str, Any] = {
            "domain_id": entity.domain_id,
            "name": entity.name,
            "lat": entity.lat,
            "lon": entity.lon,
            "adm1": entity.adm1,
            "adm2": entity.adm2,
            "adm3": entity.adm3,
            "attributes_json": json.dumps(entity.attributes, ensure_ascii=False, sort_keys=True),
            "source": entity.source,
            "external_id": entity.external_id,
            "current_status": entity.current_status,
            "confidence": entity.confidence,
            "last_report_at": _naive_utc(entity.last_report_at) if entity.last_report_at else None,
            "served_population": entity.served_population,
        }
        with self.engine.begin() as conn:
            exists = conn.execute(select(entities.c.id).where(entities.c.id == entity.id)).first()
            if exists:
                conn.execute(update(entities).where(entities.c.id == entity.id).values(**values))
            else:
                conn.execute(insert(entities).values(id=entity.id, **values))
            if entity.aliases:
                conn.execute(delete(aliases).where(aliases.c.entity_id == entity.id))
                conn.execute(
                    insert(aliases),
                    [{"entity_id": entity.id, "alias": a} for a in dict.fromkeys(entity.aliases)],
                )

    def add_aliases(self, entity_id: str, new_aliases: Iterable[str]) -> None:
        wanted = [a for a in dict.fromkeys(new_aliases) if a.strip()]
        if not wanted:
            return
        with self.engine.begin() as conn:
            existing = {
                r[0] for r in conn.execute(select(aliases.c.alias).where(aliases.c.entity_id == entity_id))
            }
            rows = [{"entity_id": entity_id, "alias": a} for a in wanted if a not in existing]
            if rows:
                conn.execute(insert(aliases), rows)

    def _alias_map(self, conn: Any, entity_ids: Sequence[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if not entity_ids:
            return out
        for eid, alias in conn.execute(
            select(aliases.c.entity_id, aliases.c.alias).where(aliases.c.entity_id.in_(list(entity_ids)))
        ):
            out.setdefault(eid, []).append(alias)
        return out

    @staticmethod
    def _row_to_entity(row: Row[Any], alias_list: list[str]) -> Entity:
        m = row._mapping
        return Entity(
            id=m["id"],
            domain_id=m["domain_id"],
            name=m["name"],
            aliases=sorted(alias_list),
            lat=m["lat"],
            lon=m["lon"],
            adm1=m["adm1"],
            adm2=m["adm2"],
            adm3=m["adm3"],
            attributes=json.loads(m["attributes_json"] or "{}"),
            source=m["source"],
            external_id=m["external_id"],
            current_status=m["current_status"],
            confidence=m["confidence"],
            last_report_at=_aware(m["last_report_at"]),
            served_population=m["served_population"],
        )

    def list_entities(self, domain_id: str | None = None, bbox: BBox | None = None) -> list[Entity]:
        stmt = select(entities)
        if domain_id:
            stmt = stmt.where(entities.c.domain_id == domain_id)
        if bbox:
            min_lat, min_lon, max_lat, max_lon = bbox
            stmt = stmt.where(
                and_(
                    entities.c.lat >= min_lat,
                    entities.c.lat <= max_lat,
                    entities.c.lon >= min_lon,
                    entities.c.lon <= max_lon,
                )
            )
        stmt = stmt.order_by(entities.c.name)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).all()
            alias_map = self._alias_map(conn, [r._mapping["id"] for r in rows])
        return [self._row_to_entity(r, alias_map.get(r._mapping["id"], [])) for r in rows]

    def get_entity(self, entity_id: str) -> Entity | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(entities).where(entities.c.id == entity_id)).first()
            if row is None:
                return None
            alias_map = self._alias_map(conn, [entity_id])
        return self._row_to_entity(row, alias_map.get(entity_id, []))

    def find_by_external_id(self, source: str, external_id: str) -> Entity | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(entities).where(
                    and_(entities.c.source == source, entities.c.external_id == external_id)
                )
            ).first()
            if row is None:
                return None
            alias_map = self._alias_map(conn, [row._mapping["id"]])
        return self._row_to_entity(row, alias_map.get(row._mapping["id"], []))

    def update_entity_status(
        self, entity_id: str, status: str, confidence: float, last_report_at: datetime | None
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(entities)
                .where(entities.c.id == entity_id)
                .values(
                    current_status=status,
                    confidence=confidence,
                    last_report_at=_naive_utc(last_report_at) if last_report_at else None,
                )
            )

    def count_entities(self, domain_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(entities)
        if domain_id:
            stmt = stmt.where(entities.c.domain_id == domain_id)
        with self.engine.connect() as conn:
            return int(conn.execute(stmt).scalar_one())

    # ----------------------------------------------------------------- reports
    def add_report(self, report: Report) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(reports).values(
                    entity_id=report.entity_id,
                    reporter_hash=report.reporter_hash,
                    channel=report.channel,
                    lang=report.lang,
                    raw_text=report.raw_text,
                    status_claimed=report.status_claimed,
                    note=report.note,
                    weight=report.weight,
                    created_at=_naive_utc(report.created_at),
                )
            )
            pk = result.inserted_primary_key
            return int(pk[0]) if pk is not None else 0

    @staticmethod
    def _row_to_report(row: Row[Any]) -> ReportOut:
        m = row._mapping
        return ReportOut(
            id=m["id"],
            entity_id=m["entity_id"],
            reporter_hash=m["reporter_hash"],
            channel=m["channel"],
            lang=m["lang"],
            raw_text=m["raw_text"],
            status_claimed=m["status_claimed"],
            note=m["note"],
            weight=m["weight"],
            created_at=_aware(m["created_at"]) or datetime.now(UTC),
            entity_name=m.get("name"),
            domain_id=m.get("domain_id"),
        )

    def reports_for_entity(self, entity_id: str, limit: int = 200) -> list[ReportOut]:
        stmt = (
            select(reports, entities.c.name, entities.c.domain_id)
            .join(entities, entities.c.id == reports.c.entity_id)
            .where(reports.c.entity_id == entity_id)
            .order_by(reports.c.created_at.desc(), reports.c.id.desc())
            .limit(limit)
        )
        with self.engine.connect() as conn:
            return [self._row_to_report(r) for r in conn.execute(stmt)]

    def list_reports(
        self,
        domain_id: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
        exclude_channels: Iterable[Channel] = ("import",),
    ) -> list[ReportOut]:
        stmt = select(reports, entities.c.name, entities.c.domain_id).join(
            entities, entities.c.id == reports.c.entity_id
        )
        if domain_id:
            stmt = stmt.where(entities.c.domain_id == domain_id)
        if since:
            stmt = stmt.where(reports.c.created_at >= _naive_utc(since))
        excluded = list(exclude_channels)
        if excluded:
            stmt = stmt.where(reports.c.channel.not_in(excluded))
        stmt = stmt.order_by(reports.c.created_at.desc(), reports.c.id.desc()).limit(limit)
        with self.engine.connect() as conn:
            return [self._row_to_report(r) for r in conn.execute(stmt)]

    def count_reports_by_reporter(self, reporter_hash: str, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(reports)
            .where(and_(reports.c.reporter_hash == reporter_hash, reports.c.created_at >= _naive_utc(since)))
        )
        with self.engine.connect() as conn:
            return int(conn.execute(stmt).scalar_one())

    # ------------------------------------------------------------ interactions
    def log_interaction(self, item: Interaction) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(interactions).values(
                    channel=item.channel,
                    sender_hash=item.sender_hash,
                    lang=item.lang,
                    body=item.body[:500],
                    reply=item.reply[:1000],
                    intent=item.intent,
                    entity_id=item.entity_id,
                    latency_ms=item.latency_ms,
                    created_at=_naive_utc(item.created_at),
                )
            )
            pk = result.inserted_primary_key
            return int(pk[0]) if pk is not None else 0

    def list_interactions(self, limit: int = 50) -> list[Interaction]:
        stmt = (
            select(interactions)
            .order_by(interactions.c.created_at.desc(), interactions.c.id.desc())
            .limit(limit)
        )
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [
            Interaction(
                id=r._mapping["id"],
                channel=r._mapping["channel"],
                sender_hash=r._mapping["sender_hash"],
                lang=r._mapping["lang"],
                body=r._mapping["body"],
                reply=r._mapping["reply"],
                intent=r._mapping["intent"],
                entity_id=r._mapping["entity_id"],
                latency_ms=r._mapping["latency_ms"],
                created_at=_aware(r._mapping["created_at"]) or datetime.now(UTC),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------- stats
    def stats(self, domain_id: str, bad_statuses: Iterable[str], verified_min_confidence: float) -> Stats:
        bad = list(bad_statuses)
        with self.engine.connect() as conn:
            total = int(
                conn.execute(
                    select(func.count()).select_from(entities).where(entities.c.domain_id == domain_id)
                ).scalar_one()
            )
            by_status = {
                str(status): int(n)
                for status, n in conn.execute(
                    select(entities.c.current_status, func.count())
                    .where(entities.c.domain_id == domain_id)
                    .group_by(entities.c.current_status)
                )
            }
            people = conn.execute(
                select(func.coalesce(func.sum(entities.c.served_population), 0)).where(
                    and_(entities.c.domain_id == domain_id, entities.c.current_status.in_(bad))
                )
            ).scalar_one()
            verified = int(
                conn.execute(
                    select(func.count())
                    .select_from(entities)
                    .where(
                        and_(
                            entities.c.domain_id == domain_id,
                            entities.c.confidence >= verified_min_confidence,
                            entities.c.current_status.not_in(["unknown", "disputed"]),
                        )
                    )
                ).scalar_one()
            )
            disputed = by_status.get("disputed", 0)
            since = datetime.now(UTC) - timedelta(hours=24)
            reports_24h = int(
                conn.execute(
                    select(func.count())
                    .select_from(reports)
                    .join(entities, entities.c.id == reports.c.entity_id)
                    .where(
                        and_(
                            entities.c.domain_id == domain_id,
                            reports.c.created_at >= _naive_utc(since),
                            reports.c.channel != "import",
                        )
                    )
                ).scalar_one()
            )
        return Stats(
            domain_id=domain_id,
            total=total,
            by_status=by_status,
            people_affected=int(people or 0),
            verified=verified,
            unverified=max(0, total - verified - disputed),
            disputed=disputed,
            reports_24h=reports_24h,
        )

    # ---------------------------------------------------------- conversations
    def set_pending(self, pending: PendingQuestion) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(conversations).where(conversations.c.key == pending.key))
            conn.execute(
                insert(conversations).values(
                    key=pending.key,
                    channel=pending.channel,
                    domain_id=pending.domain_id,
                    lang=pending.lang,
                    kind=pending.kind,
                    status_claimed=pending.status_claimed,
                    candidates_json=json.dumps(pending.candidate_ids),
                    raw_text=pending.raw_text,
                    attempts=pending.attempts,
                    created_at=_naive_utc(pending.created_at),
                    expires_at=_naive_utc(pending.expires_at),
                )
            )

    def get_pending(self, key: str, now: datetime) -> PendingQuestion | None:
        with self.engine.begin() as conn:
            row = conn.execute(select(conversations).where(conversations.c.key == key)).first()
            if row is None:
                return None
            m = row._mapping
            expires = _aware(m["expires_at"]) or now
            if expires <= (now if now.tzinfo else now.replace(tzinfo=UTC)):
                conn.execute(delete(conversations).where(conversations.c.key == key))
                return None
            return PendingQuestion(
                key=m["key"],
                channel=m["channel"],
                domain_id=m["domain_id"],
                lang=m["lang"],
                kind=m["kind"],
                status_claimed=m["status_claimed"],
                candidate_ids=json.loads(m["candidates_json"] or "[]"),
                raw_text=m["raw_text"],
                attempts=m["attempts"],
                created_at=_aware(m["created_at"]) or now,
                expires_at=expires,
            )

    def clear_pending(self, key: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(conversations).where(conversations.c.key == key))

    # ------------------------------------------------------------------- admin
    def clear_all(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(conversations))
            conn.execute(delete(interactions))
            conn.execute(delete(reports))
            conn.execute(delete(aliases))
            conn.execute(delete(entities))

    def clear_live_reports(self) -> None:
        """Demo reset: drop everything that is not an imported baseline."""
        with self.engine.begin() as conn:
            conn.execute(delete(reports).where(reports.c.channel != "import"))
            conn.execute(delete(interactions))
            conn.execute(delete(conversations))
