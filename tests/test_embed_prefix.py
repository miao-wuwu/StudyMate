"""embedding 前缀策略的单元测试（不联网，mock 掉 HTTP 调用）。"""

from __future__ import annotations

import pytest

from ai import llm


class Recorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, url, payload, *args, **kwargs):  # 模拟 _post_json
        self.prompts.append(payload["prompt"])
        return {"embedding": [0.1, 0.2, 0.3]}


@pytest.fixture()
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(llm, "_post_json", rec)
    monkeypatch.setattr(llm.config, "OLLAMA_EMBED_MODEL", "nomic-embed-text", raising=False)
    return rec


def test_document_prefix(recorder):
    llm.embed(["数组是连续内存"], kind="document")
    assert recorder.prompts == ["search_document: 数组是连续内存"]


def test_query_prefix(recorder):
    llm.embed(["数组为什么随机访问快"], kind="query")
    assert recorder.prompts == ["search_query: 数组为什么随机访问快"]


def test_default_kind_is_document(recorder):
    llm.embed(["默认按文档处理"])
    assert recorder.prompts == ["search_document: 默认按文档处理"]


def test_no_prefix_for_other_models(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(llm, "_post_json", rec)
    monkeypatch.setattr(llm.config, "OLLAMA_EMBED_MODEL", "bge-m3", raising=False)
    llm.embed(["换个模型就不加前缀"], kind="query")
    assert rec.prompts == ["换个模型就不加前缀"]


def test_blank_texts_are_skipped(recorder):
    assert llm.embed(["", "   "]) == []
    assert recorder.prompts == []
