
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app, Base, get_db


@pytest.fixture
def client(tmp_path):
    """为每个测试创建独立的临时数据库。"""
    test_db_path = tmp_path / "test_tasks.db"

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


def test_create_task(client):
    response = client.post(
        "/tasks",
        json={
            "title": "学习 Python",
            "due_date": "2026-12-31",
            "category": "编程",
            "completed": False,
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "学习 Python"
    assert data["due_date"] == "2026-12-31"
    assert data["category"] == "编程"
    assert data["completed"] is False
    assert "id" in data


def test_get_tasks(client):
    client.post(
        "/tasks",
        json={
            "title": "任务一",
            "due_date": "2026-12-30",
        },
    )
    client.post(
        "/tasks",
        json={
            "title": "任务二",
            "due_date": "2026-12-31",
        },
    )

    response = client.get("/tasks")

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert {task["title"] for task in data} == {
        "任务一",
        "任务二",
    }


def test_toggle_task(client):
    create_response = client.post(
        "/tasks",
        json={
            "title": "待完成任务",
            "due_date": "2026-12-31",
        },
    )
    task_id = create_response.json()["id"]

    response = client.patch(f"/tasks/{task_id}/toggle")

    assert response.status_code == 200
    assert response.json()["completed"] is True

    # 再切换一次，应恢复为未完成
    response = client.patch(f"/tasks/{task_id}/toggle")

    assert response.status_code == 200
    assert response.json()["completed"] is False


def test_delete_task(client):
    create_response = client.post(
        "/tasks",
        json={
            "title": "待删除任务",
            "due_date": "2026-12-31",
        },
    )
    task_id = create_response.json()["id"]

    delete_response = client.delete(f"/tasks/{task_id}")

    assert delete_response.status_code == 200

    list_response = client.get("/tasks")
    assert list_response.status_code == 200
    assert all(
        task["id"] != task_id
        for task in list_response.json()
    )


def test_create_task_rejects_empty_title(client):
    response = client.post(
        "/tasks",
        json={
            "title": "   ",
            "due_date": "2026-12-31",
        },
    )

    assert response.status_code == 422
