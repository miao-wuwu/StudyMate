import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";
import CheckinPanel from "./CheckinPanel";
import TimerPanel from "./TimerPanel";
import DashboardPanel from "./DashboardPanel";
import AchievementsPanel from "./AchievementsPanel";

type Note = {
  id: number;
  title: string;
  content: string;
  category: string;
};

type Task = {
  id: number;
  title: string;
  due_date: string;
  category: string;
  completed: boolean;
};

type SortOrder = "newest" | "oldest" | "title";
type TaskFilter = "all" | "today" | "pending" | "completed";

const API_URL = "http://127.0.0.1:8000";
const DAILY_GOAL = 3;

const CATEGORIES = [
  "未分类",
  "Python",
  "数学",
  "英语",
  "计算机",
  "其他",
];

function todayString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function App() {
  const [page, setPage] = useState<
    "notes" | "tasks" | "checkin" | "timer" | "dashboard" | "achievements"
  >("notes");

  // 笔记数据
  const [notes, setNotes] = useState<Note[]>([]);
  const [allNotes, setAllNotes] = useState<Note[]>([]);
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("全部");
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("未分类");
  const [editingId, setEditingId] = useState<number | null>(null);

  // 学习任务数据
  const [tasks, setTasks] = useState<Task[]>([]);
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDate, setTaskDate] = useState(todayString());
  const [taskCategory, setTaskCategory] = useState("未分类");
  const [taskEditingId, setTaskEditingId] = useState<number | null>(null);
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("all");
  const [taskSearch, setTaskSearch] = useState("");

  const [loading, setLoading] = useState(true);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [taskMessage, setTaskMessage] = useState("");

  // 加载笔记
  const loadNotes = useCallback(async () => {
    setLoading(true);

    try {
      const params = new URLSearchParams();
      params.set("q", search);

      if (selectedCategory !== "全部") {
        params.set("category", selectedCategory);
      }

      const response = await fetch(`${API_URL}/notes?${params}`);

      if (!response.ok) {
        throw new Error("读取笔记失败");
      }

      const data: Note[] = await response.json();
      setNotes(data);
    } catch {
      setMessage("无法读取笔记，请确认后端服务正在运行。");
    } finally {
      setLoading(false);
    }
  }, [search, selectedCategory]);

  // 加载全部笔记，用于统计
  const loadAllNotes = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/notes`);

      if (!response.ok) {
        throw new Error("读取统计数据失败");
      }

      setAllNotes(await response.json());
    } catch {
      setMessage("统计数据加载失败，请检查后端服务。");
    }
  }, []);

  // 加载当前筛选条件下的任务列表
  const loadTasks = useCallback(async () => {
    setTasksLoading(true);

    try {
      const params = new URLSearchParams();

      if (taskSearch.trim()) {
        params.set("q", taskSearch.trim());
      }

      if (taskFilter === "pending" || taskFilter === "completed") {
        params.set("status", taskFilter);
      }

      if (taskFilter === "today") {
        params.set("due_date", todayString());
      }

      const response = await fetch(`${API_URL}/tasks?${params}`);

      if (!response.ok) {
        throw new Error("读取任务失败");
      }

      setTasks(await response.json());
    } catch {
      setTaskMessage("无法读取学习任务，请确认后端服务正常。");
    } finally {
      setTasksLoading(false);
    }
  }, [taskFilter, taskSearch]);

  // 独立加载全部任务，确保每日目标不受搜索和筛选影响
  const loadAllTasks = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/tasks`);

      if (!response.ok) {
        throw new Error("读取全部任务失败");
      }

      const data: Task[] = await response.json();
      setAllTasks(data);
    } catch {
      setTaskMessage("无法读取每日目标数据，请检查后端服务。");
    }
  }, []);

  useEffect(() => {
    void loadNotes();
  }, [loadNotes]);

  useEffect(() => {
    void loadAllNotes();
  }, [loadAllNotes]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    void loadAllTasks();
  }, [loadAllTasks]);

  // 笔记操作
  function resetNoteForm() {
    setTitle("");
    setContent("");
    setCategory("未分类");
    setEditingId(null);
  }

  function handleEditNote(note: Note) {
    setEditingId(note.id);
    setTitle(note.title);
    setContent(note.content);
    setCategory(note.category || "未分类");
    setMessage("");

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleNoteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!title.trim() || !content.trim()) {
      setMessage("请填写笔记标题和内容。");
      return;
    }

    setSaving(true);
    setMessage("");

    try {
      const isEditing = editingId !== null;

      const url = isEditing
        ? `${API_URL}/notes/${editingId}`
        : `${API_URL}/notes`;

      const response = await fetch(url, {
        method: isEditing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          content: content.trim(),
          category,
        }),
      });

      if (!response.ok) {
        throw new Error(isEditing ? "修改笔记失败。" : "保存笔记失败。");
      }

      resetNoteForm();

      setMessage(isEditing ? "笔记修改成功！" : "笔记保存成功！");

      await Promise.all([loadNotes(), loadAllNotes()]);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "操作失败。"
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteNote(note: Note) {
    if (!window.confirm(`确定删除笔记「${note.title}」吗？`)) {
      return;
    }

    try {
      const response = await fetch(`${API_URL}/notes/${note.id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("删除笔记失败。");
      }

      if (editingId === note.id) {
        resetNoteForm();
      }

      setMessage("笔记删除成功！");

      await Promise.all([loadNotes(), loadAllNotes()]);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "删除失败。"
      );
    }
  }

  // 学习任务操作
  function resetTaskForm() {
    setTaskTitle("");
    setTaskDate(todayString());
    setTaskCategory("未分类");
    setTaskEditingId(null);
  }

  function handleEditTask(task: Task) {
    setTaskEditingId(task.id);
    setTaskTitle(task.title);
    setTaskDate(task.due_date);
    setTaskCategory(task.category || "未分类");
    setTaskMessage("");

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleTaskSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!taskTitle.trim() || !taskDate) {
      setTaskMessage("请填写任务名称并选择日期。");
      return;
    }

    setSaving(true);
    setTaskMessage("");

    try {
      const existing = allTasks.find(
        (task) => task.id === taskEditingId
      );

      const isEditing = taskEditingId !== null;

      const response = await fetch(
        isEditing
          ? `${API_URL}/tasks/${taskEditingId}`
          : `${API_URL}/tasks`,
        {
          method: isEditing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: taskTitle.trim(),
            due_date: taskDate,
            category: taskCategory,
            completed: existing?.completed ?? false,
          }),
        }
      );

      if (!response.ok) {
        throw new Error("保存任务失败，请检查后端。");
      }

      resetTaskForm();

      setTaskMessage(
        isEditing ? "任务修改成功！" : "任务创建成功！"
      );

      await Promise.all([loadTasks(), loadAllTasks()]);
    } catch (error) {
      setTaskMessage(
        error instanceof Error ? error.message : "任务操作失败。"
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleTask(task: Task) {
    setBusyTaskId(task.id);
    setTaskMessage("");

    try {
      const response = await fetch(
        `${API_URL}/tasks/${task.id}/toggle`,
        { method: "PATCH" }
      );

      if (!response.ok) {
        throw new Error("更新任务状态失败。");
      }

      await Promise.all([loadTasks(), loadAllTasks()]);
    } catch (error) {
      setTaskMessage(
        error instanceof Error ? error.message : "操作失败。"
      );
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleDeleteTask(task: Task) {
    if (!window.confirm(`确定删除任务「${task.title}」吗？`)) {
      return;
    }

    setBusyTaskId(task.id);
    setTaskMessage("");

    try {
      const response = await fetch(`${API_URL}/tasks/${task.id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("删除任务失败。");
      }

      if (taskEditingId === task.id) {
        resetTaskForm();
      }

      setTaskMessage("任务删除成功！");

      await Promise.all([loadTasks(), loadAllTasks()]);
    } catch (error) {
      setTaskMessage(
        error instanceof Error ? error.message : "删除失败。"
      );
    } finally {
      setBusyTaskId(null);
    }
  }

  // 笔记统计
  const totalNotes = allNotes.length;

  const usedCategories = useMemo(
    () => new Set(allNotes.map((note) => note.category || "未分类")),
    [allNotes]
  );

  const categorizedNotes = allNotes.filter(
    (note) => (note.category || "未分类") !== "未分类"
  ).length;

  const categoryStats = useMemo(() => {
    return Array.from(
      new Set([
        ...CATEGORIES,
        ...allNotes.map((note) => note.category || "未分类"),
      ])
    )
      .map((name) => ({
        name,
        count: allNotes.filter(
          (note) => (note.category || "未分类") === name
        ).length,
      }))
      .filter((item) => item.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [allNotes]);

  const displayedNotes = useMemo(() => {
    const result = [...notes];

    result.sort((a, b) => {
      if (sortOrder === "oldest") {
        return a.id - b.id;
      }

      if (sortOrder === "title") {
        return a.title.localeCompare(b.title, "zh-CN") || a.id - b.id;
      }

      return b.id - a.id;
    });

    return result;
  }, [notes, sortOrder]);

  // 任务统计
  const taskCounts = useMemo(() => {
    const today = todayString();

    return {
      total: tasks.length,
      completed: tasks.filter((task) => task.completed).length,
      pending: tasks.filter((task) => !task.completed).length,
      today: tasks.filter((task) => task.due_date === today).length,
    };
  }, [tasks]);

  const completionRate = taskCounts.total
    ? Math.round(
        (taskCounts.completed / taskCounts.total) * 100
      )
    : 0;

  // 每日目标独立统计全部任务，不受列表筛选影响
  const todayTaskCounts = useMemo(() => {
    const today = todayString();

    const todayTasks = allTasks.filter(
      (task) => task.due_date === today
    );

    return {
      total: todayTasks.length,
      completed: todayTasks.filter((task) => task.completed).length,
    };
  }, [allTasks]);

  const dailyGoalProgress = Math.min(
    100,
    Math.round(
      (todayTaskCounts.completed / DAILY_GOAL) * 100
    )
  );

  return (
    <main className="app">
      <header className="topbar">
        <a
          className="brand"
          href="/"
          onClick={(event) => {
            event.preventDefault();
            setPage("notes");
          }}
        >
          <span className="brand-icon">S</span>
          <span>StudyMate</span>
        </a>

        <span className="topbar-label">个人学习空间</span>
      </header>

      <section className="hero">
        <p className="eyebrow">YOUR PERSONAL STUDY SPACE</p>
        <h1>让每一次学习，都有所积累。</h1>
        <p className="hero-description">
          记录灵感、安排计划，把今天学到的东西留给明天的自己。
        </p>
      </section>

      <nav className="main-tabs" aria-label="功能页面">
        <button
          className={`main-tab ${page === "notes" ? "active" : ""}`}
          onClick={() => setPage("notes")}
          type="button"
        >
          ✎ 学习笔记
        </button>

        <button
          className={`main-tab ${page === "tasks" ? "active" : ""}`}
          onClick={() => setPage("tasks")}
          type="button"
        >
          ✓ 学习计划
        </button>

        <button
          className={`main-tab ${page === "checkin" ? "active" : ""}`}
          onClick={() => setPage("checkin")}
          type="button"
        >
          ♡ 每日打卡
        </button>

        <button
          className={`main-tab ${page === "timer" ? "active" : ""}`}
          onClick={() => setPage("timer")}
          type="button"
        >
          ◷ 专注计时
        </button>

        <button
          className={`main-tab ${page === "dashboard" ? "active" : ""}`}
          onClick={() => setPage("dashboard")}
          type="button"
        >
          ▥ 学习仪表盘
        </button>

        <button
          className={`main-tab ${page === "achievements" ? "active" : ""}`}
          onClick={() => setPage("achievements")}
          type="button"
        >
          🏆 学习成就
        </button>
      </nav>

      {page === "notes" ? (
        <>
          <section className="statistics-section">
            <div className="statistics-heading">
              <div>
                <span className="section-kicker">YOUR PROGRESS</span>
                <h2>学习数据概览</h2>
              </div>

              <span className="statistics-tip">
                每一次记录，都是进步
              </span>
            </div>

            <div className="statistics-grid">
              <article className="stat-card stat-purple">
                <div className="stat-card-top">
                  <span>笔记总数</span>
                  <span className="stat-icon">✎</span>
                </div>
                <div className="stat-number">{totalNotes}</div>
                <div className="stat-description">已积累的学习笔记</div>
              </article>

              <article className="stat-card stat-blue">
                <div className="stat-card-top">
                  <span>学习分类</span>
                  <span className="stat-icon">▦</span>
                </div>
                <div className="stat-number">{usedCategories.size}</div>
                <div className="stat-description">已使用的分类数量</div>
              </article>

              <article className="stat-card stat-green">
                <div className="stat-card-top">
                  <span>已分类笔记</span>
                  <span className="stat-icon">✓</span>
                </div>
                <div className="stat-number">{categorizedNotes}</div>
                <div className="stat-description">不包含未分类笔记</div>
              </article>
            </div>

            <div className="category-stat-panel">
              <div className="category-stat-heading">
                <div>
                  <h3>分类分布</h3>
                  <p>看看你的知识主要积累在哪些领域</p>
                </div>

                <span className="category-total">
                  {totalNotes} 篇笔记
                </span>
              </div>

              {totalNotes === 0 ? (
                <div className="statistics-empty">
                  <span className="statistics-empty-icon">✧</span>
                  <p>还没有学习数据</p>
                  <span>
                    保存第一篇笔记后，这里就会显示统计结果。
                  </span>
                </div>
              ) : (
                <div className="category-stat-list">
                  {categoryStats.map((item) => {
                    const percentage = Math.round(
                      (item.count / totalNotes) * 100
                    );

                    return (
                      <div
                        className="category-stat-item"
                        key={item.name}
                      >
                        <div className="category-stat-info">
                          <span className="category-stat-name">
                            {item.name}
                          </span>
                          <span className="category-stat-count">
                            {item.count} 篇 · {percentage}%
                          </span>
                        </div>

                        <div className="category-progress-track">
                          <div
                            className="category-progress-fill"
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </section>

          <section className="workspace">
            <div className="editor-panel">
              <div className="section-heading">
                <div>
                  <span className="section-kicker">
                    {editingId !== null ? "EDIT NOTE" : "CREATE"}
                  </span>
                  <h2>
                    {editingId !== null ? "编辑学习笔记" : "写一篇新笔记"}
                  </h2>
                </div>

                <span className="pencil-icon">✎</span>
              </div>

              <form onSubmit={handleNoteSubmit}>
                <label htmlFor="note-title">笔记标题</label>
                <input
                  id="note-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="例如：今天学会了什么？"
                  maxLength={200}
                  required
                />

                <label htmlFor="note-category">学习分类</label>
                <select
                  id="note-category"
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                >
                  {CATEGORIES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>

                <label htmlFor="note-content">笔记内容</label>
                <textarea
                  id="note-content"
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  placeholder="记录知识点、学习心得或待解决的问题……"
                  rows={7}
                  required
                />

                <button
                  className="save-button"
                  type="submit"
                  disabled={saving}
                >
                  {saving
                    ? "正在保存…"
                    : editingId !== null
                      ? "保存修改 →"
                      : "保存笔记 →"}
                </button>

                {editingId !== null && (
                  <button
                    className="cancel-edit-button"
                    type="button"
                    onClick={resetNoteForm}
                  >
                    取消编辑
                  </button>
                )}
              </form>

              {message && (
                <p className="status-message" role="status">
                  {message}
                </p>
              )}
            </div>

            <div className="notes-panel">
              <div className="section-heading">
                <div>
                  <span className="section-kicker">YOUR LIBRARY</span>
                  <h2>我的学习笔记</h2>
                </div>

                <span className="note-count">
                  {loading ? "加载中…" : `${notes.length} 篇`}
                </span>
              </div>

              <div className="search-box">
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索笔记标题或内容……"
                  aria-label="搜索学习笔记"
                />
              </div>

              <div className="sort-controls">
                <label htmlFor="note-sort">排序方式</label>
                <select
                  id="note-sort"
                  value={sortOrder}
                  onChange={(event) =>
                    setSortOrder(event.target.value as SortOrder)
                  }
                >
                  <option value="newest">最新创建</option>
                  <option value="oldest">最早创建</option>
                  <option value="title">标题 A–Z</option>
                </select>
              </div>

              <div className="category-filters">
                {["全部", ...CATEGORIES].map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={`category-filter ${
                      selectedCategory === item ? "active" : ""
                    }`}
                    onClick={() => setSelectedCategory(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>

              {loading ? (
                <p className="empty-state">正在加载笔记…</p>
              ) : displayedNotes.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">✧</span>
                  <p>没有找到匹配的笔记</p>
                  <span>试试其他关键词或分类。</span>
                </div>
              ) : (
                <div className="note-list">
                  {displayedNotes.map((note) => (
                    <article className="note-card" key={note.id}>
                      <div className="note-card-top">
                        <span className="note-tag">学习笔记</span>
                        <span className="note-id">
                          #{String(note.id).padStart(3, "0")}
                        </span>
                      </div>

                      <h3>{note.title}</h3>
                      <p className="note-content">{note.content}</p>

                      <div className="note-category-row">
                        <span className="note-category-tag">
                          {note.category || "未分类"}
                        </span>
                      </div>

                      <div className="note-actions">
                        <button
                          type="button"
                          className="edit-button"
                          onClick={() => handleEditNote(note)}
                        >
                          编辑
                        </button>

                        <button
                          type="button"
                          className="delete-button"
                          onClick={() => void handleDeleteNote(note)}
                        >
                          删除笔记
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </section>
        </>
      ) : page === "tasks" ? (
        <section className="task-page">
          <div className="task-page-heading">
            <div>
              <span className="section-kicker">YOUR DAILY PLAN</span>
              <h2>学习计划与每日任务</h2>
              <p>把目标拆成每天可以完成的小事。</p>
            </div>
          </div>

          <div className="task-stats-grid">
            <article className="task-stat-card">
              <span>任务总数</span>
              <strong>{taskCounts.total}</strong>
            </article>

            <article className="task-stat-card">
              <span>今日任务</span>
              <strong>{taskCounts.today}</strong>
            </article>

            <article className="task-stat-card">
              <span>待完成</span>
              <strong>{taskCounts.pending}</strong>
            </article>

            <article className="task-stat-card">
              <span>已完成</span>
              <strong>{taskCounts.completed}</strong>
            </article>
          </div>

          <div className="daily-goal-panel">
            <div className="daily-goal-heading">
              <div>
                <span className="section-kicker">TODAY'S GOAL</span>
                <h3>今日学习目标</h3>
                <p>
                  每天完成 {DAILY_GOAL} 个学习任务，一点一点积累进步。
                </p>
              </div>

              <div className="daily-goal-count">
                <strong>{todayTaskCounts.completed}</strong>
                <span> / {DAILY_GOAL}</span>
              </div>
            </div>

            <div
              className="daily-goal-track"
              role="progressbar"
              aria-label="今日学习目标完成进度"
              aria-valuemin={0}
              aria-valuemax={DAILY_GOAL}
              aria-valuenow={Math.min(
                todayTaskCounts.completed,
                DAILY_GOAL
              )}
            >
              <div
                className="daily-goal-fill"
                style={{ width: `${dailyGoalProgress}%` }}
              />
            </div>

            <div className="daily-goal-footer">
              <span>
                今日已完成 {todayTaskCounts.completed} 个任务
                （今日共安排 {todayTaskCounts.total} 个）
              </span>

              {todayTaskCounts.completed >= DAILY_GOAL ? (
                <strong>🎉 今日目标达成！太棒了！</strong>
              ) : (
                <span>
                  还需完成 {DAILY_GOAL - todayTaskCounts.completed} 个任务
                </span>
              )}
            </div>
          </div>

          <div className="task-progress-panel">
            <div className="task-progress-heading">
              <div>
                <h3>整体完成进度</h3>
                <p>完成任务，一点一点积累学习成果。</p>
              </div>

              <strong>{completionRate}%</strong>
            </div>

            <div className="task-progress-track">
              <div
                className="task-progress-fill"
                style={{ width: `${completionRate}%` }}
              />
            </div>
          </div>

          <div className="task-layout">
            <div className="task-form-panel">
              <div className="section-heading">
                <div>
                  <span className="section-kicker">
                    {taskEditingId !== null ? "EDIT TASK" : "NEW TASK"}
                  </span>
                  <h2>
                    {taskEditingId !== null ? "编辑学习任务" : "添加学习任务"}
                  </h2>
                </div>

                <span className="pencil-icon">✓</span>
              </div>

              <form onSubmit={handleTaskSubmit}>
                <label htmlFor="task-title">任务名称</label>
                <input
                  id="task-title"
                  value={taskTitle}
                  onChange={(event) => setTaskTitle(event.target.value)}
                  placeholder="例如：复习 Python 列表"
                  maxLength={200}
                  required
                />

                <label htmlFor="task-date">计划日期</label>
                <input
                  id="task-date"
                  type="date"
                  value={taskDate}
                  onChange={(event) => setTaskDate(event.target.value)}
                  required
                />

                <label htmlFor="task-category">学习分类</label>
                <select
                  id="task-category"
                  value={taskCategory}
                  onChange={(event) => setTaskCategory(event.target.value)}
                >
                  {CATEGORIES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>

                <button
                  className="save-button"
                  type="submit"
                  disabled={saving}
                >
                  {saving
                    ? "正在保存…"
                    : taskEditingId !== null
                      ? "保存修改 →"
                      : "创建任务 →"}
                </button>

                {taskEditingId !== null && (
                  <button
                    className="cancel-edit-button"
                    type="button"
                    onClick={resetTaskForm}
                  >
                    取消编辑
                  </button>
                )}
              </form>

              {taskMessage && (
                <p className="status-message" role="status">
                  {taskMessage}
                </p>
              )}
            </div>

            <div className="task-list-panel">
              <div className="section-heading">
                <div>
                  <span className="section-kicker">YOUR CHECKLIST</span>
                  <h2>我的学习任务</h2>
                </div>
              </div>

              <div className="search-box">
                <input
                  value={taskSearch}
                  onChange={(event) => setTaskSearch(event.target.value)}
                  placeholder="搜索任务名称……"
                  aria-label="搜索学习任务"
                />
              </div>

              <div className="task-filters">
                {([
                  ["all", "全部任务"],
                  ["today", "今日任务"],
                  ["pending", "待完成"],
                  ["completed", "已完成"],
                ] as [TaskFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`category-filter ${
                      taskFilter === value ? "active" : ""
                    }`}
                    onClick={() => setTaskFilter(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {tasksLoading ? (
                <p className="empty-state">正在加载任务…</p>
              ) : tasks.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">✧</span>
                  <p>这里还没有学习任务</p>
                  <span>创建一个小目标，开始今天的学习吧。</span>
                </div>
              ) : (
                <div className="task-list">
                  {tasks.map((task) => (
                    <article
                      className={`task-card ${
                        task.completed ? "task-completed" : ""
                      }`}
                      key={task.id}
                    >
                      <label className="task-check">
                        <input
                          type="checkbox"
                          checked={task.completed}
                          disabled={busyTaskId === task.id}
                          onChange={() => void handleToggleTask(task)}
                        />
                        <span className="task-checkmark" />
                      </label>

                      <div className="task-card-body">
                        <h3>{task.title}</h3>

                        <div className="task-meta">
                          <span>{task.category || "未分类"}</span>
                          <span>计划日期：{task.due_date}</span>
                        </div>

                        <span
                          className={`task-status ${
                            task.completed ? "done" : ""
                          }`}
                        >
                          {task.completed
                            ? "已完成"
                            : task.due_date < todayString()
                              ? "已逾期"
                              : "待完成"}
                        </span>

                        <div className="note-actions">
                          <button
                            type="button"
                            className="edit-button"
                            onClick={() => handleEditTask(task)}
                            disabled={busyTaskId !== null}
                          >
                            编辑
                          </button>

                          <button
                            type="button"
                            className="delete-button"
                            onClick={() => void handleDeleteTask(task)}
                            disabled={busyTaskId !== null}
                          >
                            删除任务
                          </button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      ) : page === "checkin" ? (
        <CheckinPanel />
      ) : page === "timer" ? (
        <TimerPanel />
      ) : page === "dashboard" ? (
        <DashboardPanel />
      ) : (
        <AchievementsPanel />
      )}

      <footer className="footer">
        StudyMate · 每天进步一点点
      </footer>
    </main>
  );
}

export default App;
