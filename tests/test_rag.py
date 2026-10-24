# -*- coding: utf-8 -*-
"""RAG 相关测试：分块、入库、检索、以及 /ai/* 的文档接口。

全部用临时数据库 + mock 向量，不连 Ollama、不污染真实的 studymate.db。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from ai import llm, store
from main import app


@pytest.fixture()
def temp_store(tmp_path, monkeypatch):
    """把 store.engine 换成临时库，跑完自动丢弃。"""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(store, "engine", eng)
    store.init_db()
    yield eng


@pytest.fixture()
def fake_vectors(monkeypatch):
    """确定性向量：包含「打卡」返回 [1,0,0]，包含「复习」返回 [0,1,0]，其它 [0,0,1]。"""

    def _embed(texts, *args, **kwargs):
        out = []
        for text in texts:
            if "打卡" in text:
                out.append([1.0, 0.0, 0.0])
            elif "复习" in text:
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return out

    monkeypatch.setattr(llm, "embed", _embed)
    return _embed


def test_chunk_text_keeps_short_text_whole():
    assert store.chunk_text("今天只学了二十分钟。") == ["今天只学了二十分钟。"]


def test_chunk_text_splits_long_text_with_overlap():
    text = "。".join([f"第{i}句关于卷积神经网络的理解" for i in range(80)]) + "。"
    chunks = store.chunk_text(text, size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 150 for c in chunks)
    # 相邻块之间应有重叠（上一块尾部出现在下一块里）
    assert chunks[0][-10:] in chunks[1] or chunks[1][:10] in chunks[0]


def test_add_and_search_document(temp_store):
    store.add_document(
        "打卡说明",
        "每天打卡可以获得积分。" * 10,
        vectors=[[1.0, 0.0, 0.0]],
    )
    hits = store.search([1.0, 0.0, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0]["title"] == "打卡说明"
    assert hits[0]["score"] > 0.9


def test_search_skips_dimension_mismatch(temp_store):
    store.add_document("维度不同", "内容一段。", vectors=[[1.0, 0.0, 0.0, 0.0]])
    assert store.search([1.0, 0.0, 0.0], top_k=3) == []


def test_documents_endpoint_roundtrip(temp_store, fake_vectors):
    with TestClient(app) as client:
        created = client.post(
            "/ai/documents",
            json={"title": "学习笔记", "content": "每天打卡可以积累连续天数。" * 20, "source": "notes.md"},
        )
        assert created.status_code == 201, created.text
        doc_id = created.json()["id"]

        listed = client.get("/ai/documents").json()
        assert listed["total"] == 1
        assert listed["items"][0]["title"] == "学习笔记"

        deleted = client.delete(f"/ai/documents/{doc_id}")
        assert deleted.status_code == 200
        assert client.get("/ai/documents").json()["total"] == 0


def test_search_endpoint_returns_hits(temp_store, fake_vectors):
    store.add_document("复习方法", "复习要间隔重复。", vectors=[[0.0, 1.0, 0.0]])
    with TestClient(app) as client:
        resp = client.post("/ai/search", json={"query": "怎么复习", "top_k": 3})
        assert resp.status_code == 200
        hits = resp.json()["hits"]
        assert hits and hits[0]["title"] == "复习方法"


def test_ask_endpoint_uses_rag_with_sources(temp_store, fake_vectors, monkeypatch):
    store.add_document("复习方法", "复习要间隔重复，先做题再看答案。", vectors=[[0.0, 1.0, 0.0]])
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["system"] = messages[0]["content"]
        captured["user"] = messages[-1]["content"]
        return "建议间隔重复复习[1]。"

    monkeypatch.setattr(llm, "chat", fake_chat)
    with TestClient(app) as client:
        resp = client.post("/ai/ask", json={"question": "怎么复习更高效？"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "rag"
        assert body["sources"][0]["title"] == "复习方法"
        assert "资料片段" in captured["user"]


def test_ask_falls_back_to_chat_without_documents(temp_store, monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda messages, **kwargs: "先定个小目标。")
    with TestClient(app) as client:
        body = client.post("/ai/ask", json={"question": "怎么开始学习？"}).json()
        assert body["mode"] == "chat"
        assert body["sources"] == []


def test_upload_rejects_unsupported_type(temp_store, fake_vectors):
    with TestClient(app) as client:
        resp = client.post(
            "/ai/documents/upload",
            files={"file": ("a.docx", b"whatever", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "暂不支持" in resp.json()["detail"]
