# -*- coding: utf-8 -*-
"""Agent 循环的单元测试：模型、工具、检索全部用 monkeypatch 顶掉，不联网。"""
import json

import pytest
from fastapi.testclient import TestClient

from ai import agent, llm, rag
from ai.agent import loop, tools
from main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _fake_model(script):
    """按顺序吐出预设文本；用完就一直重复最后一条。"""
    calls = {"n": 0}

    def fake(messages, **kwargs):
        idx = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        return script[idx], {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "model": "fake",
            "cost_usd": 0.0,
        }

    return fake


# ---------------- 解析 ----------------

def test_parse_action_handles_fenced_json():
    text = '好的：\n```json\n{"thought": "查一下", "tool": "search_notes", "args": {"query": "梯度"}}\n```'
    kind, payload = agent.parse_action(text)
    assert kind == "tool"
    assert payload["tool"] == "search_notes"
    assert payload["args"]["query"] == "梯度"


def test_parse_action_final_and_invalid():
    kind, payload = agent.parse_action('{"thought": "够了", "final": "答案在这里"}')
    assert kind == "final"
    assert payload["answer"] == "答案在这里"

    kind, _ = agent.parse_action("我直接说吧：这个我不知道")
    assert kind == "invalid"


# ---------------- 循环 ----------------

def test_run_calls_tool_then_answers(monkeypatch):
    script = [
        json.dumps({"thought": "先检索", "tool": "search_notes", "args": {"query": "反向传播"}}),
        json.dumps({"thought": "可以答了", "final": "反向传播是链式法则的应用 [1]"}),
    ]
    monkeypatch.setattr(llm, "chat_detailed", _fake_model(script))
    seen = {}

    def fake_execute(name, args):
        seen["name"] = name
        seen["args"] = args
        return '{"hits": [{"title": "深度学习笔记", "seq": 1}]}', ""

    monkeypatch.setattr(tools, "execute", fake_execute)

    result = agent.run("什么是反向传播")
    assert result["fallback"] is False
    assert result["answer"].startswith("反向传播")
    assert seen["name"] == "search_notes"
    assert result["tools_used"] == ["search_notes"]
    assert len(result["steps"]) == 2
    assert result["totals"]["prompt_tokens"] == 200
    assert result["totals"]["total_tokens"] == 240


def test_run_falls_back_when_model_never_returns_json(monkeypatch):
    monkeypatch.setattr(llm, "chat_detailed", _fake_model(["我觉得应该先看看书"]))
    monkeypatch.setattr(rag, "ask", lambda q, **kw: {"answer": "降级答案", "sources": [], "mode": "chat"})

    result = agent.run("随便问问")
    assert result["fallback"] is True
    assert result["answer"] == "降级答案"
    assert "JSON" in result["fallback_reason"]
    assert len(result["steps"]) == 2          # 两次非法输出都留了痕，方便排查
    assert all(s["error"] for s in result["steps"])


def test_run_stops_at_step_limit(monkeypatch):
    loop_script = [
        json.dumps({"thought": "再查", "tool": "list_notes", "args": {"k": i}})
        for i in range(10)
    ]
    monkeypatch.setattr(llm, "chat_detailed", _fake_model(loop_script))
    monkeypatch.setattr(tools, "execute", lambda name, args: ('{"count": 0}', ""))
    monkeypatch.setattr(rag, "ask", lambda q, **kw: {"answer": "兜底", "sources": [], "mode": "chat"})

    result = agent.run("无限循环测试", max_steps=2)
    assert result["fallback"] is True
    assert "上限" in result["fallback_reason"]
    assert len(result["steps"]) == 2


def test_repeat_call_is_guarded(monkeypatch):
    same = json.dumps({"thought": "查", "tool": "search_notes", "args": {"query": "同一个"}})
    script = [same, same, json.dumps({"thought": "ok", "final": "好了"})]
    monkeypatch.setattr(llm, "chat_detailed", _fake_model(script))
    executed = {"n": 0}

    def counting(name, args):
        executed["n"] += 1
        return "{}", ""

    monkeypatch.setattr(tools, "execute", counting)

    result = agent.run("重复调用")
    assert executed["n"] == 1              # 第二次没有再真正执行
    assert result["steps"][1]["error"]     # 被记录为重复
    assert result["answer"] == "好了"


def test_tool_error_is_reported_to_model(monkeypatch):
    script = [
        json.dumps({"thought": "查", "tool": "quiz", "args": {}}),
        json.dumps({"thought": "知道了", "final": "需要文档 id"}),
    ]
    monkeypatch.setattr(llm, "chat_detailed", _fake_model(script))
    monkeypatch.setattr(tools, "execute", lambda name, args: ("", "缺少 document_id"))

    result = agent.run("出题")
    assert result["steps"][0]["error"] == "缺少 document_id"
    assert result["steps"][0]["observation"].startswith("调用失败")


# ---------------- 接口 ----------------

def test_agent_tools_endpoint(client):
    body = client.get("/ai/agent/tools").json()
    names = [t["name"] for t in body["tools"]]
    assert set(names) == {"list_notes", "search_notes", "summarize", "quiz"}


def test_agent_run_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        agent, "run",
        lambda q, **kw: {"answer": "好", "fallback": False, "mode": "agent",
                         "steps": [], "totals": {}, "tools_used": []},
    )
    resp = client.post("/ai/agent/run", json={"question": "你好"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "好"
    assert resp.json()["model"]


def test_agent_run_endpoint_maps_error_to_502(client, monkeypatch):
    def boom(q, **kw):
        raise agent.AgentError("模型挂了")

    monkeypatch.setattr(agent, "run", boom)
    resp = client.post("/ai/agent/run", json={"question": "你好"})
    assert resp.status_code == 502