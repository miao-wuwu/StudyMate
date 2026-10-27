# -*- coding: utf-8 -*-
"""Agent 运行轨迹（trace）：每一步做了什么、花了多久、吃了多少 token。

设计成纯 dict 列表，方便直接 JSON 返回给前端画时间线，也方便测试里断言。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


def estimate_cost(prompt_tokens: int, completion_tokens: int, usage_cost: float = 0.0) -> float:
    """上游若给了 cost 就用它；否则按可选配置的单价估算（本地 Ollama 为 0）。"""
    if usage_cost:
        return float(usage_cost)
    from .. import config

    price_in = float(getattr(config, "PRICE_IN_PER_M", 0.0) or 0.0)
    price_out = float(getattr(config, "PRICE_OUT_PER_M", 0.0) or 0.0)
    return round(prompt_tokens / 1_000_000 * price_in
                 + completion_tokens / 1_000_000 * price_out, 6)


@dataclass
class Step:
    index: int
    thought: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)
    observation: str = ""
    error: str = ""
    elapsed_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "thought": self.thought,
            "tool": self.tool,
            "args": self.args,
            "observation": self.observation,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
        }


class Trace:
    """收集 Step，顺便累计总用量。"""

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.started = time.time()

    def new_step(self) -> Step:
        step = Step(index=len(self.steps) + 1)
        self.steps.append(step)
        return step

    def record_usage(self, step: Step, usage: dict) -> None:
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        step.prompt_tokens += pt
        step.completion_tokens += ct
        step.cost_usd = round(step.cost_usd
                              + estimate_cost(pt, ct, float(usage.get("cost_usd") or 0.0)), 6)

    def totals(self) -> dict:
        return {
            "steps": len(self.steps),
            "prompt_tokens": sum(s.prompt_tokens for s in self.steps),
            "completion_tokens": sum(s.completion_tokens for s in self.steps),
            "total_tokens": sum(s.prompt_tokens + s.completion_tokens for s in self.steps),
            "cost_usd": round(sum(s.cost_usd for s in self.steps), 6),
            "elapsed_ms": int((time.time() - self.started) * 1000),
        }

    def to_list(self) -> list[dict]:
        return [s.to_dict() for s in self.steps]