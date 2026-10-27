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
_CITE_RE = re.compile(r"\[\d+\]")
_SOURCE_RE = re.compile(r"\s*来源：[^\n]*")

SYSTEM_PROMPT = (
    "你是 StudyMate 的学习助手。下面是按用户问题检索到的「资料片段」。\n"
    "按顺序判断：\n"
    "1. 只要片段里有和问题相关的内容，就必须依据片段回答，关键结论后标 [1][2] 编号，"
    "并在末尾写「来源：标题」——不要明明有内容却说没有。\n"
    "2. 只有片段确实和问题无关时，才写一句「你的资料里没有找到相关内容。」\n"
    "3. 需要时另起一段，以「补充（通用知识，未引用资料）：」开头，用你自己的知识补充；"
    "这一段不要出现 [1][2] 编号，也不要写「来源：」。\n"
    "不要编造片段里没有的细节；回答用中文，条理清晰。"
)


def strip_general_citations(text: str) -> str:
    """清掉不该出现的引用：通用知识段落里的 [n]、「来源：」行，以及全文无 [n] 时的来源行。

    模型（尤其是 3B）经常给通用知识也贴上 [1]，看起来像是用户资料里的内容。
    这里做一层确定性兜底，避免「假引用」。
    """
    if not text:
        return text
    has_any_citation = bool(_CITE_RE.search(text))
    kept: list[str] = []
    inside = False
    for line in text.splitlines():
        if "通用知识" in line:
            inside = True
        if inside:
            line = _CITE_RE.sub("", line)
        stripped = line.strip()
        if "来源：" in stripped and (inside or not has_any_citation):
            line = _SOURCE_RE.sub("", line)
        kept.append(line)
    return "\n".join(kept).strip()


def _is_refusal(text: str) -> bool:
    return "没有找到" in (text or "")


def supplement_general(question: str, answer: str) -> str:
    """回答里说「没找到」时，补一段明确标注的通用知识（可用 AI_GENERAL_FALLBACK=0 关掉）。

    严格接地有它的价值，但用户问「洛必达法则是什么」这种资料外的问题时，
    只回一句「没找到」等于什么也没解决——所以补一小段，并且讲清楚它不是资料里的内容。
    """
    if not config.GENERAL_FALLBACK:
        return answer
    if "通用知识" in answer or not _is_refusal(answer):
        return answer
    try:
        extra = llm.chat(
            [
                {"role": "system",
                 "content": "你是学习助手。用中文简明回答，分点，别超过 5 行；"
                            "不要编造具体的数据、论文出处。"},
                {"role": "user", "content": question},
            ]
        )
    except Exception:  # noqa: BLE001 - 补充失败不影响主回答
        return answer
    extra = _CITE_RE.sub("", extra or "").strip()
    if not extra:
        return answer
    return (answer.rstrip() + "\n\n补充（通用知识，未引用资料）：\n" + extra).strip()


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
    vectors = llm.embed(pieces, kind="document")
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
    query_vector = llm.embed([question], kind="query")[0]
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
    answer = strip_general_citations(reply)
    return {"answer": supplement_general(question, answer), "sources": sources, "mode": "rag"}


def ingest_bytes(filename: str, data: bytes, title: str | None = None) -> dict:
    """给上传接口用：从一个文件字节流走完整流程。"""
    text = extract_text(data, filename)
    if not text:
        raise ValueError("这个文件里没有抽取到文字（可能是扫描版 PDF，需要先 OCR）")
    return ingest(title=title or Path(filename).stem, text=text, source=filename)


def ingest_path(path: str | Path, title: str | None = None) -> dict:
    p = Path(path)
    return ingest_bytes(p.name, p.read_bytes(), title=title)
