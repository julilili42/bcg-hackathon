"""Retry committed reports whose Qdrant writes failed, using stable report UUIDs."""
import infrastructure as db
import knowledge as kb

if __name__ == "__main__":
    kb.initialize()
    indexed, failed = db.reindex()
    print(f"Indexed {indexed} reports; {failed} remain pending.")
    raise SystemExit(bool(failed))
