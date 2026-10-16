"""JSON API for the web map and dashboard. Contract: docs/api/openapi.yaml."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from reach import __version__
from reach.core.geo import parse_bbox
from reach.core.schemas import DomainOut, Entity, Interaction, ReportIn, ReportOut, Stats
from reach.core.service import ReachService, hash_reporter

router = APIRouter(prefix="/api", tags=["web"])


def _service(request: Request) -> ReachService:
    service: ReachService = request.app.state.service
    return service


def _feature(entity: Entity, verified_min: float, domains: Any) -> dict[str, Any]:
    cfg = domains.get(entity.domain_id)
    props = entity.model_dump(mode="json", exclude={"lat", "lon"})
    props["verified"] = (
        entity.current_status not in ("unknown", "disputed") and entity.confidence >= verified_min
    )
    props["status_label"] = {
        "en": cfg.label("en", entity.current_status) if cfg else entity.current_status,
        "sw": cfg.label("sw", entity.current_status) if cfg else entity.current_status,
    }
    props["is_good"] = bool(cfg and cfg.is_good(entity.current_status))
    return {
        "type": "Feature",
        "id": entity.id,
        "geometry": {"type": "Point", "coordinates": [entity.lon, entity.lat]},
        "properties": props,
    }


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    service = _service(request)
    return {
        "status": "ok",
        "version": __version__,
        "domains": sorted(service.domains),
        "entities": service.repo.count_entities(),
        "understanding": service.understander.name,
        "tts": request.app.state.tts.name,
        "demo_phone": bool(request.app.state.settings.demo_phone),
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/domains", response_model=list[DomainOut])
def domains(request: Request) -> list[DomainOut]:
    return [cfg.to_out() for cfg in _service(request).domains.values()]


@router.get("/entities")
def entities(
    request: Request,
    domain: str = Query(default="water"),
    bbox: str | None = Query(default=None, description="minLon,minLat,maxLon,maxLat"),
) -> dict[str, Any]:
    service = _service(request)
    if domain not in service.domains:
        raise HTTPException(status_code=404, detail=f"unknown domain {domain}")
    box = None
    if bbox:
        try:
            box = parse_bbox(bbox)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    ents = service.repo.list_entities(domain, box)
    verified_min = service.params.verified_min_confidence
    return {
        "type": "FeatureCollection",
        "features": [_feature(e, verified_min, service.domains) for e in ents],
    }


@router.get("/entities/{entity_id}")
def entity_detail(request: Request, entity_id: str) -> dict[str, Any]:
    service = _service(request)
    entity = service.repo.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="entity not found")
    cfg = service.domains[entity.domain_id]
    reports = service.repo.reports_for_entity(entity_id, limit=50)
    alternatives = [] if cfg.is_good(entity.current_status) else service.alternatives_for(entity, cfg)
    return {
        "entity": _feature(entity, service.params.verified_min_confidence, service.domains),
        "reports": [_public_report(r) for r in reports],
        "alternatives": [a.model_dump(mode="json") for a in alternatives],
    }


def _public_report(report: ReportOut) -> dict[str, Any]:
    data = report.model_dump(mode="json")
    data["reporter_hash"] = report.reporter_hash[:8]
    return data


@router.get("/reports")
def reports(
    request: Request,
    domain: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    service = _service(request)
    return [_public_report(r) for r in service.repo.list_reports(domain, since, limit)]


@router.post("/reports", status_code=201)
def create_report(request: Request, body: ReportIn) -> dict[str, Any]:
    service = _service(request)
    client = request.client.host if request.client else "web"
    reporter = hash_reporter(f"web:{client}", request.app.state.settings.reporter_salt)
    try:
        result = service.web_report(body.entity_id, body.status, body.note, body.lang, reporter)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="entity not found")
    entity, derived, alternatives = result
    return {
        "entity": _feature(entity, service.params.verified_min_confidence, service.domains),
        "derived": {
            "status": derived.status,
            "confidence": derived.confidence,
            "report_count": derived.report_count,
            "votes": derived.votes,
        },
        "alternatives": [a.model_dump(mode="json") for a in alternatives],
    }


@router.get("/stats", response_model=Stats)
def stats(request: Request, domain: str = Query(default="water")) -> Stats:
    service = _service(request)
    if domain not in service.domains:
        raise HTTPException(status_code=404, detail=f"unknown domain {domain}")
    cfg = service.domains[domain]
    return service.repo.stats(domain, cfg.statuses.bad, service.params.verified_min_confidence)


@router.get("/interactions", response_model=list[Interaction])
def interactions(request: Request, limit: int = Query(default=30, ge=1, le=200)) -> list[Interaction]:
    items = _service(request).repo.list_interactions(limit)
    return [i.model_copy(update={"sender_hash": i.sender_hash[:8]}) for i in items]


@router.post("/admin/reset")
def admin_reset(
    request: Request,
    mode: str = Query(default="live", pattern="^(live|all)$"),
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Demo reset. Requires ADMIN_TOKEN to be configured and sent as X-Admin-Token."""
    settings = request.app.state.settings
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="admin token required")
    service = _service(request)
    if mode == "all":
        service.repo.clear_all()
        return {"reset": "all", "entities": 0}
    service.repo.clear_live_reports()
    n = service.recompute_all()
    return {"reset": "live", "entities": n}
