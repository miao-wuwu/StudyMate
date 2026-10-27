# -*- coding: utf-8 -*-
"""Agent 主循环：规划 → 调工具 → 看结果 → 再规划，直到给出最终答案。

刻意不引入 LangChain 之类的框架：循环本身只有几十行，可读、可测、可讲；
重试、降级、步数上限这些"工程细节"反而是面试里更值钱的部分。
"""
from __future__ import annotations

import json
import re
import time

from .. import llm, rag
from . import prompts, tools
from .trace import Trace

MAX_STEPS_DEFAULT = 5
MAX_OBSERVATION_FEED = 1200   # 喂回模型的观察文本上限
MAX_INVALID_RETRIES = 2       # 连续 JSON 解析失败几次后放弃


class AgentError(RuntimeError):
    """Agent 无法完成时的统一异常（路由层翻成 502）。"""


def _extract_json(text: str) -> dict | None:
    """从模型输出里抠出第一个平衡的 JSON 对象。

    模型经常加 ```json 围栏、前后废话，或者写成 {"thought": ..., "tool": ...}{...}。
    """
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(cleaned[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
        start = cleaned.find("{", start + 1)
    return None


def parse_action(text: str) -> tuple[str, dict]:
    """返回 ('tool'|'final'|'invalid', payload)。"""
    obj = _extract_json(text)
    if not obj:
        return "invalid", {"raw": (text or "")[:200]}
    if isinstance(obj.get("final"), str) and obj["final"].strip():
        return "final", {"thought": str(obj.get("thought") or "").strip(),
                         "answer": obj["final"].strip()}
    name = obj.get("tool") or obj.get("action") or obj.get("name")
    if isinstance(name, str) and name.strip():
        args = obj.get("args") or obj.get("arguments") or obj.get("parameters") or {}
        if not isinstance(args, dict):
            args = {}
        return "tool", {"thought": str(obj.get("thought") or "").strip(),
                        "tool": name.strip(), "args": args}
    return "invalid", {"raw": json.dumps(obj, ensure_ascii=False)[:200]}


def _fallback(question: str, reason: str, trace: Trace | None = None) -> dict:
    """Agent 走不通时退化成普通 RAG 问答：永远给用户一个能看的答案。

    已经跑过的步骤照样带回去，前端能看出「它在哪一步卡住了」。
    """
    try:
        result = rag.ask(question)
        answer = result.get("answer") or ""
        sources = result.get("sources") or []
        mode = result.get("mode", "rag")
    except Exception as exc:  # noqa: BLE001
        raise AgentError(f"Agent 与 RAG 都失败了：{exc}") from exc
    return {
        "answer": answer,
        "fallback": True,
        "fallback_reason": reason,
        "mode": mode,
        "sources": sources,
        "steps": trace.to_list() if trace else [],
        "totals": trace.totals() if trace else {
            "steps": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "cost_usd": 0.0, "elapsed_ms": 0,
        },
        "tools_used": [],
    }


def run(question: str, *, max_steps: int = MAX_STEPS_DEFAULT,
        temperature: float = 0.2, on_event=None) -> dict:
    """跑一次 Agent，返回 {answer, fallback, steps, totals, tools_used, ...}。

    on_event(dict) 可选：每完成一步回调一次，SSE 接口用它做流式进度。
    """

    def emit(event: dict) -> None:
        if on_event is None:
            return
        try:
            on_event(event)
        except Exception:  # noqa: BLE001 - 前端断连不该影响 Agent 本身
            pass
    question = (question or "").strip()
    if not question:
        raise AgentError("question 不能为空")
    max_steps = max(1, min(int(max_steps or MAX_STEPS_DEFAULT), 8))

    trace = Trace()
    messages: list[dict] = [
        {"role": "system", "content": prompts.system_prompt(max_steps)},
        {"role": "user", "content": question},
    ]
    invalid = 0
    tools_used: list[str] = []
    repeat_guard: set[tuple[str, str]] = set()

    try:
        for i in range(max_steps):
            if i == max_steps - 1:
                # 最后一步：明确要求收敛，避免弱模型在原地打转
                messages.append({"role": "user",
                                 "content": "这是最后一步了，请直接输出 final，不要再调用工具。"})
            step = trace.new_step()
            t0 = time.time()
            text, usage = llm.chat_detailed(messages, temperature=temperature)
            step.elapsed_ms = int((time.time() - t0) * 1000)
            trace.record_usage(step, usage)

            kind, payload = parse_action(text)
            if kind == "final":
                step.thought = payload["thought"]
                emit({"type": "final", "answer": payload["answer"]})
                return {
                    "answer": payload["answer"],
                    "fallback": False,
                    "mode": "agent",
                    "steps": trace.to_list(),
                    "totals": trace.totals(),
                    "tools_used": _dedupe(tools_used),
                }

            if kind == "invalid":
                invalid += 1
                step.thought = "（模型输出不是合法 JSON）"
                step.error = payload.get("raw", "")
                if invalid >= MAX_INVALID_RETRIES:
                    emit({"type": "fallback", "reason": f"模型连续 {invalid} 次没有输出合法 JSON"})
                    return _fallback(question, f"模型连续 {invalid} 次没有输出合法 JSON", trace)
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": prompts.CORRECTION})
                continue

            invalid = 0
            name, args = payload["tool"], payload["args"]
            step.thought = payload["thought"]
            step.tool = name
            step.args = args

            key = (name, json.dumps(args, ensure_ascii=False, sort_keys=True))
            if key in repeat_guard:
                step.error = "重复调用同一工具同一参数"
                observation = "你已经用相同参数调过这个工具了，换一个工具或直接给 final。"
            else:
                repeat_guard.add(key)
                observation, error = tools.execute(name, args)
                step.error = error
                if error:
                    observation = f"调用失败：{error}"
                else:
                    tools_used.append(name)
            step.observation = observation[:MAX_OBSERVATION_FEED]
            emit({"type": "step", "step": step.to_dict()})

            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": f"工具结果（{name}）：\n{observation}"})

        emit({"type": "fallback", "reason": f"达到步数上限 {max_steps} 仍未收敛"})
        return _fallback(question, f"达到步数上限 {max_steps} 仍未收敛", trace)
    except llm.LLMError as exc:
        emit({"type": "fallback", "reason": f"模型调用失败：{exc}"})
        return _fallback(question, f"模型调用失败：{exc}", trace)


def _dedupe(names: list[str]) -> list[str]:
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen
