"""对话历史裁剪的单元测试（不需要 Ollama）。"""

from __future__ import annotations

from ai import llm


def make_messages(pairs: list[tuple[str, str]]) -> list[dict]:
    return [{"role": role, "content": content} for role, content in pairs]


def test_short_history_untouched():
    msgs = make_messages([("user", "你好"), ("assistant", "你好，有什么可以帮你"), ("user", "什么是栈")])
    out, trimmed = llm.trim_messages(msgs, max_chars=1000, max_messages=10)
    assert trimmed is False
    assert [m["content"] for m in out] == [m["content"] for m in msgs]
    assert not any("省略" in (m["content"] or "") for m in out)


def test_keeps_system_and_drops_oldest():
    msgs = make_messages(
        [("system", "你是学习助手")]
        + [("user", "第%d轮问题" % i + "内容" * 50) for i in range(1, 11)]
    )
    out, trimmed = llm.trim_messages(msgs, max_chars=600, max_messages=20)
    assert trimmed is True
    assert out[0]["role"] == "system"
    assert out[0]["content"].startswith("你是学习助手")
    assert "省略" in out[0]["content"]
    # 最后一条一定还在
    assert out[-1]["content"].startswith("第10轮问题")
    # 正文总长度控制在预算之内（system 与提示语单独算）
    body = sum(len(m["content"] or "") for m in out[1:])
    assert body <= 600


def test_respects_message_count_limit():
    msgs = make_messages([("user", "问题") for _ in range(30)])
    out, trimmed = llm.trim_messages(msgs, max_chars=100000, max_messages=5)
    assert trimmed is True
    assert len([m for m in out if m["role"] != "system"]) == 5


def test_single_huge_message_is_clipped():
    msgs = make_messages([("user", "长" * 5000)])
    out, trimmed = llm.trim_messages(msgs, max_chars=500, max_messages=20)
    assert trimmed is True
    kept = [m for m in out if m["role"] != "system"]
    assert len(kept) == 1
    assert kept[0]["content"].endswith("…")
    assert len(kept[0]["content"]) <= 510


def test_empty_history_returns_empty():
    assert llm.trim_messages([], max_chars=100, max_messages=5) == ([], False)


def test_chat_applies_trimming(monkeypatch):
    """chat() 内部要真的把历史裁剪后再发给 provider。"""
    captured = {}

    def fake_ollama_chat(messages, temperature, num_ctx):
        captured["messages"] = messages
        return "好的"

    monkeypatch.setattr(llm.config, "HISTORY_MAX_CHARS", 10000)
    monkeypatch.setattr(llm.config, "HISTORY_MAX_MESSAGES", 3)
    monkeypatch.setattr(llm, "_ollama_chat", fake_ollama_chat)
    monkeypatch.setattr(llm.config, "LLM_PROVIDER", "ollama")

    history = make_messages([("user", "内容" * 100) for _ in range(6)])
    reply = llm.chat(history)

    assert reply == "好的"
    kept = [m for m in captured["messages"] if m["role"] != "system"]
    assert len(kept) == 3
    assert kept[-1]["content"].startswith("内容")
