# -*- coding: utf-8 -*-
"""AI 相关接口：健康检查、对话、资料入库、检索、检索问答。

阶段一：/ai/health、/ai/chat
阶段二：/ai/documents*、/ai/search、/ai/ask
阶段三：/ai/summary、/ai/quiz（后续）
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import llm, rag, store, study

router = APIRouter(prefix="/ai", tags=["ai"])

_BAD_REQUEST = 400
_BAD_GATEWAY = 502


# ==================== 数据模型 ====================

class ChatMessage(BaseModel):
    role: str = Field(default="user", description="user / assistant / system")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str


class TextDocRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source: str = ""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=20)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SummaryRequest(BaseModel):
    """不传 document_id 就用资料库全部内容；也可以直接给 text。"""

    document_id: int | None = Field(default=None, ge=1)
    text: str | None = None
    max_points: int = Field(default=6, ge=3, le=12)


class QuizRequest(BaseModel):
    document_id: int | None = Field(default=None, ge=1)
    text: str | None = None
    count: int = Field(default=3, ge=1, le=10)


# ==================== 基础 ====================

def _model_name() -> str:
    return llm.config.OLLAMA_MODEL if llm.config.LLM_PROVIDER == "ollama" else llm.config.DEEPSEEK_MODEL


@router.get("/health")
def ai_health() -> dict:
    """前端面板打开时先探一次，据此决定是否显示「AI 未就绪」。"""
    info = llm.health()
    info["rag"] = store.stats()
    return info


@router.post("/chat", response_model=ChatResponse)
def ai_chat(payload: ChatRequest) -> ChatResponse:
    messages = [m.model_dump() for m in payload.messages]
    try:
        reply = llm.chat(messages, temperature=payload.temperature)
    except llm.LLMError as exc:
        raise HTTPException(status_code=_BAD_GATEWAY, detail=str(exc)) from exc
    return ChatResponse(reply=reply, provider=llm.config.LLM_PROVIDER, model=_model_name())


# ==================== 资料管理 ====================

@router.get("/documents")
def list_documents() -> dict:
    docs = store.list_documents()
    return {"total": len(docs), "items": docs, "stats": store.stats()}


@router.post("/documents", status_code=201)
def add_text_document(payload: TextDocRequest) -> dict:
    """直接提交纯文本（方便用 curl / 测试灌资料）。"""
    try:
        result = rag.ingest(title=payload.title, text=payload.content, source=payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=_BAD_GATEWAY, detail=str(exc)) from exc
    return result


@router.post("/documents/upload", status_code=201)
async def upload_document(file: UploadFile = File(...), title: str | None = None) -> dict:
    """上传 .txt / .md / .pdf，抽文本 → 分块 → 向量化 → 入库。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=_BAD_REQUEST, detail="文件是空的")
    try:
        return rag.ingest_bytes(file.filename or "未命名", data, title=title)
    except ValueError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=_BAD_GATEWAY, detail=str(exc)) from exc


@router.delete("/documents/{doc_id}")
def remove_document(doc_id: int) -> dict:
    if not store.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"deleted": doc_id}


# ==================== 检索与问答 ====================

@router.post("/search")
def search(payload: SearchRequest) -> dict:
    try:
        vector = llm.embed([payload.query], kind="query")[0]
    except llm.LLMError as exc:
        raise HTTPException(status_code=_BAD_GATEWAY, detail=str(exc)) from exc
    hits = store.search(vector, top_k=payload.top_k)
    return {"query": payload.query, "total": len(hits), "hits": hits}


@router.post("/ask")
def ask(payload: AskRequest) -> dict:
    try:
        return rag.ask(payload.question, top_k=payload.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=_BAD_GATEWAY, detail=str(exc)) from exc


# ==================== 摘要与复习题 ====================

@router.post("/summary")
def summary(payload: SummaryRequest) -> dict:
    """把整篇资料压成「一句话概括 + 若干要点」，用于课后快速回顾。"""
    try:
        result = study.summarize(
            document_id=payload.document_id,
            text=payload.text,
            max_points=payload.max_points,
        )
    except ValueError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=_BAD_GATEWAY, detail=str(exc)) from exc
    result["model"] = _model_name()
    return result


@router.post("/quiz")
def quiz(payload: QuizRequest) -> dict:
    """根据资料出选择题，带答案与解析。"""
    try:
        result = study.quiz(
            document_id=payload.document_id,
            text=payload.text,
            count=payload.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=_BAD_GATEWAY, detail=str(exc)) from exc
    result["model"] = _model_name()
    return result
