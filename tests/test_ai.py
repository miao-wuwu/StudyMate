# -*- coding: utf-8 -*-
"""AI 接口的单元测试：不依赖真实的 Ollama，用 monkeypatch 顶掉模型调用。

这样 CI 里没有 GPU、没装模型也能跑，模型联调放到本地手测。
"""
import pytest
from fastapi.testclient import TestClient

from ai import llm
from main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health_reports_unavailable_without_raising(client, monkeypatch):
    def boom(*args, **kwargs):
        raise llm.LLMError("connection refused")

    monkeypatch.setattr(llm, "_get_json", boom)
    resp = client.get("/ai/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "不可用" in body["detail"] or "ollama" in body["detail"].lower()


def test_chat_returns_reply(client, monkeypatch):
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "复习建议：先过一遍错题。"

    monkeypatch.setattr(llm, "chat", fake_chat)
    resp = client.post(
        "/ai/chat",
        json={"messages": [{"role": "user", "content": "帮我规划今天的复习"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"].startswith("复习建议")
    assert captured["messages"][0]["content"] == "帮我规划今天的复习"


def test_chat_upstream_error_becomes_502(client, monkeypatch):
    def boom(messages, **kwargs):
        raise llm.LLMError("连不上 http://127.0.0.1:11434")

    monkeypatch.setattr(llm, "chat", boom)
    resp = client.post("/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 502
    assert "127.0.0.1:11434" in resp.json()["detail"]


def test_chat_rejects_empty_messages(client):
    resp = client.post("/ai/chat", json={"messages": []})
    assert resp.status_code == 422


def test_existing_endpoints_still_work(client):
    """加 AI 路由不能影响原有接口。"""
    assert client.get("/").status_code == 200
    assert client.get("/notes").status_code == 200
    assert client.get("/tasks").status_code == 200
