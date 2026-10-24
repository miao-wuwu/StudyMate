# -*- coding: utf-8 -*-
"""检索增强问答（RAG）：把上传的资料切成块、算向量、存库，问答时先检索再让模型带着原文回答。

流程：
    ingest()  文本/PDF → chunk → embed → 存 documents/chunks
    ask()     问题 → embed → 余弦检索 top-k → 拼上下文 → chat() → 带引用的回答
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from . import config, llm, store

SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf"}

SYSTEM_PROMPT = (
    "你是 StudyMate 的学习助手。请仅依据下面提供的「资料片段」回答问题；"
    "如果片段里没有足够信息，就直说资料中没有相关内容，不要编造。"
    "回答用中文，条理清晰，关键结论后面用 [1][2] 这样的编号标注来源片段。"
)


def extract_text(data: bytes, filename: str) -> str:
    """从上传的字节流里抽纯文本。PDF 走 PyMuPDF，文本类直接解码。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"暂不支持 {suffix or '无扩展名'}，支持：{', '.join(sorted(SUPPORTED_SUFFIXES))}")

    if suffix == ".pdf":
        try:
            import pymupdf  # PyMuPDF 2.x 的新名字
        except ImportError:  # 兼容旧版本
            import fitz as pymupdf  # type: ignore
        doc = pymupdf.open(stream=data, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        text = "\n\n".join(pages)
    else:
        text = data.decode("utf-8", errors="ignore")

    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ingest(title: str, text: str, source: str = "") -> dict:
    """切片 → 批量算向量 → 落库。"""
    pieces = store.chunk_text(text)
    if not pieces:
        raise ValueError("没有可入库的文本（内容为空？）")
    vectors = llm.embed(pieces)
    return store.add_document(title=title, content=text, source=source, vectors=vectors)


def ask(question: str, top_k: int | None = None) -> dict:
    """检索 + 生成。返回回答和引用的片段，前端可以折叠展示原文。"""
    question = (question or "").strip()
    if not question:
        raise ValueError("问题不能为空")

    if store.stats()["embedded"] == 0:
        # 没有资料时退化成普通对话，不让用户觉得「AI 坏了」
        reply = llm.chat(
            [
                {"role": "system", "content": "你是 StudyMate 的学习助手，回答简洁实用，用中文。"},
                {"role": "user", "content": question},
            ]
        )
        return {"answer": reply, "sources": [], "mode": "chat"}

    top_k = top_k or config.TOP_K
    query_vector = llm.embed([question])[0]
    hits = store.search(query_vector, top_k=top_k)

    context_lines = []
    sources = []
    for idx, hit in enumerate(hits, start=1):
        context_lines.append(f"[{idx}] 《{hit['title']}》第 {hit['seq'] + 1} 段：{hit['content']}")
        sources.append(
            {
                "index": idx,
                "document_id": hit["document_id"],
                "title": hit["title"],
                "seq": hit["seq"],
                "score": hit["score"],
                "content": hit["content"],
            }
        )

    user_prompt = "资料片段：\n" + "\n".join(context_lines) + f"\n\n问题：{question}\n\n请依据上面的片段作答，并标注来源编号。"

    reply = llm.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    return {"answer": reply, "sources": sources, "mode": "rag"}


def ingest_bytes(filename: str, data: bytes, title: str | None = None) -> dict:
    """给上传接口用：从一个文件字节流走完整流程。"""
    text = extract_text(data, filename)
    if not text:
        raise ValueError("这个文件里没有抽取到文字（可能是扫描版 PDF，需要先 OCR）")
    return ingest(title=title or Path(filename).stem, text=text, source=filename)


def ingest_path(path: str | Path, title: str | None = None) -> dict:
    p = Path(path)
    return ingest_bytes(p.name, p.read_bytes(), title=title)
