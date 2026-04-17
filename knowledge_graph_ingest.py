#!/usr/bin/env python3
"""
knowledge_graph_ingest.py — seed samaritan_beliefs Qdrant collection.

Pulls all active beliefs from MySQL, embeds topic+content via nomic-embed-text,
and upserts into the samaritan_beliefs collection on NUC11 Qdrant.

Run once manually, then re-run whenever beliefs change significantly:
  cd /home/markj/projects/samaritan-webfe && source venv/bin/activate
  python knowledge_graph_ingest.py

Collection: samaritan_beliefs @ 10.0.0.101:6333
Embedding:  nomic-embed-text @ 10.0.0.101:8000  (768 dims)
"""

import os
import sys
import time
import httpx
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv()

MYSQL_USER   = os.getenv("MYSQL_USER", "markj")
MYSQL_PASS   = os.getenv("MYSQL_PASS", "")
MYSQL_HOST   = os.getenv("MYSQL_HOST", "localhost")
MYSQL_DB     = "mymcp"

QDRANT_HOST  = os.getenv("QDRANT_HOST", "10.0.0.101")
QDRANT_PORT  = int(os.getenv("QDRANT_PORT", "6333"))
EMBED_URL    = os.getenv("EMBED_URL", "http://10.0.0.101:8000/v1/embeddings")
EMBED_MODEL  = os.getenv("EMBED_MODEL", "nomic-embed-text")
VECTOR_DIMS  = 768
COLLECTION   = "samaritan_beliefs"
BATCH_SIZE   = 20


def embed(text: str) -> list[float]:
    resp = httpx.post(
        EMBED_URL,
        json={"input": f"search_document: {text}", "model": EMBED_MODEL},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def ensure_collection(qc):
    from qdrant_client.models import Distance, VectorParams
    existing = {c.name for c in qc.get_collections().collections}
    if COLLECTION not in existing:
        qc.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIMS, distance=Distance.COSINE),
        )
        print(f"Created collection: {COLLECTION}")
    else:
        print(f"Collection exists: {COLLECTION}")


def main():
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10)
    ensure_collection(qc)

    conn = pymysql.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, topic, content, confidence FROM samaritan_beliefs "
            "WHERE status='active' ORDER BY id"
        )
        rows = cur.fetchall()
    conn.close()

    print(f"Embedding {len(rows)} active beliefs…")
    points = []
    errors = 0

    for i, row in enumerate(rows):
        text = f"{row['topic']}. {row['content'] or ''}".strip()[:1000]
        try:
            vector = embed(text)
        except Exception as e:
            print(f"  [!] belief {row['id']} embed failed: {e}")
            errors += 1
            continue

        points.append(PointStruct(
            id=row["id"],
            vector=vector,
            payload={
                "topic":      row["topic"],
                "content":    (row["content"] or "")[:500],
                "confidence": row["confidence"],
                "type":       "belief",
            },
        ))

        if len(points) >= BATCH_SIZE:
            qc.upsert(collection_name=COLLECTION, points=points)
            print(f"  upserted {i+1}/{len(rows)} beliefs…")
            points = []
            time.sleep(0.1)

    if points:
        qc.upsert(collection_name=COLLECTION, points=points)

    print(f"Done. {len(rows) - errors} upserted, {errors} errors.")
    info = qc.get_collection(COLLECTION)
    print(f"Collection vectors_count: {info.vectors_count}")


if __name__ == "__main__":
    main()
