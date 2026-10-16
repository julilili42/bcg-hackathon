"""Community knowledge in one Qdrant collection: every report is a point with a dense vector (FastEmbed) and a
BM25 sparse vector, retrieved with native RRF fusion. Reports are never overwritten, each one is new evidence.
`uv run -m gateway.knowledge` seeds the collection from the water point table (safe to rerun)."""
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models
from . import db

COLLECTION = os.environ.get("QDRANT_COLLECTION", "").strip() or "water_knowledge"
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
BM25_MODEL = "Qdrant/bm25"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


@lru_cache
def client():
    # cloud_inference: BM25 documents are embedded by the Qdrant server, only the dense vector is computed here
    return QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
                        api_key=os.environ.get("QDRANT_API_KEY") or None, cloud_inference=True, timeout=60)


@lru_cache
def embedder():
    return TextEmbedding(model_name=DENSE_MODEL)


def dense(text):
    return next(iter(embedder().embed([text]))).tolist()


@lru_cache
def initialize():
    """Collection + payload indexes, once per process."""
    c = client()
    if not c.collection_exists(COLLECTION):
        c.create_collection(COLLECTION,
            vectors_config={"dense": models.VectorParams(size=384, distance=models.Distance.COSINE)},
            sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)})
    for field in ("village", "asset_id", "record_type", "attribute"):
        c.create_payload_index(COLLECTION, field, models.PayloadSchemaType.KEYWORD, wait=True)
    return True


def ingest(payload):
    initialize()
    point_id = str(uuid5(NAMESPACE_URL, f"waterline:{payload['record_type']}:{payload['source_id']}:{payload['chunk_index']}"))
    client().upsert(COLLECTION, points=[models.PointStruct(id=point_id,
        vector={"dense": dense(payload["text"]), "bm25": models.Document(text=payload["text"], model=BM25_MODEL)},
        payload={"source_text": payload["text"], **payload, "ingested_at": utcnow()})], wait=True)
    return point_id


def store_facts(facts, message, user_id, turn_id, received_at):
    """One point per fact; the id is derived from (turn_id, index), so a retried turn does not duplicate."""
    return [ingest({**fact.model_dump(exclude={"statement"}), "text": fact.statement,
        "source_text": message, "record_type": "community_report", "source_id": turn_id,
        "chunk_index": i, "user_id": user_id, "source_type": "community_user",
        "verification_status": "unverified", "reported_at": received_at}) for i, fact in enumerate(facts)]


def payload_filter(asset_id=None, village=None, attribute=None):
    fields = {"asset_id": asset_id, "village": village, "attribute": attribute}
    conditions = [models.FieldCondition(key=k, match=models.MatchValue(value=v)) for k, v in fields.items() if v]
    return models.Filter(must=conditions) if conditions else None


def hybrid_search(question, asset_id=None, village=None):
    initialize()
    filt = payload_filter(asset_id, village)
    hits = client().query_points(COLLECTION, prefetch=[
        models.Prefetch(query=dense(question), using="dense", limit=25, filter=filt),
        models.Prefetch(query=models.Document(text=question, model=BM25_MODEL), using="bm25", limit=25, filter=filt)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=12, with_payload=True).points
    return [{**p.payload, "point_id": str(p.id)} for p in hits]


def status_history(asset_id=None, village=None):
    """Exact scroll, so the newest status report is found even when it is not in the fused top 12."""
    initialize()
    points, offset = client().scroll(COLLECTION, scroll_filter=payload_filter(asset_id, village, "operational_status"),
                                     limit=100, with_payload=True, with_vectors=False)
    if offset is not None:
        raise RuntimeError("status history exceeds 100 records; narrow the query before answering")
    return [{**p.payload, "point_id": str(p.id)} for p in points]


def event_time(p):
    value = p.get("observed_at") or p.get("reported_at") or p.get("document_date")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def resolve_evidence(records, current_status=False, turn_id=None):
    """Only compare the same asset/attribute; keep nearby conflicts and verified dissent."""
    records = list({p["point_id"]: p for p in records}.values())
    selected, groups = [], {}
    for p in records:
        if current_status and p.get("asset_id") and p.get("attribute") == "operational_status":
            groups.setdefault((p["asset_id"], p["attribute"]), []).append(p)
        else:
            selected.append(p)
    for group in groups.values():
        group.sort(key=event_time, reverse=True)
        newest = group[0]
        chosen = [newest]
        for older in group[1:]:
            if older.get("value") != newest.get("value") and (
                    event_time(newest) - event_time(older) <= timedelta(days=1)
                    or older.get("verification_status") in {"verified", "confirmed"}):
                chosen.append(older)
                break
        for p in chosen:
            selected.append({**p, "conflict": len(chosen) > 1, "latest_for_asset": p is newest})
    # never hand private provenance to the answer model or the API
    return [{k: v for k, v in {**p, "time_basis": "observed_at" if p.get("observed_at") else "report/document time",
                               "just_reported": p.get("source_id") == turn_id}.items()
             if k not in {"user_id", "source_text", "ingested_at"}} for p in selected]


def seed():
    """One registry record and one status observation per water point in the table."""
    ids = []
    for w in db.waterpoints():
        common = dict(asset_id=w["name"], village=w["village"], asset_name=w["name"], record_type="document_chunk",
                      user_id=None, source_type="registry", verification_status="unverified", chunk_index=0)
        ids.append(ingest({**common, "source_id": f"registry-{w['name']}", "document_date": "2013-01-01T00:00:00Z",
            "text": f"{w['name']} is a water point in {w['village']}, Soga ward, Kibaha (Ministry of Water mapping 2011-2013). "
                    "No water-quality evidence is available."}))
        when = str(w["updated"]).replace(" ", "T") + "Z"
        ids.append(ingest({**common, "source_id": f"status-{w['name']}", "attribute": "operational_status",
            "value": {"ok": "working"}.get(w["status"], w["status"]), "observed_at": when, "reported_at": when,
            "text": f"{w['name']} in {w['village']} was reported {w['status']} on {when[:10]}."}))
    return ids


if __name__ == "__main__":
    print(f"seeded {len(seed())} records into {COLLECTION} (safe to rerun)")
