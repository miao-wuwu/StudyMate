
import { useCallback, useEffect, useMemo, useState } from "react";
import "./DashboardPanel.css";

const API_URL = "http://127.0.0.1:8000";

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

type CheckinData = {
  dates: string[];
  total: number;
  streak: number;
  checked_today: boolean;
  today: string;
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

function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function startOfWeek(date: Date) {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  result.setDate(result.getDate() - ((result.getDay() + 6) % 7));
  return result;
}

export default function DashboardPanel() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [checkins, setCheckins] = useState<CheckinData | null>(null);
  const [sessions, setSessions] = useState<StudySession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const responses = await Promise.all([
        fetch(`${API_URL}/notes`),
        fetch(`${API_URL}/tasks`),
        fetch(`${API_URL}/checkins`),
        fetch(`${API_URL}/study-sessions?limit=200`),
      ]);

      if (responses.some((response) => !response.ok)) {
        throw new Error("部分数据读取失败，请确认后端服务正在运行。");
      }

      const [noteData, taskData, checkinData, sessionData] =
        await Promise.all(responses.map((response) => response.json()));

      setNotes(noteData);
      setTasks(taskData);
      setCheckins(checkinData);
      setSessions(sessionData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "无法读取学习数据。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const metrics = useMemo(() => {
    const now = new Date();
    const today = localDateKey(now);
    const weekStart = localDateKey(startOfWeek(now));

    const todayMinutes = sessions
      .filter((session) => session.study_date === today)
      .reduce((sum, session) => sum + session.duration_minutes, 0);

    const weekMinutes = sessions
      .filter(
        (session) =>
          session.study_date >= weekStart &&
          session.study_date <= today,
      )
      .reduce((sum, session) => sum + session.duration_minutes, 0);

    const totalMinutes = sessions.reduce(
      (sum, session) => sum + session.duration_minutes,
      0,
    );

    const todayTasks = tasks.filter((task) => task.due_date === today);
    const completed = tasks.filter((task) => task.completed).length;

    const completionRate = tasks.length
      ? Math.round((completed / tasks.length) * 100)
      : 0;

    const trend = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(now);
      date.setDate(now.getDate() - (6 - index));

      const key = localDateKey(date);

      const minutes = sessions
        .filter((session) => session.study_date === key)
        .reduce((sum, session) => sum + session.duration_minutes, 0);

      return {
        key,
        label: `${date.getMonth() + 1}/${date.getDate()}`,
        minutes,
      };
    });

    return {
      todayMinutes,
      weekMinutes,
      totalMinutes,
      todayTasks: todayTasks.length,
      completedToday: todayTasks.filter((task) => task.completed).length,
      completed,
      completionRate,
      trend,
      totalSessions: sessions.length,
    };
  }, [sessions, tasks]);

  const maxTrend = Math.max(
    25,
    ...metrics.trend.map((item) => item.minutes),
  );

  return (
    <section className="dashboard-page">
      <header className="dashboard-hero">
        <div>
          <span className="dashboard-eyebrow">
            YOUR LEARNING OVERVIEW
          </span>
          <h2>学习数据仪表盘</h2>
          <p>
            把每一次专注、每一篇笔记和每一个完成的任务，
            变成看得见的成长。
          </p>
        </div>

        <button
          className="dashboard-refresh"
          type="button"
          onClick={() => void load()}
          disabled={loading}
        >
          {loading ? "更新中…" : "↻ 刷新数据"}
        </button>
      </header>

      {error && (
        <p className="dashboard-error" role="alert">
          {error}
        </p>
      )}

      <div className="dashboard-metric-grid">
        <article className="dashboard-metric">
          <span>今日专注</span>
          <strong>
            {loading ? "—" : metrics.todayMinutes}
            <small> 分钟</small>
          </strong>
          <p>今天完成的专注记录</p>
        </article>

        <article className="dashboard-metric">
          <span>本周专注</span>
          <strong>
            {loading ? "—" : metrics.weekMinutes}
            <small> 分钟</small>
          </strong>
          <p>本周一至今天</p>
        </article>

        <article className="dashboard-metric">
          <span>累计专注</span>
          <strong>
            {loading ? "—" : metrics.totalMinutes}
            <small> 分钟</small>
          </strong>
          <p>共 {metrics.totalSessions} 次专注记录</p>
        </article>

        <article className="dashboard-metric">
          <span>笔记积累</span>
          <strong>
            {loading ? "—" : notes.length}
            <small> 篇</small>
          </strong>
          <p>保存到学习数据库的笔记</p>
        </article>
      </div>

      <div className="dashboard-columns">
        <article className="dashboard-card">
          <div className="dashboard-card-heading">
            <div>
              <span className="dashboard-eyebrow">LAST 7 DAYS</span>
              <h3>最近 7 天专注趋势</h3>
            </div>
            <span className="dashboard-pill">分钟</span>
          </div>

          {loading ? (
            <p className="dashboard-muted">正在读取数据…</p>
          ) : (
            <div
              className="dashboard-chart"
              role="img"
              aria-label="最近七天每天的专注分钟数柱状图"
            >
              {metrics.trend.map((day) => (
                <div
                  className="dashboard-chart-column"
                  key={day.key}
                  title={`${day.key}：${day.minutes} 分钟`}
                >
                  <strong>{day.minutes || ""}</strong>

                  <div className="dashboard-chart-track">
                    <div
                      className="dashboard-chart-bar"
                      style={{
                        height: `${
                          day.minutes
                            ? Math.max(
                                8,
                                (day.minutes / maxTrend) * 100,
                              )
                            : 0
                        }%`,
                      }}
                    />
                  </div>

                  <span>{day.label}</span>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="dashboard-card">
          <div className="dashboard-card-heading">
            <div>
              <span className="dashboard-eyebrow">
                TASK PROGRESS
              </span>
              <h3>任务完成情况</h3>
            </div>
            <strong className="dashboard-rate">
              {metrics.completionRate}%
            </strong>
          </div>

          <div className="dashboard-progress-track">
            <div
              className="dashboard-progress-fill"
              style={{ width: `${metrics.completionRate}%` }}
            />
          </div>

          <div className="dashboard-progress-labels">
            <span>已完成 {metrics.completed} 个</span>
            <span>共 {tasks.length} 个任务</span>
          </div>

          <div className="dashboard-mini-stats">
            <div>
              <span>今日任务</span>
              <strong>
                {metrics.completedToday}/{metrics.todayTasks}
              </strong>
            </div>

            <div>
              <span>累计打卡</span>
              <strong>{checkins?.total ?? "—"} 天</strong>
            </div>

            <div>
              <span>连续打卡</span>
              <strong>{checkins?.streak ?? "—"} 天</strong>
            </div>
          </div>
        </article>
      </div>

      <article className="dashboard-card dashboard-summary">
        <div className="dashboard-card-heading">
          <div>
            <span className="dashboard-eyebrow">KEEP GOING</span>
            <h3>你的学习足迹</h3>
          </div>
        </div>

        <div className="dashboard-summary-grid">
          <div>
            <span className="dashboard-summary-icon">✎</span>
            <strong>{notes.length}</strong>
            <span>篇学习笔记</span>
          </div>

          <div>
            <span className="dashboard-summary-icon">✓</span>
            <strong>
              {tasks.filter((task) => task.completed).length}
            </strong>
            <span>个已完成任务</span>
          </div>

          <div>
            <span className="dashboard-summary-icon">♡</span>
            <strong>{checkins?.streak ?? 0}</strong>
            <span>天连续打卡</span>
          </div>

          <div>
            <span className="dashboard-summary-icon">◷</span>
            <strong>{metrics.totalSessions}</strong>
            <span>次专注完成</span>
          </div>
        </div>

        {!loading && sessions.length === 0 && (
          <p className="dashboard-muted">
            完成一次专注计时后，学习趋势图就会开始记录你的成长。
          </p>
        )}
      </article>
    </section>
  );
}
