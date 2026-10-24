
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session


# ==================== 数据库配置 ====================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR / 'studymate.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

app = FastAPI(title="StudyMate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 数据表 ====================

class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(
        String(50),
        nullable=False,
        default="未分类",
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    due_date = Column(String(10), nullable=False, index=True)
    category = Column(
        String(50),
        nullable=False,
        default="未分类",
    )
    completed = Column(Boolean, nullable=False, default=False)


class Checkin(Base):
    __tablename__ = "checkins"

    __table_args__ = (
        UniqueConstraint(
            "checkin_date",
            name="uq_checkin_date",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    checkin_date = Column(String(10), nullable=False, index=True)


class StudySession(Base):
    """学习计时完成记录。"""

    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=True, index=True)
    task_title = Column(
        String(200),
        nullable=False,
        default="自由学习",
    )
    duration_minutes = Column(Integer, nullable=False)
    started_at = Column(String(40), nullable=False)
    completed_at = Column(String(40), nullable=False, index=True)
    study_date = Column(String(10), nullable=False, index=True)


# 兼容旧数据库：notes 表缺少 category 时添加该列。
inspector = inspect(engine)

if inspector.has_table("notes"):
    note_columns = {
        column["name"]
        for column in inspector.get_columns("notes")
    }

    if "category" not in note_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE notes "
                    "ADD COLUMN category VARCHAR(50) "
                    "NOT NULL DEFAULT '未分类'"
                )
            )

# 只创建不存在的表，不会删除现有数据。
Base.metadata.create_all(bind=engine)


# ==================== 数据库连接 ====================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== 请求模型 ====================

class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    category: str = Field(
        default="未分类",
        max_length=50,
    )


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date
    category: str = Field(
        default="未分类",
        max_length=50,
    )
    completed: bool = False


class StudySessionInput(BaseModel):
    task_id: int | None = None
    task_title: str = Field(
        default="自由学习",
        min_length=1,
        max_length=200,
    )
    duration_minutes: int = Field(ge=1, le=240)
    started_at: datetime
    completed_at: datetime


# ==================== 数据格式转换 ====================

def note_dict(note: Note):
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "category": note.category or "未分类",
    }


def task_dict(task: Task):
    return {
        "id": task.id,
        "title": task.title,
        "due_date": task.due_date,
        "category": task.category or "未分类",
        "completed": task.completed,
    }


def study_session_dict(record: StudySession):
    return {
        "id": record.id,
        "task_id": record.task_id,
        "task_title": record.task_title,
        "duration_minutes": record.duration_minutes,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "study_date": record.study_date,
    }


# ==================== 首页接口 ====================

@app.get("/")
def root():
    return {"message": "StudyMate API is running"}


# ==================== 学习笔记接口 ====================

@app.get("/notes")
def get_notes(
    q: str = "",
    category: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Note)

    if q.strip():
        keyword = f"%{q.strip()}%"
        query = query.filter(
            (Note.title.like(keyword))
            | (Note.content.like(keyword))
        )

    if category and category != "全部":
        query = query.filter(Note.category == category)

    return [
        note_dict(note)
        for note in query.order_by(Note.id.desc()).all()
    ]


@app.post("/notes")
def create_note(
    data: NoteInput,
    db: Session = Depends(get_db),
):
    title = data.title.strip()
    content = data.content.strip()

    if not title or not content:
        raise HTTPException(
            status_code=422,
            detail="标题和内容不能为空",
        )

    note = Note(
        title=title,
        content=content,
        category=data.category.strip() or "未分类",
    )

    db.add(note)
    db.commit()
    db.refresh(note)

    return note_dict(note)


@app.put("/notes/{note_id}")
def update_note(
    note_id: int,
    data: NoteInput,
    db: Session = Depends(get_db),
):
    note = db.query(Note).filter(Note.id == note_id).first()

    if not note:
        raise HTTPException(
            status_code=404,
            detail="笔记不存在",
        )

    title = data.title.strip()
    content = data.content.strip()

    if not title or not content:
        raise HTTPException(
            status_code=422,
            detail="标题和内容不能为空",
        )

    note.title = title
    note.content = content
    note.category = data.category.strip() or "未分类"

    db.commit()
    db.refresh(note)

    return note_dict(note)


@app.delete("/notes/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
):
    note = db.query(Note).filter(Note.id == note_id).first()

    if not note:
        raise HTTPException(
            status_code=404,
            detail="笔记不存在",
        )

    db.delete(note)
    db.commit()

    return {"message": "笔记删除成功"}


# ==================== 学习任务接口 ====================

@app.get("/tasks")
def get_tasks(
    q: str = "",
    status: str = "all",
    due_date: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Task)

    if q.strip():
        query = query.filter(
            Task.title.like(f"%{q.strip()}%")
        )

    if status == "pending":
        query = query.filter(Task.completed.is_(False))
    elif status == "completed":
        query = query.filter(Task.completed.is_(True))

    if due_date:
        query = query.filter(Task.due_date == due_date)

    tasks = query.order_by(
        Task.due_date.asc(),
        Task.id.desc(),
    ).all()

    return [task_dict(task) for task in tasks]


@app.post("/tasks")
def create_task(
    data: TaskInput,
    db: Session = Depends(get_db),
):
    title = data.title.strip()

    if not title:
        raise HTTPException(
            status_code=422,
            detail="任务名称不能为空",
        )

    task = Task(
        title=title,
        due_date=data.due_date.isoformat(),
        category=data.category.strip() or "未分类",
        completed=data.completed,
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return task_dict(task)


@app.put("/tasks/{task_id}")
def update_task(
    task_id: int,
    data: TaskInput,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )

    title = data.title.strip()

    if not title:
        raise HTTPException(
            status_code=422,
            detail="任务名称不能为空",
        )

    task.title = title
    task.due_date = data.due_date.isoformat()
    task.category = data.category.strip() or "未分类"
    task.completed = data.completed

    db.commit()
    db.refresh(task)

    return task_dict(task)


@app.patch("/tasks/{task_id}/toggle")
def toggle_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )

    task.completed = not task.completed

    db.commit()
    db.refresh(task)

    return task_dict(task)


@app.delete("/tasks/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )

    db.delete(task)
    db.commit()

    return {"message": "任务删除成功"}


# ==================== 每日学习打卡接口 ====================

@app.get("/checkins")
def get_checkins(db: Session = Depends(get_db)):
    records = (
        db.query(Checkin)
        .order_by(Checkin.checkin_date.desc())
        .all()
    )

    dates = [record.checkin_date for record in records]
    checked_dates = set(dates)
    today = date.today()

    streak = 0
    current_day = today

    # 今天还没打卡时，从昨天开始计算连续天数。
    if current_day.isoformat() not in checked_dates:
        current_day -= timedelta(days=1)

    while current_day.isoformat() in checked_dates:
        streak += 1
        current_day -= timedelta(days=1)

    return {
        "dates": dates,
        "total": len(dates),
        "streak": streak,
        "checked_today": today.isoformat() in checked_dates,
        "today": today.isoformat(),
    }


@app.post("/checkins/today")
def checkin_today(db: Session = Depends(get_db)):
    today = date.today().isoformat()

    existing = (
        db.query(Checkin)
        .filter(Checkin.checkin_date == today)
        .first()
    )

    if existing:
        return {
            "message": "今天已经打过卡了",
            "checked_today": True,
        }

    db.add(Checkin(checkin_date=today))
    db.commit()

    return {
        "message": "打卡成功！",
        "checked_today": True,
    }


@app.delete("/checkins/today")
def cancel_checkin_today(db: Session = Depends(get_db)):
    today = date.today().isoformat()

    record = (
        db.query(Checkin)
        .filter(Checkin.checkin_date == today)
        .first()
    )

    if record:
        db.delete(record)
        db.commit()

    return {
        "message": "已取消今日打卡",
        "checked_today": False,
    }


# ==================== 学习计时记录接口 ====================

@app.get("/study-sessions")
def get_study_sessions(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    safe_limit = max(1, min(limit, 200))

    records = (
        db.query(StudySession)
        .order_by(StudySession.completed_at.desc())
        .limit(safe_limit)
        .all()
    )

    return [
        study_session_dict(record)
        for record in records
    ]


@app.post("/study-sessions")
def create_study_session(
    data: StudySessionInput,
    db: Session = Depends(get_db),
):
    if data.completed_at <= data.started_at:
        raise HTTPException(
            status_code=422,
            detail="结束时间必须晚于开始时间",
        )

    task_title = data.task_title.strip() or "自由学习"

    if data.task_id is not None:
        task = (
            db.query(Task)
            .filter(Task.id == data.task_id)
            .first()
        )

        if not task:
            raise HTTPException(
                status_code=404,
                detail="关联的学习任务不存在",
            )

        # 保存任务名称快照，便于查看历史记录。
        task_title = task.title

    record = StudySession(
        task_id=data.task_id,
        task_title=task_title,
        duration_minutes=data.duration_minutes,
        started_at=data.started_at.isoformat(),
        completed_at=data.completed_at.isoformat(),
        study_date=data.completed_at.date().isoformat(),
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return study_session_dict(record)


# ==================== AI 能力（阶段一：本地模型对话） ====================

from ai.router import router as ai_router  # noqa: E402  放最后，避免循环导入

app.include_router(ai_router)
