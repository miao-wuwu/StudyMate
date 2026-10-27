# -*- coding: utf-8 -*-
"""LLM 调用层：把「本地 Ollama」和「云端 DeepSeek」藏在同一组函数后面。

对外只有三个函数：
    chat(messages, ...)  -> str            一次对话补全
    embed(texts)         -> list[vector]   文本向量（只支持 Ollama，DeepSeek 没有公开 embedding）
    health()             -> dict           探测当前 provider 是否可用

用标准库 urllib 而不是 requests：项目现有依赖里没有 requests，
少装一个包，部署时也少一处坑。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterable

from . import config


class LLMError(RuntimeError):
    """把底层各种异常统一成一种，方便路由层翻译成 HTTP 502。"""


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: float | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # 4xx / 5xx
        detail = exc.read().decode("utf-8", "ignore")[:500]
        raise LLMError(f"上游返回 {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:  # 连不上：Ollama 没启动最常见
        raise LLMError(
            f"连不上 {url}（{exc.reason}）。如果用的是本地模型，确认 `ollama serve` 在跑。"
        ) from exc
    except TimeoutError as exc:
        raise LLMError(f"请求 {url} 超时（>{config.REQUEST_TIMEOUT}s）") from exc


def _get_json(url: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 健康检查不该把异常抛出去
        raise LLMError(str(exc)) from exc


# ==================== Ollama ====================

def _ollama_chat_raw(messages: list[dict], temperature: float, num_ctx: int) -> dict:
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": config.KEEP_ALIVE,   # 空闲多久卸载模型，避免常驻显存
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    return _post_json(f"{config.OLLAMA_HOST}/api/chat", payload)


def _ollama_chat(messages: list[dict], temperature: float, num_ctx: int) -> str:
    data = _ollama_chat_raw(messages, temperature, num_ctx)
    try:
        return data["message"]["content"].strip()
    except (KeyError, TypeError) as exc:
        raise LLMError(f"Ollama 返回结构不符合预期: {str(data)[:300]}") from exc


def _ollama_embed(texts: list[str], kind: str = "document") -> list[list[float]]:
    # nomic-embed-text 是按「任务前缀」训练的：文档用 search_document，检索用 search_query，
    # 不加前缀时相似度排序会明显变差（实测 top-1 命中率差 10 个点以上）。
    model = (config.OLLAMA_EMBED_MODEL or "").split(":")[0]
    prefix = ""
    if model == "nomic-embed-text":
        prefix = "search_document: " if kind == "document" else "search_query: "
    vectors = []
    for text in texts:  # /api/embeddings 一次只吃一条
        data = _post_json(
            f"{config.OLLAMA_HOST}/api/embeddings",
            {
                "model": config.OLLAMA_EMBED_MODEL,
                "prompt": prefix + text,
                "keep_alive": config.KEEP_ALIVE,
            },
        )
        vector = data.get("embedding")
        if not vector:
            raise LLMError(f"Ollama 没有返回 embedding: {str(data)[:300]}")
        vectors.append(vector)
    return vectors


# ==================== DeepSeek（OpenAI 兼容） ====================

def _deepseek_chat_raw(messages: list[dict], temperature: float) -> dict:
    if not config.DEEPSEEK_API_KEY:
        raise LLMError("LLM_PROVIDER=deepseek 但没有配置 DEEPSEEK_API_KEY")
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    return _post_json(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
    )


def _deepseek_chat(messages: list[dict], temperature: float, num_ctx: int) -> str:  # num_ctx 仅保留接口一致
    data = _deepseek_chat_raw(messages, temperature)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"DeepSeek 返回结构不符合预期: {str(data)[:300]}") from exc


# ==================== 上下文裁剪 ====================

_TRIM_NOTICE = "（为节省上下文，更早的对话已省略）"


def trim_messages(
    messages: Iterable[dict],
    *,
    max_chars: int | None = None,
    max_messages: int | None = None,
) -> tuple[list[dict], bool]:
    """把多轮对话裁到预算内，返回 (裁剪后的消息, 是否发生了裁剪)。

    规则：
    1. system 消息永远保留（放在最前面，多条会合并成一条）；
    2. 其余消息从最新往前累加，超出字符预算或条数上限就丢弃更早的；
    3. 至少保留最后一条；若它自己就超预算，则截断正文并加省略号；
    4. 真正发生裁剪时，在 system 之后插一条简短提示，让模型知道有历史被省略。
    """
    budget = config.HISTORY_MAX_CHARS if max_chars is None else max_chars
    limit = config.HISTORY_MAX_MESSAGES if max_messages is None else max_messages
    msgs = [m for m in messages if isinstance(m, dict) and m.get("role")]

    systems = [m for m in msgs if m.get("role") == "system"]
    rest = [m for m in msgs if m.get("role") != "system"]
    if not rest:
        return systems, False

    system_chars = sum(len(m.get("content") or "") for m in systems)
    budget = max(budget - system_chars, 200)

    kept: list[dict] = []
    used = 0
    trimmed = False
    for message in reversed(rest):
        content = message.get("content") or ""
        cost = len(content)
        if kept and (used + cost > budget or len(kept) >= limit):
            trimmed = True
            break
        if not kept and cost > budget:
            # 单条消息就超预算：截断它自己
            trimmed = True
            content = content[:budget] + "…"
            cost = len(content)
        kept.append({"role": message["role"], "content": content})
        used += cost

    kept.reverse()
    if len(kept) < len(rest):
        trimmed = True

    # system 与提示语合并成一条，避免出现多个 system 消息
    system_text = "\n".join(m.get("content") or "" for m in systems).strip()
    if trimmed:
        system_text = f"{system_text}\n{_TRIM_NOTICE}".strip()
    result: list[dict] = []
    if system_text:
        result.append({"role": "system", "content": system_text})
    result.extend(kept)
    return result, trimmed


# ==================== 统一入口 ====================

def chat(
    messages: Iterable[dict],
    *,
    temperature: float | None = None,
    num_ctx: int | None = None,
) -> str:
    """messages 形如 [{"role": "user", "content": "..."}]。"""
    msgs = list(messages)
    if not msgs:
        raise LLMError("messages 不能为空")
    msgs, _ = trim_messages(msgs)
    temp = config.TEMPERATURE if temperature is None else temperature
    ctx = config.NUM_CTX if num_ctx is None else num_ctx

    if config.LLM_PROVIDER == "ollama":
        return _ollama_chat(msgs, temp, ctx)
    if config.LLM_PROVIDER == "deepseek":
        return _deepseek_chat(msgs, temp, ctx)
    raise LLMError(f"未知的 LLM_PROVIDER: {config.LLM_PROVIDER}")


def chat_detailed(
    messages: Iterable[dict],
    *,
    temperature: float | None = None,
    num_ctx: int | None = None,
) -> tuple[str, dict]:
    """和 chat() 一样，但额外返回用量：{prompt_tokens, completion_tokens, total_tokens, model}。

    Agent 的 trace 要用它统计每步成本；Ollama 本地模型成本记为 0，但 token 数照记。
    """
    msgs = list(messages)
    if not msgs:
        raise LLMError("messages 不能为空")
    msgs, _ = trim_messages(msgs)
    temp = config.TEMPERATURE if temperature is None else temperature
    ctx = config.NUM_CTX if num_ctx is None else num_ctx

    if config.LLM_PROVIDER == "ollama":
        data = _ollama_chat_raw(msgs, temp, ctx)
        try:
            text = data["message"]["content"].strip()
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Ollama 返回结构不符合预期: {str(data)[:300]}") from exc
        pt = int(data.get("prompt_eval_count") or 0)
        ct = int(data.get("eval_count") or 0)
        usage = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
            "model": config.OLLAMA_MODEL,
            "cost_usd": 0.0,
        }
        return text, usage

    if config.LLM_PROVIDER == "deepseek":
        data = _deepseek_chat_raw(msgs, temp)
        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"DeepSeek 返回结构不符合预期: {str(data)[:300]}") from exc
        raw_usage = data.get("usage") or {}
        pt = int(raw_usage.get("prompt_tokens") or 0)
        ct = int(raw_usage.get("completion_tokens") or 0)
        usage = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": int(raw_usage.get("total_tokens") or pt + ct),
            "model": config.DEEPSEEK_MODEL,
            "cost_usd": 0.0,
        }
        return text, usage

    raise LLMError(f"未知的 LLM_PROVIDER: {config.LLM_PROVIDER}")


def embed(texts: Iterable[str], kind: str = "document") -> list[list[float]]:
    """kind="document" 用于入库文本块，"query" 用于检索问题（部分模型需要不同前缀）。"""
    items = [t for t in texts if t and t.strip()]
    if not items:
        return []
    if config.LLM_PROVIDER != "ollama":
        raise LLMError("embedding 目前只走本地 Ollama（DeepSeek 未开放 embedding 接口）")
    return _ollama_embed(items, kind=kind)


def health() -> dict:
    """返回当前 provider 的状态；连不上不抛异常，交给调用方展示。"""
    info = {
        "provider": config.LLM_PROVIDER,
        "model": config.OLLAMA_MODEL if config.LLM_PROVIDER == "ollama" else config.DEEPSEEK_MODEL,
        "embed_model": config.OLLAMA_EMBED_MODEL if config.LLM_PROVIDER == "ollama" else None,
        "ok": False,
        "detail": "",
    }
    if config.LLM_PROVIDER == "ollama":
        try:
            tags = _get_json(f"{config.OLLAMA_HOST}/api/tags")
            names = [m.get("name", "") for m in tags.get("models", [])]
            info["ok"] = True
            info["models"] = names
            info["model_loaded"] = any(n.startswith(config.OLLAMA_MODEL.split(":")[0]) for n in names)
            info["detail"] = "ollama 可访问"
        except LLMError as exc:
            info["detail"] = f"ollama 不可用: {exc}"
    else:
        info["ok"] = bool(config.DEEPSEEK_API_KEY)
        info["detail"] = "已配置 key" if info["ok"] else "缺少 DEEPSEEK_API_KEY"
    return info
