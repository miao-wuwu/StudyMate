
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app, Base, get_db


@pytest.fixture
def client(tmp_path):
    """为每个测试创建独立的临时数据库。"""
    test_db_path = tmp_path / "test_studymate.db"

    test_engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def test_create_note(client):
    response = client.post(
        "/notes",
        json={
            "title": "Python 测试笔记",
            "content": "学习 pytest 自动化测试",
            "category": "编程",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Python 测试笔记"
    assert data["content"] == "学习 pytest 自动化测试"
    assert data["category"] == "编程"
    assert "id" in data


def test_get_notes(client):
    client.post(
        "/notes",
        json={"title": "第一篇笔记", "content": "内容一"},
    )
    client.post(
        "/notes",
        json={"title": "第二篇笔记", "content": "内容二"},
    )

    response = client.get("/notes")

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "第二篇笔记"
    assert data[1]["title"] == "第一篇笔记"


def test_search_notes(client):
    client.post(
        "/notes",
        json={"title": "Python 入门", "content": "学习编程"},
    )
    client.post(
        "/notes",
        json={"title": "英语笔记", "content": "学习单词"},
    )

    response = client.get("/notes", params={"q": "Python"})

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Python 入门"


def test_update_note(client):
    create_response = client.post(
        "/notes",
        json={"title": "旧标题", "content": "旧内容"},
    )
    note_id = create_response.json()["id"]

    response = client.put(
        f"/notes/{note_id}",
        json={
            "title": "新标题",
            "content": "新内容",
            "category": "学习",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "新标题"
    assert data["content"] == "新内容"
    assert data["category"] == "学习"


def test_delete_note(client):
    create_response = client.post(
        "/notes",
        json={"title": "待删除笔记", "content": "测试删除"},
    )
    note_id = create_response.json()["id"]

    delete_response = client.delete(f"/notes/{note_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "笔记删除成功"

    list_response = client.get("/notes")
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_update_missing_note_returns_404(client):
    response = client.put(
        "/notes/999999",
        json={"title": "新标题", "content": "新内容"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "笔记不存在"


def test_delete_missing_note_returns_404(client):
    response = client.delete("/notes/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "笔记不存在"
