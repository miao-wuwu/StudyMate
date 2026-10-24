# -*- coding: utf-8 -*-
"""阶段三（摘要 / 出题）的单元测试。

LLM 一律用 monkeypatch 替掉，测试只验证「取正文 → 提示词 → 解析」这条链路，
不依赖本机 Ollama 是否在跑。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from ai import llm, store, study
from main import app


@pytest.fixture()
def temp_store(monkeypatch, tmp_path):
    """把向量库换到临时 SQLite，避免污染日常资料。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'study.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(store, "engine", engine)
    store.init_db()
    return engine


@pytest.fixture()
def client(temp_store):
    return TestClient(app)


def _seed_document() -> int:
    result = store.add_document(
        title="番茄工作法学习笔记",
        content=(
            "番茄工作法的基本单位是 25 分钟专注加 5 分钟休息。"
            "每完成四个番茄钟，休息时间延长到 15 至 30 分钟。"
            "连续打卡天数从今天往前数，今天没打卡就从昨天开始数。"
        ),
        vectors=[[0.1, 0.2, 0.3]],
    )
    return result["id"]


# ==================== 解析工具 ====================

def test_loads_json_strips_code_fence():
    raw = '好的，结果如下：\n```json\n{"summary": "讲番茄工作法", "points": ["25 分钟"]}\n```\n希望有帮助'
    data = study._loads_json(raw)
    assert isinstance(data, dict)
    assert data["summary"] == "讲番茄工作法"


def test_loads_json_returns_none_for_plain_text():
    assert study._loads_json("这是一段没有 JSON 的普通回答") is None


def test_as_points_accepts_dict_and_string_items():
    summary, points = study._as_points(
        {"summary": "概述", "points": [{"title": "要点一", "detail": "细节"}, "要点二"]}
    )
    assert summary == "概述"
    assert points == ["要点一：细节", "要点二"]


# ==================== 摘要 ====================

def test_summarize_parses_model_json(temp_store, monkeypatch):
    _seed_document()
    monkeypatch.setattr(
        llm,
        "chat",
        lambda messages, **kwargs: '```json\n{"summary": "讲了番茄工作法与打卡规则", '
        '"points": ["25 分钟专注 + 5 分钟休息", "四个番茄钟后长休息", "打卡天数从今天往前数"]}\n```',
    )

    result = study.summarize()

    assert result["parsed"] is True
    assert result["summary"] == "讲了番茄工作法与打卡规则"
    assert len(result["points"]) == 3
    assert result["sources"][0]["title"] == "番茄工作法学习笔记"
    assert result["raw"] is None


def test_summarize_falls_back_to_raw_when_unparsable(temp_store, monkeypatch):
    _seed_document()
    monkeypatch.setattr(llm, "chat", lambda messages, **kwargs: "这份资料主要讲番茄工作法，没有 JSON。")

    result = study.summarize()

    assert result["parsed"] is False
    assert result["points"] == []
    assert "番茄工作法" in result["summary"]
    assert result["raw"]


def test_summarize_rejects_empty_library(temp_store):
    with pytest.raises(ValueError, match="资料库是空的"):
        study.summarize()


def test_summarize_accepts_inline_text(temp_store, monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda messages, **kwargs: '{"summary": "临时文本的总结", "points": ["甲"]}')
    result = study.summarize(text="这里是一段临时粘贴的内容。")
    assert result["summary"] == "临时文本的总结"
    assert result["sources"] == []


# ==================== 出题 ====================

def test_quiz_parses_questions(temp_store, monkeypatch):
    _seed_document()
    monkeypatch.setattr(
        llm,
        "chat",
        lambda messages, **kwargs: '{"questions": [{"question": "一个番茄钟多长？", '
        '"options": ["15 分钟", "25 分钟", "45 分钟", "60 分钟"], "answer": "b", '
        '"explanation": "资料写明 25 分钟专注"}]}',
    )

    result = study.quiz(count=1)

    assert result["parsed"] is True
    assert result["questions"][0]["answer"] == "B"  # 统一转大写
    assert result["questions"][0]["options"][1] == "25 分钟"
    assert result["truncated"] is False


def test_quiz_drops_items_without_options(temp_store, monkeypatch):
    _seed_document()
    monkeypatch.setattr(
        llm,
        "chat",
        lambda messages, **kwargs: '{"questions": [{"question": "没有选项的题", "answer": "A"}]}',
    )

    result = study.quiz()

    assert result["questions"] == []
    assert result["parsed"] is False
    assert result["raw"]


# ==================== 接口层 ====================

def test_summary_endpoint(client, monkeypatch):
    _seed_document()
    monkeypatch.setattr(llm, "chat", lambda messages, **kwargs: '{"summary": "接口层摘要", "points": ["一"]}')

    response = client.post("/ai/summary", json={"max_points": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "接口层摘要"
    assert body["model"]
    assert body["parsed"] is True


def test_quiz_endpoint_with_document_id(client, monkeypatch):
    doc_id = _seed_document()
    monkeypatch.setattr(
        llm,
        "chat",
        lambda messages, **kwargs: '{"questions": [{"question": "打卡天数怎么数？", '
        '"options": ["从今天", "从昨天", "从周一开始"], "answer": "B", "explanation": "资料里有说明"}]}',
    )

    response = client.post("/ai/quiz", json={"document_id": doc_id, "count": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["questions"][0]["answer"] == "B"
    assert body["sources"][0]["document_id"] == doc_id


def test_summary_endpoint_empty_library_returns_400(client):
    response = client.post("/ai/summary", json={})
    assert response.status_code == 400
    assert "资料库是空的" in response.json()["detail"]


def test_quiz_endpoint_missing_document_returns_400(client):
    response = client.post("/ai/quiz", json={"document_id": 9999})
    assert response.status_code == 400
    assert "文档不存在" in response.json()["detail"]


def test_summary_endpoint_maps_llm_error_to_502(client, monkeypatch):
    _seed_document()

    def boom(messages, **kwargs):
        raise llm.LLMError("连不上 ollama")

    monkeypatch.setattr(llm, "chat", boom)
    response = client.post("/ai/summary", json={})
    assert response.status_code == 502
