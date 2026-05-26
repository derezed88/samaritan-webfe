#!/usr/bin/env python3
"""
knowledge_graph_ingest_sources.py — embed samaritan_sources into Qdrant.

Pulls sources from MySQL that are missing from the samaritan_sources Qdrant
collection (by checking existing point IDs), embeds title + summary + domain_tags
via nomic-embed-text, and upserts into the collection.

Run whenever sources are inserted directly via SQL (bypassing llmem-gw):
  cd /home/markj/projects/samaritan-webfe && source venv/bin/activate
  python knowledge_graph_ingest_sources.py [--all]

  --all  : re-embed every active source, not just new ones

Collection: samaritan_sources @ 192.168.10.101:6333
Embedding:  nomic-embed-text @ 192.168.10.101:8000  (768 dims)
"""

import os
import sys
import time
import json
import httpx
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv("/home/markj/projects/.env", override=True)

MYSQL_USER  = os.getenv("MYSQL_USER", "markj")
MYSQL_PASS  = os.getenv("MYSQL_PASS", "")
MYSQL_HOST  = os.getenv("MYSQL_HOST", "localhost")
MYSQL_DB    = "mymcp"

QDRANT_HOST = os.getenv("QDRANT_HOST", "192.168.10.101")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
EMBED_URL   = os.getenv("EMBED_URL", "http://192.168.10.101:8000/v1/embeddings")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
VECTOR_DIMS = 768
COLLECTION  = "samaritan_sources"
BATCH_SIZE  = 20


def embed(text: str) -> list[float]:
    resp = httpx.post(
        EMBED_URL,
        json={"input": f"search_document: {text}", "model": EMBED_MODEL},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def get_existing_ids(qc) -> set[int]:
    """Return all point IDs already in the Qdrant collection."""
    existing = set()
    offset = None
    while True:
        result = qc.scroll(
            collection_name=COLLECTION,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        points, next_offset = result
        for p in points:
            existing.add(p.id)
        if next_offset is None:
            break
        offset = next_offset
    return existing


def main():
    re_embed_all = "--all" in sys.argv

    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10)

    conn = pymysql.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, canonical_url, summary, domain_tags, source_type, truth_score "
            "FROM samaritan_sources ORDER BY id"
        )
        rows = cur.fetchall()
    conn.close()

    if not re_embed_all:
        existing_ids = get_existing_ids(qc)
        rows = [r for r in rows if r["id"] not in existing_ids]
        print(f"Found {len(rows)} sources not yet in Qdrant (use --all to re-embed everything)")
    else:
        print(f"Re-embedding all {len(rows)} sources")

    if not rows:
        print("Nothing to do.")
        return

    points = []
    errors = 0

    for i, row in enumerate(rows):
        # Build embed text: title + summary + domain tags
        tags_raw = row["domain_tags"] or ""
        try:
            tags_list = json.loads(tags_raw) if tags_raw.strip().startswith("[") else tags_raw.split(",")
            tags_str = " ".join(t.strip() for t in tags_list if t.strip())
        except Exception:
            tags_str = tags_raw

        parts = [
            row["title"] or row["canonical_url"] or "",
            (row["summary"] or "")[:400],
            tags_str,
        ]
        text = ". ".join(p for p in parts if p).strip()[:1000]

        try:
            vector = embed(text)
        except Exception as e:
            print(f"  [!] source {row['id']} embed failed: {e}")
            errors += 1
            continue

        points.append(PointStruct(
            id=row["id"],
            vector=vector,
            payload={
                "title":       row["title"] or "",
                "url":         row["canonical_url"] or "",
                "summary":     (row["summary"] or "")[:500],
                "domain_tags": tags_str,
                "source_type": row["source_type"] or "",
                "truth_score": float(row["truth_score"] or 0),
                "type":        "source",
            },
        ))

        if len(points) >= BATCH_SIZE:
            qc.upsert(collection_name=COLLECTION, points=points)
            print(f"  upserted {i+1}/{len(rows)} sources…")
            points = []
            time.sleep(0.05)

    if points:
        qc.upsert(collection_name=COLLECTION, points=points)

    print(f"Done. {len(rows) - errors} upserted, {errors} errors.")
    info = qc.get_collection(COLLECTION)
    print(f"Collection points_count: {info.points_count}")


if __name__ == "__main__":
    main()
