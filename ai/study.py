# -*- coding: utf-8 -*-
"""阶段三：把资料变成能复习的东西——摘要与练习题。

设计取舍：
* 不引入结构化输出（JSON schema / function calling）——qwen2.5:3b 走 Ollama 原生
  /api/chat 时对 JSON 模式支持有限，改用「提示词约束 + 宽松解析」更稳：
  让模型输出 ```json 代码块，解析时剥掉围栏、容忍前后缀文字，实在解析失败就
  把原文放进 raw 返回，前端仍然能显示内容。
* 一次只处理有限长度（默认 6000 字）：3B 模型上下文只有 4k token，宁可截断
  （并告知被截断），也不要塞进去导致质量崩塌或超时。
"""
from __future__ import annotations

import json
import re

from . import llm, store

MAX_CHARS = 6000


def _collect(
    document_id: int | None = None,
    text: str | None = None,
    max_chars: int = MAX_CHARS,
) -> tuple[str, list[dict], bool]:
    """取出待处理正文。

    优先级：显式 text > 指定 document_id > 全部资料。
    返回 (正文, 来源列表, 是否截断)。
    """
    sources: list[dict] = []

    if text and text.strip():
        body = text.strip()
        truncated = len(body) > max_chars
        return body[:max_chars], sources, truncated

    if document_id is not None:
        doc = store.get_document(document_id)
        if not doc:
            raise ValueError("文档不存在")
        chunks = store.list_chunks(document_id)
        body = "\n".join(item["content"] for item in chunks)
        sources.append({"document_id": doc["id"], "title": doc["title"], "chunks": len(chunks)})
    else:
        docs = store.list_documents()
        if not docs:
            raise ValueError("资料库是空的，先上传一份资料")
        parts: list[str] = []
        for doc in docs[:5]:  # 只取最近上传的几篇，避免一次塞爆上下文
            chunks = store.list_chunks(doc["id"])
            joined = "\n".join(item["content"] for item in chunks)
            if not joined:
                continue
            parts.append(f"《{doc['title']}》\n{joined}")
            sources.append({"document_id": doc["id"], "title": doc["title"], "chunks": len(chunks)})
        body = "\n\n".join(parts)

    if not body.strip():
        raise ValueError("没有可处理的正文")
    truncated = len(body) > max_chars
    return body[:max_chars], sources, truncated


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _loads_json(raw: str) -> dict | list | None:
    """宽松解析：先剥代码围栏，再从原文里截取第一个 JSON 对象/数组。"""
    text = (raw or "").strip()
    if not text:
        return None

    candidates: list[str] = []
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(text)

    for candidate in candidates:
        for opener, closer in (("{", "}"), ("[", "]")):
            start = candidate.find(opener)
            end = candidate.rfind(closer)
            if start != -1 and end > start:
                snippet = candidate[start : end + 1]
                try:
                    return json.loads(snippet)
                except json.JSONDecodeError:
                    continue
    return None


def _as_points(data: dict | list | None) -> tuple[str, list[str]]:
    """把模型输出规整成 (摘要正文, 要点列表)。"""
    if isinstance(data, dict):
        summary = str(data.get("summary") or data.get("摘要") or "").strip()
        points = data.get("points") or data.get("要点") or []
    elif isinstance(data, list):
        summary, points = "", data
    else:
        return "", []

    cleaned: list[str] = []
    for item in points if isinstance(points, list) else []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            title = str(item.get("title") or item.get("point") or "").strip()
            detail = str(item.get("detail") or item.get("content") or "").strip()
            text = f"{title}：{detail}" if title and detail else (title or detail)
        else:
            text = str(item).strip()
        if text:
            cleaned.append(text)
    return summary, cleaned


def summarize(
    document_id: int | None = None,
    text: str | None = None,
    max_points: int = 6,
) -> dict:
    """生成摘要与要点。"""
    body, sources, truncated = _collect(document_id, text)
    prompt = (
        "你是学习助手。请阅读下面的资料，输出中文总结。\n"
        "要求：\n"
        f"1. summary 用 2-3 句话概括这份资料在讲什么；\n"
        f"2. points 给出 {max_points} 条要点，每条 20-40 字，覆盖关键概念、公式或结论；\n"
        "3. 只依据资料内容，不要编造资料里没有的事实；\n"
        "4. 严格输出 JSON：{\"summary\": \"...\", \"points\": [\"...\", \"...\"]}\n\n"
        f"资料：\n{body}"
    )
    raw = llm.chat(
        [
            {"role": "system", "content": "你是一个严谨的中文学习助手，擅长把资料压缩成要点。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    data = _loads_json(raw)
    summary, points = _as_points(data)
    parsed = bool(summary or points)
    if not summary and not points:
        summary = raw.strip()[:800]
    return {
        "summary": summary,
        "points": points,
        "parsed": parsed,
        "sources": sources,
        "truncated": truncated,
        "max_points": max_points,
        "raw": None if parsed else raw,
    }


def quiz(
    document_id: int | None = None,
    text: str | None = None,
    count: int = 3,
) -> dict:
    """生成复习题（单选为主，可带解析）。"""
    body, sources, truncated = _collect(document_id, text)
    prompt = (
        "你是出题老师。请根据下面的资料出题，用来检验学生对这份资料的理解。\n"
        "要求：\n"
        f"1. 一共 {count} 道题，每题 4 个选项且只有一个正确答案；\n"
        "2. 每道题考察不同的知识点，不要重复同一句话换个说法再问一遍；\n"
        "3. 题干要具体（问性质、区别、复杂度、操作结果），不要问「下列描述正确的是」这种"
        "四个选项只有语序不同的题；\n"
        "4. 先在心里核对：正确答案必须与资料一致，且与 explanation 一致；\n"
        "5. answer 只能是 A/B/C/D 之一，explanation 先写依据再给结论，1-2 句；\n"
        "6. 只依据资料内容，不要出资料里没有的知识点；\n"
        "7. 严格输出 JSON：{\"questions\": [{\"question\": \"...\", \"options\": "
        "[\"...\", \"...\", \"...\", \"...\"], \"answer\": \"A\", \"explanation\": \"...\"}]}\n\n"
        f"资料：\n{body}"
    )
    raw = llm.chat(
        [
            {"role": "system", "content": "你是一个出题严谨的中文老师，只出有确定答案的客观题。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    data = _loads_json(raw)
    items = []
    if isinstance(data, dict):
        items = data.get("questions") or data.get("题目") or []
    elif isinstance(data, list):
        items = data

    questions = []
    seen: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or item.get("题目") or "").strip()
        options = item.get("options") or item.get("选项") or []
        options = [str(opt).strip() for opt in options if str(opt).strip()][:4]
        answer = str(item.get("answer") or item.get("答案") or "").strip().upper()[:1]
        explanation = str(item.get("explanation") or item.get("解析") or "").strip()
        if not (question and options):
            continue
        if answer not in {"A", "B", "C", "D"} or len(options) < 2:
            continue
        # 去重：题干相同或选项几乎一样的，只保留第一题
        key = re.sub(r"\s+", "", question)
        opt_key = "|".join(sorted(re.sub(r"\s+", "", opt) for opt in options))
        if key in seen or opt_key in seen:
            continue
        seen.add(key)
        seen.add(opt_key)
        questions.append(
            {
                "question": question,
                "options": options,
                "answer": answer,
                "explanation": explanation,
            }
        )

    return {
        "questions": questions,
        "parsed": bool(questions),
        "sources": sources,
        "truncated": truncated,
        "count": count,
        "raw": None if questions else raw,
    }
