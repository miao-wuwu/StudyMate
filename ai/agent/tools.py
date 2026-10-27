# -*- coding: utf-8 -*-
"""Agent 的工具注册表。

每个工具都做两件事：
1. 用 SPECS 里的 JSON Schema 告诉模型它存在、参数长什么样；
2. execute() 里把参数喂给已有的 rag / study / store 函数，结果压成一段短观察文本，
   避免工具返回把上下文撑爆（Agent 循环最容易被大段检索结果拖垮）。
"""
from __future__ import annotations

import json
from typing import Callable

from .. import llm, rag, store, study

MAX_OBSERVATION = 1500  # 单条观察文本上限，超出就截断并注明


def _clip(text: str, limit: int = MAX_OBSERVATION) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + f"…（已截断，原长 {len(text)} 字）"


# ---------------- 工具实现 ----------------

def search_notes(query: str, top_k: int = 4) -> dict:
    """语义检索本地笔记，返回最相关的片段。"""
    query = (query or "").strip()
    if not query:
        return {"error": "query 不能为空"}
    top_k = max(1, min(int(top_k or 4), 8))
    vectors = llm.embed([query], kind="query")
    if not vectors:
        return {"error": "embedding 失败"}
    hits = store.search(vectors[0], top_k=top_k)
    if not hits:
        return {"query": query, "hits": [], "note": "笔记库里还没有可检索的向量"}
    return {
        "query": query,
        "hits": [
            {
                "document_id": h["document_id"],
                "title": h["title"],
                "seq": h["seq"],
                "score": round(float(h["score"]), 4),
                "content": (h["content"] or "")[:400],
            }
            for h in hits
        ],
    }


def summarize(document_id: int | None = None, text: str = "", max_points: int = 5) -> dict:
    """对某篇笔记（或直接给的文本）做结构化摘要。"""
    if not document_id and not (text or "").strip():
        return {"error": "需要 document_id 或 text 之一"}
    if document_id and not store.get_document(int(document_id)):
        ids = [d["id"] for d in store.list_documents()][:20]
        return {"error": f"文档 {document_id} 不存在", "available_document_ids": ids}
    return study.summarize(document_id=document_id, text=text, max_points=max(2, min(int(max_points or 5), 10)))


def quiz(document_id: int | None = None, count: int = 3) -> dict:
    """基于笔记生成选择题，用于自测。"""
    if not document_id:
        return {"error": "quiz 需要 document_id"}
    if not store.get_document(int(document_id)):
        ids = [d["id"] for d in store.list_documents()][:20]
        return {"error": f"文档 {document_id} 不存在", "available_document_ids": ids}
    return study.quiz(document_id=document_id, count=max(1, min(int(count or 3), 5)))


def list_notes() -> dict:
    """列出资料库里的文档（id / 标题 / 片段数）。"""
    docs = store.list_documents()
    return {
        "count": len(docs),
        "documents": [
            {"id": d["id"], "title": d["title"], "chunks": d.get("chunks") or d.get("chunk_count") or 0}
            for d in docs
        ],
    }


EXECUTORS: dict[str, Callable[..., dict]] = {
    "search_notes": search_notes,
    "summarize": summarize,
    "quiz": quiz,
    "list_notes": list_notes,
}

SPECS: list[dict] = [
    {
        "name": "list_notes",
        "description": "列出资料库里的所有文档（标题、id、片段数）。不确定有哪些资料时先调它。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_notes",
        "description": "语义检索笔记内容，返回最相关的若干片段（带标题、相似度、document_id）。回答事实性问题前用它。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题，尽量具体"},
                "top_k": {"type": "integer", "description": "返回片段数，默认 4，最大 8"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "summarize",
        "description": "对指定文档（document_id，可从 search_notes / list_notes 的返回里拿）或直接给的文本做摘要与要点提炼。",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "文档 id，可省略"},
                "text": {"type": "string", "description": "直接给的原文本，可省略"},
                "max_points": {"type": "integer", "description": "要点条数，默认 5"},
            },
            "required": [],
        },
    },
    {
        "name": "quiz",
        "description": "基于某篇文档生成选择题（题干/选项/答案/解析），用于自测或复习。",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "文档 id"},
                "count": {"type": "integer", "description": "题目数量，默认 3，最大 5"},
            },
            "required": ["document_id"],
        },
    },
]


def specs_text() -> str:
    """给系统提示词用的紧凑工具说明。"""
    lines = []
    for spec in SPECS:
        params = spec["parameters"]
        props = params.get("properties") or {}
        req = set(params.get("required") or [])
        arg_desc = []
        for name, meta in props.items():
            mark = "" if name in req else "?"
            arg_desc.append(f"{name}{mark}: {meta.get('description', '')}")
        lines.append(f"- {spec['name']}({'; '.join(arg_desc)}) — {spec['description']}")
    return "\n".join(lines)


def execute(name: str, args: dict | None) -> tuple[str, str]:
    """执行工具，返回 (observation_text, error)。error 非空表示这次调用失败。"""
    fn = EXECUTORS.get(name)
    if fn is None:
        return "", f"工具不存在：{name}；可用工具：{', '.join(EXECUTORS)}"
    call_args = args or {}
    if not isinstance(call_args, dict):
        return "", "args 必须是对象（JSON object）"
    try:
        result = fn(**call_args)
    except TypeError as exc:
        return "", f"参数不对：{exc}"
    except llm.LLMError as exc:
        return "", f"LLM 调用失败：{exc}"
    except Exception as exc:  # noqa: BLE001 - 工具异常不该炸掉整个循环
        return "", f"工具执行异常：{type(exc).__name__}: {exc}"
    return _clip(json.dumps(result, ensure_ascii=False)), ""