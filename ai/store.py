# -*- coding: utf-8 -*-
"""文档与向量存储：复用同一个 SQLite 文件，新增 documents / chunks 两张表。

设计取舍：
* 不引入 FAISS / Chroma —— Python 3.13 上它们没有稳定的 wheel，而本项目的数据量
  （几十份资料、几千个分块）用 numpy 做一次矩阵乘法完全够用，ms 级。
* 不引入 Alembic —— 用 CREATE TABLE IF NOT EXISTS，和项目现有「启动时 ALTER TABLE
  补列」的做法保持一致，零迁移成本。
* 向量以 float32 的二进制块存 BLOB —— 比存 JSON 文本小一半，读回来 np.frombuffer 就还原。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import create_engine, text

from . import config

engine = create_engine(
    f"sqlite:///{config.DB_PATH}",
    connect_args={"check_same_thread": False},
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    source       TEXT    DEFAULT '',
    char_count   INTEGER DEFAULT 0,
    chunk_count  INTEGER DEFAULT 0,
    created_at   TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    content      TEXT    NOT NULL,
    embedding    BLOB,
    dim          INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
"""


def init_db() -> None:
    with engine.begin() as conn:
        for stmt in filter(None, (s.strip() for s in _SCHEMA.split(";"))):
            conn.execute(text(stmt))


init_db()


# ==================== 分块 ====================

_SENT_SPLIT = re.compile(r"(?<=[。！？；.!?;])\s*")


def chunk_text(content: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """按「段落 → 句子」贪心拼块，块之间保留少量重叠，避免答案被切断。

    比固定长度硬切的好处：每块尽量落在句子边界上，检索出来更像人写的一段话。
    """
    size = size or config.CHUNK_SIZE
    overlap = overlap if overlap is not None else config.CHUNK_OVERLAP
    content = (content or "").strip()
    if not content:
        return []
    if len(content) <= size:
        return [content]

    # 先按空行分段，段内再按句子切
    units: list[str] = []
    for para in re.split(r"\n\s*\n", content):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            units.append(para)
            continue
        for sent in _SENT_SPLIT.split(para):
            sent = sent.strip()
            if sent:
                units.append(sent)

    chunks: list[str] = []
    buffer = ""
    for unit in units:
        if not buffer:
            buffer = unit
        elif len(buffer) + 1 + len(unit) <= size:
            buffer = f"{buffer} {unit}"
        else:
            chunks.append(buffer)
            # 重叠：带上上一块末尾 overlap 个字符，保证跨块语义连续
            tail = buffer[-overlap:] if overlap > 0 else ""
            buffer = f"{tail} {unit}".strip() if tail else unit
    if buffer:
        chunks.append(buffer)

    # 兜底：极端情况下单块仍超长（超长句子），按硬长度再切一次
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= size * 1.5:
            result.append(chunk)
        else:
            for i in range(0, len(chunk), size):
                result.append(chunk[i : i + size])
    return result


# ==================== 写入 ====================

def _to_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def add_document(title: str, content: str, source: str = "", vectors: list[list[float]] | None = None) -> dict:
    """写入一篇文档及其分块。vectors 由调用方先用 embed() 算好，便于测试时 mock。"""
    pieces = chunk_text(content)
    if not pieces:
        raise ValueError("文档内容为空")
    if vectors is not None and len(vectors) != len(pieces):
        raise ValueError(f"向量数量({len(vectors)})与分块数量({len(pieces)})不一致")

    now = datetime.now().isoformat(timespec="seconds")
    with engine.begin() as conn:
        doc_id = conn.execute(
            text(
                "INSERT INTO documents (title, source, char_count, chunk_count, created_at) "
                "VALUES (:t, :s, :c, :n, :now)"
            ),
            {"t": title, "s": source, "c": len(content), "n": len(pieces), "now": now},
        ).lastrowid
        rows = []
        for seq, piece in enumerate(pieces):
            vec = vectors[seq] if vectors is not None else None
            rows.append(
                {
                    "d": doc_id,
                    "seq": seq,
                    "content": piece,
                    "blob": _to_blob(vec) if vec else None,
                    "dim": len(vec) if vec else 0,
                }
            )
        conn.execute(
            text(
                "INSERT INTO chunks (document_id, seq, content, embedding, dim) "
                "VALUES (:d, :seq, :content, :blob, :dim)"
            ),
            rows,
        )
    return {"id": doc_id, "title": title, "chunks": len(pieces), "chars": len(content)}


def list_documents() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, title, source, char_count, chunk_count, created_at FROM documents ORDER BY id DESC")
        ).mappings().all()
    return [dict(r) for r in rows]


def get_document(doc_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, title, source, char_count, chunk_count, created_at FROM documents WHERE id = :d"),
            {"d": doc_id},
        ).mappings().first()
    return dict(row) if row else None


def list_chunks(doc_id: int) -> list[dict]:
    """按 seq 顺序取出某篇文档的全部分块，供摘要 / 出题使用。"""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, document_id, seq, content FROM chunks WHERE document_id = :d ORDER BY seq"),
            {"d": doc_id},
        ).mappings().all()
    return [dict(r) for r in rows]


def update_chunk_vectors(doc_id: int, vectors: list[list[float]]) -> int:
    """按 seq 顺序覆盖某篇文档所有分块的向量，返回更新条数。

    用途：换 embedding 模型、或模型侧改了前缀策略后，用新向量重建旧数据。
    """
    if not vectors:
        return 0
    updated = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id FROM chunks WHERE document_id = :d ORDER BY seq"),
            {"d": doc_id},
        ).scalars().all()
        if len(rows) != len(vectors):
            raise ValueError(f"向量数({len(vectors)})与分块数({len(rows)})不一致")
        for chunk_id, vector in zip(rows, vectors):
            conn.execute(
                text("UPDATE chunks SET embedding = :v, dim = :n WHERE id = :i"),
                {"v": _to_blob(vector), "n": len(vector), "i": chunk_id},
            )
            updated += 1
    return updated


def delete_document(doc_id: int) -> bool:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM chunks WHERE document_id = :d"), {"d": doc_id})
        result = conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})
    return result.rowcount > 0


# ==================== 检索 ====================

def search(query_vector: list[float], top_k: int | None = None) -> list[dict[str, Any]]:
    """余弦相似度暴力检索。向量先归一化，点积即余弦，省一次除法。"""
    top_k = top_k or config.TOP_K
    q = np.asarray(query_vector, dtype=np.float32)
    norm = float(np.linalg.norm(q)) or 1.0
    q = q / norm

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.id, c.document_id, c.seq, c.content, c.embedding, d.title, d.source "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.embedding IS NOT NULL"
            )
        ).mappings().all()

    scored = []
    for row in rows:
        vec = _from_blob(row["embedding"])
        if vec.shape != q.shape:
            continue  # 换过 embedding 模型的旧数据直接跳过，避免维度对不上
        score = float(np.dot(vec / (np.linalg.norm(vec) or 1.0), q))
        scored.append(
            {
                "chunk_id": row["id"],
                "document_id": row["document_id"],
                "title": row["title"],
                "seq": row["seq"],
                "score": round(score, 4),
                "content": row["content"],
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def stats() -> dict:
    with engine.connect() as conn:
        docs = conn.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 0
        chunks = conn.execute(text("SELECT COUNT(*) FROM chunks")).scalar() or 0
        embedded = conn.execute(text("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")).scalar() or 0
    return {"documents": docs, "chunks": chunks, "embedded": embedded, "db": str(config.DB_PATH)}


def dumps(obj: Any) -> str:  # 小工具：给脚本调试用
    return json.dumps(obj, ensure_ascii=False, indent=2)
