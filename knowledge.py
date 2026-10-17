"""One collection, native hybrid retrieval, and explicit temporal evidence rules."""
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

load_dotenv()
COLLECTION = os.getenv("QDRANT_COLLECTION", "").strip() or "water_knowledge"
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
BM25_MODEL = "Qdrant/bm25"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


@lru_cache
def client():
    # cloud_inference sends Document objects to the server, rather than local FastEmbed.
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"),
                        api_key=os.getenv("QDRANT_API_KEY") or None,
                        cloud_inference=True, timeout=60)


@lru_cache
def embedder():
    return TextEmbedding(model_name=DENSE_MODEL)


def dense(text):
    return next(iter(embedder().embed([text]))).tolist()


def initialize():
    c = client()
    if not c.collection_exists(COLLECTION):
        c.create_collection(COLLECTION,
            vectors_config={"dense": models.VectorParams(size=384, distance=models.Distance.COSINE)},
            sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)})
    for field in ("village", "asset_id", "record_type", "attribute"):
        c.create_payload_index(COLLECTION, field, models.PayloadSchemaType.KEYWORD, wait=True)


def ingest(payload, point_id=None):
    point_id = point_id or str(uuid5(NAMESPACE_URL, f"waterline:{payload['record_type']}:{payload['source_id']}:{payload['chunk_index']}"))
    client().upsert(COLLECTION, points=[models.PointStruct(id=point_id,
        vector={"dense": dense(payload["text"]),
                "bm25": models.Document(text=payload["text"], model=BM25_MODEL)},
        payload={"source_text": payload["text"], **payload, "ingested_at": utcnow()})], wait=True)
    return point_id


def store_facts(facts, message, user_id, turn_id, received_at):
    return [ingest({**fact.model_dump(exclude={"statement"}), "text": fact.statement,
        "source_text": message, "record_type": "community_report", "source_id": turn_id,
        "chunk_index": i, "user_id": user_id, "source_type": "community_user",
        "verification_status": "unverified", "reported_at": received_at,
        "synthetic": True}) for i, fact in enumerate(facts)]


def payload_filter(asset_id=None, village=None, attribute=None):
    fields = {"asset_id": asset_id, "village": village, "attribute": attribute}
    conditions = [models.FieldCondition(key=k, match=(models.MatchAny(any=v) if isinstance(v, list)
                                                    else models.MatchValue(value=v)))
                  for k, v in fields.items() if v]
    return models.Filter(must=conditions) if conditions else None


def hybrid_search(question, asset_id=None, village=None):
    filt = payload_filter(asset_id, village)
    hits = client().query_points(COLLECTION, prefetch=[
        models.Prefetch(query=dense(question), using="dense", limit=25, filter=filt),
        models.Prefetch(query=models.Document(text=question, model=BM25_MODEL),
                        using="bm25", limit=25, filter=filt)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=12, with_payload=True).points
    return [{**p.payload, "point_id": str(p.id)} for p in hits]


def status_history(asset_id=None, village=None):
    points, offset = client().scroll(COLLECTION,
        scroll_filter=payload_filter(asset_id, village, "operational_status"),
        limit=100, with_payload=True, with_vectors=False)
    if offset is not None:
        raise RuntimeError("Demo status history exceeds 100 records; narrow the query before answering.")
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
            selected.append({**p, "conflict": len(chosen) > 1,
                             "latest_for_asset": p is newest})
    # Never send private provenance identifiers to the answer model or API sources.
    return [{k: v for k, v in {**p,
        "time_basis": "observed_at" if p.get("observed_at") else "report/document time",
        "just_reported": p.get("source_id") == turn_id}.items()
        if k not in {"user_id", "source_text", "ingested_at"}} for p in selected]
