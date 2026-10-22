
import { useCallback, useEffect, useRef, useState } from "react";
import "./TimerPanel.css";
import "./TimerPanel.additions.css";

const API_URL = "http://127.0.0.1:8000";

type Task = {
  id: number;
  title: string;
  due_date: string;
  category: string;
  completed: boolean;
};

type StudySession = {
  id: number;
  task_id: number | null;
  task_title: string;
  duration_minutes: number;
  started_at: string;
  completed_at: string;
  study_date: string;
};

const DURATIONS = [15, 25, 45, 60];
const DAILY_FOCUS_GOAL = 60;

function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  return `${String(minutes).padStart(2, "0")}:${String(
    remainingSeconds,
  ).padStart(2, "0")}`;
}

function formatDateTime(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function TimerPanel() {
  const [duration, setDuration] = useState(25);
  const [remaining, setRemaining] = useState(25 * 60);
  const [running, setRunning] = useState(false);
  const [selectedTask, setSelectedTask] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [sessions, setSessions] = useState<StudySession[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const startedAtRef = useRef<string | null>(null);
  const savedRef = useRef(false);
  const runningRef = useRef(false);
  const endAtRef = useRef<number | null>(null);
  const remainingRef = useRef(25 * 60);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [taskResponse, sessionResponse] = await Promise.all([
        fetch(`${API_URL}/tasks?status=pending`),
        fetch(`${API_URL}/study-sessions?limit=50`),
      ]);

      if (!taskResponse.ok || !sessionResponse.ok) {
        throw new Error("读取数据失败，请检查后端是否已启动。");
      }

      const taskData: Task[] = await taskResponse.json();
      const sessionData: StudySession[] = await sessionResponse.json();

      setTasks(taskData);
      setSessions(sessionData);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "无法连接后端，请检查网络和服务状态。",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const saveSession = useCallback(async () => {
    if (savedRef.current || !startedAtRef.current) {
      return;
    }

    savedRef.current = true;
    runningRef.current = false;
    setRunning(false);
    setSaving(true);
    setMessage("");
    setError("");

    const completedAt = new Date();

    const task = tasks.find(
      (item) => String(item.id) === selectedTask,
    );

    const payload = {
      task_id: task ? task.id : null,
      task_title: task?.title ?? "自由学习",
      duration_minutes: duration,
      started_at: startedAtRef.current,
      completed_at: completedAt.toISOString(),
    };

    try {
      const response = await fetch(`${API_URL}/study-sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "保存专注记录失败。");
      }

      const newSession: StudySession = await response.json();

      setSessions((previous) => [
        newSession,
        ...previous.filter((item) => item.id !== newSession.id),
      ]);

      setMessage("专注完成！学习记录已保存。");

      if ("Notification" in window) {
        if (Notification.permission === "granted") {
          new Notification("StudyMate：专注完成！", {
            body: `你完成了 ${duration} 分钟的专注学习。`,
          });
        }
      }
    } catch (err) {
      savedRef.current = false;

      setError(
        err instanceof Error
          ? `计时已结束，但记录保存失败：${err.message}`
          : "计时已结束，但记录保存失败。",
      );
    } finally {
      setSaving(false);
    }
  }, [duration, selectedTask, tasks]);

  useEffect(() => {
    if (!running) {
      return;
    }

    const timerId = window.setInterval(() => {
      const endAt = endAtRef.current;

      if (endAt === null) {
        return;
      }

      const nextRemaining = Math.max(
        0,
        Math.ceil((endAt - Date.now()) / 1000),
      );

      remainingRef.current = nextRemaining;
      setRemaining(nextRemaining);

      if (nextRemaining <= 0) {
        runningRef.current = false;
        setRunning(false);
        endAtRef.current = null;
        void saveSession();
      }
    }, 200);

    return () => window.clearInterval(timerId);
  }, [running, saveSession]);

  function handleDurationChange(minutes: number) {
    if (running || saving) {
      return;
    }

    setDuration(minutes);
    setRemaining(minutes * 60);
    remainingRef.current = minutes * 60;
    startedAtRef.current = null;
    endAtRef.current = null;
    savedRef.current = false;
    setMessage("");
    setError("");
  }

  async function startTimer() {
    if (saving) {
      return;
    }

    setMessage("");
    setError("");

    if (remainingRef.current <= 0) {
      setRemaining(duration * 60);
      remainingRef.current = duration * 60;
    }

    if (!startedAtRef.current) {
      startedAtRef.current = new Date().toISOString();
      savedRef.current = false;
    }

    if (
      "Notification" in window &&
      Notification.permission === "default"
    ) {
      try {
        await Notification.requestPermission();
      } catch {
        // 即使通知不可用，计时也能正常运行。
      }
    }

    endAtRef.current = Date.now() + remainingRef.current * 1000;
    runningRef.current = true;
    setRunning(true);
  }

  function pauseTimer() {
    if (!runningRef.current || endAtRef.current === null) {
      return;
    }

    const nextRemaining = Math.max(
      0,
      Math.ceil((endAtRef.current - Date.now()) / 1000),
    );

    remainingRef.current = nextRemaining;
    setRemaining(nextRemaining);
    endAtRef.current = null;
    runningRef.current = false;
    setRunning(false);

    if (nextRemaining <= 0) {
      void saveSession();
    }
  }

  function resetTimer() {
    runningRef.current = false;
    setRunning(false);
    endAtRef.current = null;
    startedAtRef.current = null;
    savedRef.current = false;

    remainingRef.current = duration * 60;
    setRemaining(duration * 60);
    setMessage("");
    setError("");
  }

  const today = localDateKey(new Date());

  const todaySessions = sessions.filter(
    (session) => session.study_date === today,
  );

  const todayMinutes = todaySessions.reduce(
    (total, session) => total + session.duration_minutes,
    0,
  );

  const todayFocusCount = todaySessions.length;

  const dailyGoalProgress = Math.min(
    100,
    Math.round((todayMinutes / DAILY_FOCUS_GOAL) * 100),
  );

  const progress =
    ((duration * 60 - remaining) / (duration * 60)) * 100;

  return (
    <div className="timer-page">
      <section className="timer-hero">
        <div className="timer-heading">
          <span className="timer-eyebrow">FOCUS TIME</span>
          <h2>专注计时</h2>
          <p>把注意力放在当下，一次完成一小步。</p>
        </div>

        <div className="timer-today">
          <span>今日累计专注</span>
          <strong>{todayMinutes}</strong>
          <small>分钟</small>

          <div
            className="timer-goal-track"
            aria-label={`每日目标完成 ${dailyGoalProgress}%`}
          >
            <div
              className="timer-goal-fill"
              style={{ width: `${dailyGoalProgress}%` }}
            />
          </div>

          <small className="timer-goal-caption">
            每日目标 {DAILY_FOCUS_GOAL} 分钟 · 已完成 {dailyGoalProgress}%
          </small>

          <small className="timer-goal-caption">
            今日完成 {todayFocusCount} 次专注
          </small>
        </div>
      </section>

      <div className="timer-layout">
        <section className="timer-card">
          <div className="timer-card-top">
            <h3>番茄钟</h3>
            <span className={`timer-status ${running ? "active" : ""}`}>
              {saving
                ? "正在保存"
                : running
                  ? "专注中"
                  : remaining === 0
                    ? "已完成"
                    : startedAtRef.current
                      ? "已暂停"
                      : "准备开始"}
            </span>
          </div>

          <div
            className="timer-ring"
            style={{
              background: `conic-gradient(#50745c ${progress}%, #e7ece5 ${progress}%)`,
            }}
          >
            <div className="timer-ring-inner">
              <span className="timer-clock">
                {formatTime(remaining)}
              </span>
              <span className="timer-clock-caption">
                {running ? "保持专注" : "专注每一分钟"}
              </span>
            </div>
          </div>

          <div className="timer-duration">
            <span>选择专注时长</span>

            <div className="timer-duration-options">
              {DURATIONS.map((minutes) => (
                <button
                  key={minutes}
                  type="button"
                  className={
                    duration === minutes
                      ? "timer-duration-button selected"
                      : "timer-duration-button"
                  }
                  disabled={running || saving}
                  onClick={() => handleDurationChange(minutes)}
                >
                  {minutes} 分钟
                </button>
              ))}
            </div>
          </div>

          <label className="timer-task-label" htmlFor="timer-task">
            本次学习内容
          </label>

          <select
            id="timer-task"
            className="timer-task-select"
            value={selectedTask}
            disabled={running || saving}
            onChange={(event) => setSelectedTask(event.target.value)}
          >
            <option value="">自由学习（不关联任务）</option>

            {tasks.map((task) => (
              <option key={task.id} value={String(task.id)}>
                {task.title}
              </option>
            ))}
          </select>

          <div className="timer-actions">
            {!running ? (
              <button
                type="button"
                className="timer-primary-button"
                disabled={saving}
                onClick={() => void startTimer()}
              >
                {remaining === 0
                  ? "重新开始"
                  : startedAtRef.current
                    ? "继续专注"
                    : "开始专注"}
              </button>
            ) : (
              <button
                type="button"
                className="timer-primary-button"
                onClick={pauseTimer}
              >
                暂停
              </button>
            )}

            <button
              type="button"
              className="timer-secondary-button"
              disabled={saving}
              onClick={resetTimer}
            >
              重置
            </button>
          </div>

          {loading && (
            <p className="timer-hint">正在读取学习数据……</p>
          )}

          {message && <p className="timer-message">{message}</p>}

          {error && <p className="timer-error">{error}</p>}

          <p className="timer-hint">
            计时结束后会自动保存记录。离开或刷新页面可能中断正在进行的计时。
          </p>
        </section>

        <section className="timer-history-card">
          <div className="timer-history-heading">
            <div>
              <span className="timer-eyebrow">YOUR PROGRESS</span>
              <h3>最近专注记录</h3>
            </div>

            <span className="timer-history-count">
              {sessions.length} 条
            </span>
          </div>

          {sessions.length === 0 ? (
            <div className="timer-empty">
              <span className="timer-empty-icon">◷</span>
              <strong>还没有专注记录</strong>
              <p>完成第一次计时后，记录就会显示在这里。</p>
            </div>
          ) : (
            <div className="timer-session-list">
              {sessions.slice(0, 10).map((session) => (
                <article
                  className="timer-session-item"
                  key={session.id}
                >
                  <div className="timer-session-icon">✓</div>

                  <div className="timer-session-info">
                    <strong>{session.task_title}</strong>
                    <span>{formatDateTime(session.completed_at)}</span>
                  </div>

                  <div className="timer-session-duration">
                    <strong>{session.duration_minutes}</strong>
                    <span>分钟</span>
                  </div>
                </article>
              ))}
            </div>
          )}

          <div className="timer-tips">
            <strong>专注小建议</strong>
            <p>
              开始前确定一个小目标，计时期间尽量减少通知和干扰。
              每完成一轮，建议休息 5 分钟，让注意力恢复。
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
