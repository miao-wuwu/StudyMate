# -*- coding: utf-8 -*-
"""Agent 冒烟测试：真的跑一次本地模型，看看规划/工具/降级链路是否通。

用法：
    .\\.venv\\Scripts\\python.exe scripts/agent_smoke.py "我的笔记里有哪些内容？"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import agent  # noqa: E402


def main() -> None:
    question = " ".join(sys.argv[1:]) or "我的资料库里有什么？请概括一下"
    result = agent.run(question, max_steps=4)
    print("=" * 60)
    print("问题:", question)
    print("降级:", result["fallback"], result.get("fallback_reason") or "")
    print("工具:", result.get("tools_used"))
    print("用量:", json.dumps(result.get("totals"), ensure_ascii=False))
    print("-" * 60)
    for step in result.get("steps", []):
        print(f"[{step['index']}] {step['elapsed_ms']}ms tool={step['tool'] or '-'} "
              f"err={step['error'][:60] or '-'}")
        if step["thought"]:
            print("    thought:", step["thought"][:100])
        if step["observation"]:
            print("    obs:", step["observation"][:160].replace("\n", " "))
    print("-" * 60)
    print("答案:\n" + (result.get("answer") or "")[:800])


if __name__ == "__main__":
    main()